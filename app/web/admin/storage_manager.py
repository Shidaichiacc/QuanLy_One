"""Storage inventory and explicit, preview-bound cleanup. No automatic deletion."""
import hashlib
import os
import re
import secrets
import shutil
import stat
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from flask import jsonify, request, session

GROUPS = {
    'game': ('Log game', '#55b9d2'),
    'dump': ('Dump khi crash', '#ec8b69'),
    'system': ('Log hệ thống / Web', '#b89ce5'),
    'backup': ('Backup', '#d5b367'),
    'cache': ('Cache / bộ cài', '#79b58a'),
    'data': ('Dữ liệu server / ứng dụng', '#708aa3'),
    'custom': ('Thư mục theo dõi', '#ac9d8c'),
    'ram': ('Journal trong RAM', '#77c5ba'),
}
GAME_LOGS = (
    ('server1/Logs', 'GameServer'),
    ('server1/vng_data/Logs', 'Dữ liệu GameServer'),
    ('gateway/Logs', 'Gateway'),
    ('gateway/s3relay/Logs', 'S3Relay'),
    ('gateway/s3relay/relay_log', 'Relay log'),
    ('server1/itemexchange_setting/rolevalue_log', 'Log trao đổi vật phẩm'),
    ('server1/rolevalueladder_setting/rolevalue_log', 'Log bảng giá trị nhân vật'),
    ('gateway/rolevalue_setting/rolevalue_log', 'Log giá trị nhân vật'),
)
PROTECTED_GAME = (
    ('gateway/Backup', 'Backup Gateway', 'backup'),
    ('gateway/roleback', 'Roleback Gateway', 'backup'),
    ('gateway/s3relay/roleback', 'Roleback S3Relay', 'backup'),
    ('gateway/s3relay/RelayRunData', 'Dữ liệu runtime S3Relay', 'data'),
)


def ident(value):
    return hashlib.sha256(str(value).encode('utf-8', 'surrogateescape')).hexdigest()[:24]


def fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_nlink)


@contextmanager
def parent_fd(path):
    """Pin every parent directory; reject symlinks, including replaced ancestors."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Đường dẫn không hợp lệ')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd, path.name
    finally:
        os.close(fd)


def safe_stat(path):
    with parent_fd(path) as (fd, name):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError('Không phải file thường')
        return st


def safe_directory(path):
    try:
        with parent_fd(Path(path) / '.storage-probe'):
            return True
    except (OSError, ValueError):
        return False


def open_inodes():
    """Failure to inspect a live process makes cleanup fail closed."""
    result = set()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    st = fd.stat()
                    if stat.S_ISREG(st.st_mode):
                        result.add((st.st_dev, st.st_ino))
                except FileNotFoundError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise ValueError('Không kiểm tra được file đang mở; chưa cho phép dọn dữ liệu')
    return result


def is_core(path):
    if not re.match(r'^core(?:[._-].*)?$', path.name):
        return False
    try:
        with parent_fd(path) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                head = os.read(fd, 18)
            finally:
                os.close(fd)
        return (head[:4] == b'\x7fELF' and len(head) == 18 and
                int.from_bytes(head[16:18], 'little' if head[5] == 1 else 'big') == 4)
    except OSError:
        return False


class StorageManager:
    def __init__(self, extension):
        self.ext = extension
        self.lock = threading.RLock()
        self.cleanup_lock = threading.Lock()
        self.snapshot = None
        self.previews = {}

    def catalog(self):
        ext = self.ext
        sources = {}
        versions = []
        active = ext._active_server()

        def add(path, label, group, mode='protected', version='', note=''):
            path = Path(path)
            key = ident(str(path) + ':' + group)
            sources[key] = dict(id=key, path=str(path), label=label, group=group,
                                mode=mode, version=version, note=note)
            return key

        selections = ext._load_server_selections()
        for version in sorted(ext.SERVERS_ROOT.iterdir() if ext.SERVERS_ROOT.exists() else []):
            if version.is_symlink() or not version.is_dir():
                continue
            root = ext._server_root_from_selection(version, selections.get(version.name, '.'))
            is_active = bool(active and (version == active or version in active.parents))
            if is_active:
                root = active
            versions.append(dict(name=version.name, active=is_active))
            if root:
                for relative, label in GAME_LOGS:
                    add(root / relative, label, 'game', 'files', version.name)
                for relative, label, group in PROTECTED_GAME:
                    add(root / relative, label, group, version=version.name,
                        note='Dữ liệu cần giữ; quản lý riêng, không dọn chung với log.')
                for relative in ext._load_custom_log_directories():
                    try:
                        relative = ext._normalize_log_relative(relative)
                    except ValueError:
                        continue
                    if relative not in {row[0] for row in GAME_LOGS + PROTECTED_GAME}:
                        custom_id = add(root / relative, 'Thư mục theo dõi', 'custom', version=version.name,
                                        note='Chưa xác minh loại dữ liệu; chỉ thống kê.')
                        sources[custom_id]['custom_relative'] = relative
            add(version, 'Dữ liệu phiên bản ' + version.name, 'data', version=version.name,
                note='Cấu hình, MOD, script và dữ liệu game được giữ lại.')
        add('/var/lib/apport/coredump', 'Core dump Apport', 'dump', 'dump')
        add('/var/lib/systemd/coredump', 'Core dump systemd', 'dump', 'dump')
        add('/var/crash', 'Báo cáo crash Ubuntu', 'dump', 'crash')
        add('/var/log/nginx', 'Nginx', 'system', 'rotated', note='Chỉ dọn log đã xoay vòng; giữ file .log hiện tại.')
        for base, group in ((Path('/var/log/journal'), 'system'), (Path('/run/log/journal'), 'ram')):
            if base.is_dir():
                for directory in sorted(base.iterdir()):
                    if directory.is_dir() and not directory.is_symlink():
                        add(directory, 'Journal JXNative' if directory.name.endswith('.jxnative') else 'Journal Ubuntu',
                            group, 'journal', note='Dọn journal lưu trữ bằng journalctl; giữ journal đang ghi.')
        add(ext.STATE_ROOT, 'Log QuanLy One', 'system', 'state', note='Chỉ dọn log đã đóng; giữ cấu hình và trạng thái quản trị.')
        for container, label in ext.DOCKER_LOG_CONTAINERS:
            try:
                proc = subprocess.run(['docker', 'inspect', '--format', '{{.LogPath}}', container],
                                      capture_output=True, text=True, timeout=5, check=False)
                path = Path(proc.stdout.strip())
                if proc.returncode == 0 and path.is_absolute() and str(path).startswith('/var/lib/docker/containers/'):
                    add(path.parent, 'Docker ' + label, 'system', 'docker',
                        note='Tự xoay vòng theo Docker; không xóa file log trực tiếp.')
            except (OSError, subprocess.TimeoutExpired):
                pass
        add(ext.PROJECT_ROOT / 'data/database/backups', 'Backup database', 'backup',
            note='Mở Sao lưu & Khôi phục để xóa trọn bộ backup và cập nhật danh mục.')
        add(ext.PROJECT_ROOT / 'data/backups-code', 'Backup mã ứng dụng', 'backup')
        add(ext.PROJECT_ROOT / 'data/database', 'Dữ liệu MySQL / MSSQL', 'data')
        add(ext.UPLOAD_ROOT, 'Bộ cài / file upload', 'cache', note='Giữ file upload; kiểm tra mục nhập phiên bản trước khi xóa.')
        add('/var/cache/apt/archives', 'Cache gói APT', 'cache', 'apt', note='Chỉ file .deb hoàn tất; bỏ qua partial và lock.')
        add('/var/log', 'Log hệ thống khác', 'system', note='Chỉ thống kê; chưa có chính sách dọn cho nguồn này.')
        add(ext.PROJECT_ROOT, 'Ứng dụng / dữ liệu khác', 'data')
        return sources, versions

    def scan(self):
        with self.lock:
            started = time.time()
            sources, versions = self.catalog()
            records = {}
            seen = set()
            errors = []
            # Specific roots own their files. Generic sources never double-count them.
            ordered = sorted(sources.values(), key=lambda s: (-len(Path(s['path']).parts), s['path']))
            known_roots = {s['path'] for s in ordered}
            for source in ordered:
                root = Path(source['path'])
                source.update(files=0, bytes=0, allocated=0, latest=0, errors=0,
                              exists=safe_directory(root), devices={})
                if not source['exists']:
                    if root.exists():
                        source['errors'] += 1
                    continue
                def onerror(exc):
                    source['errors'] += 1
                    if len(errors) < 20:
                        errors.append(str(exc))
                for parent, dirs, files, fd in os.fwalk(root, follow_symlinks=False, onerror=onerror):
                    dirs[:] = [name for name in dirs if str(Path(parent) / name) not in known_roots]
                    for name in files:
                        try:
                            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                            if not stat.S_ISREG(st.st_mode):
                                continue
                            inode = (st.st_dev, st.st_ino)
                            if inode in seen:
                                continue
                            path = Path(parent) / name
                            mode = source['mode']
                            if mode == 'state' and not re.match(r'^(game-start\.log|game-reload\.log|activity\.jsonl|admin-login-audit\.jsonl|storage-cleanup\.jsonl)(\..+)?$', name):
                                continue
                            if mode == 'docker' and not re.search(r'-json\.log(?:\.\d+(?:\.gz)?)?$', name):
                                continue
                            seen.add(inode)
                            target = source
                            if source['group'] in ('data', 'game') and self.project_process(path) and is_core(path):
                                key = ident(str(path.parent) + ':dump')
                                if key not in sources:
                                    sources[key] = dict(id=key, path=str(path.parent), label='Core dump trong server' if source['version'] else 'Core dump ứng dụng',
                                                       group='dump', mode='core', version=source['version'], note='',
                                                       files=0, bytes=0, allocated=0, latest=0, errors=0, exists=True, devices={})
                                target = sources[key]
                            allocated = st.st_blocks * 512
                            key = ident(path)
                            row = dict(id=key, source=target['id'], path=str(path), name=name, bytes=st.st_size,
                                       allocated=allocated, mtime=st.st_mtime, fingerprint=fingerprint(st),
                                       device=str(st.st_dev), links=st.st_nlink)
                            if target['group'] == 'dump':
                                row['process'] = self.dump_process(path)
                                prefix = str(self.ext.SERVERS_ROOT) + '/' if hasattr(self.ext, 'SERVERS_ROOT') else ''
                                if prefix and row['process'].startswith(prefix):
                                    row['version'] = row['process'][len(prefix):].split('/')[0]
                            row['cleanup_group'] = self.cleanup_group(target, row)
                            row['display_group'] = self.display_group(target)
                            row['memory'] = target['group'] == 'ram'
                            records[key] = row
                            target['files'] += 1
                            target['bytes'] += st.st_size
                            target['allocated'] += allocated
                            target['latest'] = max(target['latest'], st.st_mtime)
                            target['devices'][str(st.st_dev)] = target['devices'].get(str(st.st_dev), 0) + allocated
                        except OSError as exc:
                            onerror(exc)
            disks = self.disks(sources)
            self.snapshot = dict(scanned_at=time.time(), duration=round(time.time() - started, 2),
                                 sources=sources, records=records, versions=versions, disks=disks, errors=errors)
            return self.public_snapshot()

    @staticmethod
    def dump_process(path):
        # Filename is evidence, not a basis for assigning another program's dump to a version.
        if path.suffix == '.crash':
            try:
                with parent_fd(path) as (parent, name):
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    try:
                        head = os.read(fd, 65536).decode('utf-8', 'replace')
                    finally:
                        os.close(fd)
                match = re.search(r'^ExecutablePath: (.+)$', head, re.M)
                if match:
                    return match.group(1)[:400]
            except OSError:
                pass
        for process in ('jx_linux_y', 's3relay_y', 'bishop_y', 'goddess_y', 'paysys_y', 'relay_y'):
            if process in path.name:
                return process + ' (theo tên file)'
        return 'Chưa xác định'

    def project_process(self, value):
        """Only project executable/cwd paths establish ownership; comm alone cannot."""
        value = str(value).strip()
        if not value.startswith('/') or '..' in Path(value).parts:
            return False
        roots = [self.ext.PROJECT_ROOT / 'JX_Servers' / 'JX_Versions',
                 self.ext.PROJECT_ROOT / 'JX_Servers' / 'Active',
                 self.ext.PROJECT_ROOT / 'app', self.ext.PROJECT_ROOT / 'tools']
        return any(value == str(root) or value.startswith(str(root) + '/') for root in roots)

    @staticmethod
    def display_group(source):
        if source['mode'] == 'state':
            return 'app'
        if source['group'] in ('game', 'dump'):
            return source['group']
        if source['group'] in ('system', 'ram'):
            return 'system'
        return ''

    def cleanup_group(self, source, row):
        if source['group'] == 'game' and source['mode'] == 'files':
            return 'game'
        if source['mode'] == 'state':
            return 'app'
        if source['group'] in ('system', 'ram'):
            return 'system'
        if source['group'] != 'dump':
            return ''
        path = Path(row['path'])
        if source['mode'] == 'core' and self.project_process(path):
            return 'dump'
        if self.project_process(row.get('process', '')):
            return 'dump'
        try:
            with parent_fd(path) as (parent, name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                try:
                    # systemd-coredump stores provenance as extended attributes.
                    for attribute in ('user.coredump.exe', 'user.coredump.cwd'):
                        try:
                            value = os.getxattr(fd, attribute).decode('utf-8', 'replace')
                            if self.project_process(value):
                                return 'dump'
                        except OSError:
                            pass
                    if path.suffix == '.crash':
                        head = os.read(fd, 65536).decode('utf-8', 'replace')
                        for value in re.findall(r'^(?:ExecutablePath|ProcCwd): (.+)$', head, re.M):
                            if self.project_process(value):
                                return 'dump'
                finally:
                    os.close(fd)
        except OSError:
            return ''
        # Apport sometimes embeds the full executable path in a core filename.
        # Never accept only a process basename (e.g. core.python / core.jx_linux_y).
        if source['mode'] == 'dump':
            for relative in ('JX_Servers/JX_Versions', 'JX_Servers/Active', 'app', 'tools'):
                prefix = str(self.ext.PROJECT_ROOT / relative).replace('/', '_') + '_'
                if path.name.startswith('core.' + prefix):
                    return 'dump'
        return ''

    def cleanup_view(self, snap):
        groups = [dict(id='game', label='Log server', color='#55b9d2'),
                  dict(id='dump', label='Dump / crash', color='#ec8b69'),
                  dict(id='app', label='Log QuanLy One', color='#b89ce5'),
                  dict(id='system', label='Log dịch vụ', color='#79b58a')]
        rows = {}
        # Keep empty/missing locations visible, especially Apport and systemd-coredump.
        for key, source in snap['sources'].items():
            group = self.display_group(source)
            if group:
                rows[key] = dict(source, group=group, memory=source['group'] == 'ram',
                                 files=0, bytes=0, allocated=0, latest=0, devices={})
        unknown_dumps = 0
        for record in snap['records'].values():
            if record['source'] not in rows:
                continue
            source = rows[record['source']]
            if source['group'] == 'dump' and not record.get('cleanup_group'):
                unknown_dumps += 1
            source['files'] += 1
            source['bytes'] += record['bytes']
            source['allocated'] += record['allocated']
            source['latest'] = max(source['latest'], record['mtime'])
            device = record['device']
            source['devices'][device] = source['devices'].get(device, 0) + record['allocated']
        for group in groups:
            members = [row for row in rows.values() if row['group'] == group['id']]
            group.update(files=sum(s['files'] for s in members),
                         allocated=sum(s['allocated'] for s in members if not s['memory']),
                         memory_allocated=sum(s['allocated'] for s in members if s['memory']))
        return dict(groups=groups, sources=list(rows.values()), unknown_dumps=unknown_dumps)

    def disks(self, sources):
        disks = {}
        paths = [Path('/'), self.ext.PROJECT_ROOT] + [Path(s['path']) for s in sources.values() if s['group'] != 'ram']
        for path in paths:
            try:
                if not path.exists():
                    continue
                device = str(path.stat().st_dev)
                if device in disks:
                    continue
                usage = shutil.disk_usage(path)
                mount = path
                while mount.parent != mount and mount.parent.stat().st_dev == int(device):
                    mount = mount.parent
                disks[device] = dict(id=device, path=str(mount), total=usage.total, used=usage.used,
                                     free=usage.free, reserved=max(0, usage.total - usage.used - usage.free))
            except OSError:
                continue
        return list(disks.values())

    def public_snapshot(self):
        snap = self.snapshot
        if snap is None:
            return self.scan()
        return dict(scanned_at=snap['scanned_at'], duration=snap['duration'], versions=snap['versions'],
                    disks=snap['disks'], sources=list(snap['sources'].values()), errors=snap['errors'],
                    cleanup=self.cleanup_view(snap),
                    groups=[dict(id=key, label=value[0], color=value[1]) for key, value in GROUPS.items()])

    def details(self, source_id, sort='size', query='', page=1, quick=False):
        with self.lock:
            if self.snapshot is None:
                self.scan()
            source = self.snapshot['sources'].get(source_id)
            if not source:
                raise ValueError('Nguồn không còn trong lần quét; hãy quét lại')
            rows = [r for r in self.snapshot['records'].values() if r['source'] == source_id
                    and query.casefold() in r['path'].casefold() and (not quick or r.get('display_group'))]
            rows.sort(key=lambda r: r['mtime'] if sort in ('new', 'old') else r['bytes'], reverse=sort != 'old')
            page = max(1, min(page, max(1, (len(rows) + 99) // 100)))
            return dict(source=source, total=len(rows), page=page, pages=max(1, (len(rows) + 99) // 100),
                        files=[self.public_file(r) for r in rows[(page - 1) * 100:page * 100]])

    @staticmethod
    def public_file(row):
        return {key: value for key, value in row.items() if key != 'fingerprint'}

    @staticmethod
    def reason(source, row, st, opened, cutoff, now):
        if st.st_nlink != 1:
            return 'File có hard link; cần kiểm tra riêng'
        if (st.st_dev, st.st_ino) in opened:
            return 'File đang được sử dụng'
        if st.st_mtime >= now - 600 or st.st_ctime >= now - 600:
            return 'File vừa tạo/thay đổi trong 10 phút; chờ ổn định'
        if cutoff is not None and st.st_mtime >= cutoff:
            return 'Giữ lại theo mốc thời gian'
        mode, name = source['mode'], Path(row['path']).name
        if mode == 'rotated' and not re.search(r'\.log\.[0-9][\w.-]*$', name):
            return 'Giữ log hiện tại / file chưa xác minh'
        if mode == 'apt' and (not name.endswith('.deb') or '/partial/' in row['path']):
            return 'Không phải gói APT tải hoàn tất'
        if mode == 'crash' and not name.endswith('.crash'):
            return 'Không phải báo cáo .crash'
        if mode == 'dump' and not (is_core(Path(row['path'])) or re.match(r'^core\..+\.(zst|lz4|xz|gz)$', name)):
            return 'Chưa xác minh là core dump'
        if mode == 'core' and not is_core(Path(row['path'])):
            return 'File không còn là core dump'
        return ''

    def preview(self, owner, source_ids, days, file_ids=None, quick=False):
        if str(days) not in ('1', '7', 'all'):
            raise ValueError('Chọn cũ hơn 1 ngày, 7 ngày hoặc tất cả')
        if not (quick and source_ids is None) and (not isinstance(source_ids, list) or not source_ids or len(source_ids) > 200):
            raise ValueError('Chọn ít nhất một nguồn dữ liệu')
        if file_ids is not None and (not isinstance(file_ids, list) or not file_ids or len(file_ids) > 1000):
            raise ValueError('Danh sách file không hợp lệ')
        with self.lock:
            # Fresh inventory, not a stale cached list, is used to build the preview.
            self.scan()
            if quick:
                allowed = {key for key, source in self.snapshot['sources'].items() if self.display_group(source)}
                if source_ids is None:
                    source_ids = sorted(allowed)
                elif not set(source_ids).issubset(allowed):
                    raise ValueError('Nguồn này không thuộc log/dump đã xác minh của server và QuanLy One')
            sources = [self.snapshot['sources'].get(key) for key in set(source_ids)]
            if any(s is None or (not quick and s['mode'] in ('protected', 'docker')) for s in sources):
                raise ValueError('Nguồn chỉ được theo dõi, không được dọn trực tiếp')
            journals = [s for s in sources if s['mode'] == 'journal']
            if journals and (file_ids is not None or (not quick and len(sources) != 1)):
                raise ValueError('Dọn từng nguồn journal riêng bằng cơ chế hệ thống')
            now = time.time()
            opened = open_inodes()
            cutoff = None if days == 'all' else now - int(days) * 86400
            rows = [r for r in self.snapshot['records'].values() if r['source'] in source_ids
                    and (file_ids is None or r['id'] in file_ids) and (not quick or r.get('display_group'))]
            if file_ids is not None and set(file_ids) != {r['id'] for r in rows}:
                raise ValueError('Một số file đã thay đổi hoặc không thuộc nguồn đã chọn; mở chi tiết lại')
            candidates, skipped = [], []
            for row in rows:
                source = self.snapshot['sources'][row['source']]
                try:
                    st = safe_stat(row['path'])
                    if source['mode'] in ('protected', 'docker'):
                        reason = 'Docker tự xoay log; không xóa trực tiếp' if source['mode'] == 'docker' else 'Chỉ theo dõi; chưa có chính sách dọn cho nguồn này'
                    elif quick and not row.get('cleanup_group'):
                        reason = 'Dump chưa xác định thuộc server/QuanLy One; giữ lại để kiểm tra'
                    elif fingerprint(st) != row['fingerprint']:
                        reason = 'File đã thay đổi trong lúc quét'
                    else:
                        reason = self.reason(source, row, st, opened, cutoff, now)
                    if source['mode'] == 'journal' and not reason and '@' not in row['name']:
                        reason = 'Journal đang ghi / chưa lưu trữ'
                except (OSError, ValueError):
                    reason = 'File không còn tồn tại hoặc không thể đọc an toàn'
                if reason:
                    skipped.append(dict(self.public_file(row), reason=reason))
                else:
                    candidates.append(row)
            token = secrets.token_urlsafe(32)
            self.previews = {k: v for k, v in self.previews.items() if v['expires'] > now}
            if len(self.previews) >= 30:
                self.previews.pop(next(iter(self.previews)))
            preview = dict(owner=owner, expires=now + 300, sources=sources, days=days,
                           candidates=candidates, skipped=skipped, journal=bool(journals), quick=quick)
            self.previews[token] = preview
            return dict(token=token, expires=preview['expires'], files=len(candidates),
                        bytes=sum(r['bytes'] for r in candidates),
                        allocated=sum(r['allocated'] for r in candidates if not r.get('memory')),
                        memory_allocated=sum(r['allocated'] for r in candidates if r.get('memory')), skipped=len(skipped),
                        sources=sources, journal=bool(journals), quick=quick,
                        # Lists paginate independently through preview-details.
                        sample=[self.public_file(r) for r in candidates[:100]], skipped_sample=skipped[:100])

    def preview_details(self, owner, token, page=1, skipped=False):
        with self.lock:
            plan = self.previews.get(token)
            if not plan or plan['owner'] != owner or plan['expires'] < time.time():
                raise ValueError('Bản xem trước hết hạn; vui lòng xem trước lại')
            rows = plan['skipped'] if skipped else plan['candidates']
            page = max(1, min(page, max(1, (len(rows) + 99) // 100)))
            return dict(files=[self.public_file(r) for r in rows[(page - 1)*100:page*100]],
                        page=page, pages=max(1, (len(rows)+99)//100), total=len(rows))

    @staticmethod
    def vacuum_journal(source, days, candidates):
        if not safe_directory(source['path']):
            raise ValueError('Đường dẫn journal đã thay đổi')
        duration = '1s' if days == 'all' else str(days) + 'd'
        before = []
        for path in Path(source['path']).iterdir():
            if path.name.endswith(('.journal', '.journal~')):
                try:
                    before.append((path, safe_stat(path).st_size))
                except (OSError, ValueError):
                    pass
        result = subprocess.run(['journalctl', '--directory=' + source['path'],
                                 '--vacuum-time=' + duration], capture_output=True, text=True,
                                timeout=60, check=False)
        errors = [(result.stderr or result.stdout)[-1000:]] if result.returncode else []
        removed = [(path, size) for path, size in before if not path.exists()]
        return (len(removed), sum(size for path, size in removed),
                sum(1 for row in candidates if Path(row['path']).exists()), errors)

    def execute(self, owner, token):
        if not self.cleanup_lock.acquire(blocking=False):
            raise ValueError('Đang có lượt dọn khác; vui lòng chờ hoàn tất')
        try:
            with self.lock:
                plan = self.previews.get(token)
                if not plan or plan['owner'] != owner or plan['expires'] < time.time():
                    raise ValueError('Bản xem trước hết hạn hoặc đã sử dụng; vui lòng xem trước lại')
                del self.previews[token]  # one use only, even after failure
                opened = open_inodes()
                inventory = self.snapshot['sources'] if self.snapshot else self.catalog()[0]
                before = self.disks(inventory)
                removed, skipped, errors, removed_bytes = 0, 0, [], 0
                sources = {s['id']: s for s in plan['sources']}
                now = time.time()
                cutoff = None if plan['days'] == 'all' else now - int(plan['days']) * 86400
                memory_removed = 0
                for source in plan['sources']:
                    if source['mode'] != 'journal':
                        continue
                    candidates = [r for r in plan['candidates'] if r['source'] == source['id']]
                    try:
                        count, size, remaining, journal_errors = self.vacuum_journal(source, plan['days'], candidates)
                        removed += count
                        removed_bytes += size
                        skipped += remaining
                        errors.extend(journal_errors)
                        if source['group'] == 'ram':
                            memory_removed += size
                    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                        errors.append(source['path'] + ': ' + str(exc))
                for row in plan['candidates']:
                    source = sources[row['source']]
                    if source['mode'] == 'journal':
                        continue
                    try:
                        with parent_fd(row['path']) as (fd, name):
                            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                            if (not stat.S_ISREG(st.st_mode) or fingerprint(st) != row['fingerprint']
                                    or self.reason(source, row, st, opened, cutoff, now)):
                                skipped += 1
                                continue
                            os.unlink(name, dir_fd=fd)
                            removed += 1
                            removed_bytes += st.st_size
                    except FileNotFoundError:
                        skipped += 1
                    except (OSError, ValueError) as exc:
                        errors.append(row['path'] + ': ' + str(exc))
                after = self.disks(inventory)
                old_free = {d['id']: d['free'] for d in before}
                changes = [dict(path=d['path'], delta=d['free']-old_free[d['id']])
                           for d in after if d['id'] in old_free]
                result = dict(removed=removed, removed_bytes=removed_bytes, skipped=skipped,
                              kept=len(plan['skipped']), errors=errors[:50], error_count=len(errors), disk_changes=changes,
                              journal=plan['journal'], memory_removed=memory_removed)
                # Audit records only the operation, no file contents.
                audit = self.ext.STATE_ROOT / 'storage-cleanup.jsonl'
                audit.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with audit.open('a', encoding='utf-8') as stream:
                        import json
                        stream.write(json.dumps(dict(time=now, sources=list(sources), days=plan['days'],
                                                     result=result), ensure_ascii=True) + '\n')
                except OSError as exc:
                    result['errors'].append('Không ghi được nhật ký dọn: ' + str(exc))
                    result['error_count'] += 1
                self.snapshot = None
                return result
        finally:
            self.cleanup_lock.release()


def register_storage_routes(blueprint, extension):
    manager = StorageManager(extension)

    def owner():
        return ident(session.get('csrf_token', ''))

    def payload():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            raise ValueError('Yêu cầu không hợp lệ')
        expected = session.get('csrf_token', '')
        import hmac
        supplied = request.headers.get('X-CSRF-Token', '')
        if not expected or not hmac.compare_digest(expected, supplied):
            raise ValueError('Phiên không hợp lệ; tải lại trang')
        return data

    def respond(function):
        try:
            response = jsonify(function())
            response.headers['Cache-Control'] = 'no-store'
            return response
        except (ValueError, TypeError, KeyError) as exc:
            return jsonify(error=str(exc)), 400
        except (OSError, subprocess.TimeoutExpired) as exc:
            return jsonify(error='Không hoàn tất thao tác: ' + str(exc)), 503

    @blueprint.route('/server-setup/storage/snapshot')
    def storage_snapshot():
        return respond(manager.public_snapshot)

    @blueprint.route('/server-setup/storage/scan', methods=['POST'])
    def storage_scan():
        return respond(lambda: (payload(), manager.scan())[1])

    @blueprint.route('/server-setup/storage/details')
    def storage_details():
        return respond(lambda: manager.details(request.args.get('source', ''), request.args.get('sort', 'size'),
                                               request.args.get('q', ''), int(request.args.get('page', 1)), request.args.get('scope') == 'quick'))

    @blueprint.route('/server-setup/storage/preview', methods=['POST'])
    def storage_preview():
        def run():
            data = payload()
            return manager.preview(owner(), data.get('sources'), data.get('days'), data.get('files'), data.get('scope') == 'quick')
        return respond(run)

    @blueprint.route('/server-setup/storage/preview-details', methods=['POST'])
    def storage_preview_details():
        def run():
            data = payload()
            return manager.preview_details(owner(), data.get('token'), int(data.get('page', 1)), bool(data.get('skipped')))
        return respond(run)

    @blueprint.route('/server-setup/storage/delete', methods=['POST'])
    def storage_delete():
        def run():
            data = payload()
            if data.get('confirm') is not True:
                raise ValueError('Cần xác nhận danh sách sẽ xóa')
            return manager.execute(owner(), data.get('token'))
        return respond(run)
    return manager

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile
from functools import wraps
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import pymssql
import pymysql


PROJECT_ROOT = Path(os.environ.get("QUANLY_ONE_ROOT", "/opt/QuanLy_One"))
JX_ROOT = PROJECT_ROOT / "JX_Servers"
SERVERS_ROOT = JX_ROOT / "JX_Versions"
UPLOAD_ROOT = PROJECT_ROOT / "data" / "uploads"
STATE_ROOT = PROJECT_ROOT / "data" / "state"
IMPORT_JOBS_ROOT = STATE_ROOT / "import-jobs"
INSTALL_STATE_FILE = STATE_ROOT / "installation.json"
DATABASE_JOB_FILE = STATE_ROOT / "database-job.json"
ENV_FILE = PROJECT_ROOT / ".env"
COMPOSE_FILE = PROJECT_ROOT / "deploy" / "docker-compose.yml"
ACTIVE_LINK = JX_ROOT / "Active"
AUTH_FILE = STATE_ROOT / "manager-auth.json"
SERVER_SELECTIONS_FILE = STATE_ROOT / "server-selections.json"
LOG_DIRECTORIES_FILE = STATE_ROOT / "log-directories.json"
SERVER_IP_FILE = STATE_ROOT / "server-ip"
GAME_UNITS = ("jxgame", "jxs3relay", "jxbishop", "jxgoddess", "jxrelaypay", "jxpaysys")
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
GITHUB_URL_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$")
GIT_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
ALLOWED_SUFFIXES = (".zip", ".tgz", ".tar.gz")
SERVER_BINARIES = (
    "gateway/bishop_y",
    "gateway/goddess_y",
    "gateway/s3relay/s3relay_y",
    "server1/jx_linux_y",
)
DEFAULT_GAME_LOG_DIRS = (
    ("server1/Logs", "GameServer"),
    ("server1/vng_data/Logs", "Dữ liệu GameServer"),
    ("gateway/Logs", "Gateway"),
    ("gateway/s3relay/Logs", "S3Relay"),
)
JXNATIVE_STATE_LOGS = (
    STATE_ROOT / "game-start.log",
    STATE_ROOT / "game-reload.log",
    STATE_ROOT / "activity.jsonl",
)
DOCKER_LOG_CONTAINERS = (
    ("quanlyone_mssql", "MSSQL"),
    ("quanlyone_mysql", "MySQL"),
)

sys.path.insert(0, str(PROJECT_ROOT / "app" / "shared"))
from admin_login_security import AdminLoginSecurity, format_duration, format_timestamp
from database_credentials import (patch_all_credentials, patch_server_credentials,
                                  read_env, restore_snapshots,
                                  validate_database_password, write_env)

LOGIN_SECURITY = AdminLoginSecurity(STATE_ROOT)
DATABASE_JOB_LOCK = threading.Lock()


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _read_json(path, fallback=None):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else (fallback or {})
    except (OSError, ValueError):
        return fallback or {}


def _write_database_job(mode, state, percent, phase, message=""):
    _atomic_json(DATABASE_JOB_FILE, {
        "mode": mode,
        "state": state,
        "percent": max(0, min(100, int(percent))),
        "phase": str(phase)[:100],
        "message": str(message)[:1200],
        "updated": int(time.time()),
    })


def _database_passwords():
    values = read_env(ENV_FILE)
    return values.get("MYSQL_ROOT_PASSWORD", ""), values.get("MSSQL_SA_PASSWORD", "")


def _database_setup_complete():
    state = _read_json(INSTALL_STATE_FILE)
    return state.get("complete") is True


def _mark_database_setup_complete():
    _atomic_json(INSTALL_STATE_FILE, {
        "complete": True,
        "completed_at": int(time.time()),
        "version": (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if (PROJECT_ROOT / "VERSION").is_file() else "unknown",
    })


def _run_setup_command(command, timeout=1200, env=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                            check=False, env=env)
    if result.returncode:
        detail = (result.stderr or result.stdout or "Lệnh hệ thống thất bại").strip()
        raise RuntimeError(detail[-1200:])
    return result


def _wait_mysql(password, database="server1", timeout=240):
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            connection = pymysql.connect(host="127.0.0.1", port=3306, user="root",
                                         password=password, database=database,
                                         connect_timeout=5, autocommit=True)
            connection.close()
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError("MySQL chưa sẵn sàng: " + last_error[-500:])


def _wait_mssql(password, database="master", timeout=240):
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            connection = pymssql.connect(server="127.0.0.1", port=1433, user="sa",
                                         password=password, database=database,
                                         login_timeout=5, autocommit=True)
            connection.close()
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError("MSSQL chưa sẵn sàng: " + last_error[-500:])


def _refresh_runtime_credentials(app, mysql_password, mssql_password):
    os.environ["MYSQL_ROOT_PASSWORD"] = mysql_password
    os.environ["MSSQL_SA_PASSWORD"] = mssql_password
    credentials = app.extensions.get("database_credentials", {})
    if credentials.get("mysql") is not None:
        credentials["mysql"]["password"] = mysql_password
    if credentials.get("mssql") is not None:
        credentials["mssql"]["password"] = mssql_password


def _compose_up(environment, mode=None, progress_start=25, progress_end=47):
    command = [
        "docker", "compose", "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE),
        "up", "-d", "--remove-orphans",
    ]
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                   text=True, env=environment)
        started = time.time()
        while process.poll() is None:
            elapsed = int(time.time() - started)
            if mode:
                # Đây là phần trăm của toàn bộ quy trình, không giả làm phần trăm byte tải Docker.
                estimate = min(progress_end - 1, progress_start + elapsed // 6)
                _write_database_job(
                    mode, "working", estimate,
                    "Khởi động database" if mode == "initial" else "Áp dụng Docker",
                    f"Docker đang tải/khởi tạo container · đã chạy {elapsed} giây "
                    f"· tiến độ tổng theo giai đoạn {estimate}%",
                )
            time.sleep(2)
            if time.time() - started > 1800:
                process.kill()
                process.wait(timeout=10)
                raise RuntimeError("Docker chạy quá 30 phút nên đã dừng")
        output.seek(0)
        detail = output.read()
        if process.returncode:
            raise RuntimeError((detail or "Docker Compose thất bại").strip()[-1200:])


def _initial_database_worker(app, mysql_password, mssql_password):
    with DATABASE_JOB_LOCK, app.app_context():
        try:
            _write_database_job("initial", "working", 5, "Kiểm tra cấu hình",
                                "Đã kiểm tra định dạng hai mật khẩu")
            validate_database_password(mysql_password, "Mật khẩu MySQL")
            validate_database_password(mssql_password, "Mật khẩu MSSQL")
            if mysql_password == mssql_password:
                raise ValueError("MySQL và MSSQL phải dùng hai mật khẩu khác nhau")

            _write_database_job("initial", "working", 12, "Lưu cấu hình an toàn",
                                "Đang tạo .env và cấu hình JX")
            write_env(ENV_FILE, {
                "MYSQL_ROOT_PASSWORD": mysql_password,
                "MSSQL_SA_PASSWORD": mssql_password,
            })
            changed, _snapshots = patch_all_credentials(PROJECT_ROOT, mysql_password, mssql_password)
            environment = os.environ.copy()
            environment.update({"MYSQL_ROOT_PASSWORD": mysql_password,
                                "MSSQL_SA_PASSWORD": mssql_password})

            _write_database_job("initial", "working", 25, "Khởi động database",
                                "Docker có thể cần tải image trong lần đầu")
            _compose_up(environment, "initial", 25, 47)
            _write_database_job("initial", "working", 48, "Chờ MySQL",
                                "Đang nạp dữ liệu đăng nhập server1")
            _wait_mysql(mysql_password)
            _write_database_job("initial", "working", 65, "Chờ MSSQL",
                                "Đang đợi SQL Server nhận kết nối")
            _wait_mssql(mssql_password)

            _write_database_job("initial", "working", 76, "Nạp dữ liệu MSSQL",
                                "Đang kiểm tra hoặc phục hồi account_tong")
            _run_setup_command([sys.executable, str(PROJECT_ROOT / "tools" / "init_databases.py")],
                               timeout=900, env=environment)
            _wait_mssql(mssql_password, "account_tong")

            _write_database_job("initial", "working", 90, "Hoàn thiện dịch vụ Web",
                                "Đang bật Website công khai và lịch sao lưu")
            _refresh_runtime_credentials(app, mysql_password, mssql_password)
            _run_setup_command(["systemctl", "enable", "jx-backup-scheduler"], timeout=30)
            _run_setup_command(["systemctl", "restart", "quanly-public", "jx-backup-scheduler"], timeout=60)
            _mark_database_setup_complete()
            _write_database_job("initial", "done", 100, "Thiết lập hoàn tất",
                                f"MySQL và MSSQL đã sẵn sàng; đã cập nhật {changed} trường cấu hình JX. Game chưa tự chạy.")
        except Exception as exc:
            _write_database_job("initial", "error", 100, "Thiết lập chưa hoàn tất", str(exc))


def _alter_mysql_password(old_password, new_password):
    connection = pymysql.connect(host="127.0.0.1", port=3306, user="root",
                                 password=old_password, database="mysql",
                                 connect_timeout=8, autocommit=True)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT Host FROM mysql.user WHERE User='root'")
        hosts = [str(row[0]) for row in cursor.fetchall()]
        if not hosts:
            raise RuntimeError("Không tìm thấy tài khoản root của MySQL")
        for host in hosts:
            cursor.execute("ALTER USER 'root'@%s IDENTIFIED BY %%s" % connection.escape(host),
                           (new_password,))
    finally:
        connection.close()


def _alter_mssql_password(old_password, new_password):
    connection = pymssql.connect(server="127.0.0.1", port=1433, user="sa",
                                 password=old_password, database="master",
                                 login_timeout=8, autocommit=True)
    try:
        escaped = new_password.replace("'", "''")
        connection.cursor().execute("ALTER LOGIN [sa] WITH PASSWORD=N'%s'" % escaped)
    finally:
        connection.close()


def _restore_env_bytes(content):
    temporary = ENV_FILE.with_suffix(".env.rollback.tmp")
    temporary.write_bytes(content)
    os.chmod(temporary, 0o600)
    os.replace(temporary, ENV_FILE)


def _rotate_database_worker(app, mysql_password, mssql_password, stop_requested=False):
    with DATABASE_JOB_LOCK, app.app_context():
        active_units = [unit for unit in GAME_UNITS if _unit_active(unit)]
        if active_units:
            if not stop_requested:
                _write_database_job("rotate", "error", 100, "Chưa thể đổi mật khẩu",
                                    "Server vẫn đang chạy; chưa có xác nhận Stop All.")
                return
            try:
                _write_database_job("rotate", "working", 3, "Đang Stop All",
                                    "Đang dừng an toàn 6 thành phần và chờ lưu dữ liệu")
                stop_game_stack = app.extensions.get("stop_game_stack")
                if not callable(stop_game_stack):
                    raise RuntimeError("Chức năng Stop All chưa sẵn sàng")
                _stopped, stop_errors = stop_game_stack()
                remaining = [unit for unit in GAME_UNITS if _unit_active(unit)]
                if stop_errors or remaining:
                    details = "; ".join(stop_errors or remaining)
                    raise RuntimeError("Stop All chưa hoàn tất: " + details)
            except Exception as exc:
                _write_database_job("rotate", "error", 100, "Không đổi mật khẩu",
                                    str(exc) + ". Database chưa bị thay đổi.")
                return
        old_mysql, old_mssql = _database_passwords()
        original_env = ENV_FILE.read_bytes()
        snapshots = {}
        mysql_changed = False
        mssql_changed = False
        try:
            _write_database_job("rotate", "working", 7, "Kiểm tra an toàn", "Server game đã tắt")
            validate_database_password(mysql_password, "Mật khẩu MySQL")
            validate_database_password(mssql_password, "Mật khẩu MSSQL")
            if mysql_password == mssql_password:
                raise ValueError("MySQL và MSSQL phải dùng hai mật khẩu khác nhau")
            if not old_mysql or not old_mssql:
                raise RuntimeError("Chưa có mật khẩu database hiện tại")

            _write_database_job("rotate", "working", 15, "Tạo backup an toàn",
                                "Đang sao lưu MySQL và MSSQL trước khi đổi")
            backup = app.extensions.get("create_database_backup")
            if not callable(backup):
                raise RuntimeError("Chức năng backup chưa sẵn sàng")
            backup_name = backup(prefix="before_restore")

            _write_database_job("rotate", "working", 32, "Đổi mật khẩu MySQL",
                                "Đang cập nhật các tài khoản root")
            _alter_mysql_password(old_mysql, mysql_password)
            mysql_changed = True
            _write_database_job("rotate", "working", 47, "Đổi mật khẩu MSSQL",
                                "Đang cập nhật tài khoản sa")
            _alter_mssql_password(old_mssql, mssql_password)
            mssql_changed = True

            _write_database_job("rotate", "working", 60, "Đồng bộ cấu hình",
                                "Đang cập nhật .env và các file JX tương thích")
            write_env(ENV_FILE, {"MYSQL_ROOT_PASSWORD": mysql_password,
                                 "MSSQL_SA_PASSWORD": mssql_password})
            changed, snapshots = patch_all_credentials(
                PROJECT_ROOT, mysql_password, mssql_password, snapshots
            )
            environment = os.environ.copy()
            environment.update({"MYSQL_ROOT_PASSWORD": mysql_password,
                                "MSSQL_SA_PASSWORD": mssql_password})
            _write_database_job("rotate", "working", 74, "Áp dụng Docker",
                                "Đang đồng bộ biến môi trường container")
            _compose_up(environment, "rotate", 74, 87)
            _write_database_job("rotate", "working", 88, "Kiểm tra kết nối mới",
                                "Đang xác nhận cả hai database")
            _wait_mysql(mysql_password, timeout=120)
            _wait_mssql(mssql_password, "account_tong", timeout=120)
            _refresh_runtime_credentials(app, mysql_password, mssql_password)
            _run_setup_command(["systemctl", "restart", "quanly-public", "jx-backup-scheduler"], timeout=60)
            _write_database_job("rotate", "done", 100, "Đổi mật khẩu hoàn tất",
                                f"Backup an toàn: {backup_name}. Đã cập nhật {changed} trường cấu hình JX.")
        except Exception as exc:
            rollback_errors = []
            if mssql_changed:
                try:
                    _alter_mssql_password(mssql_password, old_mssql)
                except Exception as rollback_exc:
                    rollback_errors.append("MSSQL: " + str(rollback_exc))
            if mysql_changed:
                try:
                    _alter_mysql_password(mysql_password, old_mysql)
                except Exception as rollback_exc:
                    rollback_errors.append("MySQL: " + str(rollback_exc))
            try:
                _restore_env_bytes(original_env)
                rollback_errors.extend(restore_snapshots(snapshots))
                environment = os.environ.copy()
                environment.update({"MYSQL_ROOT_PASSWORD": old_mysql,
                                    "MSSQL_SA_PASSWORD": old_mssql})
                _compose_up(environment)
                _refresh_runtime_credentials(app, old_mysql, old_mssql)
            except Exception as rollback_exc:
                rollback_errors.append("Cấu hình: " + str(rollback_exc))
            message = str(exc)
            if rollback_errors:
                message += " | Rollback cần kiểm tra: " + "; ".join(rollback_errors)
            else:
                message += " | Đã phục hồi mật khẩu và cấu hình cũ."
            _write_database_job("rotate", "error", 100, "Đổi mật khẩu thất bại", message)


def _load_auth():
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if AUTH_FILE.exists():
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    data = {
        "username": os.environ.get("MANAGER_DEFAULT_USER", "admin"),
        "password_hash": generate_password_hash(os.environ.get("MANAGER_DEFAULT_PASSWORD", "admin123")),
        "must_change": True,
    }
    _save_auth(data)
    return data


def _save_auth(data):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    temp = AUTH_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, AUTH_FILE)


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _valid_csrf():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


def _logged_in():
    return bool(session.get("manager_authenticated"))


def _safe_next(value):
    return value if value and value.startswith("/") and not value.startswith("//") else None


def _active_server():
    if not ACTIVE_LINK.is_symlink():
        return None
    try:
        target = ACTIVE_LINK.resolve(strict=True)
        target.relative_to(SERVERS_ROOT.resolve())
        return target
    except (OSError, ValueError):
        return None


def _unit_active(unit):
    result = subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False)
    return result.returncode == 0


def _safe_archive_member(name):
    candidate = Path(name)
    return not candidate.is_absolute() and ".." not in candidate.parts


def _extract_archive(archive_path, destination, progress=None):
    if archive_path.name.lower().endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            for member in members:
                if not _safe_archive_member(member.filename):
                    raise ValueError("Archive chứa đường dẫn không an toàn")
            total = max(1, len(members))
            last_percent = -1
            for index, member in enumerate(members, 1):
                archive.extract(member, destination)
                percent = int(index * 100 / total)
                if progress and percent != last_percent:
                    progress(percent, index, total)
                    last_percent = percent
        return

    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        for member in members:
            if (
                not _safe_archive_member(member.name)
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("Archive chứa đường dẫn, liên kết hoặc thiết bị không an toàn")
        total = max(1, len(members))
        last_percent = -1
        for index, member in enumerate(members, 1):
            archive.extract(member, destination)
            percent = int(index * 100 / total)
            if progress and percent != last_percent:
                progress(percent, index, total)
                last_percent = percent


IMPORT_JOB_RE = re.compile(r"^[a-f0-9]{32}$")


def _import_job_path(job_id):
    return IMPORT_JOBS_ROOT / (job_id + ".json")


def _write_import_job(job_id, state, phase, percent, message=""):
    if not IMPORT_JOB_RE.fullmatch(job_id or ""):
        return
    IMPORT_JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "phase": phase,
        "percent": max(0, min(100, int(percent))),
        "message": str(message)[:500],
        "updated": int(time.time()),
    }
    path = _import_job_path(job_id)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _prune_import_jobs():
    try:
        cutoff = time.time() - 86400
        for path in IMPORT_JOBS_ROOT.glob("*.json"):
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                path.unlink()
    except OSError:
        pass


def _load_server_selections():
    try:
        data = json.loads(SERVER_SELECTIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_server_selections(data):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = SERVER_SELECTIONS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, SERVER_SELECTIONS_FILE)


def _format_size(size):
    value = float(max(0, size or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def _load_custom_log_directories():
    try:
        data = json.loads(LOG_DIRECTORIES_FILE.read_text(encoding="utf-8"))
        values = data.get("paths", []) if isinstance(data, dict) else []
        return [value for value in values if isinstance(value, str)]
    except (OSError, ValueError):
        return []


def _save_custom_log_directories(values):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = LOG_DIRECTORIES_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"paths": values}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, LOG_DIRECTORIES_FILE)


def _normalize_log_relative(value):
    value = (value or "").strip().replace("\\", "/").strip("/")
    candidate = Path(value)
    if not value or candidate.is_absolute() or value == "." or ".." in candidate.parts:
        raise ValueError("Đường dẫn log phải là thư mục con bên trong server đang sử dụng")
    if any(not part or part in (".", "..") for part in candidate.parts):
        raise ValueError("Đường dẫn log không hợp lệ")
    return candidate.as_posix()


def _active_log_path(relative, require_exists=True):
    active = _active_server()
    if active is None:
        raise ValueError("Chưa có phiên bản server đang sử dụng")
    relative = _normalize_log_relative(relative)
    current = active
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Không cho phép thư mục log đi qua symbolic link")
    if require_exists and (not current.exists() or not current.is_dir()):
        raise ValueError("Thư mục log không tồn tại")
    try:
        current.resolve(strict=require_exists).relative_to(active.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("Đường dẫn nằm ngoài server đang sử dụng")
    return current


def _browse_safe_directory(root, relative=""):
    """Resolve an existing directory without ever crossing a symlink or root boundary."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Thư mục gốc không tồn tại hoặc không an toàn")
    clean = (relative or "").strip().replace("\\", "/").strip("/")
    candidate = Path(clean) if clean else Path(".")
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Đường dẫn không hợp lệ")
    current = root
    for part in candidate.parts:
        if part in ("", "."):
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError("Không cho phép đi qua symbolic link")
    if not current.is_dir():
        raise ValueError("Thư mục không tồn tại")
    try:
        current.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("Đường dẫn nằm ngoài khu vực được phép")
    normalized = current.relative_to(root).as_posix()
    return current, "." if normalized == "." else normalized


def _browse_directory_rows(root, relative=""):
    current, normalized = _browse_safe_directory(root, relative)
    rows = []
    try:
        entries = sorted(os.scandir(current), key=lambda entry: entry.name.lower())
    except OSError as exc:
        raise ValueError("Không đọc được thư mục: " + str(exc))
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                continue
            child = Path(entry.path)
            rows.append({
                "name": entry.name,
                "valid_server": ((child / "gateway").is_dir() and not (child / "gateway").is_symlink()
                                 and (child / "server1").is_dir() and not (child / "server1").is_symlink()),
            })
        except OSError:
            continue
    parent = None if normalized == "." else (Path(normalized).parent.as_posix() or ".")
    valid_server = ((current / "gateway").is_dir() and not (current / "gateway").is_symlink()
                    and (current / "server1").is_dir() and not (current / "server1").is_symlink())
    return {"path": normalized, "parent": parent, "directories": rows, "valid_server": valid_server}


def _directory_usage(path):
    files = 0
    size = 0
    errors = 0
    if not path.is_dir() or path.is_symlink():
        return files, size, errors
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            files += 1
                            size += stat.st_size
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return files, size, errors


def _delete_directory_files(path):
    removed = 0
    released = 0
    errors = []
    if not path.is_dir() or path.is_symlink():
        return removed, released, errors
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            os.unlink(entry.path)
                            removed += 1
                            released += stat.st_size
                    except OSError as exc:
                        errors.append(f"{entry.name}: {exc}")
        except OSError as exc:
            errors.append(f"{current}: {exc}")
    return removed, released, errors


def _configured_game_log_directories():
    rows = [(path, label, False) for path, label in DEFAULT_GAME_LOG_DIRS]
    defaults = {path for path, _label in DEFAULT_GAME_LOG_DIRS}
    for relative in _load_custom_log_directories():
        try:
            normalized = _normalize_log_relative(relative)
        except ValueError:
            continue
        if normalized not in defaults and all(normalized != item[0] for item in rows):
            rows.append((normalized, "Tùy chỉnh", True))
    return rows


def _game_log_rows():
    result = []
    for relative, label, custom in _configured_game_log_directories():
        try:
            path = _active_log_path(relative)
            files, size, errors = _directory_usage(path)
            exists = True
        except ValueError:
            files, size, errors, exists = 0, 0, 0, False
        result.append({"path": relative, "label": label, "custom": custom, "exists": exists,
                       "files": files, "bytes": size, "size": _format_size(size), "errors": errors})
    return result


def _filesystem_usage(path):
    files, size, errors = _directory_usage(Path(path))
    return {"files": files, "bytes": size, "size": _format_size(size), "errors": errors}


def _docker_log_rows():
    rows = []
    for container, label in DOCKER_LOG_CONTAINERS:
        log_path = ""
        size = 0
        try:
            result = subprocess.run(["docker", "inspect", "--format", "{{.LogPath}}", container],
                                    capture_output=True, text=True, timeout=5, check=False)
            if result.returncode == 0:
                log_path = result.stdout.strip()
                if log_path and Path(log_path).is_file() and not Path(log_path).is_symlink():
                    size = Path(log_path).stat().st_size
        except (OSError, subprocess.TimeoutExpired):
            pass
        rows.append({"container": container, "label": label, "path": log_path,
                     "bytes": size, "size": _format_size(size)})
    return rows


def _system_log_summary():
    persistent = _filesystem_usage("/var/log/journal")
    runtime_all = _filesystem_usage("/run/log/journal")
    jx_files = 0
    jx_bytes = 0
    jx_errors = 0
    try:
        namespace_paths = list(Path("/run/log/journal").glob("*.jxnative"))
    except OSError:
        namespace_paths = []
    for namespace_path in namespace_paths:
        files, size, errors = _directory_usage(namespace_path)
        jx_files += files
        jx_bytes += size
        jx_errors += errors
    jx_runtime = {"files": jx_files, "bytes": jx_bytes,
                  "size": _format_size(jx_bytes), "errors": jx_errors}
    runtime_bytes = max(0, runtime_all["bytes"] - jx_bytes)
    runtime = {"files": max(0, runtime_all["files"] - jx_files),
               "bytes": runtime_bytes, "size": _format_size(runtime_bytes),
               "errors": runtime_all["errors"]}
    state_size = 0
    state_files = 0
    for path in JXNATIVE_STATE_LOGS:
        try:
            if path.is_file() and not path.is_symlink():
                state_size += path.stat().st_size
                state_files += 1
        except OSError:
            pass
    return {
        "persistent": persistent,
        "runtime": runtime,
        "jx_runtime": jx_runtime,
        "state": {"files": state_files, "bytes": state_size, "size": _format_size(state_size)},
        "docker": _docker_log_rows(),
    }


def _server_candidates(version_root):
    candidates = []
    try:
        version_resolved = version_root.resolve(strict=True)
    except OSError:
        return candidates
    paths = [version_root]
    paths.extend(path for path in version_root.rglob("*") if path.is_dir())
    for candidate in paths:
        try:
            relative = candidate.relative_to(version_root)
            candidate.resolve(strict=True).relative_to(version_resolved)
        except (OSError, ValueError):
            continue
        if len(relative.parts) > 6:
            continue
        if (
            not candidate.is_symlink()
            and (candidate / "gateway").is_dir()
            and not (candidate / "gateway").is_symlink()
            and (candidate / "server1").is_dir()
            and not (candidate / "server1").is_symlink()
        ):
            candidates.append(("." if not relative.parts else relative.as_posix(), candidate))
    return candidates


def _server_root_from_selection(version_root, selected):
    """Resolve one saved/browsed path without scanning the whole server archive."""
    if not selected:
        return None
    try:
        candidate, _normalized = _browse_safe_directory(version_root, selected)
    except ValueError:
        return None
    if (
        (candidate / "gateway").is_dir()
        and not (candidate / "gateway").is_symlink()
        and (candidate / "server1").is_dir()
        and not (candidate / "server1").is_symlink()
    ):
        return candidate
    return None


def _selected_server_root(server_name):
    if not SERVER_NAME_RE.fullmatch(server_name):
        return None
    version_root = SERVERS_ROOT / server_name
    if not version_root.is_dir():
        return None
    selected = _load_server_selections().get(server_name)
    if not selected and _server_root_from_selection(version_root, ".") is not None:
        selected = "."
    return _server_root_from_selection(version_root, selected)


def _mark_binaries_executable(root):
    for relative in SERVER_BINARIES:
        path = root / relative
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o111)


def _finalize_imported_server(server_name, destination):
    candidates = _server_candidates(destination)
    if len(candidates) == 1:
        selections = _load_server_selections()
        selections[server_name] = candidates[0][0]
        _save_server_selections(selections)
        _mark_binaries_executable(candidates[0][1])
    return candidates


def _network_addresses():
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show"], capture_output=True, text=True, timeout=5, check=True
        )
        interfaces = json.loads(result.stdout)
    except Exception:
        return []
    addresses = []
    for interface in interfaces:
        name = interface.get("ifname", "unknown")
        if name == "lo" or name.startswith(("docker", "br-", "veth")):
            continue
        for info in interface.get("addr_info", []):
            address = info.get("local")
            if address:
                kind = "VPN" if name.startswith(("zt", "zerotier", "tailscale", "wg", "tun", "tap")) else "LAN"
                addresses.append((name, address, kind))
    return addresses


def _update_server_ip(root, value):
    ipaddress.IPv4Address(value)
    replacements = {
        "server1/servercfg.ini": {"InternetIp": value},
        "server1/servercf0.ini": {"InternetIp": value},
        "gateway/goddess.cfg": {"InternetIp": value, "IntranetIp": value},
        "gateway/bishop.cfg": {
            "AccSvrIP": "127.0.0.1",
            "RoleSvrIP": "127.0.0.1",
            "InternetIp": value,
            "IntranetIp": value,
        },
        "gateway/s3relay/relay_config.ini": {"InternetIp": value},
    }
    changed = []
    for relative, values in replacements.items():
        path = root / relative
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text = raw.decode("latin-1")
        updated = text
        found = False
        for key, replacement in values.items():
            expression = re.compile(
                rf"^(\s*{re.escape(key)}\s*=\s*).*$", re.IGNORECASE | re.MULTILINE
            )
            updated, count = expression.subn(
                lambda match, replacement=replacement: match.group(1) + replacement,
                updated,
            )
            found = found or bool(count)
        if found:
            path.write_bytes(updated.encode("latin-1"))
            changed.append(relative)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    temp = SERVER_IP_FILE.with_suffix(".tmp")
    temp.write_text(value + "\n", encoding="ascii")
    os.replace(temp, SERVER_IP_FILE)
    return changed


def _preferred_server_ip(current_root=None):
    addresses = _network_addresses()
    local_values = {address for _interface, address, _kind in addresses}
    try:
        saved = SERVER_IP_FILE.read_text(encoding="ascii").strip()
        ipaddress.IPv4Address(saved)
        if saved in local_values:
            return saved
    except (OSError, ValueError):
        pass
    current = _read_server_ip(current_root)
    if current in local_values:
        return current
    for _interface, address, kind in addresses:
        if kind == "LAN":
            return address
    return addresses[0][1] if addresses else ""


def _read_server_ip(root):
    if root is None:
        return ""
    expression = re.compile(r"^\s*InternetIp\s*=\s*([^\s;#]+)", re.IGNORECASE | re.MULTILINE)
    for relative in ("server1/servercfg.ini", "server1/servercf0.ini", "gateway/goddess.cfg"):
        path = root / relative
        try:
            match = expression.search(path.read_bytes().decode("latin-1"))
            if match:
                ipaddress.IPv4Address(match.group(1))
                return match.group(1)
        except (OSError, ValueError):
            continue
    return ""


LOGIN_PAGE = """
<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đăng nhập JXNative</title>
<style>
:root{--gold:#c9a45f;--gold-light:#efd18c;--line:#443426;--mut:#9f9180;--fg:#e8dfd1}*{box-sizing:border-box}body{font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;background:radial-gradient(circle at 72% 8%,rgba(197,143,59,.16),transparent 30rem),linear-gradient(135deg,#080604,#130e09 55%,#080604);color:var(--fg);display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}.login-shell{width:min(430px,100%)}.login-brand{text-align:center;margin-bottom:18px;color:var(--gold-light)}.login-brand span{display:block;font-size:29px;line-height:1}.login-brand b{display:block;margin-top:7px;font:700 25px Georgia,"Times New Roman",serif;letter-spacing:.02em}.login-card{background:linear-gradient(180deg,rgba(26,20,15,.98),rgba(17,13,10,.98));padding:29px;border:1px solid var(--line);border-radius:14px;box-shadow:0 28px 80px rgba(0,0,0,.48)}h1{margin:0 0 5px;color:#f0d9aa;font:700 22px Georgia,"Times New Roman",serif}.login-subtitle{margin:0 0 18px;color:var(--mut);font-size:13px}.first-login{border:1px solid rgba(201,164,95,.45);background:rgba(201,164,95,.08);padding:13px 14px;border-radius:9px;margin:14px 0}.first-login>b{display:block;color:var(--gold-light);margin-bottom:7px}.credential{display:flex;justify-content:space-between;gap:15px;padding:4px 0;font-size:13px}.credential code{color:#fff2cf;font-weight:700}.first-login small{display:block;color:#b8aa99;margin-top:8px;line-height:1.45}.field{display:block;margin-top:12px;color:#b8aa99;font-size:12px}.field input{box-sizing:border-box;width:100%;padding:11px 12px;margin-top:5px;border-radius:7px;border:1px solid #4a392b;background:#0d0a08;color:#fff;font:inherit}.field input:focus{outline:0;border-color:var(--gold);box-shadow:0 0 0 3px rgba(201,164,95,.12)}button{box-sizing:border-box;width:100%;padding:11px;margin-top:18px;border-radius:7px;border:1px solid #c0974d;background:#9d7838;color:#fff8e9;font-weight:750;cursor:pointer}button:hover{background:#b48a43}.err{padding:9px 11px;border:1px solid rgba(224,90,84,.4);border-radius:7px;background:rgba(224,90,84,.09);color:#ef8078;font-size:13px}.login-foot{text-align:center;color:#6f6458;font-size:11px;margin-top:14px}@media(max-width:480px){.login-card{padding:23px 19px}}
</style></head><body><div class="login-shell"><div class="login-brand"><span>⚔</span><b>JXNative</b></div><form method="post" class="login-card"><h1>Đăng nhập quản trị</h1><p class="login-subtitle">Một tài khoản cho quản lý server và website.</p>{% for message in get_flashed_messages() %}<p class="err">{{ message }}</p>{% endfor %}{% if first_login %}<div class="first-login"><b>🔑 Thông tin đăng nhập lần đầu</b><div class="credential"><span>Tài khoản</span><code>{{ default_user }}</code></div><div class="credential"><span>Mật khẩu</span><code>{{ default_password }}</code></div><small>Sau lần đăng nhập này, hệ thống sẽ yêu cầu đặt mật khẩu riêng.</small></div>{% endif %}<input type="hidden" name="csrf_token" value="{{ csrf }}"><label class="field">Tài khoản<input name="username" value="{{ default_user if first_login else '' }}" autocomplete="username" required autofocus></label><label class="field">Mật khẩu<input name="password" type="password" value="{{ default_password if first_login else '' }}" autocomplete="current-password" required></label><button>Đăng nhập</button></form><div class="login-foot">JXNative Server Control</div></div></body></html>
"""

LOGIN_PAGE = LOGIN_PAGE.replace(
    'h1{margin:0 0 5px;color:#f0d9aa;font:700 22px Georgia,"Times New Roman",serif}',
    'h1{margin:0 0 5px;color:#f0d9aa;font:750 22px Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}',
)


SETUP_PAGE_LEGACY = r"""
<style>
.setup-summary{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:10px}.setup-stat{border:1px solid var(--line);border-radius:10px;padding:12px;background:rgba(59,137,212,.06)}.setup-stat small{display:block;color:var(--mut);margin-bottom:5px}.setup-stat b,.setup-stat code{overflow-wrap:anywhere}.setup-two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.log-center-grid{display:grid;grid-template-columns:minmax(620px,65%) minmax(360px,35%);gap:18px;align-items:start}.history-log{height:calc(100vh - 260px);min-height:620px;background:#03060b;border:1px solid var(--line);border-radius:9px;padding:12px;overflow:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap}.history-source{padding:6px 9px}.compact-log-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}.compact-log-row code{display:block;white-space:normal;overflow-wrap:anywhere;margin-top:3px}.compact-log-actions{display:flex;gap:5px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.log-manage-table td:nth-child(2){white-space:normal;min-width:220px}.log-manage-table code{overflow-wrap:anywhere}.log-actions{display:flex;gap:6px;align-items:center}.log-note{border-left:3px solid var(--warn);padding:9px 12px;background:rgba(232,162,59,.08);margin:10px 0}.danger-note{color:var(--err)}.folder-path-form{display:grid;gap:7px;min-width:230px}.selected-folder{display:block;max-width:340px;white-space:normal;overflow-wrap:anywhere;color:var(--fg)}.folder-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:100;align-items:center;justify-content:center;padding:18px}.folder-modal.open{display:flex}.folder-dialog{width:min(680px,100%);max-height:82vh;background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.35);display:flex;flex-direction:column}.folder-head,.folder-foot{padding:14px 16px;display:flex;gap:9px;align-items:center}.folder-head{border-bottom:1px solid var(--line)}.folder-head h2{margin:0;flex:1}.folder-foot{border-top:1px solid var(--line);justify-content:flex-end}.folder-location{padding:10px 16px;background:rgba(59,137,212,.07);border-bottom:1px solid var(--line);overflow-wrap:anywhere}.folder-list{padding:10px;min-height:230px;overflow:auto}.folder-entry{width:100%;display:flex;align-items:center;gap:10px;text-align:left;background:transparent;color:var(--fg);border-radius:7px;padding:10px}.folder-entry:hover{background:rgba(59,137,212,.12);opacity:1}.folder-entry .folder-name{flex:1}.folder-entry .pill{margin-left:auto}.folder-empty,.folder-error{padding:30px;text-align:center;color:var(--mut)}.folder-error{color:var(--err)}
@media(max-width:1100px){.log-center-grid{grid-template-columns:1fr}.history-log{height:540px;min-height:400px}}@media(max-width:900px){.setup-summary,.setup-two{grid-template-columns:1fr}}
</style>
<h1 class="page-heading">Server & Dữ liệu</h1>
<div class="server-center-tabs">
  <a class="server-center-tab {{'active' if active_tab=='versions' else ''}}" href="{{ url_for('manager_ext.setup', tab='versions') }}">Phiên bản & IP</a>
  <a class="server-center-tab {{'active' if active_tab=='logs' else ''}}" href="{{ url_for('manager_ext.setup', tab='logs') }}">Log & Dung lượng</a>
  <a class="server-center-tab" href="{{ url_for('database_tools') }}">Sao lưu & Khôi phục</a>
</div>
{% if active_tab == 'versions' %}
<section class="card"><h2>📌 Server đang sử dụng</h2><div class="setup-summary"><div class="setup-stat"><small>Phiên bản</small><b>{{ active_name or 'Chưa chọn' }}</b></div><div class="setup-stat"><small>Đường dẫn chạy</small><code>{{ active_path or 'Chưa có' }}</code></div><div class="setup-stat"><small>IP cấu hình gần nhất</small><b>{{ current_ip or 'Chưa xác định' }}</b></div></div></section>

<section class="card"><h2>🌐 Cấu hình IP game</h2><p class="muted">Chọn IP LAN/ZeroTier phát hiện trên máy hoặc nhập IPv4 thủ công. Sau khi đổi IP, dùng Reload hoặc Start All để áp dụng.</p>
<form method="post" action="{{ url_for('manager_ext.set_ip') }}"><input type="hidden" name="csrf_token" value="{{ csrf }}"><div class="row"><label>Địa chỉ phát hiện trên máy<select name="selected_ip"><option value="">-- Chọn IP --</option>{% for interface,address,kind in addresses %}<option value="{{ address }}">{{ interface }} — {{ address }} ({{ kind }})</option>{% endfor %}</select></label><label>Nhập IPv4 thủ công<input name="manual_ip" placeholder="Ví dụ: 192.168.1.55"></label></div><button>Cập nhật IP server</button></form></section>

<section class="card"><h2>📦 Các phiên bản server</h2><p class="muted">Chọn thư mục bằng cửa sổ duyệt an toàn. Chỉ thư mục có đồng thời <code>gateway/</code> và <code>server1/</code> mới dùng được. Phải Stop All trước khi đổi phiên bản.</p>
<div class="scroll"><table><thead><tr><th>Phiên bản</th><th>Đường dẫn chạy</th><th>Kiểm tra</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>
{% for server in servers %}<tr><td><b>{{ server.name }}</b><form method="post" action="{{ url_for('manager_ext.rename_server') }}" style="display:flex;gap:5px;margin-top:7px"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="server_name" value="{{ server.name }}"><input name="new_name" value="{{ server.name }}" style="min-width:145px;padding:6px"><button class="mut" {{ 'disabled' if server.active else '' }}>Đổi tên</button></form></td>
<td><form method="post" action="{{ url_for('manager_ext.select_server_path') }}" class="folder-path-form"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="server_name" value="{{ server.name }}"><input type="hidden" name="server_path" value="{{ server.selected_path }}"><code class="selected-folder">/JX_Servers/JX_Versions/{{ server.name }}{{ '' if not server.selected_path or server.selected_path == '.' else '/' + server.selected_path }}</code><button type="button" class="mut browse-folder" data-mode="server" data-server="{{ server.name }}" data-current="{{ server.selected_path or '.' }}" {{ 'disabled' if server.active else '' }}>📁 Chọn thư mục</button></form></td>
<td>{% if not server.selected_path %}<span class="pill off">Chưa chọn đường dẫn</span>{% elif server.missing %}<span class="pill off" title="{{ server.missing|join(', ') }}">Thiếu {{ server.missing|length }} binary</span>{% else %}<span class="pill on">Đủ điều kiện</span>{% endif %}</td><td>{% if server.active %}<span class="pill on">Đang sử dụng</span>{% else %}<span class="pill">Sẵn sàng</span>{% endif %}</td><td><form class="inline" method="post" action="{{ url_for('manager_ext.activate') }}"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="server_name" value="{{ server.name }}"><button {{ 'disabled' if server.active or server.missing or not server.selected_path else '' }}>Kích hoạt</button></form> <form class="inline" method="post" action="{{ url_for('manager_ext.delete_server') }}" data-confirm="Chuyển phiên bản {{ server.name }} vào thùng rác?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="server_name" value="{{ server.name }}"><button class="err" {{ 'disabled' if server.active else '' }}>Xóa</button></form></td></tr>{% else %}<tr><td colspan="5">Chưa tải lên phiên bản server nào.</td></tr>{% endfor %}</tbody></table></div></section>

<div class="setup-two"><section class="card"><h2>⬆️ Upload phiên bản mới</h2><p class="muted">Nhận .zip, .tgz hoặc .tar.gz; giữ nguyên cấu trúc và tự dò đường dẫn hợp lệ.</p><form method="post" action="{{ url_for('manager_ext.upload') }}" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{ csrf }}"><label>Tên phiên bản<input name="server_name" placeholder="Ví dụ: jx-2026-08" required></label><label>File server<input type="file" name="archive" accept=".zip,.tgz,.gz" required></label><button>Upload và giải nén</button></form></section>
<section class="card"><h2>🐙 Tải từ GitHub</h2><p class="muted">Dùng repository công khai và chỉ tải lịch sử mới nhất.</p><form method="post" action="{{ url_for('manager_ext.clone_github') }}"><input type="hidden" name="csrf_token" value="{{ csrf }}"><div class="row"><label>Tên phiên bản<input name="server_name" placeholder="Ví dụ: jx-main" required></label><label>Nhánh (có thể trống)<input name="branch" placeholder="main"></label></div><label>Link GitHub<input name="github_url" type="url" placeholder="https://github.com/tai-khoan/repository.git" required></label><button>Tải về từ GitHub</button></form></section></div>
{% else %}
<div class="log-center-grid" id="log-management"><section class="card"><h2>📜 Toàn bộ log JXNative còn lưu</h2><p class="muted">Khu vực lịch sử đọc trực tiếp journal và Docker. Dashboard chỉ hiển thị phiên thao tác hiện tại.</p>
<div class="row" style="align-items:flex-end"><label>Nguồn<select id="historySource">{% for key,label in history_log_sources %}<option value="{{key}}">{{label}}</option>{% endfor %}</select></label><label>Số dòng<select id="historyTail"><option value="300">300</option><option value="1000">1.000</option><option value="10000">10.000</option><option value="all">Tối đa 50.000</option></select></label><div style="flex:0"><button type="button" id="historyRefresh">Làm mới</button></div></div>
<div class="history-log" id="historyLog">Đang tải...</div></section><div>
<section class="card"><h2>🧹 Log game</h2><p class="muted">Chỉ xóa file trong server active, không xóa thư mục và không đi theo symbolic link.</p>
{% if active_path %}{% for row in game_logs %}<div class="compact-log-row"><div><b>{{row.label}}{% if row.custom %} <span class="pill">Tùy chỉnh</span>{% endif %}</b><code>{{row.path}}</code><span class="muted">{{row.files}} file · {{row.size}}</span>{% if not row.exists %}<br><span class="danger-note">Chưa tồn tại hoặc không an toàn</span>{% endif %}</div><div class="compact-log-actions"><form method="post" action="{{ url_for('manager_ext.delete_game_log') }}" data-confirm="Xóa toàn bộ file bên trong {{ row.path }}?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="path" value="{{ row.path }}"><button class="err" {{'disabled' if not row.exists else ''}}>Xóa</button></form>{% if row.custom %}<form method="post" action="{{ url_for('manager_ext.remove_game_log_path') }}"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="path" value="{{ row.path }}"><button class="mut" title="Chỉ bỏ khỏi danh sách">−</button></form>{% endif %}</div></div>{% endfor %}
<details style="margin-top:12px"><summary style="cursor:pointer;font-weight:700">＋ Thêm thư mục log</summary><form method="post" action="{{ url_for('manager_ext.add_game_log_path') }}" id="addLogFolderForm"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="path" required><label>Thư mục trong server active</label><code class="selected-folder" id="selectedLogFolder">Chưa chọn</code><div class="tools"><button type="button" class="mut browse-folder" data-mode="logs" data-current=".">📁 Duyệt thư mục</button><button id="addLogFolderButton" disabled>Thêm đường dẫn</button></div></form></details>
<form method="post" action="{{ url_for('manager_ext.delete_all_game_logs') }}" style="margin-top:12px" data-confirm="XÓA TẤT CẢ file trong mọi thư mục log game đang liệt kê?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="err">Xóa tất cả log game</button></form>{% else %}<p class="danger-note">Chưa kích hoạt server nên chưa thể quản lý thư mục log game.</p>{% endif %}

</section>
<section class="card"><h2>🖥️ Log hệ thống</h2><div class="log-note"><b>Lưu ý:</b> journal dùng chung cho cả Ubuntu. Dọn journal không cần tắt game nhưng log đã dọn không thể khôi phục.</div>
<div class="compact-log-row"><div><b>Journal trên ổ + RAM</b><code>/var/log/journal · /run/log/journal</code><span class="muted">{{system_logs.persistent.size}} + {{system_logs.runtime.size}}</span></div><form method="post" action="{{ url_for('manager_ext.clean_system_logs') }}" data-confirm="Dọn journal toàn máy xuống khoảng 100 MB?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="err" {{'disabled' if not journal_needs_cleanup else ''}}>{{'Chưa cần dọn' if not journal_needs_cleanup else 'Dọn xuống 100 MB'}}</button></form></div>
<div class="compact-log-row"><div><b>Log thao tác JXNative</b><code>game-start.log · game-reload.log · activity.jsonl</code><span class="muted">{{system_logs.state.size}}</span></div><form method="post" action="{{ url_for('manager_ext.clear_operation_logs') }}" data-confirm="Làm trống log Start All, Reload và Nhật ký hoạt động?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="err" {{'disabled' if not system_logs.state.bytes else ''}}>Làm trống</button></form></div>
{% for row in system_logs.docker %}<div class="compact-log-row"><div><b>Docker {{row.label}}</b><code>{{row.path or row.container}}</code><span class="muted">{{row.size}}</span></div><span class="pill on">Tự xoay 20 MB × 5</span></div>{% endfor %}
</section></div></div>
<script>(function(){
const source=document.getElementById('historySource'),tail=document.getElementById('historyTail'),box=document.getElementById('historyLog'),button=document.getElementById('historyRefresh');
const colors={PaySys:'#18ffff',RelayPay:'#ff4081',Goddess:'#e040fb',Bishop:'#448aff',S3Relay:'#76ff03',GameServer:'#ff9100',MSSQL:'#ffd54f',MySQL:'#00bfa5'};
function render(text){box.replaceChildren();for(const raw of text.split(/\r?\n/)){if(!raw)continue;const line=document.createElement('div'),match=raw.match(/^([^|]+)\s*\|\s*(.*)$/);line.textContent=raw;if(match){line.style.color=colors[match[1].trim()]||'#cdd6e6';const lower=match[2].toLowerCase();if(/error|failed|fatal|exception|exit-code/.test(lower))line.style.color='#ff5c72';else if(/warn|warning/.test(lower))line.style.color='#ffb02e'}box.appendChild(line)}if(!box.childNodes.length)box.textContent='(chưa có log)';box.scrollTop=box.scrollHeight}
async function load(){button.disabled=true;box.textContent='Đang tải...';try{const query=new URLSearchParams({mode:'history',tail:tail.value,timestamps:'1'}),response=await fetch('/logs/'+encodeURIComponent(source.value)+'/raw?'+query,{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);render(await response.text())}catch(error){box.textContent='Không đọc được log: '+error.message}finally{button.disabled=false}}
button.addEventListener('click',load);source.addEventListener('change',load);tail.addEventListener('change',load);load();
})();</script>
{% endif %}
<div class="folder-modal" id="folderModal" aria-hidden="true">
  <div class="folder-dialog" role="dialog" aria-modal="true" aria-labelledby="folderTitle">
    <div class="folder-head"><h2 id="folderTitle">📁 Chọn thư mục</h2><button type="button" class="mut" id="folderClose" aria-label="Đóng">✕</button></div>
    <div class="folder-location"><b>Vị trí:</b> <code id="folderLocation">--</code></div>
    <div class="folder-list" id="folderList"><div class="folder-empty">Đang tải...</div></div>
    <div class="folder-foot"><button type="button" class="mut" id="folderBack">← Thư mục cha</button><button type="button" class="ok" id="folderSelect">Sử dụng thư mục này</button></div>
  </div>
</div>
<script>(function(){
const modal=document.getElementById('folderModal');if(!modal)return;
const list=document.getElementById('folderList'),location=document.getElementById('folderLocation'),back=document.getElementById('folderBack'),select=document.getElementById('folderSelect');
let state={mode:'',server:'',path:'.',parent:null,root:'',valid:false,trigger:null};
function close(){modal.classList.remove('open');modal.setAttribute('aria-hidden','true');state.trigger?.focus()}
function joinPath(base,name){return base&&base!=='.'?base+'/'+name:name}
async function load(path){list.innerHTML='<div class="folder-empty">Đang tải thư mục...</div>';select.disabled=true;const query=new URLSearchParams({mode:state.mode,path:path||'.'});if(state.server)query.set('server_name',state.server);try{const response=await fetch({{ url_for('manager_ext.browse_folders')|tojson }}+'?'+query,{cache:'no-store',headers:{Accept:'application/json'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Không đọc được thư mục');state.path=data.path;state.parent=data.parent;state.root=data.root_label;state.valid=state.mode==='server'?!!data.valid_server:data.path!=='.';location.textContent=data.root_label+(data.path==='.'?'':'/'+data.path);back.disabled=data.parent===null;select.disabled=!state.valid;select.title=state.mode==='server'&&!state.valid?'Thư mục cần có gateway và server1':state.mode==='logs'&&!state.valid?'Hãy chọn một thư mục con':'';list.replaceChildren();for(const item of data.directories){const row=document.createElement('button');row.type='button';row.className='folder-entry';const icon=document.createElement('span');icon.textContent='📁';const name=document.createElement('span');name.className='folder-name';name.textContent=item.name;row.append(icon,name);if(state.mode==='server'&&item.valid_server){const badge=document.createElement('span');badge.className='pill on';badge.textContent='Hợp lệ';row.appendChild(badge)}row.addEventListener('click',()=>load(joinPath(data.path,item.name)));list.appendChild(row)}if(!data.directories.length)list.innerHTML='<div class="folder-empty">Thư mục này không có thư mục con.</div>'}catch(error){list.innerHTML='';const message=document.createElement('div');message.className='folder-error';message.textContent=error.message;list.appendChild(message)}}
document.querySelectorAll('.browse-folder').forEach(button=>button.addEventListener('click',()=>{state={mode:button.dataset.mode,server:button.dataset.server||'',path:button.dataset.current||'.',parent:null,root:'',valid:false,trigger:button};document.getElementById('folderTitle').textContent=state.mode==='server'?'📁 Chọn đường dẫn chạy':'📁 Chọn thư mục log';modal.classList.add('open');modal.setAttribute('aria-hidden','false');load(state.path)}));
back.addEventListener('click',()=>{if(state.parent!==null)load(state.parent)});
select.addEventListener('click',()=>{if(!state.valid)return;if(state.mode==='server'){const form=state.trigger.closest('form');form.elements.server_path.value=state.path;form.submit()}else{const form=document.getElementById('addLogFolderForm');form.elements.path.value=state.path;document.getElementById('selectedLogFolder').textContent=state.path;document.getElementById('addLogFolderButton').disabled=false;close()}});
document.getElementById('folderClose').addEventListener('click',close);modal.addEventListener('click',event=>{if(event.target===modal)close()});document.addEventListener('keydown',event=>{if(event.key==='Escape'&&modal.classList.contains('open'))close()});
})();</script>
"""

SETUP_PAGE = r"""
<style>
.center-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:11px;overflow:hidden;margin-bottom:16px}.summary-item{background:var(--card);padding:11px 13px;min-width:0}.summary-item small{display:block;color:var(--mut);margin-bottom:3px}.summary-item b,.summary-item code{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.section-head h2{margin:0}.compact-table td{vertical-align:middle}.server-name-cell b{display:block}.server-path{display:block;max-width:420px;overflow:hidden;text-overflow:ellipsis}.row-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px}.version-action-button{min-width:36px}.version-action-grid{display:grid;gap:15px}.version-action-block{padding:13px;border:1px solid var(--line);border-radius:10px}.version-action-block h3{margin:0 0 9px}.version-action-block form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.version-action-block code{display:block;overflow-wrap:anywhere;margin-bottom:8px}.version-action-block.danger{border-color:rgba(224,90,84,.35)}.sub-tabs{display:flex;gap:5px;margin-bottom:16px}.sub-tab{padding:9px 14px;border-radius:8px;text-decoration:none;background:#232c3d;color:var(--mut);font-weight:700}.sub-tab.active{background:var(--acc);color:#fff}.log-viewer-card{padding-bottom:14px}.history-log-v116{height:calc(100vh - 260px);min-height:520px;background:#03060b;border:1px solid var(--line);border-radius:9px;padding:12px;overflow:auto;font:12px/1.62 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;color:#d8d1c5}.history-log-v116:fullscreen{height:100vh;padding:20px;border:0;border-radius:0}.log-toolbar-v116{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:10px}.log-toolbar-v116 label{margin:0;min-width:150px}.log-toolbar-v116 .toggle-line{min-width:auto}.history-log-v116 .log-line{display:flex;align-items:flex-start;min-height:1.62em;margin:0;line-height:1.62}.history-log-v116 .console-log-source{flex:0 0 88px;width:88px;padding:0;border:0;background:transparent;font-weight:700}.history-log-v116 .log-separator{flex:0 0 16px;color:#68717d}.history-log-v116 .log-time{flex:0 0 76px;margin:0;color:#68717d;opacity:1}.history-log-v116 .log-message{flex:1 1 auto;min-width:0;color:#d8d1c5}.history-log-v116 .log-message.is-success{color:#52d6b5}.history-log-v116 .log-message.is-warning{color:#f0b44c}.history-log-v116 .log-message.is-error{color:#ff6678}.history-log-v116 .log-message.is-debug{color:#89919b}.history-log-v116 .log-date-divider{display:flex;align-items:center;gap:10px;margin:8px 0 5px;color:#8e97a2;font-size:11px}.history-log-v116 .log-date-divider:before,.history-log-v116 .log-date-divider:after{content:"";height:1px;background:#252b31}.history-log-v116 .log-date-divider:before{width:28px}.history-log-v116 .log-date-divider:after{flex:1}.storage-list{display:grid;grid-template-columns:1fr 1fr;gap:16px}.storage-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}.storage-row code{display:block;white-space:normal;overflow-wrap:anywhere;margin:3px 0}.storage-actions{display:flex;gap:5px}.storage-total{font-variant-numeric:tabular-nums}.ui-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:100;align-items:center;justify-content:center;padding:18px}.ui-modal.open{display:flex}.ui-dialog{width:min(680px,100%);max-height:86vh;background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.4);display:flex;flex-direction:column}.ui-dialog.wide{width:min(820px,100%)}.ui-head,.ui-foot{padding:14px 16px;display:flex;align-items:center;gap:9px}.ui-head{border-bottom:1px solid var(--line)}.ui-head h2{margin:0;flex:1}.ui-body{padding:16px;overflow:auto}.ui-foot{border-top:1px solid var(--line);justify-content:flex-end}.import-tabs{display:flex;gap:6px;margin-bottom:14px}.import-tab.active{background:var(--acc)}.import-panel{display:none}.import-panel.active{display:block}.folder-location{padding:10px 16px;background:rgba(59,137,212,.07);border-bottom:1px solid var(--line);overflow-wrap:anywhere}.folder-list{padding:10px;min-height:230px;overflow:auto}.folder-entry{width:100%;display:flex;align-items:center;gap:10px;text-align:left;background:transparent;color:var(--fg);border-radius:7px;padding:10px}.folder-entry:hover{background:rgba(59,137,212,.12);opacity:1}.folder-entry .folder-name{flex:1}.folder-empty,.folder-error{padding:30px;text-align:center;color:var(--mut)}.folder-error{color:var(--err)}.selected-folder{display:block;white-space:normal;overflow-wrap:anywhere;margin-bottom:7px}.danger-note{color:var(--err)}
.import-progress{margin-top:14px;padding:13px;border:1px solid var(--line);border-radius:9px;background:rgba(201,164,95,.045)}.progress-line+.progress-line{margin-top:11px}.progress-line>div{display:flex;justify-content:space-between;gap:10px;margin-bottom:6px;font-size:12px}.progress-line span{color:var(--acc-strong);font-variant-numeric:tabular-nums}.progress-line progress{display:block;width:100%;height:9px;border:0;border-radius:20px;overflow:hidden;background:#0d0b09}.progress-line progress::-webkit-progress-bar{background:#0d0b09}.progress-line progress::-webkit-progress-value{background:linear-gradient(90deg,#9b7331,#dfb95f)}.progress-line progress::-moz-progress-bar{background:linear-gradient(90deg,#9b7331,#dfb95f)}.import-progress-message{margin:10px 0 0;color:var(--mut);font-size:12px}.import-progress.ok{border-color:rgba(42,199,165,.4);background:rgba(42,199,165,.06)}.import-progress.ok .import-progress-message{color:var(--ok)}.import-progress.error{border-color:rgba(224,90,84,.45);background:rgba(224,90,84,.06)}.import-progress.error .import-progress-message{color:var(--err)}.summary-tools{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.db-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.db-warning{padding:10px 12px;border-left:3px solid var(--warn);background:rgba(232,162,59,.08);color:var(--mut)}
@media(max-width:1100px){.center-summary{grid-template-columns:1fr 1fr}.storage-list{grid-template-columns:1fr}.history-log-v116{height:540px}}@media(max-width:700px){.center-summary,.db-grid{grid-template-columns:1fr}.section-head{align-items:flex-start;flex-direction:column}.compact-table th:nth-child(2),.compact-table td:nth-child(2){display:none}.version-action-block form{grid-template-columns:1fr}}
</style>
<h1 class="page-heading">Server & Dữ liệu</h1>
<div class="server-center-tabs">
  <a class="server-center-tab {{'active' if active_tab=='versions' else ''}}" href="{{ url_for('manager_ext.setup', tab='versions') }}">Server game</a>
  <a class="server-center-tab {{'active' if active_tab=='logs' else ''}}" href="{{ url_for('manager_ext.setup', tab='logs') }}">Log & Dung lượng</a>
  <a class="server-center-tab" href="{{ url_for('database_tools') }}">Sao lưu & Khôi phục</a>
</div>
{% if active_tab == 'versions' %}
<div class="center-summary">
  <div class="summary-item"><small>Server đang dùng</small><b>{{active_name or 'Chưa chọn'}}</b></div>
  <div class="summary-item" title="{{active_path or ''}}"><small>Đường dẫn chạy</small><code>{{active_path or 'Chưa có'}}</code></div>
  <div class="summary-item"><small>IP game</small><b>{{current_ip or 'Chưa xác định'}}</b></div>
  <div class="summary-item"><small>Thao tác</small><div class="summary-tools"><button type="button" data-open-modal="ipModal" {{'disabled' if not active_path else ''}}>🌐 Đổi IP</button></div></div>
</div>
<section class="card"><div class="section-head"><div><h2>📦 Phiên bản server</h2><span class="muted">Chỉ kích hoạt đường dẫn có đủ gateway và server1.</span></div><button type="button" class="ok" data-open-modal="importModal">＋ Thêm phiên bản</button></div>
<div class="scroll server-version-scroll"><table class="compact-table"><thead><tr><th>Phiên bản</th><th>Đường dẫn</th><th>Trạng thái</th><th style="text-align:right">Thao tác</th></tr></thead><tbody>
{% for server in servers %}<tr><td class="server-name-cell"><b>{{server.name}}</b></td><td><code class="server-path" title="/JX_Servers/JX_Versions/{{server.name}}{{'' if not server.selected_path or server.selected_path=='.' else '/'+server.selected_path}}">/JX_Servers/JX_Versions/{{server.name}}{{'' if not server.selected_path or server.selected_path=='.' else '/'+server.selected_path}}</code></td><td>{% if server.active %}<span class="pill on">Đang sử dụng</span>{% elif not server.selected_path or server.missing %}<span class="pill off">Chưa hợp lệ</span>{% else %}<span class="pill">Sẵn sàng</span>{% endif %}</td><td><div class="row-actions">{% if not server.active %}<form method="post" action="{{url_for('manager_ext.activate')}}"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="server_name" value="{{server.name}}"><button {{'disabled' if server.missing or not server.selected_path else ''}}>Kích hoạt</button></form><button type="button" class="mut version-action-button" title="Thao tác khác" data-version-name="{{server.name}}" data-version-path="{{server.selected_path or '.'}}" data-version-display="/JX_Servers/JX_Versions/{{server.name}}{{'' if not server.selected_path or server.selected_path=='.' else '/'+server.selected_path}}">⋮</button>{% else %}<span class="muted">Không có thao tác</span>{% endif %}</div></td></tr>{% else %}<tr><td colspan="4" class="muted">Chưa có phiên bản server. Bấm “Thêm phiên bản”.</td></tr>{% endfor %}
</tbody></table></div></section>

<div class="ui-modal" id="versionActionModal" aria-hidden="true"><div class="ui-dialog"><div class="ui-head"><h2>Thao tác phiên bản <span id="versionActionTitle"></span></h2><button type="button" class="mut modal-close">✕</button></div><div class="ui-body version-action-grid"><div class="version-action-block"><h3>Đổi tên phiên bản</h3><form method="post" action="{{url_for('manager_ext.rename_server')}}" id="versionRenameForm"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="server_name"><input name="new_name" required><button class="mut">Đổi tên</button></form></div><div class="version-action-block"><h3>Đổi đường dẫn chạy</h3><code id="versionPathDisplay"></code><form method="post" action="{{url_for('manager_ext.select_server_path')}}" id="versionPathForm"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="server_name"><input type="hidden" name="server_path"><button type="button" class="mut browse-folder" data-mode="server">📁 Chọn thư mục</button></form></div><div class="version-action-block danger"><h3>Xóa phiên bản</h3><p class="muted">Phiên bản sẽ được chuyển vào thùng rác.</p><form method="post" action="{{url_for('manager_ext.delete_server')}}" id="versionDeleteForm"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="server_name"><button class="err">🗑 Xóa phiên bản</button></form></div></div><div class="ui-foot"><button type="button" class="mut modal-close">Đóng</button></div></div></div>

<div class="ui-modal" id="ipModal" aria-hidden="true"><div class="ui-dialog"><div class="ui-head"><h2>🌐 Đổi IP game</h2><button type="button" class="mut modal-close">✕</button></div><form method="post" action="{{url_for('manager_ext.set_ip')}}"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="ui-body"><p class="muted">Chọn IP LAN/ZeroTier hoặc nhập IPv4 thủ công. Sau khi lưu, dùng Reload hoặc Start All.</p><label>IP phát hiện trên máy<select name="selected_ip"><option value="">-- Chọn IP --</option>{% for interface,address,kind in addresses %}<option value="{{address}}">{{interface}} — {{address}} ({{kind}})</option>{% endfor %}</select></label><label>Hoặc nhập IPv4 thủ công<input name="manual_ip" placeholder="Ví dụ: 192.168.1.55"></label></div><div class="ui-foot"><button type="button" class="mut modal-close">Hủy</button><button>Lưu IP</button></div></form></div></div>
<div class="ui-modal" id="databasePasswordModal" aria-hidden="true"><div class="ui-dialog wide"><div class="ui-head"><h2>🔐 Đổi mật khẩu database</h2><button type="button" class="mut modal-close">✕</button></div><form id="databasePasswordForm" method="post" action="{{url_for('manager_ext.rotate_database_passwords')}}"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="ui-body"><div class="db-warning">Bắt buộc Stop All. Hệ thống sẽ backup trước, đổi mật khẩu thật trong MySQL/MSSQL, mã hóa và đồng bộ các file JX, rồi kiểm tra kết nối. Nếu lỗi sẽ tự rollback.</div><label>Mật khẩu Admin hiện tại<input type="password" name="admin_password" autocomplete="current-password" required></label><div class="db-grid"><label>Mật khẩu MySQL mới<input type="password" name="mysql_password" autocomplete="new-password" required minlength="12" maxlength="20"></label><label>Nhập lại MySQL<input type="password" name="mysql_confirm" autocomplete="new-password" required minlength="12" maxlength="20"></label><label>Mật khẩu MSSQL mới<input type="password" name="mssql_password" autocomplete="new-password" required minlength="12" maxlength="20"></label><label>Nhập lại MSSQL<input type="password" name="mssql_confirm" autocomplete="new-password" required minlength="12" maxlength="20"></label></div><p class="muted">12–20 ký tự, có chữ hoa, chữ thường, số và một ký tự @ _ ! . hoặc -.</p><button type="button" class="mut" id="generateDatabasePasswords">Tạo hai mật khẩu mạnh</button><div class="import-progress" id="databasePasswordProgress" hidden><div class="progress-line"><div><b id="databasePasswordPhase">Đang chuẩn bị</b><span id="databasePasswordPercent">0%</span></div><progress id="databasePasswordBar" max="100" value="0"></progress></div><p class="import-progress-message" id="databasePasswordMessage"></p></div></div><div class="ui-foot"><button type="button" class="mut modal-close">Hủy</button><button id="databasePasswordSubmit">Backup và đổi mật khẩu</button></div></form></div></div>
<div class="ui-modal" id="importModal" aria-hidden="true"><div class="ui-dialog wide"><div class="ui-head"><h2>＋ Thêm phiên bản server</h2><button type="button" class="mut modal-close">✕</button></div><div class="ui-body"><div class="import-tabs"><button type="button" class="import-tab active" data-import="upload">⬆ Upload file</button><button type="button" class="import-tab mut" data-import="github">🐙 GitHub</button></div><div class="import-panel active" data-panel="upload"><form id="serverUploadForm" method="post" action="{{url_for('manager_ext.upload')}}" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="job_id"><label>Tên phiên bản<input name="server_name" placeholder="Ví dụ: jx-2026-08" required></label><label>File server (.zip, .tgz, .tar.gz)<input type="file" name="archive" accept=".zip,.tgz,.gz" required></label><button id="serverUploadButton">Upload và giải nén</button><div class="import-progress" id="serverUploadProgress" hidden><div class="progress-line"><div><b>Tải file lên máy chủ</b><span id="uploadPercent">0%</span></div><progress id="uploadBar" max="100" value="0"></progress></div><div class="progress-line"><div><b id="extractPhase">Chờ giải nén</b><span id="extractPercent">0%</span></div><progress id="extractBar" max="100" value="0"></progress></div><p class="import-progress-message" id="uploadMessage">Đang chuẩn bị…</p></div></form></div><div class="import-panel" data-panel="github"><form method="post" action="{{url_for('manager_ext.clone_github')}}"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="row"><label>Tên phiên bản<input name="server_name" placeholder="Ví dụ: jx-main" required></label><label>Nhánh<input name="branch" placeholder="main"></label></div><label>Link GitHub<input name="github_url" type="url" placeholder="https://github.com/tai-khoan/repository.git" required></label><button>Tải từ GitHub</button></form></div></div></div></div>
{% else %}
{% if log_view == 'storage' %}<div class="center-summary"><div class="summary-item"><small>Server</small><b>{{active_name or 'Chưa chọn'}}</b></div><div class="summary-item"><small>Log game</small><b class="storage-total">{{game_log_size}}</b></div><div class="summary-item"><small>Journal</small><b class="storage-total">{{journal_size}}</b></div><div class="summary-item"><small>Ổ đĩa còn trống</small><b class="storage-total">{{disk_free}}</b></div></div>{% endif %}
<div class="sub-tabs"><a class="sub-tab {{'active' if log_view=='viewer' else ''}}" href="{{url_for('manager_ext.setup',tab='logs',view='viewer')}}">Xem log</a><a class="sub-tab {{'active' if log_view=='storage' else ''}}" href="{{url_for('manager_ext.setup',tab='logs',view='storage')}}">Quản lý dung lượng</a></div>
{% if log_view == 'viewer' %}<section class="card log-viewer-card"><div class="section-head"><div><h2>📜 Log server đầy đủ</h2><span class="muted">Chọn nguồn và bấm Tải log khi cần. Trang này không tự đọc log và không chạy realtime.</span></div><button type="button" class="mut" id="historyFullscreen">⛶ Toàn màn hình</button></div><div class="log-toolbar-v116"><label>Nguồn<select id="historySource">{% for key,label in history_log_sources %}<option value="{{key}}">{{label}}</option>{% endfor %}</select></label><label>Số dòng<select id="historyTail"><option value="1000">1.000</option><option value="3000">3.000</option><option value="all">Tất cả</option></select></label><label class="toggle-line"><input type="checkbox" id="historyTimestamps"> Hiện thời gian</label><button type="button" id="historyRefresh">Tải log</button><button type="button" class="mut" id="historyBottom">↓ Cuối log</button></div><p class="muted">Tất cả hiển thị tối đa 50.000 dòng gần nhất để bảo vệ trình duyệt.</p><div class="history-log-v116" id="historyLog">Chưa tải log. Chọn nguồn và bấm “Tải log”.</div></section>
{% else %}<div class="storage-list" id="log-management"><section class="card"><div class="section-head"><div><h2>🧹 Log game</h2><span class="muted">Chỉ xóa file trong server active.</span></div>{% if active_path %}<button type="button" class="mut browse-folder" data-mode="logs" data-current=".">＋ Thêm thư mục</button>{% endif %}</div>{% if active_path %}{% for row in game_logs %}<div class="storage-row"><div><b>{{row.label}}{% if row.custom %} <span class="pill">Tùy chỉnh</span>{% endif %}</b><code title="{{row.path}}">{{row.path}}</code><span class="muted">{{row.files}} file · {{row.size}}</span></div><div class="storage-actions"><form method="post" action="{{url_for('manager_ext.delete_game_log')}}" data-confirm="Xóa toàn bộ file trong {{row.path}}?"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="path" value="{{row.path}}"><button class="err" {{'disabled' if not row.exists else ''}}>Xóa</button></form>{% if row.custom %}<form method="post" action="{{url_for('manager_ext.remove_game_log_path')}}"><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="path" value="{{row.path}}"><button class="mut" title="Bỏ khỏi danh sách">−</button></form>{% endif %}</div></div>{% endfor %}<form method="post" action="{{url_for('manager_ext.delete_all_game_logs')}}" style="margin-top:14px" data-confirm="XÓA TẤT CẢ file trong các thư mục log game đang liệt kê?"><input type="hidden" name="csrf_token" value="{{csrf}}"><button class="err">Xóa tất cả log game</button></form>{% else %}<p class="danger-note">Chưa kích hoạt server.</p>{% endif %}</section>
<section class="card"><h2>🖥️ Log hệ thống</h2><div class="storage-row"><div><b>Journal Ubuntu</b><code>/var/log/journal · /run/log/journal</code><span class="muted">{{system_logs.persistent.size}} + {{system_logs.runtime.size}} · giới hạn 100 MB trên ổ</span></div><form method="post" action="{{url_for('manager_ext.clean_system_logs')}}" data-confirm="Dọn journal Ubuntu xuống khoảng 100 MB?"><input type="hidden" name="csrf_token" value="{{csrf}}"><button class="err" {{'disabled' if not journal_needs_cleanup else ''}}>{{'Chưa cần dọn' if not journal_needs_cleanup else 'Dọn xuống 100 MB'}}</button></form></div><div class="storage-row"><div><b>Journal 6 thành phần JXNative</b><code>/run/log/journal/*.jxnative</code><span class="muted">{{system_logs.jx_runtime.size}} · chỉ trong RAM · tự xoay tối đa 64 MB</span></div><span class="pill on">Tự quản lý</span></div><div class="storage-row"><div><b>Log thao tác JXNative</b><code>game-start.log · game-reload.log · activity.jsonl</code><span class="muted">{{system_logs.state.size}}</span></div><form method="post" action="{{url_for('manager_ext.clear_operation_logs')}}" data-confirm="Làm trống log Start All, Reload và Nhật ký hoạt động?"><input type="hidden" name="csrf_token" value="{{csrf}}"><button class="err" {{'disabled' if not system_logs.state.bytes else ''}}>Làm trống</button></form></div>{% for row in system_logs.docker %}<div class="storage-row"><div><b>Docker {{row.label}}</b><code>{{row.path or row.container}}</code><span class="muted">{{row.size}}</span></div><span class="pill on">Tự xoay 20 MB × 5</span></div>{% endfor %}</section></div>{% endif %}
<form method="post" action="{{url_for('manager_ext.add_game_log_path')}}" id="addLogFolderForm" hidden><input type="hidden" name="csrf_token" value="{{csrf}}"><input type="hidden" name="path"></form>
{% endif %}
<div class="ui-modal" id="folderModal" aria-hidden="true"><div class="ui-dialog"><div class="ui-head"><h2 id="folderTitle">📁 Chọn thư mục</h2><button type="button" class="mut modal-close">✕</button></div><div class="folder-location"><b>Vị trí:</b> <code id="folderLocation">--</code></div><div class="folder-list" id="folderList"><div class="folder-empty">Đang tải...</div></div><div class="ui-foot"><button type="button" class="mut" id="folderBack">← Thư mục cha</button><button type="button" class="ok" id="folderSelect">Sử dụng thư mục này</button></div></div></div>
<script>(function(){
function closeModal(modal){if(!modal||modal.dataset.busy==='1')return;modal.classList.remove('open');modal.setAttribute('aria-hidden','true')}
document.querySelectorAll('[data-open-modal]').forEach(button=>button.addEventListener('click',()=>{const modal=document.getElementById(button.dataset.openModal);if(modal){modal.classList.add('open');modal.setAttribute('aria-hidden','false')}}));document.querySelectorAll('.modal-close').forEach(button=>button.addEventListener('click',()=>closeModal(button.closest('.ui-modal'))));document.querySelectorAll('.ui-modal').forEach(modal=>modal.addEventListener('click',event=>{if(event.target===modal)closeModal(modal)}));document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.ui-modal.open').forEach(closeModal)});
const versionModal=document.getElementById('versionActionModal');document.querySelectorAll('.version-action-button').forEach(button=>button.addEventListener('click',()=>{const name=button.dataset.versionName,path=button.dataset.versionPath||'.',display=button.dataset.versionDisplay||name;document.getElementById('versionActionTitle').textContent=name;document.getElementById('versionPathDisplay').textContent=display;const rename=document.getElementById('versionRenameForm'),pathForm=document.getElementById('versionPathForm'),remove=document.getElementById('versionDeleteForm');rename.elements.server_name.value=name;rename.elements.new_name.value=name;pathForm.elements.server_name.value=name;pathForm.elements.server_path.value=path;const browse=pathForm.querySelector('.browse-folder');browse.dataset.server=name;browse.dataset.current=path;remove.elements.server_name.value=name;remove.dataset.confirm='Chuyển phiên bản '+name+' vào thùng rác?';versionModal.classList.add('open');versionModal.setAttribute('aria-hidden','false')}));
document.querySelectorAll('.import-tab').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.import-tab').forEach(item=>item.classList.toggle('active',item===button));document.querySelectorAll('.import-panel').forEach(panel=>panel.classList.toggle('active',panel.dataset.panel===button.dataset.import))}));
const uploadForm=document.getElementById('serverUploadForm');if(uploadForm){const uploadModal=document.getElementById('importModal'),box=document.getElementById('serverUploadProgress'),uploadBar=document.getElementById('uploadBar'),uploadPercent=document.getElementById('uploadPercent'),extractBar=document.getElementById('extractBar'),extractPercent=document.getElementById('extractPercent'),extractPhase=document.getElementById('extractPhase'),message=document.getElementById('uploadMessage'),submitButton=document.getElementById('serverUploadButton'),statusTemplate={{url_for('manager_ext.upload_status',job_id='__JOB__')|tojson}};let busy=false,pollTimer=null;function makeJobId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('')}function progress(bar,label,value){const percent=Math.max(0,Math.min(100,Math.round(Number(value)||0)));bar.value=percent;label.textContent=percent+'%'}function finish(ok,text){busy=false;delete uploadModal.dataset.busy;submitButton.disabled=false;box.classList.toggle('ok',ok);box.classList.toggle('error',!ok);message.textContent=text;if(pollTimer)clearTimeout(pollTimer);if(ok){progress(uploadBar,uploadPercent,100);progress(extractBar,extractPercent,100);extractPhase.textContent='Hoàn tất';setTimeout(()=>location.href={{url_for('manager_ext.setup')|tojson}},1300)}}async function poll(jobId){if(!busy)return;try{const response=await fetch(statusTemplate.replace('__JOB__',jobId),{cache:'no-store',headers:{Accept:'application/json'}}),data=await response.json();if(data.state!=='waiting'){extractPhase.textContent=data.phase||'Giải nén';progress(extractBar,extractPercent,data.percent);message.textContent=data.message||'Đang xử lý…'}if(data.state==='error'){finish(false,data.message||'Giải nén thất bại');return}}catch(error){}pollTimer=setTimeout(()=>poll(jobId),500)}uploadForm.addEventListener('submit',event=>{event.preventDefault();if(busy||!uploadForm.reportValidity())return;const jobId=makeJobId();uploadForm.elements.job_id.value=jobId;const payload=new FormData(uploadForm),xhr=new XMLHttpRequest();busy=true;uploadModal.dataset.busy='1';submitButton.disabled=true;box.hidden=false;box.className='import-progress';progress(uploadBar,uploadPercent,0);progress(extractBar,extractPercent,0);extractPhase.textContent='Chờ tải file';message.textContent='Đang tải file lên máy chủ…';xhr.open('POST',uploadForm.action);xhr.setRequestHeader('X-Requested-With','XMLHttpRequest');xhr.setRequestHeader('Accept','application/json');xhr.upload.addEventListener('progress',progressEvent=>{if(progressEvent.lengthComputable)progress(uploadBar,uploadPercent,progressEvent.loaded*100/progressEvent.total)});xhr.upload.addEventListener('load',()=>{progress(uploadBar,uploadPercent,100);extractPhase.textContent='Máy chủ đang kiểm tra';message.textContent='Tải file hoàn tất. Đang kiểm tra và giải nén…';poll(jobId)});xhr.addEventListener('load',()=>{let data={};try{data=JSON.parse(xhr.responseText)}catch(error){}finish(xhr.status>=200&&xhr.status<300&&data.ok,data.message||(xhr.status===413?'File vượt quá giới hạn upload.':'Máy chủ trả về lỗi HTTP '+xhr.status))});xhr.addEventListener('error',()=>finish(false,'Mất kết nối trong lúc upload. Hãy kiểm tra mạng rồi thử lại.'));xhr.addEventListener('abort',()=>finish(false,'Upload đã bị hủy.'));xhr.send(payload)})}
const databaseForm=document.getElementById('databasePasswordForm');if(databaseForm){const databaseModal=document.getElementById('databasePasswordModal'),box=document.getElementById('databasePasswordProgress'),bar=document.getElementById('databasePasswordBar'),percent=document.getElementById('databasePasswordPercent'),phase=document.getElementById('databasePasswordPhase'),message=document.getElementById('databasePasswordMessage'),submit=document.getElementById('databasePasswordSubmit');function strongPassword(){const groups=['abcdefghijkmnopqrstuvwxyz','ABCDEFGHJKLMNPQRSTUVWXYZ','23456789','@_!-'],all=groups.join(''),values=groups.map(group=>group[crypto.getRandomValues(new Uint32Array(1))[0]%group.length]);while(values.length<16)values.push(all[crypto.getRandomValues(new Uint32Array(1))[0]%all.length]);for(let index=values.length-1;index>0;index--){const other=crypto.getRandomValues(new Uint32Array(1))[0]%(index+1);[values[index],values[other]]=[values[other],values[index]]}return values.join('')}document.getElementById('generateDatabasePasswords').addEventListener('click',()=>{const mysql=strongPassword(),mssql=strongPassword();databaseForm.mysql_password.value=databaseForm.mysql_confirm.value=mysql;databaseForm.mssql_password.value=databaseForm.mssql_confirm.value=mssql});function updateProgress(data){const value=Math.max(0,Math.min(100,Number(data.percent)||0));bar.value=value;percent.textContent=Math.round(value)+'%';phase.textContent=data.phase||'Đang xử lý';message.textContent=data.message||'';box.classList.toggle('ok',data.state==='done');box.classList.toggle('error',data.state==='error')}async function pollDatabase(){try{const response=await fetch({{url_for('manager_ext.database_job_status')|tojson}},{cache:'no-store',headers:{Accept:'application/json'}}),data=await response.json();updateProgress(data);if(data.state==='working'){setTimeout(pollDatabase,1000);return}delete databaseModal.dataset.busy;submit.disabled=false}catch(error){message.textContent='Mất kết nối tạm thời, đang thử lại…';setTimeout(pollDatabase,1800)}}databaseForm.addEventListener('submit',async event=>{event.preventDefault();if(!databaseForm.reportValidity())return;databaseModal.dataset.busy='1';submit.disabled=true;box.hidden=false;box.className='import-progress';updateProgress({percent:1,phase:'Đang gửi yêu cầu',message:''});try{const response=await fetch(databaseForm.action,{method:'POST',body:new FormData(databaseForm),headers:{Accept:'application/json','X-Requested-With':'XMLHttpRequest'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Không bắt đầu được');pollDatabase()}catch(error){delete databaseModal.dataset.busy;submit.disabled=false;updateProgress({state:'error',percent:100,phase:'Không thể bắt đầu',message:error.message})}})}
const source=document.getElementById('historySource'),tail=document.getElementById('historyTail'),logBox=document.getElementById('historyLog'),refresh=document.getElementById('historyRefresh'),historyTimestamps=document.getElementById('historyTimestamps');if(source&&tail&&logBox&&refresh){const colors={PaySys:'#18ffff',RelayPay:'#ff4081',Goddess:'#e040fb',Bishop:'#448aff',S3Relay:'#76ff03',GameServer:'#ff9100',MSSQL:'#ffd54f',MySQL:'#00bfa5'},dayFormat=new Intl.DateTimeFormat('vi-VN',{day:'2-digit',month:'2-digit',year:'numeric'}),timeFormat=new Intl.DateTimeFormat('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});let loaded='';function severity(message){const value=message.toLowerCase();if(/error|failed|fatal|exception|segv|core-dump|exit-code|không mở được|thất bại/.test(value))return'error';if(/warn|warning|cảnh báo|timeout|retry/.test(value))return'warning';if(/success|successful|started|listening|kết nối ok|thành công/.test(value))return'success';if(/\bdebug\b|\bhex:|\bascii:/.test(value))return'debug';return''}function render(text){loaded=text;logBox.replaceChildren();let renderedDay='';const fragment=document.createDocumentFragment();for(const raw of text.split(/\r?\n/)){if(!raw)continue;const match=raw.match(/^([^|]+)\s*\|\s*(?:(\d{4}-\d{2}-\d{2}T\S+)\s+)?(.*)$/),label=match?match[1].trim():'System',stamp=match?match[2]:'',message=match?match[3]:raw;let day='',clock='';if(stamp){const date=new Date(stamp);if(!Number.isNaN(date.getTime())){day=dayFormat.format(date);clock=timeFormat.format(date)}}if(historyTimestamps.checked&&day&&day!==renderedDay){renderedDay=day;const divider=document.createElement('div');divider.className='log-date-divider';divider.textContent=day;fragment.appendChild(divider)}const line=document.createElement('div');line.className='log-line';const sourceNode=document.createElement('span');sourceNode.className='console-log-source';sourceNode.style.color=colors[label]||'#d6c09a';sourceNode.textContent=label;const separator=document.createElement('span');separator.className='log-separator';separator.textContent='|';line.append(sourceNode,separator);if(historyTimestamps.checked&&clock){const timeNode=document.createElement('span');timeNode.className='log-time';timeNode.textContent='['+clock+']';line.appendChild(timeNode)}const messageNode=document.createElement('span'),level=severity(message);messageNode.className='log-message'+(level?' is-'+level:'');messageNode.textContent=message;line.appendChild(messageNode);fragment.appendChild(line)}logBox.appendChild(fragment);if(!logBox.childNodes.length)logBox.textContent='(chưa có log)';logBox.scrollTop=logBox.scrollHeight}function reset(){loaded='';logBox.textContent='Chưa tải log. Bấm “Tải log” để đọc '+source.options[source.selectedIndex].text+'.'}async function load(){refresh.disabled=true;logBox.textContent='Đang tải log...';try{const query=new URLSearchParams({mode:'history',tail:tail.value,timestamps:'1'}),response=await fetch('/logs/'+encodeURIComponent(source.value)+'/raw?'+query,{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);render(await response.text())}catch(error){logBox.textContent='Không đọc được log: '+error.message}finally{refresh.disabled=false}}refresh.addEventListener('click',load);source.addEventListener('change',reset);tail.addEventListener('change',reset);historyTimestamps.addEventListener('change',()=>{if(loaded)render(loaded)});document.getElementById('historyBottom').addEventListener('click',()=>logBox.scrollTop=logBox.scrollHeight);document.getElementById('historyFullscreen').addEventListener('click',()=>logBox.requestFullscreen?.())}
const folderModal=document.getElementById('folderModal'),folderList=document.getElementById('folderList'),folderLocation=document.getElementById('folderLocation'),folderBack=document.getElementById('folderBack'),folderSelect=document.getElementById('folderSelect');let folder={mode:'',server:'',path:'.',parent:null,valid:false,trigger:null};function joinPath(base,name){return base&&base!=='.'?base+'/'+name:name}async function loadFolder(path){folderList.innerHTML='<div class="folder-empty">Đang tải...</div>';folderSelect.disabled=true;const query=new URLSearchParams({mode:folder.mode,path:path||'.'});if(folder.server)query.set('server_name',folder.server);try{const response=await fetch({{url_for('manager_ext.browse_folders')|tojson}}+'?'+query,{cache:'no-store'}),data=await response.json();if(!response.ok)throw new Error(data.error||'Không đọc được thư mục');folder.path=data.path;folder.parent=data.parent;folder.valid=folder.mode==='server'?!!data.valid_server:data.path!=='.';folderLocation.textContent=data.root_label+(data.path==='.'?'':'/'+data.path);folderBack.disabled=data.parent===null;folderSelect.disabled=!folder.valid;folderList.replaceChildren();for(const item of data.directories){const row=document.createElement('button');row.type='button';row.className='folder-entry';row.innerHTML='<span>📁</span><span class="folder-name"></span>';row.querySelector('.folder-name').textContent=item.name;if(folder.mode==='server'&&item.valid_server){const badge=document.createElement('span');badge.className='pill on';badge.textContent='Hợp lệ';row.appendChild(badge)}row.addEventListener('click',()=>loadFolder(joinPath(data.path,item.name)));folderList.appendChild(row)}if(!data.directories.length)folderList.innerHTML='<div class="folder-empty">Không có thư mục con.</div>'}catch(error){folderList.innerHTML='<div class="folder-error"></div>';folderList.firstChild.textContent=error.message}}document.querySelectorAll('.browse-folder').forEach(button=>button.addEventListener('click',()=>{folder={mode:button.dataset.mode,server:button.dataset.server||'',path:button.dataset.current||'.',parent:null,valid:false,trigger:button};document.getElementById('folderTitle').textContent=folder.mode==='server'?'📁 Chọn đường dẫn chạy':'📁 Thêm thư mục log';folderModal.classList.add('open');folderModal.setAttribute('aria-hidden','false');loadFolder(folder.path)}));folderBack.addEventListener('click',()=>{if(folder.parent!==null)loadFolder(folder.parent)});folderSelect.addEventListener('click',()=>{if(!folder.valid)return;if(folder.mode==='server'){const form=folder.trigger.closest('form');form.elements.server_path.value=folder.path;form.submit()}else{const form=document.getElementById('addLogFolderForm');form.elements.path.value=folder.path;form.submit()}});
})();</script>
"""

ACCOUNT_SETTINGS_PAGE = """
<style>
.account-grid{display:grid;grid-template-columns:minmax(320px,560px) minmax(520px,1fr);gap:18px;align-items:start}.security-summary{display:grid;grid-template-columns:repeat(2,minmax(180px,1fr));gap:10px;margin-bottom:16px}.security-stat{border:1px solid var(--line);border-radius:9px;padding:11px;background:rgba(59,137,212,.05)}.security-stat small{display:block;color:var(--mut);margin-bottom:4px}.security-table{width:100%;border-collapse:collapse}.security-table th,.security-table td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}.security-table th{color:var(--mut);font-size:12px}.security-table code{white-space:nowrap}.audit-scroll{max-height:390px;overflow:auto}.event-ok{color:#36d6b7}.event-warn{color:#ffb02e}.event-bad{color:#ff6b6b}.lock-note{border-left:3px solid #ffb02e;padding:9px 11px;background:rgba(255,176,46,.08);margin-bottom:14px}.inline-unlock{margin:0}.inline-unlock button{padding:6px 10px}.empty-row{text-align:center!important;color:var(--mut);padding:20px!important}@media(max-width:1100px){.account-grid{grid-template-columns:1fr}}
</style>
<h1 class="page-heading">Tài khoản Admin</h1>
<div class="account-grid">
<section class="card"><h2>🔐 Đổi tài khoản quản trị</h2><p class="muted">Tài khoản này dùng chung cho quản lý server và quản trị website.</p>{% if error %}<div class="flash err">{{ error }}</div>{% endif %}
<form method="post"><input type="hidden" name="csrf_token" value="{{ csrf }}"><label>Tài khoản hiện tại</label><input value="{{ username }}" disabled><label>Mật khẩu hiện tại</label><input type="password" name="current_password" required autocomplete="current-password"><label>Tên tài khoản mới</label><input name="new_username" value="{{ username }}" minlength="3" maxlength="32" required><label>Mật khẩu mới</label><input type="password" name="new_password" minlength="8" placeholder="Để trống nếu chỉ đổi tên tài khoản"><label>Nhập lại mật khẩu mới</label><input type="password" name="confirm_password"><button style="margin-top:18px">Lưu tài khoản quản trị</button></form></section>
<div>
<section class="card"><h2>🛡️ Bảo vệ đăng nhập</h2><div class="security-summary"><div class="security-stat"><small>IP phiên hiện tại</small><b>{{ current_ip }}</b></div><div class="security-stat"><small>Đăng nhập thành công gần nhất</small><b>{{ last_success_time }}</b><div class="muted">{{ last_success_ip }}</div></div></div><div class="lock-note">Mỗi 3 lần nhập sai: khóa 5 phút → 1 giờ → 24 giờ. Đăng nhập đúng sẽ đặt lại cấp khóa của IP đó.</div>
<div style="overflow:auto"><table class="security-table"><thead><tr><th>Địa chỉ IP</th><th>Trạng thái</th><th>Cấp</th><th>Sai</th><th>Lần sai cuối</th><th></th></tr></thead><tbody>{% for row in security_entries %}<tr><td><code>{{ row.ip }}</code></td><td>{% if row.locked %}<span class="event-bad">KHÓA {{ row.remaining_text }}</span>{% else %}<span class="event-ok">Cho phép</span>{% endif %}</td><td>{{ row.level }}/3</td><td>{{ row.failures }}/3</td><td>{{ row.last_failure_text }}</td><td>{% if row.locked or row.level or row.failures %}<form class="inline-unlock" method="post" action="{{ url_for('manager_ext.unlock_login_ip') }}" data-confirm="Mở khóa và đặt lại IP {{ row.ip }}?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="ip" value="{{ row.ip }}"><button class="mut">Mở khóa</button></form>{% endif %}</td></tr>{% else %}<tr><td class="empty-row" colspan="6">Chưa có IP nào bị sai hoặc bị khóa.</td></tr>{% endfor %}</tbody></table></div></section>
<section class="card"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><div><h2 style="margin-bottom:3px">📋 Nhật ký bảo mật gần đây</h2><span class="muted">Tối đa 1.000 bản ghi; không lưu mật khẩu.</span></div></div><div class="audit-scroll"><table class="security-table"><thead><tr><th>Thời gian</th><th>IP</th><th>Tài khoản nhập</th><th>Kết quả</th></tr></thead><tbody>{% for row in security_audit %}<tr><td>{{ row.time_text }}</td><td><code>{{ row.ip }}</code></td><td>{{ row.username or '—' }}</td><td class="{{ row.css }}">{{ row.label }}</td></tr>{% else %}<tr><td class="empty-row" colspan="4">Chưa có nhật ký đăng nhập.</td></tr>{% endfor %}</tbody></table></div></section>
</div></div>
"""

FIRST_RUN_DATABASE_PAGE = r"""
<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Thiết lập database JXNative</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;padding:28px;background:radial-gradient(circle at 70% 0,rgba(201,164,95,.15),transparent 32rem),#090705;color:#e8dfd1;font:14px/1.5 Inter,system-ui,sans-serif}.wizard{width:min(820px,100%);margin:auto}.brand{color:#f0d9aa;font:700 25px Georgia,serif;margin-bottom:20px}.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}.step{padding:10px 12px;border:1px solid #443426;border-radius:9px;color:#958879;background:#110d0a}.step.done{color:#58d8b8;border-color:#215c4f}.step.active{color:#f2d58f;border-color:#a67e38;background:#1b140c}.card{padding:24px;border:1px solid #443426;border-radius:14px;background:#15100c;box-shadow:0 24px 70px rgba(0,0,0,.45)}h1{font:700 25px Georgia,serif;margin:0 0 6px;color:#f0d9aa}p{color:#a99b8a}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.db{padding:15px;border:1px solid #3a2e24;border-radius:10px;background:#0e0b09}.db h2{font-size:16px;margin:0 0 5px}.db p{font-size:12px;margin:0 0 12px}label{display:block;color:#b8aa99;font-size:12px;margin-top:9px}input,button{font:inherit;border-radius:8px}input{width:100%;padding:10px 11px;margin-top:4px;border:1px solid #4a392b;background:#080706;color:#fff}input:focus{outline:0;border-color:#c9a45f;box-shadow:0 0 0 3px rgba(201,164,95,.12)}button{border:1px solid #936d31;background:#9d7838;color:#fff8e9;padding:10px 14px;font-weight:750;cursor:pointer}.secondary{background:#252015;border-color:#50412f;color:#d8c9b4}.tools{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:17px}.hint{font-size:12px}.progress{margin-top:18px;padding:15px;border:1px solid #4a392b;border-radius:10px;background:#090706}.bar{height:11px;overflow:hidden;border-radius:20px;background:#211b15}.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#9b7331,#e0bb65);transition:width .3s}.progress-head{display:flex;justify-content:space-between;margin-bottom:8px}.message{color:#a99b8a;margin:8px 0 0;white-space:pre-wrap}.progress.error{border-color:#8b3733}.progress.error .message{color:#ef8078}.progress.done{border-color:#216452}.progress.done .message{color:#58d8b8}.enter{display:none;margin-top:12px;text-decoration:none;text-align:center;background:#187d69;border:1px solid #2ab89a;color:#fff;padding:11px;border-radius:8px;font-weight:800}.enter.show{display:block}@media(max-width:700px){body{padding:14px}.steps,.grid{grid-template-columns:1fr}.card{padding:17px}.tools{align-items:stretch;flex-direction:column}.tools button{width:100%}}
</style></head><body><main class="wizard"><div class="brand">⚔ JXNative</div><div class="steps"><div class="step done">✓ 1. Đăng nhập Admin</div><div class="step done">✓ 2. Đổi mật khẩu Admin</div><div class="step active">3. Khởi tạo database</div></div><section class="card"><h1>Thiết lập MySQL và MSSQL lần đầu</h1><p>Chỉ thực hiện một lần. Game server chưa tự khởi động sau bước này.</p>{% if has_credentials %}<p class="hint">Đã lưu mật khẩu từ lần chạy trước. Nếu trước đó bị lỗi, để trống tất cả ô và bấm <b>Thử lại thiết lập</b>.</p>{% endif %}<form id="setupForm" method="post"><input type="hidden" name="csrf_token" value="{{csrf}}"><div class="grid"><div class="db"><h2>MySQL — dữ liệu đăng nhập</h2><p>Mật khẩu tài khoản root dùng bởi Web, backup và Goddess.</p><label>Mật khẩu mới<input type="password" name="mysql_password" autocomplete="new-password" {{'' if has_credentials else 'required'}}></label><label>Nhập lại<input type="password" name="mysql_confirm" autocomplete="new-password" {{'' if has_credentials else 'required'}}></label></div><div class="db"><h2>MSSQL — dữ liệu nhân vật</h2><p>Mật khẩu tài khoản sa dùng bởi Web, backup và PaySys native.</p><label>Mật khẩu mới<input type="password" name="mssql_password" autocomplete="new-password" {{'' if has_credentials else 'required'}}></label><label>Nhập lại<input type="password" name="mssql_confirm" autocomplete="new-password" {{'' if has_credentials else 'required'}}></label></div></div><div class="tools"><span class="hint">12–20 ký tự; có hoa, thường, số và @ _ ! . hoặc -</span><div><button type="button" class="secondary" id="generatePasswords">Tạo 2 mật khẩu mạnh</button> <button id="startSetup">{{'Thử lại thiết lập' if has_credentials else 'Bắt đầu cài database'}}</button></div></div></form><div class="progress" id="progressBox" hidden><div class="progress-head"><b id="phase">Đang chuẩn bị</b><span id="percent">0%</span></div><div class="bar"><i id="bar"></i></div><p class="message" id="message"></p><a class="enter" id="enter" href="{{url_for('dashboard')}}">Vào bảng điều khiển</a></div></section></main><script>
(function(){const form=document.getElementById('setupForm'),box=document.getElementById('progressBox'),phase=document.getElementById('phase'),percent=document.getElementById('percent'),bar=document.getElementById('bar'),message=document.getElementById('message'),start=document.getElementById('startSetup'),enter=document.getElementById('enter');function makePassword(){const lower='abcdefghijkmnopqrstuvwxyz',upper='ABCDEFGHJKLMNPQRSTUVWXYZ',digits='23456789',symbols='@_!-',all=lower+upper+digits+symbols,a=[lower,upper,digits,symbols].map(s=>s[crypto.getRandomValues(new Uint32Array(1))[0]%s.length]);while(a.length<16)a.push(all[crypto.getRandomValues(new Uint32Array(1))[0]%all.length]);for(let i=a.length-1;i>0;i--){const j=crypto.getRandomValues(new Uint32Array(1))[0]%(i+1);[a[i],a[j]]=[a[j],a[i]]}return a.join('')}document.getElementById('generatePasswords').addEventListener('click',()=>{const one=makePassword(),two=makePassword();form.mysql_password.value=form.mysql_confirm.value=one;form.mssql_password.value=form.mssql_confirm.value=two});async function poll(){try{const response=await fetch('{{url_for("manager_ext.database_job_status")}}',{cache:'no-store'}),data=await response.json();box.hidden=false;box.className='progress '+(data.state||'');phase.textContent=data.phase||'Đang xử lý';percent.textContent=(data.percent||0)+'%';bar.style.width=(data.percent||0)+'%';message.textContent=data.message||'';if(data.state==='done'){enter.classList.add('show');start.disabled=false;return}if(data.state==='error'){start.disabled=false;return}setTimeout(poll,1000)}catch(error){message.textContent='Mất kết nối tạm thời, đang thử lại…';setTimeout(poll,1800)}}form.addEventListener('submit',async event=>{event.preventDefault();start.disabled=true;box.hidden=false;box.className='progress';phase.textContent='Đang gửi yêu cầu';message.textContent='';try{const response=await fetch(form.action||location.href,{method:'POST',body:new FormData(form),headers:{'X-Requested-With':'XMLHttpRequest'}}),data=await response.json();if(!response.ok)throw new Error(data.error||'Không bắt đầu được thiết lập');poll()}catch(error){box.className='progress error';phase.textContent='Chưa thể bắt đầu';message.textContent=error.message;start.disabled=false}});{% if job_available %}poll();{% endif %}})();
</script></body></html>
"""

FIRST_RUN_DATABASE_PAGE = FIRST_RUN_DATABASE_PAGE.replace(
    '<button type="button" class="secondary" id="generatePasswords">Tạo 2 mật khẩu mạnh</button>',
    '<button type="button" class="secondary" id="generatePasswords">Tạo 2 mật khẩu mạnh</button> '
    '<button type="button" class="secondary" id="toggleGeneratedPasswords">Hiện mật khẩu</button> '
    '<button type="button" class="secondary" id="copyGeneratedPasswords" disabled>Chép cả hai</button>',
).replace(
    "form.mysql_password.value=form.mysql_confirm.value=one;form.mssql_password.value=form.mssql_confirm.value=two",
    "form.mysql_password.value=form.mysql_confirm.value=one;form.mssql_password.value=form.mssql_confirm.value=two;document.getElementById('copyGeneratedPasswords').disabled=false",
).replace(
    "async function poll(){",
    "document.getElementById('toggleGeneratedPasswords').addEventListener('click',function(){const visible=form.mysql_password.type==='text';[form.mysql_password,form.mysql_confirm,form.mssql_password,form.mssql_confirm].forEach(input=>input.type=visible?'password':'text');this.textContent=visible?'Hiện mật khẩu':'Ẩn mật khẩu'});document.getElementById('copyGeneratedPasswords').addEventListener('click',async function(){await navigator.clipboard.writeText('MySQL root: '+form.mysql_password.value+'\\nMSSQL sa: '+form.mssql_password.value);this.textContent='✓ Đã chép';setTimeout(()=>this.textContent='Chép cả hai',1500)});async function poll(){",
).replace(
    'h1{font:700 25px Georgia,serif;margin:0 0 6px;color:#f0d9aa}',
    'h1{font:750 25px Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;margin:0 0 6px;color:#f0d9aa}',
)


def _manager_page(body, page, **context):
    return current_app.extensions["render_manager_page"](body, page=page, **context)


def _login_security_page_data():
    snapshot = LOGIN_SECURITY.snapshot(audit_limit=50)
    entries = []
    for row in snapshot["entries"]:
        entries.append({
            **row,
            "remaining_text": format_duration(row["remaining"]),
            "last_failure_text": format_timestamp(row["last_failure"]),
        })
    event_info = {
        "success": ("Đăng nhập thành công", "event-ok"),
        "failure": ("Sai tài khoản/mật khẩu", "event-warn"),
        "locked": ("Sai 3 lần — đã khóa", "event-bad"),
        "blocked": ("Chặn khi đang khóa", "event-bad"),
        "csrf_invalid": ("Biểu mẫu không hợp lệ", "event-warn"),
        "unlocked": ("Admin mở khóa", "event-ok"),
        "unlock_all": ("Mở khóa tất cả", "event-ok"),
    }
    audit = []
    for row in snapshot["audit"]:
        label, css = event_info.get(row.get("event"), (row.get("event") or "Không rõ", ""))
        detail = row.get("detail", "")
        if row.get("event") == "unlocked" and "source=ssh" in detail:
            label = "Mở khóa qua SSH"
        elif row.get("event") == "unlocked" and "source=web" in detail:
            label = "Mở khóa trên Web"
        audit.append({**row, "time_text": format_timestamp(row.get("time")), "label": label, "css": css})
    last_success = snapshot.get("last_success") or {}
    return {
        "security_entries": entries,
        "security_audit": audit,
        "last_success_ip": last_success.get("ip") or "—",
        "last_success_time": format_timestamp(last_success.get("time")),
    }


def register_manager_extensions(app):
    blueprint = Blueprint("manager_ext", __name__)

    @app.before_request
    def protect_manager():
        endpoint = request.endpoint or ""
        allowed = {"manager_ext.login", "manager_ext.change_password"}
        if endpoint in allowed:
            return None
        if not _logged_in():
            next_path = (request.script_root or "") + request.full_path
            return redirect(url_for("manager_ext.login", next=next_path))
        auth = _load_auth()
        if auth.get("must_change"):
            return redirect(url_for("manager_ext.change_password"))
        setup_allowed = {"manager_ext.first_run_database", "manager_ext.database_job_status"}
        if not _database_setup_complete() and endpoint not in setup_allowed:
            return redirect(url_for("manager_ext.first_run_database"))
        return None

    @blueprint.route("/login", methods=["GET", "POST"])
    def login():
        auth = _load_auth()
        if request.method == "POST":
            client_ip = LOGIN_SECURITY.normalize_ip(request.remote_addr)
            submitted_username = request.form.get("username", "")
            lock_status = LOGIN_SECURITY.status(client_ip)
            if lock_status["locked"]:
                LOGIN_SECURITY.record_blocked(client_ip, submitted_username)
                flash("IP này đang bị khóa. Thử lại sau " + format_duration(lock_status["remaining"]) + ".")
            elif not _valid_csrf():
                LOGIN_SECURITY.record_csrf_failure(client_ip, submitted_username)
                flash("Phiên đăng nhập không hợp lệ")
            else:
                username_ok = hmac.compare_digest(submitted_username, auth["username"])
                password_ok = check_password_hash(auth["password_hash"], request.form.get("password", ""))
                if username_ok and password_ok:
                    LOGIN_SECURITY.record_success(client_ip, submitted_username)
                    session.clear()
                    session["manager_authenticated"] = True
                    session["manager_username"] = auth.get("username", "admin")
                    session["csrf_token"] = secrets.token_urlsafe(32)
                    session["manager_login_ip"] = client_ip
                    session["manager_login_at"] = int(time.time())
                    if auth.get("must_change"):
                        return redirect(url_for("manager_ext.change_password"))
                    if not _database_setup_complete():
                        return redirect(url_for("manager_ext.first_run_database"))
                    return redirect(_safe_next(request.args.get("next")) or url_for("dashboard"))
                failure = LOGIN_SECURITY.record_failure(client_ip, submitted_username)
                if failure["locked"]:
                    flash("Sai 3 lần. IP đã bị khóa " + format_duration(failure["remaining"]) + ".")
                else:
                    flash("Sai tài khoản hoặc mật khẩu")
        first_login = bool(auth.get("must_change"))
        return render_template_string(
            LOGIN_PAGE,
            csrf=_csrf_token(),
            first_login=first_login,
            default_user=auth.get("username", os.environ.get("MANAGER_DEFAULT_USER", "admin")),
            default_password=os.environ.get("MANAGER_DEFAULT_PASSWORD", "admin123") if first_login else "",
        )

    @blueprint.route("/change-password", methods=["GET", "POST"])
    def change_password():
        if not _logged_in():
            return redirect(url_for("manager_ext.login"))
        error = ""
        if request.method == "POST":
            new_password = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not _valid_csrf():
                error = "Phiên không hợp lệ"
            elif len(new_password) < 8:
                error = "Mật khẩu cần ít nhất 8 ký tự"
            elif new_password != confirm:
                error = "Hai mật khẩu không giống nhau"
            else:
                auth = _load_auth()
                auth["password_hash"] = generate_password_hash(new_password)
                auth["must_change"] = False
                _save_auth(auth)
                return redirect(url_for("manager_ext.first_run_database")
                                if not _database_setup_complete() else url_for("manager_ext.setup"))
        return render_template_string("""<!doctype html><html lang=vi><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Đặt mật khẩu JXNative</title><style>*{box-sizing:border-box}body{font:15px/1.5 Inter,system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;padding:24px;background:radial-gradient(circle at 70% 0,rgba(201,164,95,.16),transparent 30rem),#090705;color:#e8dfd1}.box{width:min(420px,100%);padding:28px;border:1px solid #443426;border-radius:14px;background:linear-gradient(180deg,#1a140f,#110d0a);box-shadow:0 28px 80px rgba(0,0,0,.48)}h1{margin:0 0 6px;color:#f0d9aa;font:700 22px Georgia,serif}p{color:#9f9180}.err{color:#ef8078}label{display:block;margin-top:12px;color:#b8aa99;font-size:12px}input,button{width:100%;padding:11px 12px;margin-top:5px;border-radius:7px;font:inherit}input{border:1px solid #4a392b;background:#0d0a08;color:#fff}input:focus{outline:0;border-color:#c9a45f;box-shadow:0 0 0 3px rgba(201,164,95,.12)}button{margin-top:18px;border:1px solid #c0974d;background:#9d7838;color:#fff8e9;font-weight:750;cursor:pointer}</style></head><body><main class=box><h1>Đặt mật khẩu quản trị</h1><p>Đăng nhập lần đầu thành công. Hãy tạo mật khẩu riêng có ít nhất 8 ký tự.</p>{% if error %}<p class=err>{{ error }}</p>{% endif %}<form method=post><input type=hidden name=csrf_token value="{{ csrf }}"><label>Mật khẩu mới<input type=password name=new_password autocomplete=new-password required minlength=8></label><label>Nhập lại mật khẩu<input type=password name=confirm_password autocomplete=new-password required minlength=8></label><button>Lưu mật khẩu mới</button></form></main></body></html>""", error=error, csrf=_csrf_token())

    @blueprint.route("/first-run/database", methods=["GET", "POST"])
    def first_run_database():
        if _database_setup_complete():
            return redirect(url_for("dashboard"))
        existing_mysql, existing_mssql = _database_passwords()
        if request.method == "POST":
            if not _valid_csrf():
                return jsonify({"error": "Phiên biểu mẫu không hợp lệ"}), 400
            job = _read_json(DATABASE_JOB_FILE)
            if job.get("state") == "working" and time.time() - int(job.get("updated", 0)) < 3600:
                return jsonify({"error": "Một tiến trình thiết lập đang chạy"}), 409
            mysql_password = request.form.get("mysql_password", "")
            mysql_confirm = request.form.get("mysql_confirm", "")
            mssql_password = request.form.get("mssql_password", "")
            mssql_confirm = request.form.get("mssql_confirm", "")
            if not any((mysql_password, mysql_confirm, mssql_password, mssql_confirm)):
                mysql_password, mssql_password = existing_mysql, existing_mssql
            elif mysql_password != mysql_confirm or mssql_password != mssql_confirm:
                return jsonify({"error": "Phần nhập lại mật khẩu không khớp"}), 400
            try:
                validate_database_password(mysql_password, "Mật khẩu MySQL")
                validate_database_password(mssql_password, "Mật khẩu MSSQL")
                if mysql_password == mssql_password:
                    raise ValueError("MySQL và MSSQL phải dùng hai mật khẩu khác nhau")
                if existing_mysql and existing_mssql and (
                    mysql_password != existing_mysql or mssql_password != existing_mssql
                ):
                    raise ValueError("Thiết lập trước đã lưu mật khẩu; hãy để trống để thử lại đúng mật khẩu đó")
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            _write_database_job("initial", "working", 1, "Bắt đầu", "Đã nhận yêu cầu thiết lập")
            app_object = current_app._get_current_object()
            threading.Thread(target=_initial_database_worker,
                             args=(app_object, mysql_password, mssql_password),
                             daemon=True, name="jx-database-initial-setup").start()
            return jsonify({"ok": True}), 202
        job = _read_json(DATABASE_JOB_FILE)
        return render_template_string(
            FIRST_RUN_DATABASE_PAGE,
            csrf=_csrf_token(),
            has_credentials=bool(existing_mysql and existing_mssql),
            job_available=job.get("mode") == "initial" and job.get("state") in ("working", "error"),
        )

    @blueprint.get("/database-job/status")
    def database_job_status():
        job = _read_json(DATABASE_JOB_FILE, {
            "state": "idle", "percent": 0, "phase": "Chưa bắt đầu", "message": ""
        })
        return jsonify(job)

    @blueprint.post("/server-setup/database-password")
    def rotate_database_passwords():
        if not _valid_csrf():
            return jsonify({"error": "Phiên biểu mẫu không hợp lệ"}), 400
        auth = _load_auth()
        if not check_password_hash(auth["password_hash"], request.form.get("admin_password", "")):
            return jsonify({"error": "Mật khẩu Admin hiện tại không đúng"}), 403
        mysql_password = request.form.get("mysql_password", "")
        mssql_password = request.form.get("mssql_password", "")
        try:
            if mysql_password != request.form.get("mysql_confirm", ""):
                raise ValueError("Nhập lại mật khẩu MySQL không khớp")
            if mssql_password != request.form.get("mssql_confirm", ""):
                raise ValueError("Nhập lại mật khẩu MSSQL không khớp")
            validate_database_password(mysql_password, "Mật khẩu MySQL")
            validate_database_password(mssql_password, "Mật khẩu MSSQL")
            if mysql_password == mssql_password:
                raise ValueError("MySQL và MSSQL phải dùng hai mật khẩu khác nhau")
            current_mysql, current_mssql = _database_passwords()
            if mysql_password == current_mysql or mssql_password == current_mssql:
                raise ValueError("Mỗi mật khẩu mới phải khác mật khẩu hiện tại")
            job = _read_json(DATABASE_JOB_FILE)
            if job.get("state") == "working" and time.time() - int(job.get("updated", 0)) < 3600:
                raise ValueError("Một tiến trình database đang chạy")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        running = [unit for unit in GAME_UNITS if _unit_active(unit)]
        stop_requested = request.form.get("stop_server") == "1"
        if running and not stop_requested:
            return jsonify({
                "error": "Server đang chạy. Cần Stop All an toàn trước khi đổi mật khẩu.",
                "requires_stop": True,
                "running": running,
            }), 409
        _write_database_job("rotate", "working", 1, "Bắt đầu", "Đã nhận yêu cầu đổi mật khẩu")
        app_object = current_app._get_current_object()
        threading.Thread(target=_rotate_database_worker,
                         args=(app_object, mysql_password, mssql_password, stop_requested),
                         daemon=True, name="jx-database-password-rotation").start()
        return jsonify({"ok": True}), 202

    @blueprint.post("/server-setup/database-password/reveal")
    def reveal_database_passwords():
        if not _valid_csrf():
            return jsonify({"error": "Phiên biểu mẫu không hợp lệ"}), 400
        auth = _load_auth()
        if not check_password_hash(auth["password_hash"], request.form.get("admin_password", "")):
            return jsonify({"error": "Mật khẩu Admin hiện tại không đúng"}), 403
        mysql_password, mssql_password = _database_passwords()
        if not mysql_password or not mssql_password:
            return jsonify({"error": "Chưa tìm thấy mật khẩu database trong cấu hình"}), 404
        response = jsonify({"mysql": mysql_password, "mssql": mssql_password, "expires_in": 30})
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @blueprint.route("/account-settings", methods=["GET", "POST"])
    def account_settings():
        auth = _load_auth()
        error = ""
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_username = request.form.get("new_username", "").strip()
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if not _valid_csrf():
                error = "Phiên biểu mẫu không hợp lệ"
            elif not check_password_hash(auth["password_hash"], current_password):
                error = "Mật khẩu hiện tại không đúng"
            elif not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", new_username):
                error = "Tên tài khoản chỉ dùng chữ, số, dấu chấm, gạch ngang hoặc gạch dưới"
            elif new_password and len(new_password) < 8:
                error = "Mật khẩu mới cần ít nhất 8 ký tự"
            elif new_password != confirm_password:
                error = "Hai mật khẩu mới không giống nhau"
            else:
                auth["username"] = new_username
                if new_password:
                    auth["password_hash"] = generate_password_hash(new_password)
                auth["must_change"] = False
                _save_auth(auth)
                session.clear()
                flash("Đã đổi tài khoản quản trị. Hãy đăng nhập lại.")
                return redirect(url_for("manager_ext.login"))
        security_context = _login_security_page_data()
        return _manager_page(
            ACCOUNT_SETTINGS_PAGE,
            "account_settings",
            username=auth["username"],
            error=error,
            csrf=_csrf_token(),
            current_ip=session.get("manager_login_ip") or LOGIN_SECURITY.normalize_ip(request.remote_addr),
            **security_context,
        )

    @blueprint.post("/account-settings/login-security/unlock")
    def unlock_login_ip():
        if not _valid_csrf():
            flash("Phiên biểu mẫu không hợp lệ")
            return redirect(url_for("manager_ext.account_settings"))
        try:
            ip = LOGIN_SECURITY.normalize_ip(request.form.get("ip", ""))
            if ip == "unknown":
                raise ValueError("Địa chỉ IP không hợp lệ")
            LOGIN_SECURITY.unlock(ip, source="web")
            flash("Đã mở khóa và đặt lại IP " + ip)
        except ValueError as exc:
            flash(str(exc))
        return redirect(url_for("manager_ext.account_settings"))

    @blueprint.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("manager_ext.login"))

    @blueprint.route("/server-setup")
    def setup():
        active_tab = request.args.get("tab", "versions")
        if active_tab not in ("versions", "logs"):
            active_tab = "versions"
        log_view = request.args.get("view", "viewer")
        if log_view not in ("viewer", "storage"):
            log_view = "viewer"
        SERVERS_ROOT.mkdir(parents=True, exist_ok=True)
        active = _active_server()
        selections = _load_server_selections()
        servers = []
        for path in sorted((entry for entry in SERVERS_ROOT.iterdir() if entry.is_dir()), key=lambda item: item.name.lower()):
            selected_path = selections.get(path.name, "")
            is_active = bool(active and (active == path.resolve() or path.resolve() in active.parents))
            if is_active:
                selected_path = active.relative_to(path.resolve()).as_posix()
                selected_path = "." if selected_path == "." else selected_path
            elif not selected_path and _server_root_from_selection(path, ".") is not None:
                selected_path = "."
            selected_root = _server_root_from_selection(path, selected_path)
            missing = ([relative for relative in SERVER_BINARIES if not (selected_root / relative).is_file()]
                       if selected_root else ["gateway/", "server1/"])
            servers.append({
                "name": path.name,
                "candidates": [],
                "selected_path": selected_path,
                "missing": missing,
                "active": is_active,
            })
        # Dung lượng log có thể phải đi qua hàng nghìn file. Chỉ tính khi người dùng
        # thực sự mở màn hình quản lý dung lượng, không làm chậm tab phiên bản/xem log.
        needs_storage = active_tab == "logs" and log_view == "storage"
        game_logs = _game_log_rows() if active and needs_storage else []
        system_logs = _system_log_summary() if needs_storage else {
            "persistent": {"bytes": 0, "size": "—"},
            "runtime": {"bytes": 0, "size": "—"},
            "jx_runtime": {"bytes": 0, "size": "—"},
            "state": {"files": 0, "bytes": 0, "size": "—"},
            "docker": [],
        }
        journal_bytes = system_logs["persistent"]["bytes"] + system_logs["runtime"]["bytes"]
        try:
            disk_free = _format_size(shutil.disk_usage(PROJECT_ROOT).free)
        except OSError:
            disk_free = "Không xác định"
        return _manager_page(
            SETUP_PAGE,
            "server_setup",
            servers=servers,
            active_name=active.relative_to(SERVERS_ROOT.resolve()).parts[0] if active else None,
            active_path=str(active) if active else None,
            current_ip=_read_server_ip(active),
            addresses=_network_addresses() if active_tab == "versions" else [],
            game_logs=game_logs,
            game_log_size=(_format_size(sum(row["bytes"] for row in game_logs))
                           if needs_storage else "Chưa tải"),
            journal_size=_format_size(journal_bytes) if needs_storage else "Chưa tải",
            disk_free=disk_free,
            system_logs=system_logs,
            journal_needs_cleanup=journal_bytes > 100 * 1024 * 1024,
            history_log_sources=(("all", "Tất cả JXNative"), ("jxpaysys", "PaySys"),
                                 ("jxrelaypay", "RelayPay"), ("jxgoddess", "Goddess"),
                                 ("jxbishop", "Bishop"), ("jxs3relay", "S3Relay"),
                                 ("jxgame", "GameServer"), ("mssql", "MSSQL"), ("mysql", "MySQL")),
            active_tab=active_tab,
            log_view=log_view,
            csrf=_csrf_token(),
        )

    @blueprint.route("/server-setup/folders")
    def browse_folders():
        mode = request.args.get("mode", "")
        relative = request.args.get("path", "")
        try:
            if mode == "server":
                server_name = request.args.get("server_name", "")
                if not SERVER_NAME_RE.fullmatch(server_name):
                    raise ValueError("Tên phiên bản không hợp lệ")
                root = SERVERS_ROOT / server_name
                if not root.is_dir() or root.is_symlink():
                    raise ValueError("Phiên bản không tồn tại")
                result = _browse_directory_rows(root, relative)
                result.update(mode="server", root_label="/JX_Servers/JX_Versions/" + server_name)
            elif mode == "logs":
                root = _active_server()
                if root is None:
                    raise ValueError("Chưa có server đang sử dụng")
                result = _browse_directory_rows(root, relative)
                result.update(mode="logs", root_label="Server đang sử dụng")
            else:
                raise ValueError("Chế độ duyệt thư mục không hợp lệ")
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @blueprint.route("/server-setup/upload", methods=["POST"])
    def upload():
        wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        job_id = (request.form.get("job_id") or "").strip().lower()
        if not IMPORT_JOB_RE.fullmatch(job_id):
            job_id = secrets.token_hex(16)

        def finish(ok, message, status=200):
            _write_import_job(job_id, "done" if ok else "error", "Hoàn tất" if ok else "Lỗi", 100 if ok else 0, message)
            if wants_json:
                return jsonify({"ok": ok, "message": message, "job_id": job_id}), status
            flash(message, "ok" if ok else "err")
            return redirect(url_for("manager_ext.setup"))

        if not _valid_csrf():
            return finish(False, "Phiên không hợp lệ", 400)
        server_name = request.form.get("server_name", "").strip()
        uploaded = request.files.get("archive")
        if not SERVER_NAME_RE.fullmatch(server_name):
            return finish(False, "Tên phiên bản chỉ được dùng chữ, số, dấu chấm, gạch ngang hoặc gạch dưới", 400)
        if not uploaded or not uploaded.filename.lower().endswith(ALLOWED_SUFFIXES):
            return finish(False, "Chỉ nhận .zip, .tgz hoặc .tar.gz", 400)
        destination = SERVERS_ROOT / server_name
        if destination.exists():
            return finish(False, "Tên phiên bản đã tồn tại", 409)
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        SERVERS_ROOT.mkdir(parents=True, exist_ok=True)
        _prune_import_jobs()
        try:
            with tempfile.TemporaryDirectory(dir=str(UPLOAD_ROOT)) as temp_dir:
                temp_root = Path(temp_dir)
                archive_path = temp_root / Path(uploaded.filename).name
                extract_root = temp_root / "extract"
                extract_root.mkdir()
                _write_import_job(job_id, "working", "Lưu file tải lên", 0, "Máy chủ đang nhận file")
                uploaded.save(archive_path)
                _write_import_job(job_id, "working", "Kiểm tra file nén", 0, "Đang kiểm tra cấu trúc và đường dẫn an toàn")
                _extract_archive(
                    archive_path,
                    extract_root,
                    lambda percent, current, total: _write_import_job(
                        job_id, "working", "Giải nén", percent,
                        "Đã xử lý %d/%d mục" % (current, total),
                    ),
                )
                _write_import_job(job_id, "working", "Kiểm tra server", 100, "Đang tìm gateway/ và server1/")
                shutil.move(str(extract_root), str(destination))
                candidates = _finalize_imported_server(server_name, destination)
            if not candidates:
                return finish(False, "Đã giải nén nhưng chưa tìm thấy thư mục có đủ gateway/ và server1/. Bạn có thể xóa phiên bản và upload lại.", 422)
            elif len(candidates) == 1:
                return finish(True, "Đã upload, giải nén và tự chọn đường dẫn server hợp lệ: " + candidates[0][0])
            else:
                return finish(True, "Đã upload và giải nén. Tìm thấy %d đường dẫn hợp lệ; hãy chọn đường dẫn cần chạy." % len(candidates))
        except Exception as exc:
            shutil.rmtree(destination, ignore_errors=True)
            return finish(False, "Upload thất bại: " + str(exc), 400)

    @blueprint.get("/server-setup/upload-status/<job_id>")
    def upload_status(job_id):
        if not IMPORT_JOB_RE.fullmatch(job_id or ""):
            return jsonify({"state": "error", "phase": "Lỗi", "percent": 0, "message": "Mã tiến trình không hợp lệ"}), 400
        try:
            payload = json.loads(_import_job_path(job_id).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            return jsonify(payload)
        except (OSError, ValueError):
            return jsonify({"state": "waiting", "phase": "Đang nhận file", "percent": 0, "message": "Chờ tải file hoàn tất"})

    @blueprint.route("/server-setup/github", methods=["POST"])
    def clone_github():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        server_name = request.form.get("server_name", "").strip()
        github_url = request.form.get("github_url", "").strip()
        branch = request.form.get("branch", "").strip()
        destination = SERVERS_ROOT / server_name
        if not SERVER_NAME_RE.fullmatch(server_name):
            flash("Tên phiên bản chỉ được dùng chữ, số, dấu chấm, gạch ngang hoặc gạch dưới", "err")
        elif not GITHUB_URL_RE.fullmatch(github_url):
            flash("Chỉ nhận link repository công khai dạng https://github.com/tai-khoan/repository", "err")
        elif branch and (not GIT_BRANCH_RE.fullmatch(branch) or ".." in branch or "//" in branch or branch.endswith(("/", ".lock"))):
            flash("Tên branch GitHub không hợp lệ", "err")
        elif destination.exists():
            flash("Tên phiên bản đã tồn tại", "err")
        elif not shutil.which("git"):
            flash("Máy chưa cài Git. Hãy chạy: sudo apt install git", "err")
        else:
            SERVERS_ROOT.mkdir(parents=True, exist_ok=True)
            command = ["git", "clone", "--depth", "1", "--single-branch"]
            if branch:
                command.extend(["--branch", branch])
            command.extend([github_url, str(destination)])
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=280, check=False)
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout or "git clone thất bại").strip()[-800:]
                    raise RuntimeError(detail)
                shutil.rmtree(destination / ".git", ignore_errors=True)
                candidates = _finalize_imported_server(server_name, destination)
                if not candidates:
                    flash("Đã tải repository nhưng không tìm thấy thư mục có đủ gateway/ và server1/", "err")
                elif len(candidates) == 1:
                    flash("Đã tải GitHub và tự chọn đường dẫn: " + candidates[0][0], "ok")
                else:
                    flash("Đã tải GitHub. Tìm thấy %d đường dẫn hợp lệ; hãy chọn đường dẫn cần chạy." % len(candidates), "ok")
            except subprocess.TimeoutExpired:
                shutil.rmtree(destination, ignore_errors=True)
                flash("Tải GitHub quá 280 giây nên đã dừng", "err")
            except Exception as exc:
                shutil.rmtree(destination, ignore_errors=True)
                flash("Không tải được GitHub: " + str(exc), "err")
        return redirect(url_for("manager_ext.setup"))

    @blueprint.route("/server-setup/activate", methods=["POST"])
    def activate():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        server_name = request.form.get("server_name", "")
        target = _selected_server_root(server_name)
        missing = [relative for relative in SERVER_BINARIES if target and not (target / relative).is_file()]
        if target is None:
            flash("Hãy chọn đường dẫn có đủ gateway/ và server1/", "err")
        elif missing:
            flash("Đường dẫn còn thiếu binary bắt buộc: " + ", ".join(missing), "err")
        elif any(_unit_active(unit) for unit in GAME_UNITS):
            flash("Hãy tắt TẤT CẢ dịch vụ JX trước khi đổi phiên bản", "err")
        else:
            selected_ip = _preferred_server_ip(_active_server())
            if not selected_ip:
                flash("Không phát hiện được IP LAN/ZeroTier để cấu hình server", "err")
            else:
                _mark_binaries_executable(target)
                changed = _update_server_ip(target, selected_ip)
                mysql_password, mssql_password = _database_passwords()
                credential_changes = 0
                if mysql_password and mssql_password:
                    credential_changes, _ = patch_server_credentials(
                        target, mysql_password, mssql_password
                    )
                temporary_link = PROJECT_ROOT / (".active-" + secrets.token_hex(6))
                temporary_link.symlink_to(target)
                os.replace(temporary_link, ACTIVE_LINK)
                flash(
                    "Đã kích hoạt %s, áp dụng IP %s vào %d file và đồng bộ %d trường mật khẩu database"
                    % (server_name, selected_ip, len(changed), credential_changes),
                    "ok",
                )
        next_path = request.form.get("next", "")
        return redirect(next_path if next_path.startswith("/") and not next_path.startswith("//") else url_for("manager_ext.setup"))

    @blueprint.route("/server-setup/path", methods=["POST"])
    def select_server_path():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        server_name = request.form.get("server_name", "")
        selected_path = request.form.get("server_path", "")
        version_root = SERVERS_ROOT / server_name
        selected_root = (_server_root_from_selection(version_root, selected_path)
                         if SERVER_NAME_RE.fullmatch(server_name) and version_root.is_dir() else None)
        active = _active_server()
        if active and version_root.is_dir() and (active == version_root.resolve() or version_root.resolve() in active.parents):
            flash("Không thể đổi đường dẫn của phiên bản đang sử dụng", "err")
        elif selected_root is None:
            flash("Chỉ được chọn thư mục có đủ gateway/ và server1/", "err")
        else:
            selections = _load_server_selections()
            selections[server_name] = selected_path
            _save_server_selections(selections)
            _mark_binaries_executable(selected_root)
            flash("Đã chọn đường dẫn /JX_Servers/JX_Versions/%s%s" % (server_name, "" if selected_path == "." else "/" + selected_path), "ok")
        return redirect(url_for("manager_ext.setup"))

    @blueprint.route("/server-setup/rename", methods=["POST"])
    def rename_server():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        server_name = request.form.get("server_name", "")
        new_name = request.form.get("new_name", "").strip()
        source = SERVERS_ROOT / server_name
        destination = SERVERS_ROOT / new_name
        active = _active_server()
        if not SERVER_NAME_RE.fullmatch(server_name) or not source.is_dir() or not SERVER_NAME_RE.fullmatch(new_name):
            flash("Tên phiên bản không hợp lệ", "err")
        elif active and (active == source.resolve() or source.resolve() in active.parents):
            flash("Không thể đổi tên phiên bản đang sử dụng", "err")
        elif destination.exists():
            flash("Tên phiên bản mới đã tồn tại", "err")
        elif new_name == server_name:
            flash("Tên phiên bản chưa thay đổi", "err")
        else:
            source.rename(destination)
            selections = _load_server_selections()
            if server_name in selections:
                selections[new_name] = selections.pop(server_name)
                _save_server_selections(selections)
            flash("Đã đổi tên %s thành %s" % (server_name, new_name), "ok")
        return redirect(url_for("manager_ext.setup"))

    @blueprint.route("/server-setup/delete", methods=["POST"])
    def delete_server():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        server_name = request.form.get("server_name", "")
        target = SERVERS_ROOT / server_name
        active = _active_server()
        if not SERVER_NAME_RE.fullmatch(server_name) or not target.is_dir():
            flash("Phiên bản không hợp lệ", "err")
        elif active and (active == target.resolve() or target.resolve() in active.parents):
            flash("Không thể xóa phiên bản đang sử dụng", "err")
        elif any(_unit_active(unit) for unit in GAME_UNITS):
            flash("Hãy tắt tất cả dịch vụ JX trước khi xóa phiên bản", "err")
        else:
            trash = STATE_ROOT / "server-trash"
            trash.mkdir(parents=True, exist_ok=True)
            destination = trash / (server_name + "-" + secrets.token_hex(4))
            shutil.move(str(target), str(destination))
            selections = _load_server_selections()
            if selections.pop(server_name, None) is not None:
                _save_server_selections(selections)
            flash("Đã chuyển phiên bản " + server_name + " vào thùng rác", "ok")
        return redirect(url_for("manager_ext.setup"))

    @blueprint.route("/server-setup/ip", methods=["POST"])
    def set_ip():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        active = _active_server()
        value = (request.form.get("manual_ip") or request.form.get("selected_ip") or "").strip()
        if active is None:
            flash("Chưa chọn server", "err")
        else:
            try:
                changed = _update_server_ip(active, value)
                flash("Đã cập nhật IP %s trong %d file" % (value, len(changed)), "ok")
            except Exception as exc:
                flash("Không cập nhật được IP: " + str(exc), "err")
        return redirect(url_for("manager_ext.setup"))

    @blueprint.route("/server-setup/logs/game/add", methods=["POST"])
    def add_game_log_path():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        try:
            relative = _normalize_log_relative(request.form.get("path", ""))
            _active_log_path(relative, require_exists=True)
            defaults = {path for path, _label in DEFAULT_GAME_LOG_DIRS}
            custom = _load_custom_log_directories()
            normalized_custom = []
            for value in custom:
                try:
                    normalized_custom.append(_normalize_log_relative(value))
                except ValueError:
                    continue
            if relative in defaults or relative in normalized_custom:
                raise ValueError("Thư mục này đã có trong danh sách")
            normalized_custom.append(relative)
            _save_custom_log_directories(normalized_custom)
            flash("Đã thêm thư mục log: " + relative, "ok")
        except Exception as exc:
            flash("Không thêm được thư mục log: " + str(exc), "err")
        return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")

    @blueprint.route("/server-setup/logs/game/remove", methods=["POST"])
    def remove_game_log_path():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        try:
            relative = _normalize_log_relative(request.form.get("path", ""))
            custom = []
            found = False
            for value in _load_custom_log_directories():
                try:
                    normalized = _normalize_log_relative(value)
                except ValueError:
                    continue
                if normalized == relative:
                    found = True
                else:
                    custom.append(normalized)
            if not found:
                raise ValueError("Chỉ có thể bỏ đường dẫn tùy chỉnh")
            _save_custom_log_directories(custom)
            flash("Đã bỏ khỏi danh sách; không xóa thư mục hay file: " + relative, "ok")
        except Exception as exc:
            flash("Không bỏ được đường dẫn: " + str(exc), "err")
        return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")

    @blueprint.route("/server-setup/logs/game/delete", methods=["POST"])
    def delete_game_log():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        try:
            relative = _normalize_log_relative(request.form.get("path", ""))
            allowed = {path for path, _label, _custom in _configured_game_log_directories()}
            if relative not in allowed:
                raise ValueError("Đường dẫn không có trong danh sách quản lý")
            path = _active_log_path(relative, require_exists=True)
            removed, released, errors = _delete_directory_files(path)
            message = "Đã xóa %d file trong %s, giải phóng %s." % (removed, relative, _format_size(released))
            if errors:
                flash(message + " Một số file lỗi: " + "; ".join(errors[:3]), "err")
            else:
                flash(message, "ok")
        except Exception as exc:
            flash("Không xóa được log game: " + str(exc), "err")
        return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")

    @blueprint.route("/server-setup/logs/game/delete-all", methods=["POST"])
    def delete_all_game_logs():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        removed = 0
        released = 0
        errors = []
        try:
            for relative, _label, _custom in _configured_game_log_directories():
                try:
                    path = _active_log_path(relative, require_exists=True)
                except ValueError:
                    continue
                count, size, current_errors = _delete_directory_files(path)
                removed += count
                released += size
                errors.extend(current_errors)
            message = "Đã xóa %d file trong tất cả thư mục log game, giải phóng %s." % (removed, _format_size(released))
            flash(message + ((" Lỗi: " + "; ".join(errors[:3])) if errors else ""), "err" if errors else "ok")
        except Exception as exc:
            flash("Không xóa được toàn bộ log game: " + str(exc), "err")
        return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")

    @blueprint.route("/server-setup/logs/system/clean", methods=["POST"])
    def clean_system_logs():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup"))
        errors = []
        released = 0
        before = _system_log_summary()
        try:
            rotate = subprocess.run(["journalctl", "--rotate"], capture_output=True, text=True,
                                    timeout=30, check=False)
            vacuum = subprocess.run(["journalctl", "--vacuum-size=100M"], capture_output=True, text=True,
                                    timeout=60, check=False)
            if rotate.returncode != 0:
                errors.append((rotate.stderr or rotate.stdout or "journalctl --rotate lỗi").strip())
            if vacuum.returncode != 0:
                errors.append((vacuum.stderr or vacuum.stdout or "journalctl --vacuum-size lỗi").strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append("Journal: " + str(exc))
        after = _system_log_summary()
        journal_before = before["persistent"]["bytes"] + before["runtime"]["bytes"]
        journal_after = after["persistent"]["bytes"] + after["runtime"]["bytes"]
        released += max(0, journal_before - journal_after)
        message = "Đã dọn journal xuống khoảng 100 MB, giải phóng khoảng %s. Log Docker tiếp tục tự xoay vòng." % _format_size(released)
        flash(message + ((" Lỗi: " + "; ".join(errors[:3])) if errors else ""), "err" if errors else "ok")
        return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")

    @blueprint.route("/server-setup/logs/operations/clear", methods=["POST"])
    def clear_operation_logs():
        if not _valid_csrf():
            flash("Phiên không hợp lệ", "err")
            return redirect(url_for("manager_ext.setup", tab="logs"))
        released = 0
        errors = []
        for status_name in ("game-start.status", "game-reload.status"):
            try:
                if (STATE_ROOT / status_name).read_text(encoding="utf-8").splitlines()[0] == "starting":
                    flash("Không làm trống log khi Start All hoặc Reload đang chạy", "err")
                    return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")
            except (OSError, IndexError):
                pass
        for path in JXNATIVE_STATE_LOGS:
            try:
                if path.is_file() and not path.is_symlink():
                    released += path.stat().st_size
                    with path.open("wb"):
                        pass
            except OSError as exc:
                errors.append(path.name + ": " + str(exc))
        message = "Đã làm trống log Start All, Reload và Nhật ký hoạt động, giải phóng %s." % _format_size(released)
        flash(message + ((" Lỗi: " + "; ".join(errors[:3])) if errors else ""), "err" if errors else "ok")
        return redirect(url_for("manager_ext.setup", tab="logs") + "#log-management")

    app.jinja_env.globals["manager_setup_url"] = lambda: url_for("manager_ext.setup")
    app.jinja_env.globals["manager_account_url"] = lambda: url_for("manager_ext.account_settings")
    app.register_blueprint(blueprint)

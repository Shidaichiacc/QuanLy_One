"""Updater regression tests. All files and service actions are isolated/mocked."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/shared'))
sys.path.insert(0, str(ROOT / 'app/web/admin'))


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


updater = load_module('update_worker_test', ROOT / 'tools/apply-update')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'JXNative-v1.3.5.tar.gz'

    def package(self, extra=(), omit=(), version='1.3.5'):
        with tarfile.open(self.archive, 'w:gz') as bundle:
            for name in sorted(updater.REQUIRED_FILES - set(omit)):
                data = (version if name == 'VERSION' else 'fixture').encode()
                member = tarfile.TarInfo('QuanLy_One/' + name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
            for member in extra:
                bundle.addfile(member, io.BytesIO(b'x' * member.size))
        return self.archive

    def test_valid_package_and_config_symlink(self):
        link = tarfile.TarInfo('QuanLy_One/JX_Servers/Runtime/config')
        link.type, link.linkname = tarfile.SYMTYPE, '../Config'
        updater.validate_archive(self.package([link]), '1.3.5')

    def test_rejects_bad_version_missing_file_and_empty_archive(self):
        for options in ({'version': '1.3.4'}, {'omit': {'update.sh'}}, {'omit': updater.REQUIRED_FILES}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                updater.validate_archive(self.package(**options), '1.3.5')

    def test_rejects_runtime_secret_traversal_and_duplicate_files(self):
        for name in ('.env', '.env.production', 'data/state/admin.json',
                     'data/backups-code/old.py', 'data/database/mysql/data/db',
                     'JX_Servers/JX_Versions/server/game', 'VERSION', '../escape', '/tmp/escape'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                updater.validate_archive(self.package([tarfile.TarInfo(name if name.startswith('/') else 'QuanLy_One/' + name)]), '1.3.5')

    def test_rejects_links_and_special_files(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            member = tarfile.TarInfo('QuanLy_One/evil')
            member.type, member.linkname = kind, '../../outside'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                updater.validate_archive(self.package([member]), '1.3.5')

    def test_checksum_requires_correct_hash_and_filename(self):
        self.package()
        checksum = self.root / 'file.sha256'
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        checksum.write_text(f'{digest}  {self.archive.name}\n')
        updater.verify_checksum(self.archive, checksum)
        for text in (f'{digest}  wrong.tar.gz\n', f'{"0" * 64}  {self.archive.name}\n'):
            checksum.write_text(text)
            with self.assertRaises(ValueError):
                updater.verify_checksum(self.archive, checksum)

    def test_extract_preserves_runtime_sentinels(self):
        live = self.root / 'QuanLy_One'
        sentinels = ('.env', 'data/state/manager-auth.json', 'data/database/mysql/data/test',
                     'data/database/backups/user.bak', 'JX_Servers/JX_Versions/game/server1')
        for name in sentinels:
            path = live / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('must survive')
        self.package()
        with patch.object(updater, 'PROJECT_ROOT', live):
            updater.validate_archive(self.archive, '1.3.5')
            updater.extract_archive(self.archive)
        self.assertEqual((live / 'VERSION').read_text(), '1.3.5')
        for name in sentinels:
            self.assertEqual((live / name).read_text(), 'must survive')

    def test_extract_preserves_local_config_and_installs_new_defaults(self):
        live = self.root / 'QuanLy_One'
        config = live / 'JX_Servers/Config'
        config.mkdir(parents=True)
        original = '[mssql]\npassword=private-local-value\nserver=custom-host\n'
        (config / 'mssql.ini').write_text(original)
        existing = tarfile.TarInfo('QuanLy_One/JX_Servers/Config/mssql.ini')
        existing.size = 10
        new = tarfile.TarInfo('QuanLy_One/JX_Servers/Config/new.ini')
        new.size = 5
        self.package([existing, new])
        with patch.object(updater, 'PROJECT_ROOT', live):
            updater.validate_archive(self.archive, '1.3.5')
            updater.extract_archive(self.archive)
        self.assertEqual((config / 'mssql.ini').read_text(), original)
        self.assertEqual((config / 'new.ini').read_text(), 'xxxxx')

    def test_worker_refuses_running_or_unknown_game_state(self):
        for state, code in (('active', 0), ('activating', 0), ('deactivating', 0), ('', 1)):
            with patch.object(updater.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stdout=state)):
                with self.assertRaises(RuntimeError):
                    updater.require_stopped_game()
        with patch.object(updater.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='inactive')) as run:
            updater.require_stopped_game()
            self.assertEqual(run.call_count, 6)

    def test_builder_excludes_private_files_and_keeps_install_seeds(self):
        source = self.root / 'source'
        for name in updater.REQUIRED_FILES | {'tools/build-release'}:
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        private = ('.env', '.env.production', 'data/state/admin.json',
                   'data/backups-code/old.py', 'data/database/backups/user.bak',
                   'JX_Servers/JX_Versions/private/server1', 'debug.log')
        for name in private:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('private fixture')
        result = subprocess.run(['bash', str(source / 'tools/build-release'), str(self.archive)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        updater.verify_checksum(self.archive, Path(str(self.archive) + '.sha256'))
        with tarfile.open(self.archive) as bundle:
            names = set(bundle.getnames())
        for name in private:
            self.assertNotIn('QuanLy_One/' + name, names)
        for name in updater.REQUIRED_FILES:
            self.assertIn('QuanLy_One/' + name, names)

    def test_worker_success_from_download_through_extraction(self):
        self.package()
        checksum = self.archive.with_suffix('.gz.sha256')
        checksum.write_text(hashlib.sha256(self.archive.read_bytes()).hexdigest() + '  ' + self.archive.name + '\n')
        live = self.root / 'QuanLy_One'
        live.mkdir()
        (live / 'VERSION').write_text('1.3.3\n')
        prefix = 'https://github.com/owner/repo/releases/download/v1.3.5/' + self.archive.name
        def download(url, destination, *_):
            shutil.copyfile(checksum if url.endswith('.sha256') else self.archive, destination)
        with patch.multiple(updater, PROJECT_ROOT=live, STATE_ROOT=live / 'state',
                            LOG_FILE=live / 'state/log', STATUS_FILE=live / 'state/status',
                            LOCK_FILE=self.root / 'lock'), \
             patch.object(sys, 'argv', ['apply-update', '1.3.5', 'owner/repo', prefix, prefix + '.sha256']), \
             patch.object(updater.os, 'geteuid', return_value=0), \
             patch.object(updater, 'download', side_effect=download), \
             patch.object(updater, 'run_update_script', return_value=0) as install, \
             patch.object(updater.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='inactive')):
            updater.main()
            install.assert_called_once()
        self.assertEqual((live / 'VERSION').read_text(), '1.3.5')
        self.assertEqual(json.loads((live / 'state/status').read_text())['state'], 'success')

    def test_failed_update_restores_version_for_retry(self):
        live = self.root / 'QuanLy_One'
        live.mkdir()
        (live / 'VERSION').write_text('1.3.3\n')
        prefix = 'https://github.com/owner/repo/releases/download/v1.3.5/JXNative-v1.3.5.tar.gz'
        def extract(_):
            (live / 'VERSION').write_text('1.3.5\n')
        with patch.multiple(updater, PROJECT_ROOT=live, STATE_ROOT=live / 'state',
                            LOG_FILE=live / 'state/log', STATUS_FILE=live / 'state/status',
                            LOCK_FILE=self.root / 'lock'), \
             patch.object(sys, 'argv', ['apply-update', '1.3.5', 'owner/repo', prefix, prefix + '.sha256']), \
             patch.object(updater.os, 'geteuid', return_value=0), \
             patch.object(updater, 'download'), patch.object(updater, 'verify_checksum'), \
             patch.object(updater, 'validate_archive'), patch.object(updater, 'require_stopped_game'), \
             patch.object(updater, 'backup_changed_shared_mods'), \
             patch.object(updater, 'extract_archive', side_effect=extract), \
             patch.object(updater, 'run_update_script', return_value=1), \
             patch.object(updater.subprocess, 'run'), self.assertRaises(SystemExit):
            updater.main()
        self.assertEqual((live / 'VERSION').read_text(), '1.3.3\n')
        self.assertEqual(json.loads((live / 'state/status').read_text())['state'], 'error')


class WebUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {'QUANLY_ONE_ROOT': cls.temp.name}):
            cls.web = load_module('update_web_test', ROOT / 'app/web/admin/app.py')
        cls.web.app.config.update(TESTING=True, SECRET_KEY='test-only')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.web.app.test_client()
        import manager_extension
        for target in (
            patch.object(manager_extension, '_load_auth', return_value={'must_change': False}),
            patch.object(manager_extension, '_database_setup_complete', return_value=True),
            patch.object(self.web, '_system_update_conflict', return_value=''),
            patch.object(self.web, 'verify_manager_password', return_value=True),
            patch.object(self.web, 'sctl', return_value=SimpleNamespace(returncode=3)),
            patch.object(self.web, 'SYSTEM_UPDATE_TOOL', str(ROOT / 'tools/apply-update')),
        ):
            target.start()
            self.addCleanup(target.stop)
        self.release = dict(status='ok', available=True, latest='1.3.5',
                            download_url='https://github.com/' + self.web.UPDATE_REPOSITORY + '/releases/download/v1.3.5/JXNative-v1.3.5.tar.gz')
        self.release['checksum_url'] = self.release['download_url'] + '.sha256'
        with self.client.session_transaction() as session:
            session.update(manager_authenticated=True, csrf_token='csrf')

    def post(self, **overrides):
        return self.client.post('/system/update/start', data=dict(csrf_token='csrf', **overrides))

    def test_auth_and_csrf_remain_required(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.post().status_code, 302)
        with self.client.session_transaction() as session:
            session.update(manager_authenticated=True, csrf_token='csrf')
        self.assertEqual(self.client.post('/system/update/start').status_code, 400)
        with patch.object(self.web, '_github_release_status', return_value=self.release), \
             patch.object(self.web, 'unit_active', return_value=False), \
             patch.object(self.web, '_start_system_update') as start, \
             patch.object(self.web, 'verify_manager_password', return_value=False) as password:
            self.assertEqual(self.post().status_code, 202)
            password.assert_not_called()
            start.assert_called_once()

    def test_missing_assets_does_not_stop_game(self):
        self.release['checksum_url'] = ''
        with patch.object(self.web, '_github_release_status', return_value=self.release), \
             patch.object(self.web, 'stop_all_gracefully') as stop:
            self.assertEqual(self.post(stop_server='1').status_code, 409)
            stop.assert_not_called()

    def test_running_game_requires_confirmation_then_starts_worker(self):
        with patch.object(self.web, '_github_release_status', return_value=self.release), \
             patch.object(self.web, 'unit_active', return_value=True), \
             patch.object(self.web, 'stop_all_gracefully') as stop:
            response = self.post()
            self.assertEqual(response.status_code, 409)
            self.assertTrue(response.json['requires_stop'])
            stop.assert_not_called()
        count = len(self.web.COMPONENTS)
        with patch.object(self.web, '_github_release_status', return_value=self.release), \
             patch.object(self.web, 'unit_active', side_effect=[True] * count + [False] * count), \
             patch.object(self.web, 'stop_all_gracefully', return_value=([], [])) as stop, \
             patch.object(self.web, '_start_system_update') as start:
            self.assertEqual(self.post(stop_server='1').status_code, 202)
            stop.assert_called_once()
            start.assert_called_once_with(self.release)

    def test_failed_stop_never_launches_update(self):
        with patch.object(self.web, '_github_release_status', return_value=self.release), \
             patch.object(self.web, 'unit_active', return_value=True), \
             patch.object(self.web, 'stop_all_gracefully', return_value=([], ['failed'])), \
             patch.object(self.web, '_start_system_update') as start:
            self.assertEqual(self.post(stop_server='1').status_code, 500)
            start.assert_not_called()

    def test_expired_session_release_cache_is_refreshed(self):
        with self.client.session_transaction() as session:
            session['jx_update_status'] = dict(status='ok', latest='1.3.4', checked_at=1,
                                               cache_id=f'{self.web.APP_VERSION}:{self.web.UPDATE_REPOSITORY}')
        with patch.object(self.web, '_github_release_status', return_value=self.release) as lookup:
            response = self.client.get('/api/update-check')
            self.assertEqual(response.json['latest'], '1.3.5')
            lookup.assert_called_once()

    def test_fresh_session_cache_and_explicit_refresh(self):
        import time
        with self.client.session_transaction() as session:
            session['jx_update_status'] = dict(status='ok', latest='1.3.4', checked_at=time.time(),
                                               cache_id=f'{self.web.APP_VERSION}:{self.web.UPDATE_REPOSITORY}')
        with patch.object(self.web, '_github_release_status', return_value=self.release) as lookup:
            self.assertEqual(self.client.get('/api/update-check').json['latest'], '1.3.4')
            lookup.assert_not_called()
            self.assertEqual(self.client.get('/api/update-check?refresh=1').json['latest'], '1.3.5')
            lookup.assert_called_once_with(self.web.APP_VERSION, force=True)

    def test_old_update_page_opens_dashboard_popup(self):
        response = self.client.get('/system/update')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/?update=1')

    def test_release_selects_exact_assets_and_reports_missing_pair(self):
        assets = [{'name': 'unrelated.tar.gz', 'browser_download_url': 'https://example.com/no'}]
        for suffix, key in (('', 'download_url'), ('.sha256', 'checksum_url')):
            assets.append(dict(name='JXNative-v1.3.5.tar.gz' + suffix, browser_download_url=self.release[key]))
        def check(items):
            response = Mock()
            response.__enter__ = Mock(return_value=io.BytesIO(json.dumps(dict(tag_name='v1.3.5', assets=items)).encode()))
            response.__exit__ = Mock(return_value=False)
            with patch.object(self.web.urllib.request, 'urlopen', return_value=response):
                return self.web._github_release_status('1.3.3', force=True)
        result = check(assets)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['available'])
        self.assertEqual(result['download_url'], self.release['download_url'])
        result = check(assets[:-1])
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['download_url'])


if __name__ == '__main__':
    unittest.main()

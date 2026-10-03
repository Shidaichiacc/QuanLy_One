"""Run with app/web/admin/venv/bin/python -m unittest discover -s tests -p test_storage_manager.py."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/web/admin'))
from storage_manager import StorageManager, ident, safe_stat, register_storage_routes
from flask import Flask, Blueprint


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.logs = self.root / 'Logs'
        self.logs.mkdir()
        self.backup = self.root / 'Backup'
        self.backup.mkdir()
        self.sources = {}
        self.add_source(self.root, 'data', 'protected')
        self.log_id = self.add_source(self.logs, 'game', 'files')
        self.backup_id = self.add_source(self.backup, 'backup', 'protected')
        self.ext = SimpleNamespace(PROJECT_ROOT=self.root, STATE_ROOT=self.root / 'state')
        self.manager = StorageManager(self.ext)
        self.manager.catalog = lambda: ({key: dict(row) for key, row in self.sources.items()}, [])
        self.now = time.time() + 1200
        self.clock = patch('storage_manager.time.time', return_value=self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.temp.cleanup()

    def add_source(self, path, group, mode):
        key = ident(str(path)+':'+group)
        self.sources[key] = dict(id=key, path=str(path), label=path.name, group=group,
                                 mode=mode, version='', note='')
        return key

    def file(self, name='old.log', age=10, parent=None):
        path = (parent or self.logs) / name
        path.write_text('test data\n')
        timestamp = self.now-age*86400
        os.utime(path, (timestamp, timestamp))
        return path

    def test_inventory_deduplicates_nested_roots_hardlinks_and_symlinks(self):
        original = self.file()
        os.link(original, self.logs / 'hardlink.log')
        (self.logs / 'external').symlink_to('/etc')
        self.file(parent=self.backup)
        snap = self.manager.scan()
        self.assertEqual(sum(s['files'] for s in snap['sources']), 2)
        self.assertEqual(len(self.manager.snapshot['records']), 2)

    def test_legacy_non_utf8_filenames_can_be_listed_and_deleted(self):
        raw = os.fsencode(self.logs) + b'/legacy_\xff.log'
        with open(raw, 'wb') as stream:
            stream.write(b'legacy filename')
        os.utime(raw, (self.now - 10*86400, self.now - 10*86400))
        plan = self.manager.preview('owner', [self.log_id], '7')
        self.assertEqual(plan['files'], 1)
        self.assertEqual(self.manager.execute('owner', plan['token'])['removed'], 1)

    def test_two_previews_remain_safe_after_inventory_invalidated(self):
        self.file()
        first = self.manager.preview('owner', [self.log_id], '7')
        second = self.manager.preview('owner', [self.log_id], '7')
        self.assertEqual(self.manager.execute('owner', first['token'])['removed'], 1)
        result = self.manager.execute('owner', second['token'])
        self.assertEqual(result['removed'], 0)
        self.assertEqual(result['skipped'], 1)

    def test_age_selection_and_explicit_all(self):
        self.file('ten-days.log',10)
        self.file('two-days.log',2)
        self.file('today.log',0.1)
        self.assertEqual(self.manager.preview('owner',[self.log_id],'7')['files'],1)
        self.assertEqual(self.manager.preview('owner',[self.log_id],'1')['files'],2)
        self.assertEqual(self.manager.preview('owner',[self.log_id],'all')['files'],3)
        with self.assertRaises(ValueError):
            self.manager.preview('owner',[self.log_id],'0')

    def test_only_previewed_files_removed_backup_and_new_files_survive(self):
        old = self.file()
        backup = self.file(parent=self.backup)
        plan = self.manager.preview('owner',[self.log_id],'7')
        new = self.file('created-after-preview.log')
        result = self.manager.execute('owner',plan['token'])
        self.assertEqual(result['removed'],1)
        self.assertFalse(old.exists())
        self.assertTrue(backup.exists())
        self.assertTrue(new.exists())
        with self.assertRaises(ValueError):
            self.manager.execute('owner',plan['token'])

    def test_modified_file_and_file_opened_after_preview_are_skipped(self):
        modified = self.file('modified.log')
        opened = self.file('opened.log')
        plan = self.manager.preview('owner',[self.log_id],'all')
        modified.write_text('changed')
        with opened.open() as stream:
            result = self.manager.execute('owner',plan['token'])
        self.assertEqual(result['removed'],0)
        self.assertEqual(result['skipped'],2)

    def test_open_file_and_recent_file_are_not_candidates(self):
        opened = self.file('opened.log')
        recent = self.file('recent.log', 0)
        with opened.open():
            plan = self.manager.preview('owner',[self.log_id],'all')
        self.assertEqual(plan['files'],0)
        self.assertEqual(plan['skipped'],2)

    def test_hardlinks_protected_sources_and_wrong_owner(self):
        old = self.file()
        os.link(old, self.logs / 'linked.log')
        self.assertEqual(self.manager.preview('owner',[self.log_id],'all')['files'],0)
        with self.assertRaises(ValueError):
            self.manager.preview('owner',[self.backup_id],'all')
        plan = self.manager.preview('owner',[self.log_id],'all')
        with self.assertRaises(ValueError):
            self.manager.execute('other',plan['token'])
        with patch('storage_manager.time.time', return_value=self.now+301):
            with self.assertRaises(ValueError):
                self.manager.execute('owner',plan['token'])

    def test_replaced_parent_symlink_cannot_delete_outside_source(self):
        old = self.file()
        plan = self.manager.preview('owner',[self.log_id],'all')
        self.logs.rename(self.root/'original-logs')
        self.logs.symlink_to(self.backup, target_is_directory=True)
        protected = self.file(parent=self.backup)
        result = self.manager.execute('owner',plan['token'])
        self.assertEqual(result['removed'],0)
        self.assertTrue(protected.exists())
        with self.assertRaises(OSError):
            safe_stat(self.logs/'old.log')

    def test_selected_files_and_preview_pagination(self):
        one = self.file('one.log')
        two = self.file('two.log')
        plan = self.manager.preview('owner',[self.log_id],'all',[ident(one)])
        self.assertEqual(plan['files'],1)
        data = self.manager.preview_details('owner',plan['token'])
        self.assertEqual(data['files'][0]['path'],str(one))
        self.assertNotIn('fingerprint',data['files'][0])
        self.manager.execute('owner',plan['token'])
        self.assertTrue(two.exists())
        with self.assertRaises(ValueError):
            self.manager.preview('owner',[self.log_id],'all',['invalid-file-id'])

    def test_nginx_active_file_and_core_named_non_dump_are_preserved(self):
        rotated = self.root/'nginx'
        rotated.mkdir()
        source = self.add_source(rotated,'system','rotated')
        self.file('access.log',parent=rotated)
        self.file('access.log.1',parent=rotated)
        plan = self.manager.preview('owner',[source],'all')
        self.assertEqual(plan['files'],1)
        self.assertEqual(plan['sample'][0]['name'],'access.log.1')
        core = self.root/'dumps'
        core.mkdir()
        source = self.add_source(core,'dump','dump')
        self.file('core.settings',parent=core)
        plan = self.manager.preview('owner',[source],'all')
        self.assertEqual(plan['files'],0)

    def test_journal_uses_native_vacuum_without_rotation(self):
        journal = self.root/'journal'
        journal.mkdir()
        source = self.add_source(journal,'system','journal')
        self.file('system@archived.journal',parent=journal)
        self.file('system.journal',parent=journal)
        plan = self.manager.preview('owner',[source],'7')
        self.assertTrue(plan['journal'])
        self.assertEqual(plan['files'],1)
        with patch('storage_manager.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
            self.manager.execute('owner',plan['token'])
        self.assertEqual(run.call_args.args[0],['journalctl','--directory='+str(journal),'--vacuum-time=7d'])
        with self.assertRaises(ValueError):
            self.manager.preview('owner',[source,self.log_id],'all')

    def test_csrf_and_confirmation_required_by_api(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        blueprint = Blueprint('storage_test',__name__)
        manager = register_storage_routes(blueprint,self.ext)
        manager.catalog = self.manager.catalog
        app.register_blueprint(blueprint)
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['csrf_token'] = 'test-csrf'
        prefix='/server-setup/storage/'
        self.file()
        self.assertEqual(client.post(prefix+'preview',json={'sources':[self.log_id],'days':'all'}).status_code,400)
        headers={'X-CSRF-Token':'test-csrf'}
        preview=client.post(prefix+'preview',json={'sources':[self.log_id],'days':'all'},headers=headers)
        self.assertEqual(preview.status_code,200)
        token=preview.json['token']
        self.assertEqual(client.post(prefix+'delete',json={'token':token},headers=headers).status_code,400)
        deleted=client.post(prefix+'delete',json={'token':token,'confirm':True},headers=headers)
        self.assertEqual(deleted.status_code,200)
        self.assertEqual(deleted.json['removed'],1)

    def crash(self, name, executable, parent):
        path = self.file(name, parent=parent)
        path.write_text('ProblemType: Crash\nExecutablePath: ' + str(executable) + '\n')
        os.utime(path, (self.now - 10*86400, self.now - 10*86400))
        return path

    def test_quick_cleanup_excludes_foreign_crashes_cache_and_backup(self):
        self.file('server.log')
        backup = self.file('backup.bak', parent=self.backup)
        state = self.ext.STATE_ROOT
        state.mkdir()
        self.add_source(state, 'system', 'state')
        app_log = self.file('game-start.log', parent=state)
        config = self.file('manager-auth.json', parent=state)
        crash_dir = self.root/'crash'
        crash_dir.mkdir()
        crash_id = self.add_source(crash_dir, 'dump', 'crash')
        ours = self.crash('game.crash', self.root/'JX_Servers/JX_Versions/one/server1/jx_linux_y', crash_dir)
        foreign = self.crash('foreign.crash', '/usr/bin/other', crash_dir)
        fake_prefix = self.crash('fake.crash', str(self.root) + '/app-unrelated/python', crash_dir)
        apt = self.root/'apt'
        apt.mkdir()
        apt_id = self.add_source(apt, 'cache', 'apt')
        package = self.file('package.deb', parent=apt)
        plan = self.manager.preview('owner', None, 'all', quick=True)
        self.assertEqual({r['path'] for r in plan['sample']}, {str(self.logs/'server.log'), str(app_log), str(ours)})
        cleanup = self.manager.public_snapshot()['cleanup']
        self.assertEqual(cleanup['unknown_dumps'], 2)
        self.assertEqual(sum(g['files'] for g in cleanup['groups']), 5)
        detail = self.manager.details(crash_id, quick=True)
        self.assertEqual({r['path'] for r in detail['files']}, {str(ours), str(foreign), str(fake_prefix)})
        with self.assertRaises(ValueError):
            self.manager.preview('owner', [apt_id], 'all', quick=True)
        foreign_plan = self.manager.preview('owner', [crash_id], 'all', [ident(foreign)], quick=True)
        self.assertEqual(foreign_plan['files'], 0)
        self.assertEqual(foreign_plan['skipped'], 1)
        result = self.manager.execute('owner', plan['token'])
        self.assertEqual(result['removed'], 3)
        for path in [backup, config, foreign, fake_prefix, package]:
            self.assertTrue(path.exists(), str(path))

    def test_quick_cleanup_does_not_trust_process_basename(self):
        dump_dir = self.root/'dumps'
        dump_dir.mkdir()
        source = self.add_source(dump_dir, 'dump', 'dump')
        unrelated = self.file('core.jx_linux_y.0.123.gz', parent=dump_dir)
        self.assertEqual(self.manager.preview('owner', None, 'all', quick=True)['files'], 0)
        self.assertTrue(unrelated.exists())
        # systemd metadata establishes actual executable ownership.
        os.setxattr(unrelated, 'user.coredump.exe', str(self.root/'JX_Servers/JX_Versions/one/server1/jx_linux_y').encode())
        self.assertEqual(self.manager.preview('owner', None, 'all', quick=True)['files'], 1)

    def test_quick_cleanup_recognizes_app_core_and_preserves_fake_core(self):
        app = self.root/'app'
        app.mkdir()
        core = self.file('core.123', parent=app)
        head = bytearray(18)
        head[:4] = b'\x7fELF'
        head[5] = 1
        head[16] = 4
        core.write_bytes(head)
        fake = self.file('core.settings', parent=app)
        plan = self.manager.preview('owner', None, 'all', quick=True)
        self.assertEqual([r['path'] for r in plan['sample']], [str(core)])
        self.manager.execute('owner', plan['token'])
        self.assertTrue(fake.exists())

    def test_empty_quick_cleanup_and_day_options(self):
        self.assertEqual(self.manager.preview('owner', None, 'all', quick=True)['files'], 0)
        self.file('old.log', 10)
        self.file('two-days.log', 2)
        self.file('today.log', .1)
        for days, expected in [('7', 1), ('1', 2), ('all', 3)]:
            self.assertEqual(self.manager.preview('owner', None, days, quick=True)['files'], expected)


    def test_empty_dump_locations_and_services_remain_visible(self):
        empty = self.root/'apport'
        empty.mkdir()
        dump_id = self.add_source(empty, 'dump', 'dump')
        missing_id = self.add_source(self.root/'systemd-coredump', 'dump', 'dump')
        nginx = self.root/'nginx'
        nginx.mkdir()
        self.add_source(nginx, 'system', 'rotated')
        self.file('access.log', parent=nginx)
        ram = self.root/'runtime-journal'
        ram.mkdir()
        self.add_source(ram, 'ram', 'journal')
        self.file('system.journal', parent=ram)
        data = self.manager.scan()['cleanup']
        rows = {r['id']: r for r in data['sources']}
        self.assertEqual(rows[dump_id]['files'], 0)
        self.assertTrue(rows[dump_id]['exists'])
        self.assertFalse(rows[missing_id]['exists'])
        service = next(g for g in data['groups'] if g['id'] == 'system')
        self.assertEqual(service['files'], 2)
        self.assertGreater(service['memory_allocated'], 0)
        self.assertEqual(service['allocated'], service['memory_allocated'])

    def test_quick_mixed_services_use_native_journal_and_keep_docker(self):
        log = self.file('old-game.log')
        nginx = self.root/'nginx'
        nginx.mkdir()
        self.add_source(nginx, 'system', 'rotated')
        active = self.file('access.log', parent=nginx)
        rotated = self.file('access.log.1', parent=nginx)
        docker = self.root/'docker'
        docker.mkdir()
        self.add_source(docker, 'system', 'docker')
        docker_file = self.file('example-json.log.1', parent=docker)
        journal = self.root/'journal'
        journal.mkdir()
        self.add_source(journal, 'system', 'journal')
        archive = self.file('system@archive.journal', parent=journal)
        current = self.file('system.journal', parent=journal)
        plan = self.manager.preview('owner', None, 'all', quick=True)
        self.assertTrue(plan['journal'])
        self.assertEqual({r['path'] for r in plan['sample']}, {str(log), str(rotated), str(archive)})
        def native(command, **kwargs):
            self.assertEqual(command, ['journalctl', '--directory='+str(journal), '--vacuum-time=1s'])
            archive.unlink()
            return SimpleNamespace(returncode=0)
        with patch('storage_manager.subprocess.run', side_effect=native) as run:
            result = self.manager.execute('owner', plan['token'])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result['removed'], 3)
        for path in (active, docker_file, current):
            self.assertTrue(path.exists())

    def test_native_journal_failure_does_not_hide_other_cleanup_results(self):
        log = self.file()
        journal = self.root/'journal'
        journal.mkdir()
        self.add_source(journal, 'system', 'journal')
        self.file('system@archive.journal', parent=journal)
        plan = self.manager.preview('owner', None, '7', quick=True)
        with patch('storage_manager.subprocess.run', side_effect=OSError('native test failure')):
            result = self.manager.execute('owner', plan['token'])
        self.assertEqual(result['removed'], 1)
        self.assertEqual(result['error_count'], 1)
        self.assertFalse(log.exists())



if __name__ == '__main__':
    unittest.main()

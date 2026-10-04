"""Regression for updates replacing native PaySys credentials with a template."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/shared'))
from database_credentials import sync_paysys_credentials


class UpdateCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'JX_Servers/Config/mssql.ini'
        self.config.parent.mkdir(parents=True)
        self.original = b'[mssql]\r\nserver=private-host:1433\r\nuser=sa\r\npassword=template\r\ndatabase=account_tong\r\n'
        self.config.write_bytes(self.original)
        self.config.chmod(0o600)
        self.env = self.root / '.env'
        self.env.write_text('MSSQL_SA_PASSWORD="Local%Value_123"\nOTHER_SETTING=keep\n')

    def test_old_updater_template_is_repaired_without_changing_env_or_host(self):
        original_env = self.env.read_bytes()
        self.assertEqual(sync_paysys_credentials(self.root), 1)
        self.assertEqual(self.config.read_bytes(), self.original.replace(b'template', b'Local%Value_123'))
        self.assertEqual(self.env.read_bytes(), original_env)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(sync_paysys_credentials(self.root), 0)

    def test_missing_password_or_config_key_fails_without_overwrite(self):
        for content in ('', 'MSSQL_SA_PASSWORD='):
            self.env.write_text(content)
            with self.assertRaises(ValueError):
                sync_paysys_credentials(self.root)
            self.assertEqual(self.config.read_bytes(), self.original)
        self.env.write_text('MSSQL_SA_PASSWORD=fixture')
        self.config.write_text('[mssql]\nserver=host\n')
        with self.assertRaises(ValueError):
            sync_paysys_credentials(self.root)

    def test_malformed_config_error_does_not_disclose_content(self):
        self.config.write_text('private-password-fixture-without-section')
        with self.assertRaises(ValueError) as caught:
            sync_paysys_credentials(self.root)
        self.assertNotIn('private-password', str(caught.exception))

    def test_symlink_config_does_not_modify_target(self):
        target = self.root / 'private.ini'
        target.write_bytes(self.original)
        self.config.unlink()
        self.config.symlink_to(target)
        with self.assertRaises(ValueError):
            sync_paysys_credentials(self.root)
        self.assertEqual(target.read_bytes(), self.original)

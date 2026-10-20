import importlib.util
import tempfile
from pathlib import Path
from unittest import TestCase, main

spec = importlib.util.spec_from_file_location('repair', Path(__file__).resolve().parents[1] /
    'infrastructure/members/repair_cloud_callback.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class CallbackTests(TestCase):
    def credentials(self):
        return {'client_id': repair.CLIENT_ID, 'issuer': repair.ISSUER,
                'redirect_uri': repair.OLD_CALLBACK}

    def test_exact_old_and_current_paths_are_accepted(self):
        for uri in (repair.OLD_CALLBACK, repair.CALLBACK):
            repair.validate(repair.CLIENT_ID, uri, self.credentials())

    def test_other_clients_and_issuers_are_rejected(self):
        for field in ('client_id', 'issuer'):
            credentials = self.credentials()
            credentials[field] = 'unexpected'
            with self.assertRaises(ValueError):
                repair.validate(repair.CLIENT_ID, repair.OLD_CALLBACK, credentials)
        with self.assertRaises(ValueError):
            repair.validate('other-client', repair.OLD_CALLBACK, self.credentials())

    def test_no_extra_redirects_or_external_urls(self):
        for uri in ('https://evil.example/code', repair.CALLBACK + '?next=evil',
                    repair.CALLBACK + ' ' + repair.OLD_CALLBACK, 'http://cloud.devantiq.com/apps/user_oidc/code'):
            with self.assertRaises(ValueError):
                repair.validate(repair.CLIENT_ID, uri, self.credentials())
            credentials = {**self.credentials(), 'redirect_uri': uri}
            with self.assertRaises(ValueError):
                repair.validate(repair.CLIENT_ID, repair.CALLBACK, credentials)

    def test_backup_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            path = Path(directory) / 'backup.json'
            repair.private_write(path, b'original')
            with self.assertRaises(FileExistsError):
                repair.private_write(path, b'replaced')
            self.assertEqual(path.read_bytes(), b'original')


if __name__ == '__main__':
    main()

import importlib.util
import json
from pathlib import Path
import shutil
import uuid
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).with_name('publish-showcase.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublishTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parent.parent
        base = workspace / ('.publish-test-' + uuid.uuid4().hex)
        base.mkdir()
        def cleanup():
            assert base.resolve().parent == workspace
            shutil.rmtree(base)
        self.addCleanup(cleanup)
        self.root, self.stage, self.backups = base / 'site', base / 'stage', base / 'backups'
        self.root.mkdir()
        manifest = {}
        for name in publisher.FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'old\n')
            source = self.stage / 'public' / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b'new\n')
            manifest[name] = {'sha256': publisher.digest(b'new\n'), 'baseline': publisher.normalized(b'old\n')}
        (self.stage / 'manifest.json').write_text(json.dumps(manifest))
        self.chown = patch.object(publisher.os, 'chown', create=True)
        self.chown.start()
        self.addCleanup(self.chown.stop)

    def test_publish_and_backup(self):
        publisher.install(self.stage, self.root, self.backups)
        for name in publisher.FILES:
            self.assertEqual((self.root / name).read_bytes(), b'new\n')
        backup = next(self.backups.iterdir())
        self.assertEqual((backup / 'index.html').read_bytes(), b'old\n')

    def test_remote_edits_stop_every_public_write(self):
        (self.root / 'index.html').write_bytes(b'remote custom edit')
        with self.assertRaisesRegex(RuntimeError, 'different du depot'):
            publisher.install(self.stage, self.root, self.backups)
        self.assertEqual((self.root / 'g1club.html').read_bytes(), b'old\n')
        self.assertFalse(self.backups.exists())

    def test_write_failure_restores_already_published_files(self):
        replace = publisher.os.replace
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated write failure')
            replace(source, target)
        with patch.object(publisher.os, 'replace', side_effect=fail_second):
            with self.assertRaises(OSError):
                publisher.install(self.stage, self.root, self.backups)
        for name in publisher.FILES:
            self.assertEqual((self.root / name).read_bytes(), b'old\n')

    def reviewed_manifest(self):
        path = self.stage / 'manifest.json'
        manifest = json.loads(path.read_text())
        for name in publisher.FILES:
            manifest[name]['baseline'] = 'outdated-git-reference'
            manifest[name]['reviewed'] = publisher.digest((self.root / name).read_bytes())
        path.write_text(json.dumps(manifest))

    def test_reviewed_snapshot_accepts_previous_deployment(self):
        self.reviewed_manifest()
        publisher.install(self.stage, self.root, self.backups)
        self.assertEqual((self.root / 'index.html').read_bytes(), b'new\n')

    def test_change_after_review_stops_publication(self):
        self.reviewed_manifest()
        (self.root / 'index.html').write_bytes(b'edit after inspection')
        with self.assertRaisesRegex(RuntimeError, 'different du depot'):
            publisher.install(self.stage, self.root, self.backups)
        self.assertEqual((self.root / 'g1club.html').read_bytes(), b'old\n')
        self.assertFalse(self.backups.exists())

    def test_missing_reviewed_file_stops_publication(self):
        self.reviewed_manifest()
        (self.root / 'index.html').unlink()
        with self.assertRaisesRegex(RuntimeError, 'absent du VPS'):
            publisher.install(self.stage, self.root, self.backups)
        self.assertFalse(self.backups.exists())

    def test_already_published_images_get_directory_permissions_repaired(self):
        for name in publisher.FILES:
            (self.root / name).write_bytes(b'new\n')
        with patch.object(Path, 'chmod', autospec=True) as chmod:
            publisher.install(self.stage, self.root, self.backups)
        for folder in ('caroussel/mycareer', 'caroussel/g1tournoi'):
            chmod.assert_any_call(self.root / folder, 0o755)

    def test_new_public_directory_overrides_private_umask(self):
        destination = self.root / 'new-public' / 'nested'
        previous = publisher.os.umask(0o077)
        try:
            with patch.object(Path, 'chmod', autospec=True) as chmod:
                publisher.public_directory(destination, self.root)
            chmod.assert_any_call(destination.parent, 0o755)
            chmod.assert_any_call(destination, 0o755)
        finally:
            publisher.os.umask(previous)


if __name__ == '__main__':
    unittest.main()

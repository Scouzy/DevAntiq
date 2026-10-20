"""Verify the narrow listener rewrites without touching live services."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'repair', Path(__file__).resolve().parents[1] / 'infrastructure/members/repair_livemonitor.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class ListenerRepairTests(unittest.TestCase):
    def test_backend_preserves_other_addresses(self):
        source = 'const other = "0.0.0.0"; server.listen(PORT, "0.0.0.0", callback);'
        self.assertEqual(repair.patch_source(source, 'backend'),
                         'const other = "0.0.0.0"; server.listen(PORT, \'127.0.0.1\', callback);')

    def test_web_cannot_be_overridden_by_host_environment(self):
        self.assertEqual(repair.patch_source("const host = process.env.HOST || '0.0.0.0';", 'web'),
                         "const host = '127.0.0.1';")

    def test_agent_preserves_handler_and_port(self):
        self.assertEqual(repair.patch_source('server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)', 'agent'),
                         "server = http.server.HTTPServer(('127.0.0.1', PORT), Handler)")

    def test_vite(self):
        self.assertEqual(repair.patch_source('server: { host: true, port: 5173 }', 'vite'),
                         "server: { host: '127.0.0.1', port: 5173 }")

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            repair.patch_source('server.listen(PORT);', 'backend')

    def test_ambiguous_source_is_rejected(self):
        with self.assertRaises(ValueError):
            repair.patch_source('server.listen(PORT, "0.0.0.0");' * 2, 'backend')


if __name__ == '__main__':
    unittest.main()

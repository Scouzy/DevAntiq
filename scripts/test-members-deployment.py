import importlib.util
from pathlib import Path
import unittest
import sys

spec = importlib.util.spec_from_file_location('nginx_portal', Path(__file__).resolve().parent.parent / 'infrastructure/members/nginx_portal.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'infrastructure/members'))
import protect_apps


class NginxTests(unittest.TestCase):
    def test_only_site_https_server_is_modified(self):
        original = '''server {listen 80; server_name devantiq.com; return 301 https://$host$request_uri;}
server {listen 443 ssl; server_name devantiq.com www.devantiq.com; location / {try_files $uri $uri/ =404;}}
server {listen 443 ssl; server_name g1crm.devantiq.com; location / {proxy_pass http://127.0.0.1:3001;}}'''
        updated = module.patch_site(original)
        self.assertEqual(updated.count(module.INCLUDE), 1)
        self.assertIn(original.splitlines()[0], updated)
        self.assertIn(original.splitlines()[2], updated)
        self.assertEqual(module.patch_site(updated), updated)

    def test_conflicting_existing_auth_is_rejected(self):
        with self.assertRaises(ValueError):
            module.patch_site('server {listen 443 ssl; server_name devantiq.com; location /auth/ {proxy_pass http://localhost:9091;}}')

    def test_comments_and_quotes_do_not_create_false_servers(self):
        text = '# server {listen 443; server_name devantiq.com;}\nserver {listen [::]:443 ssl; server_name devantiq.com; add_header Test "};";}'
        self.assertEqual(module.patch_site(text).count(module.INCLUDE), 1)

    def test_ambiguous_servers_are_rejected(self):
        with self.assertRaises(ValueError):
            module.patch_site('server {listen 443; server_name devantiq.com;}' * 2)

    def test_gateway_preserves_php_and_acme_routes(self):
        original = '''server {listen 443 ssl; server_name zabbix.devantiq.com;
location / {try_files $uri $uri/ /index.php;}
location ~ \\.php$ {fastcgi_pass unix:/run/php/php.sock;}
location ^~ /.well-known/acme-challenge/ {root /var/www/certbot;}}'''
        updated, hosts = protect_apps.patch_apps(original)
        self.assertIn('fastcgi_pass unix:/run/php/php.sock;', updated)
        self.assertIn('auth_request off;', updated)
        self.assertIn(protect_apps.INCLUDE, updated)
        self.assertEqual(hosts, {'zabbix.devantiq.com'})
        self.assertEqual(protect_apps.patch_apps(updated)[0], updated)

    def test_umami_exempts_only_collection_and_script(self):
        updated, _ = protect_apps.patch_apps('server {listen 443 ssl; server_name umami.devantiq.com; location / {proxy_pass http://127.0.0.1:3300;}}')
        self.assertIn('location = /api/send', updated)
        self.assertIn('location = /script.js', updated)
        self.assertNotIn('location /api/', updated)
        self.assertEqual(updated.count('auth_request off;'), 2)

    def test_mixed_hosts_and_existing_auth_are_rejected(self):
        for body in ['server_name g1crm.devantiq.com devantiq.com;',
                     'server_name g1crm.devantiq.com; auth_request /other;',
                     'server_name g1crm.devantiq.com; satisfy any;']:
            with self.assertRaises(ValueError):
                protect_apps.patch_apps('server {listen 443 ssl;' + body + '}')

    def test_http_alias_redirect_is_idempotent(self):
        text = 'server {listen 80;server_name crm.devantiq.com;location / {proxy_pass http://127.0.0.1:3001;}}'
        updated, _ = protect_apps.patch_apps(text)
        self.assertIn('return 308 https://g1crm.devantiq.com$request_uri;', updated)
        self.assertEqual(protect_apps.patch_apps(updated)[0], updated)


if __name__ == '__main__':
    unittest.main()

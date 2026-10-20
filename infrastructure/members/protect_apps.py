"""Protect the inventoried browser applications, preserving existing proxy/PHP routes."""
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from nginx_portal import servers

APPS = ('g1crm', 'g1profil', 'sentinet', 'livemonitor', 'umami', 'cloud', 'n8n', 'omniroute', 'zabbix')
HOSTS = {f'{app}.devantiq.com' for app in APPS} | {'admin.livemonitor.devantiq.com', 'crm.devantiq.com'}
INCLUDE = 'include /etc/nginx/snippets/devantiq/gateway.conf;'
UMAMI = '''
    # Public analytics collection used by the DevAntiq showcase.
    location = /script.js {
        auth_request off;
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:3300;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
    location = /api/send {
        auth_request off;
        limit_except POST OPTIONS { deny all; }
        proxy_pass http://127.0.0.1:3300;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
'''


def patch_apps(text):
    edits, found = [], set()
    for block, end in servers(text):
        directives = block['directives']
        names = set(v for d in directives if d and d[0] == 'server_name' for v in d[1:])
        selected = names & HOSTS
        if not selected:
            continue
        if names - HOSTS:
            raise ValueError('Serveur partage avec un hote hors perimetre : ' + ', '.join(names))
        ssl = any(d and d[0] == 'listen' and any(re.search(r'(^|:)443$', v) for v in d[1:]) for d in directives)
        body = text[block['start']:end]
        host = sorted(selected)[0]
        if not ssl or selected == {'crm.devantiq.com'}:
            canonical = 'g1crm.devantiq.com' if host == 'crm.devantiq.com' else host
            redirect = f'return 308 https://{canonical}$request_uri;'
            # Keep working HTTPS redirects; otherwise force canonical HTTPS
            # before any location can serve an unprotected HTTP origin.
            if redirect not in body and not any(d and d[0] == 'return' and len(d) > 2 and d[1] in ('301', '302', '307', '308') and d[2].startswith('https://') for d in directives):
                edits.append((block['start'] + 1, '\n    if ($uri !~ "^/\\.well-known/acme-challenge/") { ' + redirect + ' }\n'))
            continue
        found.update(selected)
        if INCLUDE in body:
            continue
        if re.search(r'\bauth_request\b|\bsatisfy\s+any\b|\berror_page\s+[^;]*(?:401|403)', body):
            raise ValueError('Protection existante a examiner : ' + host)
        if re.search(r'\breturn\s+200\b', body):
            raise ValueError('Reponse directe pouvant preceder auth_request : ' + host)
        addition = '\n    ' + INCLUDE + '\n'
        # Keep the existing ACME document root and permit certificate renewals.
        for child in block['children']:
            if child['kind'] == 'location' and '/.well-known/acme-challenge/' in child['header']:
                edits.append((child['start'] + 1, '\n        auth_request off;\n'))
        if 'umami.devantiq.com' in selected:
            if '127.0.0.1:3300' not in body or re.search(r'location\s+[^\{]*(?:/script\.js|/api/send)', body):
                raise ValueError('Routage Umami different du releve : verification requise.')
            addition += UMAMI
        edits.append((end, addition))
    for position, value in sorted(edits, reverse=True):
        text = text[:position] + value + text[position:]
    return text, found


def install():
    config = subprocess.run(['nginx', '-T'], capture_output=True, text=True, check=True).stdout
    if re.search(r'^\s*satisfy\s+any\s*;', config, re.M):
        raise RuntimeError('Directive satisfy any detectee : integration manuelle requise.')
    paths = set(Path(p).resolve() for p in re.findall(r'^# configuration file ([^\n]+):$', config, re.M))
    originals, updates, found = {}, {}, set()
    for path in paths:
        original = path.read_text()
        updated, hosts = patch_apps(original)
        found.update(hosts)
        if updated != original:
            originals[path], updates[path] = original, updated
    missing = {f'{app}.devantiq.com' for app in APPS} - found
    if missing:
        raise RuntimeError('Serveurs HTTPS non trouves : ' + ', '.join(sorted(missing)))
    backup = Path('/var/backups/devantiq') / ('members-apps-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, mode=0o700)
    for path in originals:
        saved = backup / str(path).lstrip('/')
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
    snippets = Path('/etc/nginx/snippets/devantiq')
    for name in ('gateway.conf', 'auth-location.conf'):
        target = snippets / name
        originals[target] = target.read_text() if target.exists() else None
        updates[target] = (Path(__file__).parent / 'nginx' / name).read_text()
        if originals[target] is not None:
            (backup / name).write_text(originals[target])
    try:
        for path, value in updates.items():
            path.write_text(value)
            path.chmod(0o644)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    except Exception:
        for path, value in originals.items():
            if value is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(value)
        raise
    print('Controle membres installe sur les applications. Sauvegarde : ' + str(backup))


if __name__ == '__main__':
    install()

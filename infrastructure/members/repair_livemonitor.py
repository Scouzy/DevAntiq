"""Narrow repair of the three inspected systemd services; rollback on failed health checks."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import urlopen
from urllib.error import HTTPError
import uuid

SERVICES = {
    3210: ('livemonitor-backend.service', '/api/health'),
    5173: ('livemonitor-web.service', '/'),
    9099: ('LiveMonitor-agent.service', '/metrics'),
}


def patch_source(source, kind):
    patterns = {
        'backend': r'''(\bserver\.listen\s*\(\s*PORT\s*,\s*)(["'])0\.0\.0\.0\2''',
        'web': r'''(\bconst\s+host\s*=\s*)process\.env\.HOST\s*\|\|\s*(["'])0\.0\.0\.0\2''',
        'agent': r'''(\b(?:http\.server\.)?(?:ThreadingHTTPServer|HTTPServer|TCPServer)\s*\(\s*\(\s*)(["'])0\.0\.0\.0\2''',
        'vite': r'''(\bhost\s*:\s*)true\b''',
    }
    pattern = patterns[kind]
    if len(re.findall(pattern, source)) != 1:
        raise ValueError('Option ecoute non reconnue ou ambigue (' + kind + '). Aucun fichier modifie.')
    return re.sub(pattern, lambda match: match.group(1) + "'127.0.0.1'", source, count=1)


def listeners(port):
    return subprocess.check_output(['ss', '-lntpH', f'( sport = :{port} )'], text=True)


def status(port, path):
    try:
        with urlopen(f'http://127.0.0.1:{port}{path}', timeout=4) as response:
            return response.status
    except HTTPError as error:
        return error.code


def write_atomic(path, data, metadata):
    temp = path.with_name('.devantiq-' + uuid.uuid4().hex + path.suffix)
    try:
        temp.write_bytes(data)
        temp.chmod(metadata.st_mode & 0o777)
        os.chown(temp, metadata.st_uid, metadata.st_gid)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def plan():
    changes = []
    # Complete all discovery and syntax checks before modifying any live file.
    for port, (service, health_path) in SERVICES.items():
        sockets = listeners(port)
        if not sockets.strip():
            raise RuntimeError(f'Port {port} absent : inspection requise.')
        addresses = [line.split()[3].rpartition(':')[0].strip('[]') for line in sockets.splitlines()]
        if all(address in ('127.0.0.1', '::1') for address in addresses):
            print(f'{service} : deja limite a loopback.')
            continue
        pids = set(re.findall(r'pid=(\d+)', sockets))
        if len(pids) != 1:
            raise RuntimeError(f'Proprietaire ambigu du port {port}.')
        proc = Path('/proc') / pids.pop()
        if '/' + service not in (proc / 'cgroup').read_text():
            raise RuntimeError(f'Le port {port} ne correspond plus au service inspecte.')
        args = (proc / 'cmdline').read_bytes().decode().split('\0')
        cwd = (proc / 'cwd').resolve()
        suffixes = ('.py',) if port == 9099 else ('.js', '.mjs', '.cjs')
        candidates = [Path(arg) if Path(arg).is_absolute() else cwd / arg
                      for arg in args[1:] if arg.endswith(suffixes)]
        if len(candidates) != 1:
            raise RuntimeError(f'Fichier de demarrage non reconnu pour {service}.')
        path = candidates[0].resolve(strict=True)
        kind = 'agent' if port == 9099 else 'backend' if port == 3210 else 'web'
        if port == 5173 and path.name == 'vite.js':
            if any(arg == '--host' or arg.startswith('--host=') for arg in args):
                raise RuntimeError('Vite impose --host en ligne de commande : adapter le service avant de poursuivre.')
            path = Path('/opt/LiveMonitor/vite.config.js')
            kind = 'vite'
        if port in (3210, 5173) and Path('/opt/LiveMonitor') not in path.parents:
            raise RuntimeError('Chemin LiveMonitor inattendu.')
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Fichier applicatif inattendu.')
        old = path.read_bytes()
        updated = patch_source(old.decode('utf-8'), kind).encode('utf-8')
        if port == 9099:
            ast.parse(updated.decode('utf-8'), filename=str(path))
        else:
            check = path.with_name('.devantiq-check-' + uuid.uuid4().hex + path.suffix)
            try:
                check.write_bytes(updated)
                result = subprocess.run(['/usr/bin/node', '--check', str(check)], capture_output=True)
                if result.returncode:
                    raise RuntimeError('Validation JavaScript echouee pour ' + str(path))
            finally:
                check.unlink(missing_ok=True)
        baseline = status(port, health_path)
        if baseline >= 500:
            raise RuntimeError(f'{service} est deja en erreur HTTP {baseline}.')
        changes.append((port, service, health_path, path, old, updated, path.stat(), baseline))
    return changes


def install():
    if os.geteuid() != 0:
        raise SystemExit('Executer en root.')
    # Existing proxies must already use the local IPv4 origin, as inventoried.
    nginx = subprocess.run(['nginx', '-T'], capture_output=True, text=True, check=True).stdout
    if re.search(r'proxy_pass\s+https?://(?:212\.227\.39\.182|\[::1\]):(?:3210|5173|9099)\b', nginx):
        raise RuntimeError('Un proxy utilise une autre adresse que loopback IPv4 : adapter son routage avant la correction.')
    changes = plan()
    if not changes:
        print('Les trois services sont deja limites a loopback.')
        return
    backup = Path('/var/backups/devantiq') / ('livemonitor-bind-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, mode=0o700)
    for _, _, _, path, _, _, _, _ in changes:
        saved = backup / str(path).lstrip('/')
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
    (backup / 'services.json').write_text(json.dumps([{'service': entry[1], 'file': str(entry[3])} for entry in changes]))
    print('Sauvegarde privee : ' + str(backup), flush=True)
    applied = []
    try:
        for entry in changes:
            port, service, health_path, path, old, updated, metadata, baseline = entry
            # Reject source changes made since the preflight.
            if path.read_bytes() != old:
                raise RuntimeError('Fichier modifie pendant la preparation : ' + str(path))
            write_atomic(path, updated, metadata)
            applied.append(entry)
            subprocess.run(['systemctl', 'restart', service], check=True)
            for attempt in range(20):
                try:
                    sockets = listeners(port)
                    addresses = [line.split()[3].rpartition(':')[0].strip('[]') for line in sockets.splitlines()]
                    if addresses and all(a == '127.0.0.1' for a in addresses) and status(port, health_path) == baseline:
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError(f'Controle apres redemarrage en echec : {service}')
            print(f'OK : {service}, 127.0.0.1:{port}, HTTP {baseline}', flush=True)
    except Exception:
        for entry in reversed(applied):
            write_atomic(entry[3], entry[4], entry[6])
        for entry in applied:
            subprocess.run(['systemctl', 'restart', entry[1]], check=False)
        print('Sources restaurees apres echec. Sauvegarde : ' + str(backup), flush=True)
        raise


if __name__ == '__main__':
    install()

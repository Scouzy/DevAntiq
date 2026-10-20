"""Add one include to the existing HTTPS site; never replace application blocks."""
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

INCLUDE = 'include /etc/nginx/snippets/devantiq/portal.conf;'
TOKEN = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\#[^\n]*|[{};]|[^\s{};#]+''')


def servers(text):
    if '${' in text:
        raise ValueError('Syntaxe Nginx necessitant une integration manuelle.')
    stack, statement, result = [], [], []
    for match in TOKEN.finditer(text):
        token = match.group()
        if token.startswith('#'):
            continue
        if token == '{':
            stack.append({'kind': statement[0] if statement else '', 'header': list(statement), 'start': match.start(), 'directives': [], 'children': []})
            statement = []
        elif token == '}':
            if not stack or statement:
                raise ValueError('Bloc Nginx non reconnu.')
            block = stack.pop()
            block['end'] = match.start()
            if stack:
                stack[-1]['children'].append(block)
            if block['kind'] == 'server':
                result.append((block, match.start()))
        elif token == ';':
            if stack:
                stack[-1]['directives'].append(statement)
            statement = []
        else:
            statement.append(token.strip('\"\''))
    if stack:
        raise ValueError('Configuration Nginx incomplete.')
    return result


def patch_site(text):
    candidates = []
    for block, end in servers(text):
        directives = block['directives']
        names = [d[1:] for d in directives if d and d[0] == 'server_name']
        ssl = any(d and d[0] == 'listen' and any(re.search(r'(^|:)443$', v) for v in d[1:]) for d in directives)
        if ssl and any('devantiq.com' in name for name in names):
            candidates.append((block, end))
    if len(candidates) != 1:
        raise ValueError('Il faut exactement un serveur HTTPS devantiq.com dans le fichier cible.')
    block, end = candidates[0]
    body = text[block['start']:end]
    if INCLUDE in body:
        return text
    if re.search(r'location\s+[^\{]*(?:/auth|/api/member-session|/membres\.html)', body):
        raise ValueError('Routes membres existantes : comparaison manuelle requise.')
    return text[:end] + '\n    ' + INCLUDE + '\n' + text[end:]


def install():
    config = subprocess.run(['nginx', '-T'], capture_output=True, text=True, check=True).stdout
    paths = set(Path(p).resolve() for p in re.findall(r'^# configuration file ([^\n]+):$', config, re.M))
    matches = []
    for path in paths:
        text = path.read_text()
        for block, _ in servers(text):
            d = block['directives']
            if any(x and x[0] == 'server_name' and 'devantiq.com' in x[1:] for x in d) and any(
                x and x[0] == 'listen' and any(re.search(r'(^|:)443$', v) for v in x[1:]) for x in d):
                matches.append(path)
    if len(matches) != 1:
        raise RuntimeError('Serveur HTTPS ambigu : aucun fichier Nginx modifie.')
    target = matches[0]
    original = target.read_text()
    updated = patch_site(original)
    backup = Path('/var/backups/devantiq') / ('members-nginx-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(target, backup / target.name)
    snippets = Path('/etc/nginx/snippets/devantiq')
    snippets.mkdir(parents=True, exist_ok=True)
    destination = snippets / 'portal.conf'
    old_snippet = destination.read_bytes() if destination.exists() else None
    if old_snippet is not None:
        (backup / 'portal.conf.previous').write_bytes(old_snippet)
    try:
        shutil.copyfile(Path(__file__).parent / 'nginx/portal.conf', destination)
        destination.chmod(0o644)
        target.write_text(updated)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    except Exception:
        target.write_text(original)
        if old_snippet is None:
            destination.unlink(missing_ok=True)
        else:
            destination.write_bytes(old_snippet)
        raise
    print('Connexion installee. Sauvegarde Nginx : ' + str(backup))


if __name__ == '__main__':
    install()

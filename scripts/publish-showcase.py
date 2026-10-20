"""Build a public-only bundle locally, or install it on the VPS with backups."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid

FILES = [
    'index.html', 'g1club.html', 'g1sport.html', 'g1oeil.html', 'noteazy.html',
    'mycareer.html', 'g1tournoi.html', 'membres.html', 'sitemap.xml',
    'css/devantiq.css', 'css/membres.css', 'js/product.js', 'js/membres.js', 'js/membres-motion.js',
    'img/mycareer-logo.png', 'img/g1tournoi-logo.png',
    'css/experience.css', 'js/experience.js',
    'caroussel/mycareer/accueil.png', 'caroussel/g1tournoi/accueil.png',
    'img/members/g1crm-landing.png',
    'img/members/g1profil-landing.png',
    'img/members/sentinet-landing.png',
    'img/members/livemonitor-landing.png',
    'img/members/umami-landing.png',
    'img/members/cloud-landing.png',
    'img/members/n8n-landing.png',
    'img/members/omniroute-landing.png',
    'img/members/zabbix-landing.png',
    'img/members/cloud-scene.svg',
    'img/members/cloud.svg',
    'img/members/g1crm-scene.svg',
    'img/members/g1crm.png',
    'img/members/g1profil-scene.svg',
    'img/members/g1profil.svg',
    'img/members/livemonitor-scene.svg',
    'img/members/livemonitor.png',
    'img/members/n8n-scene.svg',
    'img/members/n8n.svg',
    'img/members/omniroute-scene.svg',
    'img/members/omniroute.svg',
    'img/members/sentinet-scene.svg',
    'img/members/sentinet.svg',
    'img/members/umami-scene.svg',
    'img/members/umami.svg',
    'img/members/zabbix-scene.svg',
    'img/members/zabbix.svg',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(data):
    return digest(data.replace(b'\r\n', b'\n'))


def public_directory(directory, root):
    """Create public directories independently of the private staging umask."""
    if directory == root:
        return
    if directory.is_symlink() or root not in directory.resolve().parents:
        raise RuntimeError('Repertoire public inattendu : ' + str(directory))
    if not directory.exists():
        public_directory(directory.parent, root)
        directory.mkdir()
        directory.chmod(0o755)


def pack(output):
    root = Path(__file__).resolve().parent.parent
    reviewed_path = root / 'scripts' / 'showcase-reviewed-baseline.json'
    reviewed = json.loads(reviewed_path.read_text()) if reviewed_path.exists() else None
    if reviewed is not None and set(reviewed) != set(FILES):
        raise RuntimeError('Reference VPS incomplete : nouvelle comparaison requise.')
    manifest = {}
    with tarfile.open(output, 'w:gz') as bundle:
        for name in FILES:
            content = (root / name).read_bytes()
            baseline = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=root,
                                      capture_output=True, check=False)
            manifest[name] = {'sha256': digest(content),
                              'baseline': normalized(baseline.stdout) if baseline.returncode == 0 else None}
            if reviewed is not None:
                if digest(content) != reviewed[name]['local_sha256']:
                    raise RuntimeError('Fichier local modifie depuis la comparaison : ' + name)
                manifest[name]['reviewed'] = reviewed[name]['remote_sha256']
            info = tarfile.TarInfo('public/' + name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
        for name, content in [('manifest.json', json.dumps(manifest).encode()),
                              ('publish-showcase.py', Path(__file__).read_bytes())]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    print('Archive publique preparee : ' + str(output))


def install(stage, root=Path('/var/www/devantiq'), backup_root=Path('/var/backups/devantiq')):
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError('Racine web absente ou lien symbolique : inspection requise.')
    manifest = json.loads((stage / 'manifest.json').read_text())
    if set(manifest) != set(FILES):
        raise RuntimeError('Liste de fichiers inattendue.')
    changes = []
    # Validate EVERYTHING before the first public write.
    for name in FILES:
        source = stage / 'public' / name
        target = root / name
        if target.is_symlink() or root not in target.resolve().parents:
            raise RuntimeError('Chemin public inattendu : ' + name)
        data = source.read_bytes()
        if digest(data) != manifest[name]['sha256']:
            raise RuntimeError('Empreinte incorrecte : ' + name)
        if target.exists():
            old = target.read_bytes()
            if digest(old) == digest(data):
                continue
            matches = (digest(old) == manifest[name]['reviewed'] if 'reviewed' in manifest[name]
                       else normalized(old) == manifest[name]['baseline'])
            if not matches:
                raise RuntimeError('Fichier distant different du depot : ' + name + '. Aucun fichier publie.')
        elif manifest[name].get('reviewed', manifest[name]['baseline']) is not None:
            raise RuntimeError('Fichier attendu absent du VPS : ' + name)
        changes.append(name)
    backup = backup_root / ('showcase-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, mode=0o700 if os.name != 'nt' else 0o777)
    existing = {}
    for name in changes:
        target = root / name
        existing[name] = target.exists()
        if existing[name]:
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
    (backup / 'files.json').write_text(json.dumps(existing))
    applied = []
    try:
        for name in changes:
            target = root / name
            public_directory(target.parent, root)
            temp = target.with_name('.' + target.name + '.devantiq-' + uuid.uuid4().hex)
            try:
                temp.write_bytes((stage / 'public' / name).read_bytes())
                temp.chmod(0o644)
                owner = target.stat() if target.exists() else target.parent.stat()
                os.chown(temp, owner.st_uid, owner.st_gid)
                os.replace(temp, target)
                applied.append(name)
            finally:
                temp.unlink(missing_ok=True)
        # Repair the two screenshot folders created with mode 0700 by the
        # previous installer. Do this even when file contents already match.
        for name in ('caroussel/mycareer', 'caroussel/g1tournoi'):
            directory = root / name
            public_directory(directory, root)
            directory.chmod(0o755)
    except Exception:
        for name in reversed(applied):
            if existing[name]:
                shutil.copy2(backup / name, root / name)
            else:
                (root / name).unlink()
        raise
    print('Publication terminee : ' + str(len(changes)) + ' fichiers. Sauvegarde : ' + str(backup))
    print('La configuration Nginx et les applications VPS sont inchangees.')


if __name__ == '__main__':
    if sys.argv[1:] == ['list']:
        print('\n'.join(FILES))
        raise SystemExit(0)
    if len(sys.argv) != 3 or sys.argv[1] not in ('pack', 'install'):
        raise SystemExit('Usage: publish-showcase.py pack ARCHIVE | install DOSSIER')
    if sys.argv[1] == 'pack':
        pack(Path(sys.argv[2]))
    else:
        install(Path(sys.argv[2]).resolve())

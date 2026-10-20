"""Package only the service source and reviewed public bundle; never runtime data."""
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import uuid
import shutil

root = Path(__file__).resolve().parent.parent
source = root / 'infrastructure/members'
spec = importlib.util.spec_from_file_location('publisher', Path(__file__).with_name('publish-showcase.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
scratch = root / '.vps-inspection' / ('pack-' + uuid.uuid4().hex)
scratch.mkdir(parents=True)
try:
    public = scratch / 'public.tar.gz'
    publisher.pack(public)
    with tarfile.open(sys.argv[1], 'w:gz') as bundle:
        paths = [source / name for name in ('compose.yml', 'configure.py', 'install.sh', 'nginx_portal.py', 'protect_apps.py', 'verify_origins.py')]
        paths += list((source / 'nginx').glob('*.conf'))
        paths += [p for p in (source / 'service').rglob('*') if p.is_file()
                  and not any(part in ('data', 'staticfiles', '__pycache__') for part in p.relative_to(source).parts)
                  and (p.suffix in ('.py', '.html', '.txt') or p.name in ('Dockerfile', '.dockerignore'))]
        for path in paths:
            data = path.read_bytes().replace(b'\r\n', b'\n')
            info = tarfile.TarInfo(str(path.relative_to(source)).replace('\\', '/'))
            info.size = len(data)
            info.mode = 0o644
            bundle.addfile(info, io.BytesIO(data))
        bundle.add(public, arcname='public.tar.gz')
finally:
    assert scratch.resolve().parent == (root / '.vps-inspection').resolve()
    shutil.rmtree(scratch)
print('Service et fichiers publics prepares, sans compte ni secret.')

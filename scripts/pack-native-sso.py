import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid

root=Path(__file__).resolve().parents[1]
adapters=root/'infrastructure/members/adapters'
spec=importlib.util.spec_from_file_location('build_native',adapters/'build_bundle.py')
build=importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
stage=root/'.vps-inspection'/('native-build-'+uuid.uuid4().hex)
stage.mkdir()
source=Path(sys.argv[1]).resolve()
with tarfile.open(source) as bundle:
    bundle.extractall(stage/'inspected',filter='data')
build.build(stage/'inspected',stage/'native')
if not (adapters/'node_modules/openid-client/package.json').is_file():
    raise SystemExit('Dependances OIDC locales absentes : npm ci requis dans infrastructure/members/adapters.')
for app,entry in build.ENTRIES.items():
    target=(stage/'native'/app/entry).parent/'devantiq-sso'
    shutil.copytree(adapters/'node_modules',target/'node_modules')
    subprocess.run(['node','--check',str(stage/'native'/app/entry)],check=True)
subprocess.run([sys.executable,str(root/'scripts/pack-members.py'),str(stage/'members.tar.gz')],check=True)
shutil.copyfile(adapters/'install_native.py',stage/'install_native.py')
with tarfile.open(sys.argv[2],'w:gz') as bundle:
    for name in ('native','members.tar.gz','install_native.py'):
        bundle.add(stage/name,arcname=name)
print('Paquet prepare sans comptes ni secrets : '+sys.argv[2])

"""Collect authentication code and deployment metadata; never export runtime secrets."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile


def command(args):
    result = subprocess.run(args, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Inspection impossible : '+args[0]+' (sortie privee masquee)')
    return result.stdout


def nginx_routes(text):
    """Export only structural routing directives, not headers/passwords/config values."""
    allowed = ('server_name ', 'listen ', 'root ', 'location ', 'fastcgi_pass ',
               'proxy_pass ', 'auth_request ', 'include ')
    result = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(allowed) and not re.search(r'https?://[^/\s]*@|[?]', line):
            result.append(line)
        elif line in ('server {', '}', '};'):
            result.append(line)
    return '\n'.join(result)


CONTAINER_CODE = r'''
const fs=require('fs'), path=require('path');
const output=[];
const selected = [
 '/app/package.json', '/app/prisma/schema.prisma',
 '/app/src/lib/auth.ts', '/app/src/lib/jwt.ts', '/app/src/lib/crypto.ts',
 '/app/src/lib/constants.ts', '/app/src/lib/request.ts', '/app/src/lib/prisma.ts',
 '/app/src/lib/redis.ts', '/app/src/store/useLoginStore.ts',
 '/app/src/app/api/auth', '/app/src/app/api/users', '/app/src/queries/prisma',
 '/app/src/app/(login)', '/app/src/app/login',
 '/app/src/app/api/settings', '/app/src/server/authz',
 '/app/src/shared/utils/apiAuth.ts', '/app/src/lib/api/requireManagementAuth.ts',
 '/app/src/lib/db', '/app/src/lib/db.js', '/app/src/lib/db.ts',
 '/app/db/prisma/schema.prisma',
 '/app/.next/server/app/api/auth', '/app/.next/server/app/api/users',
 '/app/.next/server/app/api/settings'
];
let total=0;
function visit(p) {
 if(!fs.existsSync(p))return;
 const st=fs.lstatSync(p);
 if(st.isSymbolicLink())return;
 if(st.isDirectory()) { for(const n of fs.readdirSync(p)) visit(path.join(p,n)); return; }
 if(!st.isFile() || (!/\.(ts|tsx|js|mjs|prisma)$/.test(p)&&p!='/app/package.json'))return;
 if(st.size>5000000 || total+st.size>20000000)return;
 total+=st.size;
 output.push({path:p,content:fs.readFileSync(p).toString('base64')});
}
for(const p of selected)visit(p);
console.log(JSON.stringify(output));
'''


def collect(destination):
    import base64
    os.umask(0o077)
    metadata = {'containers':{}, 'zabbix':{}, 'nginx':{}}
    manifest = {}
    with tarfile.open(destination, 'w:gz') as archive:
        def add(name, content):
            info=tarfile.TarInfo(name); info.size=len(content); info.mode=0o600
            archive.addfile(info,io.BytesIO(content))
            manifest[name]=hashlib.sha256(content).hexdigest()
        for app, container in [('umami','umami_app'),('omniroute','omniroute')]:
            # Parse inspect in memory; export only deployment fields, never Config.Env.
            raw=json.loads(command(['docker','inspect',container]))[0]
            metadata['containers'][app] = {
                'image_id':raw['Image'], 'image':raw['Config']['Image'],
                'ports':raw['NetworkSettings']['Ports'],
                'mounts':[{'source':m['Source'],'destination':m['Destination'],'type':m['Type']} for m in raw['Mounts']],
                'compose_files':raw['Config'].get('Labels',{}).get('com.docker.compose.project.config_files'),
                'compose_directory':raw['Config'].get('Labels',{}).get('com.docker.compose.project.working_dir'),
            }
            rows=json.loads(command(['docker','exec',container,'node','-e',CONTAINER_CODE]))
            seen=set()
            for row in rows:
                path=row['path']
                if path in seen: continue
                seen.add(path)
                add(app+'/'+path.removeprefix('/app/'),base64.b64decode(row['content']))
        package_paths=command(['dpkg-query','-L','zabbix-frontend-php']).decode().splitlines()
        wanted=('index_http.php','include/classes/api/services/CAuthentication.php',
                'include/classes/api/services/CUser.php','include/classes/api/services/CUserGroup.php',
                'include/classes/user/CWebUser.php')
        for value in package_paths:
            path=Path(value)
            if path.is_file() and not path.is_symlink() and any(value.endswith('/'+tail) for tail in wanted):
                add('zabbix/'+next(tail for tail in wanted if value.endswith('/'+tail)),path.read_bytes())
        metadata['zabbix']['version']=command(['dpkg-query','-W','-f=${Version}','zabbix-frontend-php']).decode()
        for directory in ('/etc/nginx/sites-enabled','/etc/nginx/conf.d'):
            for path in sorted(Path(directory).glob('*')):
                if not path.is_file(): continue
                content=path.read_text()
                if not any(host+'.devantiq.com' in content for host in ('zabbix','umami','omniroute')): continue
                metadata['nginx'][str(path)]={'sha256':hashlib.sha256(content.encode()).hexdigest(),
                                             'routes':nginx_routes(content)}
        add('inspection.json',json.dumps(metadata,indent=2).encode())
        add('manifest.json',json.dumps(manifest,indent=2).encode())
    print('Inspection preparee : Zabbix, Umami, OmniRoute. Aucun compte ou service modifie.')


if __name__=='__main__':
    try: collect(sys.argv[1])
    except Exception as error:
        raise SystemExit('Inspection interrompue ('+type(error).__name__+'). Aucun secret affiche.')

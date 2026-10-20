param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$inspect = @'
python3 - <<'PY'
import json, pathlib, subprocess
print('--- Images installees (sans variables ni secrets) ---')
subprocess.run(['docker', 'ps', '--format', '{{.Names}} | {{.Image}}'], check=True)
print('--- Versions des projets locaux du VPS ---')
roots = [pathlib.Path('/opt'), pathlib.Path('/var/www')]
for root in roots:
    candidates = list(root.glob('*/package.json')) + list(root.glob('*/*/package.json'))
    for path in sorted(candidates):
        if any(part in ('node_modules', '.git') for part in path.parts):
            continue
        try:
            package = json.loads(path.read_text())
            dependencies = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
            auth = {k:v for k,v in dependencies.items() if any(word in k for word in ('auth', 'saml', 'openid', 'passport', 'oauth'))}
            print(json.dumps({'path': str(path), 'name': package.get('name'), 'version':package.get('version'), 'authentication_libraries':auth}))
        except (ValueError, OSError):
            print(str(path) + ' : lecture impossible')
print('--- Version Zabbix si installe par paquet ---')
subprocess.run(['dpkg-query', '-W', '-f=${Package} ${Version}\n', 'zabbix-frontend-php'], check=False)
print('--- Versions exactes des conteneurs ---', flush=True)
subprocess.run(['docker', 'exec', 'n8n', 'n8n', '--version'], check=False, timeout=40)
for container in ('umami_app', 'omniroute'):
    script = "const fs=require('fs'); for(const p of ['/app/package.json','/app/apps/web/package.json','/usr/src/app/package.json']) {if(fs.existsSync(p)){const x=JSON.parse(fs.readFileSync(p)); console.log(JSON.stringify({path:p,name:x.name,version:x.version}));}}"
    print(container, flush=True)
    subprocess.run(['docker', 'exec', container, 'node', '-e', script], check=False, timeout=20)
print('--- Nextcloud : version et modules de connexion ---', flush=True)
subprocess.run(['docker', 'exec', '-u', 'www-data', 'nextcloud_app', 'php', 'occ', 'status', '--output=json'], check=False, timeout=30)
result = subprocess.run(['docker', 'exec', '-u', 'www-data', 'nextcloud_app', 'php', 'occ', 'app:list', '--output=json'], capture_output=True, text=True, timeout=30)
if result.returncode == 0:
    try:
        groups = json.loads(result.stdout)
        for group, apps in groups.items():
            if isinstance(apps, dict):
                print(json.dumps({group: {k:v for k,v in apps.items() if any(word in k for word in ('oidc','saml','oauth','ldap'))}}))
    except ValueError:
        print('Liste des modules non interpretable ; aucun contenu brut affiche.')
else:
    print('Liste des modules Nextcloud indisponible.')
print('Inspection terminee. Aucun compte ou service modifie.')
PY
'@
Write-Host 'Inventaire SSO en lecture seule. Saisissez le mot de passe SSH.'
& $ssh $Server ($inspect -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Inspection interrompue. Transmettre le diagnostic sans mot de passe.' }

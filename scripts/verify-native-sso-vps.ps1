param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$script = @'
python3 - <<'PY'
import json, pathlib, subprocess
from urllib.request import Request, urlopen
from urllib.error import HTTPError
apps = {
 'g1crm':('/opt/g1crm/project/server',3001),
 'g1profil':('/opt/G1Profil/server/src',3220),
 'livemonitor':('/opt/LiveMonitor/backend',3210),
 'sentinet':('/var/www/sentinet/sentinet-app/server',3010),
}
for app,(folder,port) in apps.items():
    files = {name:(pathlib.Path(folder)/'devantiq-sso'/name).is_file()
             for name in ('connector.mjs','client.json','node_modules/openid-client/package.json')}
    status = None
    guarded = False
    try:
        req = Request('http://127.0.0.1:'+str(port)+'/api/auth/sso/login',headers={'Host':app+'.devantiq.com'})
        with urlopen(req,timeout=8) as response:
            status=response.status
    except HTTPError as error:
        status=error.code
        guarded=status==403 and b'Connexion DevAntiq refus' in error.read(4096)
    except OSError:
        pass
    print(json.dumps({'application':app,'adapter_files':files,'http_status':status,'rejects_anonymous':guarded}),flush=True)
code = """
import json
from portal.models import Application, SSOClient, Access, AccountLink
for slug in ('g1crm','g1profil','livemonitor','sentinet'):
    app=Application.objects.filter(pk=slug).first()
    client=SSOClient.objects.filter(application_id=slug).first()
    grants=Access.objects.filter(application_id=slug,user__is_active=True)
    linked=AccountLink.objects.filter(application_id=slug,access__in=grants).exclude(external_id='').count()
    print(json.dumps({'application':slug,'application_enabled':bool(app and app.enabled),
      'sso_enabled':bool(client and client.enabled),'login_path':client.login_path if client else None,
      'dedicated_accounts':getattr(client,'dedicated_accounts',False),
      'active_grants':grants.count(),'linked_accounts':linked}))
"""
result=subprocess.run(['docker','compose','exec','-T','members','python','manage.py','shell','--no-imports','-c',code],cwd='/opt/devantiq-members',capture_output=True,text=True,timeout=45)
if result.returncode:
    print('Etat central indisponible : commande Django en echec. Sortie privee masquee.')
else:
    # Only print the JSON status objects we requested, never unrelated logs.
    for line in result.stdout.splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict) and row.get('application') in apps and 'sso_enabled' in row:
                print(json.dumps(row))
        except ValueError: pass
print('Verification terminee, sans modification. Une connexion navigateur reste necessaire pour valider le parcours complet.')
PY
'@
Write-Host 'Verification SSO en lecture seule. Saisissez le mot de passe SSH.'
& (Join-Path $sshDir 'ssh.exe') $Server ($script -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Verification interrompue.' }

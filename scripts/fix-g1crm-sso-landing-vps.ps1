param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$id = [guid]::NewGuid().ToString('N')
$remote = "/var/tmp/devantiq-crm-landing-$id"
$connector = Join-Path $root 'infrastructure\members\adapters\connector.mjs'
$runtime = Join-Path $root 'infrastructure\members\adapters\install_native.py'
$hash = (Get-FileHash $connector -Algorithm SHA256).Hash.ToLowerInvariant()
$runtimeHash = (Get-FileHash $runtime -Algorithm SHA256).Hash.ToLowerInvariant()
& (Join-Path $sshDir 'scp.exe') $connector "${Server}:$remote.mjs"
if ($LASTEXITCODE -ne 0) { throw 'Transfert connecteur interrompu.' }
& (Join-Path $sshDir 'scp.exe') $runtime "${Server}:$remote.py"
if ($LASTEXITCODE -ne 0) { throw 'Transfert controle interrompu.' }
$command = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$remote.mjs' '$runtimeHash' '$remote.py' | sha256sum -c -
python3 - <<'PY'
from pathlib import Path
import hashlib, importlib.util, shutil, uuid
spec=importlib.util.spec_from_file_location('runtime','$remote.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
target=Path('/opt/g1crm/project/server/devantiq-sso/connector.mjs')
if target.is_symlink(): raise SystemExit('Lien symbolique inattendu')
before=hashlib.sha256(target.read_bytes()).hexdigest()
if before=='$hash':
    print('Correction deja presente. Aucun redemarrage.'); raise SystemExit(0)
if before!='0d1df72821c56729e5bf5746766492c9092f5dda037b95f8e0f917b5841d0c63':
    raise SystemExit('Connecteur distant different : examen requis, aucun fichier modifie.')
runtime=module.runtime(Path('/opt/g1crm/project/server/index.js'))
module.run([runtime['node'],'--check','$remote.mjs'])
backup=Path('/var/backups/devantiq')/('g1crm-landing-'+uuid.uuid4().hex)
backup.mkdir(parents=True,mode=0o700)
shutil.copy2(target,backup/'connector.mjs')
try:
    shutil.copyfile('$remote.mjs',target)
    module.restart_runtime(runtime)
    module.health('g1crm',runtime['port'])
except Exception:
    shutil.copyfile(backup/'connector.mjs',target)
    module.restart_runtime(runtime)
    raise SystemExit('Correction annulee. Connecteur restaure. Sauvegarde : '+str(backup))
print('G1CRM : redirection SSO vers /dashboard corrigee. Sauvegarde : '+str(backup))
PY
"@
Write-Host 'Correction ciblee : seul le serveur G1CRM sera redemarre. Comptes conserves.'
& (Join-Path $sshDir 'ssh.exe') $Server ($command -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Correction interrompue. Transmettre le diagnostic sans mot de passe.' }

param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'infrastructure/members/service/portal/management/commands/verify_gateway.py'
$remote = '/var/tmp/devantiq-verify-' + [guid]::NewGuid().ToString('N') + '.py'
$hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host '1/2 Transfert du controle corrige. Saisissez le mot de passe SSH.'
& $scp $source "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$check = @"
set -eu
printf '%s  %s\n' '$hash' '$remote' | sha256sum -c -
cd /opt/devantiq-members
python3 verify_origins.py
python3 - '$remote' <<'PY'
import ast, pathlib, shutil, sys, uuid
source = pathlib.Path(sys.argv[1])
ast.parse(source.read_text())
target = pathlib.Path('service/portal/management/commands/verify_gateway.py')
backup = pathlib.Path('/var/backups/devantiq') / ('gateway-check-' + uuid.uuid4().hex)
backup.mkdir(mode=0o700, parents=True)
shutil.copy2(target, backup / target.name)
shutil.copyfile(source, target)
print('Sauvegarde : ' + str(backup))
PY
docker compose exec -T members python manage.py shell -c "exec(compile(open('/dev/stdin').read(), 'verify_gateway.py', 'exec')); Command().handle()" < '$remote'
"@
Write-Host '2/2 Verification des protections et activation si tous les controles passent.'
& $ssh $Server ($check -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Controle interrompu. Transmettre le diagnostic affiche sans mot de passe.' }

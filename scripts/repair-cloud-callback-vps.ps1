param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'infrastructure/members/repair_cloud_callback.py'
$remote = '/var/tmp/devantiq-cloud-callback-' + [guid]::NewGuid().ToString('N') + '.py'
$hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host '1/2 Transfert du correctif. Saisissez votre mot de passe SSH.'
& (Join-Path $sshDir 'scp.exe') $source "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$command = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$remote' | sha256sum -c -
cd /opt/devantiq-members
docker compose exec -T members python manage.py shell --no-imports -c "exec(compile(open('/dev/stdin').read(), 'repair-cloud-callback', 'exec')); main()" < '$remote'
"@
Write-Host '2/2 Verification du client, sauvegarde et correction de son adresse de retour.'
& (Join-Path $sshDir 'ssh.exe') $Server ($command -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Correction interrompue. Transmettre le diagnostic sans mot de passe.' }

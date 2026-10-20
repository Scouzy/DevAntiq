param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'infrastructure/members/repair_livemonitor.py'
$remote = '/var/tmp/devantiq-repair-' + [guid]::NewGuid().ToString('N') + '.py'
$hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host '1/2 Transfert du correctif cible. Saisissez le mot de passe SSH.'
& $scp $source "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$finish = @"
set -eu
printf '%s  %s\n' '$hash' '$remote' | sha256sum -c -
python3 '$remote'
cd /opt/devantiq-members
python3 verify_origins.py
python3 protect_apps.py
docker compose exec -T members python manage.py verify_gateway
printf '\nEspace membres active. Attribuez les applications depuis https://devantiq.com/auth/admin/\n'
"@
Write-Host '2/2 Sauvegarde, correction des ecoutes LiveMonitor et reprise de l activation.'
Write-Host 'Les trois services LiveMonitor peuvent etre interrompus quelques secondes pendant leur redemarrage.'
& $ssh $Server ($finish -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Finalisation interrompue. Conserver les lignes de diagnostic precedentes.' }

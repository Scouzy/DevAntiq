param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$token = [guid]::NewGuid().ToString('N')
$destination = Join-Path $project ".vps-inspection\$token"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
# Reuse the exact public-file allowlist; never collect configuration or secrets.
$files = & python (Join-Path $PSScriptRoot 'publish-showcase.py') list
if ($LASTEXITCODE -ne 0 -or -not $files) { throw 'Liste des fichiers indisponible.' }
foreach ($name in $files) {
    if ($name -notmatch '^[a-zA-Z0-9_/-]+\.[a-zA-Z0-9]+$' -or $name.Contains('..')) {
        throw 'Chemin public invalide.'
    }
}
$fileArgs = ($files | ForEach-Object { "'$_'" }) -join ' '
$remote = "/var/tmp/devantiq-inspection-$token.tar.gz"
$inspect = @"
set -eu
umask 077
cd /var/www/devantiq
set --
for file in $fileArgs; do
    if [ -f "`$file" ] && [ ! -L "`$file" ]; then
        set -- "`$@" "`$file"
    fi
done
[ "`$#" -gt 0 ]
tar -czf '$remote' -- "`$@"
"@
Write-Host '1/2 Copie privee des fichiers publics du VPS. Saisissez le mot de passe SSH.'
& $ssh $Server ($inspect -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Collecte interrompue. Le site est inchange.' }
$archive = Join-Path $destination 'site-vps.tar.gz'
Write-Host '2/2 Recuperation pour comparaison. Saisissez le mot de passe SSH.'
& $scp "${Server}:$remote" $archive
if ($LASTEXITCODE -ne 0) { throw 'Recuperation interrompue. Le site est inchange.' }
Write-Host "Copie recuperee : $archive"
Write-Host 'Le site public est inchange. Revenez dans Codex pour comparer cette copie avant publication.'

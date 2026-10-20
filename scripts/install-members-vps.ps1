param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$token = [guid]::NewGuid().ToString('N')
$archive = Join-Path ([IO.Path]::GetTempPath()) "devantiq-members-$token.tar.gz"
$remote = "/var/tmp/devantiq-members-$token.tar.gz"
& python (Join-Path $PSScriptRoot 'pack-members.py') $archive
if ($LASTEXITCODE -ne 0) { throw 'Preparation impossible.' }
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host '1/2 Transfert du service. Saisissez le mot de passe SSH.'
& $scp $archive "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$deploy = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$remote' | sha256sum -c -
for path in /opt/devantiq-members /opt/devantiq-members/config /opt/devantiq-members/data /opt/devantiq-members/static; do
    if [ -L "`$path" ]; then echo 'Lien symbolique inattendu : installation interrompue.'; exit 1; fi
done
if [ -d /opt/devantiq-members ]; then
    mkdir -p /var/backups/devantiq
    tar --exclude='./data' --exclude='./static' --exclude='./public-stage' -czf '/var/backups/devantiq/members-$token.tar.gz' -C /opt/devantiq-members .
    if [ -f /opt/devantiq-members/data/members.sqlite3 ]; then
        python3 -c "import sqlite3; s=sqlite3.connect('/opt/devantiq-members/data/members.sqlite3'); d=sqlite3.connect('/var/backups/devantiq/members-$token.sqlite3'); s.backup(d); d.close(); s.close()"
    fi
fi
mkdir -p /opt/devantiq-members
chmod 755 /opt/devantiq-members
tar -xzf '$remote' -C /opt/devantiq-members --no-same-owner --no-same-permissions
cd /opt/devantiq-members
sh install.sh
"@
Write-Host '2/2 Installation ou mise a jour. Les comptes et parametres SMTP existants sont conserves.'
& $ssh -t $Server ($deploy -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Installation interrompue. Transmettre le diagnostic sans mot de passe.' }
foreach ($page in @('auth/', 'membres.html')) {
    $response = Invoke-WebRequest "https://devantiq.com/$page" -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -ne 200) { throw "Verification HTTP en echec : $page" }
    Write-Host "OK : https://devantiq.com/$page"
}

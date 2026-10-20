param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') | Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$template = Join-Path $project 'infrastructure/members/service/templates/registration/base.html'
$hash = (Get-FileHash $template -Algorithm SHA256).Hash.ToLowerInvariant()
$token = [guid]::NewGuid().ToString('N')
$stage = "/var/tmp/devantiq-auth-$token"
$backup = "/var/backups/devantiq/auth-$token"
Write-Host 'Preparation de la page de connexion. Saisissez votre mot de passe SSH.'
& $ssh $Server "set -eu; test -f /opt/devantiq-members/compose.yml; test -f /opt/devantiq-members/service/templates/registration/base.html; mkdir -m 700 '$stage'"
if ($LASTEXITCODE -ne 0) { throw 'Preparation interrompue.' }
& $scp $template "${Server}:${stage}/base.html"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$deploy = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$stage/base.html' | sha256sum -c -
cd /opt/devantiq-members
for dir in /opt/devantiq-members service service/templates service/templates/registration; do test ! -L "`$dir"; done
test ! -L service/templates/registration/base.html
container=`$(docker compose ps -q members)
test -n "`$container"
image=`$(docker inspect --format '{{.Image}}' "`$container")
mkdir -m 700 -p '$backup'
cp -p service/templates/registration/base.html '$backup/base.html'
docker tag "`$image" devantiq-members-backup:$token
printf 'services:\n  members:\n    image: devantiq-members-backup:$token\n' > '$backup/rollback.yml'
rollback() {
    cp -p '$backup/base.html' service/templates/registration/base.html
    docker compose -f compose.yml -f '$backup/rollback.yml' up -d --no-deps --no-build members
    echo 'Ancienne version restauree. Sauvegarde : $backup'
}
install -m 644 '$stage/base.html' service/templates/registration/base.html
if ! docker compose build members; then rollback; exit 1; fi
if ! docker compose up -d --no-deps members; then rollback; exit 1; fi
healthy=0
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS -H 'Host: devantiq.com' -H 'X-Forwarded-Proto: https' http://127.0.0.1:9092/auth/ > '$stage/result.html' && grep -q 'auth-sculpture' '$stage/result.html'; then healthy=1; break; fi
    sleep 2
done
if [ "`$healthy" != 1 ]; then rollback; exit 1; fi
echo 'Page de connexion mise a jour. Sauvegarde : $backup'
"@
& $ssh $Server ($deploy -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw "Publication de la connexion interrompue. Sauvegarde : $backup" }
& (Join-Path $PSScriptRoot 'publish-members-design.ps1') -Server $Server
$response = Invoke-WebRequest "https://devantiq.com/auth/?v=$token" -UseBasicParsing -TimeoutSec 30
if ($response.StatusCode -ne 200 -or $response.Content -notmatch 'auth-sculpture') { throw 'La nouvelle page de connexion publique ne peut pas etre confirmee.' }
Write-Host 'Publication verifiee : https://devantiq.com/auth/ et https://devantiq.com/membres.html'

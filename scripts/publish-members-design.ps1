param([string]$Server = 'root@212.227.39.182', [switch]$IncludeHome)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') | Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$files = @('css/membres.css','js/membres.js','js/membres-motion.js','membres.html')
if ($IncludeHome) { $files = @('css/experience.css') + $files + @('index.html') }
$remoteFiles = $files -join ' '
$localFiles = @()
$checks = @()
foreach ($file in $files) {
    $path = Join-Path $project $file
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Fichier manquant : $file" }
    $localFiles += $path
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $checks += "$hash  $([IO.Path]::GetFileName($file))"
}
$token = [guid]::NewGuid().ToString('N')
$stage = "/var/tmp/devantiq-members-design-$token"
$backup = "/var/backups/devantiq/members-design-$token"
Write-Host '1/3 Preparation. Saisissez le mot de passe SSH.'
& $ssh $Server "set -eu; test -f /var/www/devantiq/membres.html; test -d /var/www/devantiq/css; test -d /var/www/devantiq/js; mkdir -m 700 '$stage'"
if ($LASTEXITCODE -ne 0) { throw 'Preparation interrompue. Aucun fichier public modifie.' }
Write-Host '2/3 Transfert des fichiers du design. Saisissez le mot de passe SSH.'
& $scp @localFiles "${Server}:${stage}/"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu. Aucun fichier public modifie.' }
$checksumText = $checks -join "`n"
$deploy = @"
set -eu
umask 077
cd '$stage'
sha256sum -c - <<'CHECKSUMS'
$checksumText
CHECKSUMS
cd /var/www/devantiq
for file in $remoteFiles; do
    test ! -L "`$file"
done
test ! -L css
test ! -L js
mkdir -p '$backup/css' '$backup/js'
chmod 700 '$backup'
for file in $remoteFiles; do
    if [ -f "`$file" ]; then cp -p -- "`$file" '$backup/'"`$file"; fi
done
for file in $remoteFiles; do
    name=`$(basename "`$file")
    install -m 644 '$stage/'"`$name" "`$file.$token.part"
    mv -- "`$file.$token.part" "`$file"
done
echo 'Publication terminee. Sauvegarde : $backup'
"@
Write-Host '3/3 Verification, sauvegarde et publication. Saisissez le mot de passe SSH.'
& $ssh $Server ($deploy -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw "Publication interrompue. Conservez le diagnostic. Sauvegarde : $backup" }
Write-Host 'Verification des fichiers publics...'
foreach ($file in $files) {
    $response = Invoke-WebRequest ("https://devantiq.com/$file" + '?v=' + $token) -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -ne 200) { throw "Fichier indisponible : $file" }
    Write-Host "OK : $file"
}
Write-Host 'Espace Membres publie : https://devantiq.com/membres.html'
Write-Host 'Aucun service redemarre. Comptes et droits inchanges.'

if ($IncludeHome) { Write-Host 'Accueil publie : https://devantiq.com/' }

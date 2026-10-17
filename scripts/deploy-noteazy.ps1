param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$installer = Join-Path $project 'downloads/noteazy/NotEazy-Setup-1.0.37.exe'
$page = Join-Path $project 'noteazy.html'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
if (-not (Test-Path $installer)) { throw "Installateur introuvable : $installer" }
$installerHash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installerHash -ne '3bb156b31b91e47b77dd66a05e644163657ef907797a0b6f12e78bc4371b57bd') {
    throw 'Le fichier ne correspond pas a l''installateur verifie.'
}
$pageHash = (Get-FileHash $page -Algorithm SHA256).Hash.ToLowerInvariant()
$token = [guid]::NewGuid().ToString('N')
$stage = "/var/tmp/devantiq-noteazy-$token"
Write-Host '1/3 Verification du site. Saisissez le mot de passe SSH dans ce terminal.'
& $ssh $Server "set -eu; test -f /var/www/devantiq/noteazy.html; git -C /var/www/devantiq diff --quiet HEAD -- noteazy.html; mkdir -m 700 '$stage'"
if ($LASTEXITCODE -ne 0) { throw 'Verification echouee : acces, dossier ou modifications locales sur le VPS. Aucun deploiement effectue.' }
Write-Host '2/3 Transfert de l''installateur et de la page. Le mot de passe sera demande a nouveau.'
& $scp $installer $page "${Server}:${stage}/"
if ($LASTEXITCODE -ne 0) { throw "Transfert echoue. La page publique est inchangee. Fichiers temporaires : $stage" }
$deploy = @"
set -eu
cd '$stage'
printf '%s  %s\n' '$installerHash' 'NotEazy-Setup-1.0.37.exe' '$pageHash' 'noteazy.html' | sha256sum -c -
git -C /var/www/devantiq diff --quiet HEAD -- noteazy.html
mkdir -p /var/backups/devantiq /var/www/devantiq/downloads/noteazy
cp -p /var/www/devantiq/noteazy.html '/var/backups/devantiq/noteazy-$token.html'
install -m 644 NotEazy-Setup-1.0.37.exe /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe.part
mv /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe.part /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe
install -m 644 noteazy.html /var/www/devantiq/noteazy.html.part
mv /var/www/devantiq/noteazy.html.part /var/www/devantiq/noteazy.html
rm -- NotEazy-Setup-1.0.37.exe noteazy.html
rmdir '$stage'
echo 'Deploiement Noteazy termine.'
"@
Write-Host '3/3 Verification SHA-256, sauvegarde et publication. Saisissez le mot de passe SSH.'
& $ssh $Server ($deploy -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw "Deploiement interrompu. Verifier la sortie SSH. Sauvegarde eventuelle : /var/backups/devantiq/noteazy-$token.html" }
Write-Host 'Verification du telechargement public...'
$result = Invoke-WebRequest 'https://devantiq.com/downloads/noteazy/NotEazy-Setup-1.0.37.exe' -Method Head -UseBasicParsing -TimeoutSec 30
if ([long]($result.Headers['Content-Length'] | Select-Object -First 1) -ne 257246264) {
    throw 'Le fichier distant ne presente pas la taille attendue.'
}
Write-Host 'Telechargement disponible : https://devantiq.com/noteazy.html#telecharger'
Write-Host 'La page a ete deployee directement. Il faudra aussi enregistrer cette modification dans Git avant le prochain git pull.'

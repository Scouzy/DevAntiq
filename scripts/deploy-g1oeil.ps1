param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$installer = Join-Path $project 'downloads/g1oeil/G1Oeil-Setup-1.0.0.exe'
$page = Join-Path $project 'g1oeil.html'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
if (-not (Test-Path $installer)) { throw "Installateur introuvable : $installer" }
$installerHash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installerHash -ne 'c6ba167141ffa00b6b00469172f392095823ec9d3ef520fd048e3a053d1dd040') {
    throw 'Le fichier ne correspond pas a l''installateur verifie.'
}
$pageHash = (Get-FileHash $page -Algorithm SHA256).Hash.ToLowerInvariant()
$token = [guid]::NewGuid().ToString('N')
$stage = "/var/tmp/devantiq-g1oeil-$token"
Write-Host '1/3 Verification du site. Saisissez le mot de passe SSH dans ce terminal.'
& $ssh $Server "set -eu; test -f /var/www/devantiq/g1oeil.html; git -C /var/www/devantiq diff --quiet HEAD -- g1oeil.html; mkdir -m 700 '$stage'"
if ($LASTEXITCODE -ne 0) { throw 'Verification echouee : acces, dossier ou modifications locales sur le VPS. Aucun deploiement effectue.' }
Write-Host '2/3 Transfert de l''installateur et de la page. Le mot de passe sera demande a nouveau.'
& $scp $installer $page "${Server}:${stage}/"
if ($LASTEXITCODE -ne 0) { throw "Transfert echoue. La page publique est inchangee. Fichiers temporaires : $stage" }
$deploy = @"
set -eu
cd '$stage'
printf '%s  %s\n' '$installerHash' 'G1Oeil-Setup-1.0.0.exe' '$pageHash' 'g1oeil.html' | sha256sum -c -
git -C /var/www/devantiq diff --quiet HEAD -- g1oeil.html
mkdir -p /var/backups/devantiq /var/www/devantiq/downloads/g1oeil
cp -p /var/www/devantiq/g1oeil.html '/var/backups/devantiq/g1oeil-$token.html'
install -m 644 G1Oeil-Setup-1.0.0.exe /var/www/devantiq/downloads/g1oeil/G1Oeil-Setup-1.0.0.exe.part
mv /var/www/devantiq/downloads/g1oeil/G1Oeil-Setup-1.0.0.exe.part /var/www/devantiq/downloads/g1oeil/G1Oeil-Setup-1.0.0.exe
install -m 644 g1oeil.html /var/www/devantiq/g1oeil.html.part
mv /var/www/devantiq/g1oeil.html.part /var/www/devantiq/g1oeil.html
rm -- G1Oeil-Setup-1.0.0.exe g1oeil.html
rmdir '$stage'
echo 'Deploiement G1Oeil termine.'
"@
Write-Host '3/3 Verification SHA-256, sauvegarde et publication. Saisissez le mot de passe SSH.'
& $ssh $Server ($deploy -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw "Deploiement interrompu. Verifier la sortie SSH. Sauvegarde eventuelle : /var/backups/devantiq/g1oeil-$token.html" }
Write-Host 'Verification du telechargement public...'
$result = Invoke-WebRequest 'https://devantiq.com/downloads/g1oeil/G1Oeil-Setup-1.0.0.exe' -Method Head -UseBasicParsing -TimeoutSec 30
if ([long]($result.Headers['Content-Length'] | Select-Object -First 1) -ne 106358548) {
    throw 'Le fichier distant ne presente pas la taille attendue.'
}
Write-Host 'Telechargement disponible : https://devantiq.com/g1oeil.html#telecharger'
Write-Host 'La page a ete deployee directement. Il faudra aussi enregistrer cette modification dans Git avant le prochain git pull.'

param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$token = [guid]::NewGuid().ToString('N')
$archive = Join-Path ([IO.Path]::GetTempPath()) "devantiq-showcase-$token.tar.gz"
$remote = "/var/tmp/devantiq-showcase-$token.tar.gz"
$stage = "/var/tmp/devantiq-showcase-$token"
& python (Join-Path $PSScriptRoot 'publish-showcase.py') pack $archive
if ($LASTEXITCODE -ne 0) { throw 'Preparation de l archive impossible.' }
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host '1/2 Transfert des pages publiques. Saisissez votre mot de passe SSH.'
& $scp $archive "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu. Aucun fichier public modifie.' }
$deploy = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$remote' | sha256sum -c -
mkdir -m 700 '$stage'
tar -xzf '$remote' -C '$stage' --no-same-owner --no-same-permissions
python3 '$stage/publish-showcase.py' install '$stage'
"@
Write-Host '2/2 Verification, sauvegarde et publication. Saisissez votre mot de passe SSH.'
& $ssh $Server ($deploy -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw "Publication interrompue. Conserver le diagnostic affiche. Archive privee : $remote" }
Write-Host 'Verification des pages et des captures...'
foreach ($page in @('mycareer.html', 'g1tournoi.html', 'membres.html', 'caroussel/mycareer/accueil.png', 'caroussel/g1tournoi/accueil.png')) {
    $response = Invoke-WebRequest "https://devantiq.com/$page" -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -ne 200) { throw "Page indisponible : $page" }
    if ($page.EndsWith('.png') -and $response.Headers['Content-Type'] -notmatch '^image/png') {
        throw "Reponse inattendue pour l image : $page"
    }
    Write-Host "OK : https://devantiq.com/$page"
}
Write-Host 'Pages publiques et cartes membres publiees. Les comptes et droits existants sont conserves.'
foreach ($asset in Get-ChildItem -LiteralPath (Join-Path $project 'img/members') -File | Where-Object { $_.Extension -in '.svg', '.png' }) {
    $response = Invoke-WebRequest ("https://devantiq.com/img/members/" + $asset.Name) -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -ne 200 -or $response.Headers['Content-Type'] -notmatch '^image/') {
        throw ('Image membre indisponible : ' + $asset.Name)
    }
}
Write-Host 'Logos et illustrations des neuf cartes verifies.'

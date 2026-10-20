param(
    [string]$Server = 'root@212.227.39.182',
    [string]$SourceArchive = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sources = Join-Path $root '.vps-inspection\sso-sources-66bfc56f35b743c78e338e0443bd3793\sources.tar.gz'
if ($SourceArchive) {
    $sources = (Resolve-Path -LiteralPath $SourceArchive).Path
}
if (-not (Test-Path -LiteralPath $sources -PathType Leaf)) { throw 'Archive de sources introuvable.' }
Write-Host "Sources utilisees : $sources"
$python = Join-Path $root '.venv-members\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Python du projet introuvable.' }
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$id = [guid]::NewGuid().ToString('N')
$archive = Join-Path $root ".vps-inspection\native-sso-$id.tar.gz"
& $python (Join-Path $PSScriptRoot 'pack-native-sso.py') $sources $archive
if ($LASTEXITCODE -ne 0) { throw 'Preparation du paquet interrompue.' }
$remote = "/var/tmp/devantiq-native-sso-$id"
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host '1/2 Transfert des quatre raccordements. Saisissez votre mot de passe SSH.'
& (Join-Path $sshDir 'scp.exe') $archive "${Server}:$remote.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$command = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$remote.tar.gz' | sha256sum -c -
mkdir '$remote'
tar -xzf '$remote.tar.gz' -C '$remote' --no-same-owner --no-same-permissions
python3 '$remote/install_native.py' '$remote'
"@
Write-Host '2/2 Verification, sauvegarde, mise a jour membres et raccordement des applications.'
Write-Host 'Les quatre services applicatifs seront redemarres. Cloud et les comptes existants sont conserves.'
& (Join-Path $sshDir 'ssh.exe') $Server ($command -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Raccordement interrompu. Transmettre le diagnostic affiche, sans mot de passe.' }

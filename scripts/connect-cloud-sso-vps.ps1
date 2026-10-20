param([string]$Member, [string]$CloudUser, [string]$Server = 'root@212.227.39.182', [switch]$CreateCloudUser)
$ErrorActionPreference = 'Stop'
if (-not $Member) { $Member = Read-Host 'Identifiant exact du membre DevAntiq existant' }
if (-not $CloudUser) {
    if ($CreateCloudUser) { $CloudUser = 'devantiq-' + $Member }
    else { $CloudUser = Read-Host 'Identifiant exact de son compte Nextcloud existant' }
}
if (-not $Member.Trim() -or -not $CloudUser.Trim()) { throw 'Deux identifiants sont requis, sans mot de passe.' }
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$scp = Join-Path $sshDir 'scp.exe'
$source = Join-Path (Split-Path $PSScriptRoot -Parent) 'infrastructure/members/connect_nextcloud.py'
$remote = '/var/tmp/devantiq-cloud-sso-' + [guid]::NewGuid().ToString('N') + '.py'
$hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$pair = @{ member = $Member; cloud_user = $CloudUser; create_user = [bool]$CreateCloudUser } | ConvertTo-Json -Compress
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
Write-Host '1/2 Transfert du raccordement Cloud. Saisissez le mot de passe SSH.'
& $scp $source "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$command = @"
set -eu
umask 077
printf '%s  %s\n' '$hash' '$remote' | sha256sum -c -
python3 '$remote' '$encoded'
"@
Write-Host '2/2 Sauvegarde, module officiel Nextcloud et association du compte applicatif.'
if ($CreateCloudUser) { Write-Host "Creation demandee : $CloudUser (compte standard), lie a $Member." }
& $ssh $Server ($command -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Raccordement Cloud interrompu. Transmettre le diagnostic sans mot de passe.' }

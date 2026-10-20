param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$id = [guid]::NewGuid().ToString('N')
$remote = "/var/tmp/devantiq-managed-sso-$id.tar.gz"
$destination = Join-Path (Split-Path $PSScriptRoot -Parent) ".vps-inspection\managed-sso-$id"
New-Item -ItemType Directory -Path $destination | Out-Null
$python = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'inspect-managed-sso.py') -Raw -Encoding UTF8
$command = "umask 077`npython3 - '$remote' <<'DEVANTIQ_INSPECT_PY'`n$python`nDEVANTIQ_INSPECT_PY"
Write-Host '1/2 Inspection privee de Zabbix, Umami et OmniRoute. Saisissez le mot de passe SSH.'
& (Join-Path $sshDir 'ssh.exe') $Server ($command -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Inspection interrompue. Aucun raccordement applique.' }
Write-Host '2/2 Recuperation des elements techniques. Saisissez le mot de passe SSH.'
& (Join-Path $sshDir 'scp.exe') "${Server}:$remote" (Join-Path $destination 'sources.tar.gz')
if ($LASTEXITCODE -ne 0) { throw 'Recuperation interrompue.' }
Write-Host "Inspection disponible : $destination\sources.tar.gz"
Write-Host 'Archive privee : ne pas publier. Aucun compte, base ou configuration secrete exporte.'

param([string]$Server = 'root@212.227.39.182', [switch]$Diagnostic)
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$file = Join-Path (Split-Path $PSScriptRoot -Parent) 'infrastructure\members\connect_omniroute.py'
$id = [guid]::NewGuid().ToString('N')
$remote = "/var/tmp/devantiq-omniroute-$id.py"
$hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
& (Join-Path $sshDir 'scp.exe') $file "${Server}:$remote"
if ($LASTEXITCODE -ne 0) { throw 'Transfert interrompu.' }
$option = if ($Diagnostic) { '--diagnose' } else { '' }
if ($Diagnostic) { Write-Host 'Diagnostic en lecture seule : seul le mot de passe SSH sera demande.' }
else { Write-Host 'Le terminal demandera le mot de passe SSH puis celui de OmniRoute. Ne les envoyez pas dans Codex.' }
& (Join-Path $sshDir 'ssh.exe') -t $Server "chmod 600 '$remote' && printf '%s  %s\n' '$hash' '$remote' | sha256sum -c - && python3 '$remote' $option"
if ($LASTEXITCODE -ne 0) { throw 'Raccordement OmniRoute interrompu. Transmettre uniquement le diagnostic.' }

param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
# Lecture seule. Ni variables d'environnement, ni secrets, ni fichiers de comptes.
$inspect = @'
printf '\n--- SYSTEME ---\n'
hostname
printf '\n--- NGINX ---\n'
nginx -v 2>&1
ls /etc/nginx/sites-enabled 2>/dev/null
printf '\n--- ROUTAGE (directives publiques uniquement) ---\n'
nginx -T 2>/dev/null | awk '/^[[:space:]]*(server_name|listen|root|proxy_pass|auth_request)[[:space:]]/ {print}' | sed -E 's#(https?://)[^/ @]+:[^/ @]+@#\1[redacted]@#g; s#\?[^; ]*#[query-redacted]#g'
printf '\n--- STRUCTURE NGINX (sans valeurs de secrets) ---\n'
nginx -T 2>/dev/null | awk '/^# configuration file / || /^[[:space:]]*(server[[:space:]]*\{|location[[:space:]]|server_name[[:space:]]|include[[:space:]]|try_files[[:space:]]|auth_request[[:space:]]|\})/ {print}'
printf '\n--- APPLICATIONS ---\n'
ls /var/www
printf '\n--- CONTENEURS ---\n'
docker ps --format '{{.Names}} | {{.Image}} | {{.Ports}}' 2>/dev/null
printf '\n--- DNS AUTH ---\n'
getent hosts auth.devantiq.com || printf 'Sous-domaine auth non resolu ; connexion prevue sur devantiq.com/auth/.\n'
'@
Write-Host 'Inspection en lecture seule. Saisissez le mot de passe SSH dans ce terminal.'
& $ssh $Server ($inspect -replace "`r", '')
if ($LASTEXITCODE -ne 0) { Write-Warning "Une partie de l'inspection a echoue ; transmettre le resultat disponible." }

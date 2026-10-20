param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$id = [guid]::NewGuid().ToString('N')
$remote = "/var/tmp/devantiq-sso-sources-$id.tar.gz"
$destination = Join-Path (Split-Path $PSScriptRoot -Parent) ".vps-inspection\sso-sources-$id"
New-Item -ItemType Directory -Path $destination | Out-Null
$script = @'
set -eu
umask 077
python3 - <<'PY'
import pathlib, tarfile, json, io, hashlib
roots = {
 'g1crm': pathlib.Path('/opt/g1crm/project'),
 'g1profil': pathlib.Path('/opt/G1Profil'),
 'sentinet': pathlib.Path('/var/www/sentinet/sentinet-app'),
 'livemonitor': pathlib.Path('/opt/LiveMonitor'),
}
manifest = []
with tarfile.open('__ARCHIVE__', 'w:gz') as archive:
 for name, root in roots.items():
  if not root.is_dir():
   raise SystemExit('Projet absent : ' + name)
  candidates = [root / 'package.json', root / 'package-lock.json']
  for folder in ('src', 'server', 'backend'):
   base = root / folder
   if base.is_dir():
    candidates.extend(base.rglob('*'))
  for path in sorted(set(candidates)):
   relative = path.relative_to(root)
   if any(part.startswith('.') or part in ('node_modules','devantiq-sso','data','dist','build','logs','uploads','coverage') for part in relative.parts):
    continue
   if path.is_symlink() or not path.is_file() or root.resolve() not in path.resolve().parents:
    continue
   if path.suffix not in ('.js','.mjs','.cjs','.ts','.tsx','.jsx') and path.name not in ('package.json','package-lock.json'):
    continue
   if path.stat().st_size > 5_000_000:
    raise SystemExit('Source volumineuse : examen requis avant copie.')
   data = path.read_bytes()
   info = tarfile.TarInfo(name + '/' + relative.as_posix())
   info.size, info.mode = len(data), 0o600
   archive.addfile(info, io.BytesIO(data))
   manifest.append({'path': info.name, 'sha256': hashlib.sha256(data).hexdigest()})
 payload = json.dumps(manifest).encode()
 info = tarfile.TarInfo('manifest.json')
 info.size, info.mode = len(payload), 0o600
 archive.addfile(info, io.BytesIO(payload))
print('Sources copiees :', len(manifest), 'fichiers. Aucun compte ou service modifie.')
PY
'@
$script = $script.Replace('__ARCHIVE__', $remote)
Write-Host '1/2 Copie privee des sources installees. Saisissez le mot de passe SSH.'
& (Join-Path $sshDir 'ssh.exe') $Server ($script -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Inspection interrompue.' }
Write-Host '2/2 Recuperation des sources pour adaptation SSO. Saisissez le mot de passe SSH.'
& (Join-Path $sshDir 'scp.exe') "${Server}:$remote" (Join-Path $destination 'sources.tar.gz')
if ($LASTEXITCODE -ne 0) { throw 'Recuperation interrompue.' }
Write-Host "Sources disponibles : $destination\sources.tar.gz"
Write-Host 'Configurations privees, bases et fichiers utilisateurs exclus. Ne publiez pas cette archive de sources.'
Write-Host 'Revenez dans Codex pour comparer les changements avant toute nouvelle installation.'

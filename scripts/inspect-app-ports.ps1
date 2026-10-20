param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$ssh = Join-Path $sshDir 'ssh.exe'
$inspect = @'
python3 - <<'PY'
import json, pathlib, re, shutil, subprocess
result = subprocess.run(['ss', '-lntp', '( sport = :3210 or sport = :5173 or sport = :9099 )'], capture_output=True, text=True, check=True)
print(result.stdout)
pids = sorted(set(re.findall(r'pid=(\d+)', result.stdout)))
for pid in pids:
    proc = pathlib.Path('/proc') / pid
    print('Processus ' + pid)
    for name in ('cwd', 'exe'):
        try:
            print(name + ': ' + str((proc / name).resolve(strict=True)))
        except OSError:
            print(name + ': indisponible')
    try:
        cgroup = (proc / 'cgroup').read_text()
        print('Gestionnaire: ' + cgroup.strip())
        for unit in sorted(set(re.findall(r'([^/\n]+\.service)', cgroup))):
            print(subprocess.check_output(['systemctl', 'show', unit, '--property=FragmentPath', '--property=DropInPaths'], text=True))
    except (OSError, subprocess.CalledProcessError):
        print('Gestionnaire non identifie')
if shutil.which('pm2') and subprocess.run(['pgrep', '-f', 'PM2.*God Daemon'], capture_output=True).returncode == 0:
    try:
        processes = json.loads(subprocess.check_output(['pm2', 'jlist'], text=True, timeout=10))
        for process in processes:
            if str(process.get('pid')) in pids:
                env = process.get('pm2_env', {})
                print('PM2: ' + json.dumps({key: value for key, value in {
                    'name': process.get('name'), 'pid': process.get('pid'),
                    'directory': env.get('pm_cwd'), 'entrypoint': env.get('pm_exec_path')
                }.items()}))
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Metadonnees PM2 indisponibles')
PY
'@
Write-Host 'Inspection des trois ports en lecture seule. Saisissez le mot de passe SSH.'
& $ssh $Server ($inspect -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Inspection interrompue. Aucun service modifie.' }

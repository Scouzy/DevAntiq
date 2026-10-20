param([string]$Server = 'root@212.227.39.182')
$ErrorActionPreference = 'Stop'
$sshDir = @("$env:WINDIR\Sysnative\OpenSSH", "$env:WINDIR\System32\OpenSSH", 'C:\Program Files\Git\usr\bin') |
    Where-Object { Test-Path (Join-Path $_ 'ssh.exe') } | Select-Object -First 1
if (-not $sshDir) { throw 'Client SSH introuvable.' }
$inspect = @'
python3 - <<'PY'
import json, pathlib, re, subprocess
roots = ['/opt/g1crm/project', '/opt/G1Profil', '/opt/LiveMonitor', '/var/www/sentinet/sentinet-app']
versions = {}
listeners = subprocess.run(['ss','-lntp'], capture_output=True, text=True, check=True).stdout
def parent_chain(proc):
    parents = []
    seen = set()
    for _ in range(6):
        status = (proc/'status').read_text()
        pid = int(re.search(r'^PPid:\s+(\d+)', status, re.M)[1])
        if pid<=1 or pid in seen: break
        seen.add(pid)
        proc = pathlib.Path('/proc')/str(pid)
        args = (proc/'cmdline').read_bytes().decode().split('\0')
        # Classify the supervisor without printing its command or environment.
        title = args[0] if args else ''
        pm2 = bool(re.match(r'^PM2 v[0-9.]+: God Daemon', title))
        parents.append({'pid':pid, 'exe':str((proc/'exe').resolve()), 'pm2_daemon':pm2})
    return parents
for proc in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        exe = (proc/'exe').resolve()
        if exe.name not in ('node', 'nodejs'): continue
        cwd = (proc/'cwd').resolve()
        argv = (proc/'cmdline').read_bytes().decode().split('\0')
        code = []
        for arg in argv:
            # Only existing source paths: never display raw arguments or environment.
            for prefix in ('node ', 'nodejs '):
                if arg.startswith(prefix): arg = arg[len(prefix):]
            if not arg or len(arg)>1024 or arg.startswith('-'): continue
            p = (cwd/arg).resolve()
            if p.suffix in ('.js', '.mjs', '.cjs') and p.is_file(): code.append(str(p))
        if not any(str(cwd)==root or str(cwd).startswith(root+'/') or any(p.startswith(root+'/') for p in code) for root in roots): continue
        groups = (proc/'cgroup').read_text()
        units = re.findall(r'/([^/\n]+\.service)(?:/|$)', groups)
        status = (proc/'status').read_text()
        uid = int(re.search(r'^Uid:\s+(\d+)', status, re.M)[1])
        # Do not dump environ: PM2 exposes application secrets there.
        env = dict(item.split('=',1) for item in (proc/'environ').read_bytes().decode().split('\0') if '=' in item)
        pm2 = {}
        for key in ('pm_id', 'PM2_HOME', 'pm_exec_path'):
            value = env.get(key, '')
            if key == 'pm_id' and value.isdigit(): pm2[key] = int(value)
            elif key != 'pm_id' and value.startswith('/') and len(value)<1024:
                path = pathlib.Path(value)
                if path.exists(): pm2[key] = str(path.resolve())
        del env
        if str(exe) not in versions:
            result = subprocess.run([str(exe),'--version'], capture_output=True, text=True, timeout=10)
            versions[str(exe)] = result.stdout.strip() if re.fullmatch(r'v[0-9.]+\s*',result.stdout) else 'inconnue'
        ports = [line.split()[3] for line in listeners.splitlines() if re.search(r'pid='+proc.name+r',',line)]
        print(json.dumps({'pid': int(proc.name), 'exe': str(exe), 'cwd': str(cwd),
                          'source_paths': code, 'systemd_units': units,
                          'uid':uid, 'node_version':versions[str(exe)], 'listeners':ports,
                          'pm2_metadata':pm2, 'parents':parent_chain(proc),
                          'rewritten_title': argv[0].startswith(('node ', 'nodejs ')),
                          'container': 'docker' in groups or 'containerd' in groups}))
    except (OSError, UnicodeError, ValueError): continue
print('Inspection terminee. Aucun service ou compte modifie. Aucun argument brut ni secret affiche.')
PY
'@
Write-Host 'Inspection des processus applicatifs en lecture seule. Saisissez le mot de passe SSH.'
& (Join-Path $sshDir 'ssh.exe') $Server ($inspect -replace "`r", '')
if ($LASTEXITCODE -ne 0) { throw 'Inspection interrompue.' }

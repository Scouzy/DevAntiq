"""First deployment of four native adapters, guarded against source drift."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOTS = {'g1crm':Path('/opt/g1crm/project'), 'g1profil':Path('/opt/G1Profil'),
         'sentinet':Path('/var/www/sentinet/sentinet-app'), 'livemonitor':Path('/opt/LiveMonitor')}
ENTRIES = {'g1crm':'server/index.js', 'g1profil':'server/src/index.js',
           'sentinet':'server/index.js', 'livemonitor':'backend/server.js'}
MEMBERS = Path('/opt/devantiq-members')


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=600, **kwargs)
    if result.returncode:
        raise RuntimeError('Commande en echec : ' + args[0] + ' (sortie privee non affichee).')
    return result.stdout


def manage(*args):
    return run(['docker','compose','exec','-T','members','python','manage.py',*args],cwd=MEMBERS)


def matches_entry(argv, cwd, entry):
    """Accept ordinary argv and Node's rewritten process title, never cwd alone."""
    entry = entry.resolve()
    if any((cwd/arg).resolve() == entry for arg in argv[1:] if arg and not arg.startswith('-')):
        return True
    # PM2 may replace the whole cmdline with `node /absolute/path/to/main.js`.
    title = argv[0] if argv else ''
    return title in ('node '+str(entry), 'nodejs '+str(entry))


def pm2_command(item, *args):
    """Use only the already-running, inspected root PM2 daemon."""
    home = Path(item['pm2_home'])
    daemon = Path('/proc')/str(item['pm2_daemon'])
    if (home/'pm2.pid').read_text().strip() != str(item['pm2_daemon']):
        raise RuntimeError('Gestionnaire PM2 change : raccordement interrompu')
    title = (daemon/'cmdline').read_bytes().decode().split('\0')[0]
    if not re.match(r'^PM2 v[0-9.]+: God Daemon', title) or not (home/'rpc.sock').is_socket():
        raise RuntimeError('Gestionnaire PM2 inactif ou non reconnu')
    env = {**os.environ, 'PM2_HOME':str(home)}
    return run([item['node'], item['pm2_cli'], *args], env=env)


def validate_pm2_listing(rows, item, require_pid=False):
    if not isinstance(rows, list):
        raise RuntimeError('Inventaire PM2 invalide')
    selected = [row for row in rows if row.get('pm_id') == item['pm2_id']]
    if len(selected) != 1:
        raise RuntimeError('Identifiant PM2 absent ou ambigu')
    row = selected[0]
    config = row.get('pm2_env', {})
    if Path(config.get('pm_exec_path', '')).resolve() != Path(item['entry']).resolve():
        raise RuntimeError('La cible PM2 ne correspond plus au fichier attendu')
    if config.get('exec_mode') != 'fork_mode' or config.get('watch'):
        raise RuntimeError('PM2 cluster/watch non pris en charge : aucune modification effectuee')
    if require_pid and (row.get('pid') != item['pid'] or config.get('status') != 'online'):
        raise RuntimeError('Processus PM2 change depuis inspection')


def pm2_runtime(proc, item, entry):
    if item['uid'] != 0:
        raise RuntimeError('Gestionnaire PM2 non-root non pris en charge')
    env = dict(value.split('=',1) for value in (proc/'environ').read_bytes().decode().split('\0') if '=' in value)
    home, number, script = (env.get(key, '') for key in ('PM2_HOME','pm_id','pm_exec_path'))
    del env
    if home != '/root/.pm2' or not number.isdigit() or Path(script).resolve() != entry.resolve():
        raise RuntimeError('Metadonnees PM2 non reconnues')
    parent = int(re.search(r'^PPid:\s+(\d+)', (proc/'status').read_text(), re.M)[1])
    cli = shutil.which('pm2')
    if not cli:
        raise RuntimeError('Executable PM2 introuvable dans PATH')
    item.update(manager='pm2', pm2_home=home, pm2_id=int(number), pm2_daemon=parent,
                pm2_cli=str(Path(cli).resolve()), entry=str(entry))
    validate_pm2_listing(json.loads(pm2_command(item, 'jlist')), item, require_pid=True)
    return item


def runtime_key(item):
    return ('pm2', item['pm2_home'], item['pm2_id']) if item['manager']=='pm2' else ('systemd',item['unit'])


def restart_runtime(item):
    if item['manager']=='pm2':
        # Recheck the ID/path association, including during rollback after a failed start.
        validate_pm2_listing(json.loads(pm2_command(item, 'jlist')), item)
        pm2_command(item, 'restart', str(item['pm2_id']))
    else:
        run(['systemctl','restart',item['unit']])


def runtime(entry):
    matches = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            executable = (proc/'exe').resolve()
            if executable.name not in ('node','nodejs'):
                continue
            cwd = (proc/'cwd').resolve()
            argv = (proc/'cmdline').read_bytes().decode().split('\0')
            if not matches_entry(argv, cwd, entry):
                continue
            unit = re.search(r'/([^/\n]+\.service)(?:/|$)',(proc/'cgroup').read_text())
            status = (proc/'status').read_text()
            uid=int(re.search(r'^Uid:\s+(\d+)',status,re.M)[1])
            gid=int(re.search(r'^Gid:\s+(\d+)',status,re.M)[1])
            item = {'pid':int(proc.name),'node':str(executable),'uid':uid,'gid':gid}
            if unit and re.fullmatch(r'[A-Za-z0-9_.@-]+\.service',unit[1]):
                item.update(manager='systemd',unit=unit[1])
            else:
                item = pm2_runtime(proc, item, entry)
            matches.append(item)
        except (OSError,UnicodeError):
            continue
    if len(matches)!=1:
        raise RuntimeError('Processus Node unique introuvable pour ' + str(entry)
                           + ' (' + str(len(matches)) + ' correspondance(s)). '
                           + 'Executer scripts/inspect-native-runtime-vps.ps1 avant de relancer.')
    item=matches[0]
    # Restarting a shared supervisor could interrupt unrelated applications.
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if int(proc.name) == item['pid'] or (proc/'exe').resolve().name not in ('node','nodejs'):
                continue
            units = re.findall(r'/([^/\n]+\.service)(?:/|$)', (proc/'cgroup').read_text())
            if item['manager']=='systemd' and item['unit'] in units:
                raise RuntimeError('Service Node partage : '+item['unit']
                                   + '. Inspection requise ; aucun redemarrage effectue.')
        except (OSError, UnicodeError):
            continue
    version=run([item['node'],'--version']).strip()
    match=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)',version)
    if not match:
        raise RuntimeError('Version Node non reconnue')
    major,minor,_=map(int,match.groups())
    if not (major>=24 or major==22 and minor>=12 or major==20 and minor>=19):
        raise RuntimeError('Node 20.19+, 22.12+ ou 24+ requis ; version detectee : '+version)
    listeners=run(['ss','-lntp'])
    ports=set()
    for line in listeners.splitlines():
        if re.search(r'pid='+str(item['pid'])+r',',line):
            address=line.split()[3]
            host,port=address.rsplit(':',1)
            if host not in ('127.0.0.1','[::1]','::1'):
                raise RuntimeError('Origine Node publiquement exposee : raccordement refuse')
            ports.add(int(port))
    if len(ports)!=1:
        raise RuntimeError('Port local unique introuvable pour '+str(entry))
    item['port']=ports.pop()
    return item


def health(app, port):
    for _ in range(20):
        try:
            request=Request(f'http://127.0.0.1:{port}/api/auth/sso/login',headers={'Host':app+'.devantiq.com'})
            with urlopen(request,timeout=4) as response:
                pass
        except HTTPError as error:
            if error.code==403 and 'Connexion DevAntiq refus'.encode() in error.read():
                return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError('Route SSO non disponible apres redemarrage : '+app)


def install(stage):
    if os.geteuid()!=0:
        raise RuntimeError('Executer en root')
    manifest=json.loads((stage/'native/manifest.json').read_text())
    runtimes={}
    for app,root in ROOTS.items():
        if root.is_symlink():
            raise RuntimeError('Racine symbolique non prise en charge')
        for name,hashes in manifest.items():
            if not name.startswith(app+'/'): continue
            relative=name.split('/',1)[1]
            target=root/relative
            if root.resolve() not in target.resolve().parents or target.is_symlink():
                raise RuntimeError('Chemin source inattendu')
            if hashlib.sha256(target.read_bytes()).hexdigest()!=hashes['before']:
                raise RuntimeError('Source VPS modifiee depuis inspection : '+name
                    + '. Aucun fichier applicatif modifie. Executer scripts/fetch-sso-sources-vps.ps1'
                    + ' puis comparer la nouvelle archive avant installation.')
            if hashlib.sha256((stage/'native'/name).read_bytes()).hexdigest()!=hashes['after']:
                raise RuntimeError('Empreinte du correctif invalide : '+name)
        entry=root/ENTRIES[app]
        if (entry.parent/'devantiq-sso').exists():
            raise RuntimeError('Adaptateur deja present : examen requis avant reprise : '+app)
        runtimes[app]=runtime(entry.resolve())
    if len({runtime_key(item) for item in runtimes.values()})!=4:
        raise RuntimeError('Services partages detectes : deploiement automatique refuse')
    backup=Path('/var/backups/devantiq')/('native-sso-'+uuid.uuid4().hex)
    backup.mkdir(mode=0o700,parents=True)
    print('Sauvegarde privee : '+str(backup),flush=True)
    with sqlite3.connect(MEMBERS/'data/members.sqlite3') as source, sqlite3.connect(backup/'members.sqlite3') as saved:
        source.backup(saved)
    run(['tar','--exclude=./data','--exclude=./static','--exclude=./public-stage','-czf',str(backup/'members-source.tar.gz'),'-C',str(MEMBERS),'.'])
    for name in manifest:
        app,relative=name.split('/',1)
        dest=backup/'applications'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOTS[app]/relative,dest)
    print('Mise a jour du service membres (comptes et Cloud conserves)...',flush=True)
    with tarfile.open(stage/'members.tar.gz') as bundle:
        bundle.extractall(MEMBERS,filter='data')
    # Existing deployment installs migrations, rebuilds the member service,
    # validates gateway protection and publishes the hash-guarded public bundle.
    result=subprocess.run(['sh','install.sh'],cwd=MEMBERS)
    if result.returncode:
        raise RuntimeError('Mise a jour membres interrompue avant modification des applications')
    changed=[]
    try:
        for app,root in ROOTS.items():
            print('Preparation du raccordement : '+app,flush=True)
            manage('prepare_native_sso',app)
            entry=root/ENTRIES[app]
            folder=entry.parent/'devantiq-sso'
            source_folder=(stage/'native'/app/ENTRIES[app]).parent/'devantiq-sso'
            shutil.copytree(source_folder,folder)
            shutil.copy2(MEMBERS/'data/sso-clients'/(app+'.json'),folder/'client.json')
            for file in folder.rglob('*'):
                if file.is_symlink(): raise RuntimeError('Lien inattendu dans adaptateur')
                os.chown(file,runtimes[app]['uid'],runtimes[app]['gid'])
                file.chmod(0o755 if file.is_dir() else 0o644)
            (folder/'client.json').chmod(0o600)
            folder.chmod(0o755)
            for name in manifest:
                if not name.startswith(app+'/'): continue
                if app not in changed: changed.append(app)
                relative=name.split('/',1)[1]
                target=root/relative
                shutil.copyfile(stage/'native'/name,target)
            restart_runtime(runtimes[app])
            health(app,runtimes[app]['port'])
        for app in ROOTS:
            manage('prepare_native_sso',app,'--activate')
        print('Quatre raccordements actives. Les comptes dedies seront crees a leur premiere connexion.',flush=True)
        print('Recette navigateur requise : ouvrir chaque carte depuis espace membres ; verifier identite et droits.',flush=True)
    except Exception:
        try:
            manage('shell','--no-imports','-c',"from portal.models import SSOClient; SSOClient.objects.filter(application_id__in=['g1crm','g1profil','livemonitor','sentinet']).update(enabled=False)")
        except Exception:
            print('Desactivation des clients non confirmee : intervention requise.',flush=True)
        failures=[]
        for app in changed:
            try:
                for name in manifest:
                    if name.startswith(app+'/'):
                        shutil.copy2(backup/'applications'/name, ROOTS[app]/name.split('/',1)[1])
                restart_runtime(runtimes[app])
            except Exception: failures.append(app)
        print('Restauration applicative : '+(', '.join(failures)+' a verifier' if failures else 'terminee')+'. Sauvegarde : '+str(backup),flush=True)
        raise


if __name__=='__main__':
    try: install(Path(sys.argv[1]).resolve())
    except Exception as error: raise SystemExit(str(error))

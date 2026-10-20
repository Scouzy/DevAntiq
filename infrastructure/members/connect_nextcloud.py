"""Link a Nextcloud account; optional explicit creation of a dedicated standard user."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import uuid
from urllib.request import urlopen

ROOT = Path('/opt/devantiq-members')
ISSUER = 'https://devantiq.com/auth/oidc'
OCC = ['docker', 'exec', '-i', '-u', 'www-data', 'nextcloud_app', 'php', 'occ']
BOOT = "chdir('/var/www/html'); require 'lib/base.php'; "
OIDC_SETTINGS = {'auto_provision': False, 'use_pkce': True, 'single_logout': False}
CHECK_ERRORS = {
    'MEMBER_NOT_FOUND': 'Compte DevAntiq introuvable : verifier son identifiant exact (majuscules comprises).',
    'MEMBER_DISABLED': 'Compte DevAntiq desactive : le reactiver dans sa fiche administrateur.',
    'CLOUD_NOT_GRANTED': 'Acces Cloud non attribue a ce membre. Dans Administration DevAntiq > Utilisateurs > sa fiche, ajouter Cloud dans Applications attribuees a ce membre, puis enregistrer. Un superadministrateur doit aussi recevoir cet acces.',
    'CLOUD_DISABLED': 'Application Cloud desactivee dans DevAntiq : verifier son activation avant de poursuivre.',
    'MEMBER_ALREADY_LINKED': 'Ce membre est deja associe a un autre compte Cloud. Association existante conservee.',
    'CLOUD_ALREADY_LINKED': 'Ce compte Cloud est deja associe a un autre membre. Association existante conservee.',
}


def run(args, *, data=None, step='commande', check=True):
    result = subprocess.run(args, input=data, capture_output=True, text=True, cwd=ROOT, timeout=300)
    if check and result.returncode:
        # Never display captured application output: it could contain configuration secrets.
        if step == 'controle DevAntiq':
            for line in result.stdout.splitlines():
                if line.startswith('DEVANTIQ_CHECK:'):
                    message = CHECK_ERRORS.get(line.removeprefix('DEVANTIQ_CHECK:'))
                    if message:
                        raise RuntimeError(message)
        detail = ''
        # Recognize fixed upstream errors without disclosing arbitrary output.
        captured = result.stdout + '\n' + result.stderr
        if 'could not be read or is empty' in captured and 'Client secret file' in captured:
            detail = ' Le module ne peut pas lire le flux du secret client.'
        elif 'does not exist' in captured and '--' in captured:
            detail = ' Une option de commande est indisponible dans le module installe.'
        elif 'Provider not found' in captured:
            detail = ' Le fournisseur demande est absent.'
        raise RuntimeError(f'{step} en echec (code {result.returncode}).{detail} Aucun secret affiche.')
    return result


def occ(*args, **kwargs):
    step = kwargs.pop('step', 'Nextcloud ' + args[0])
    return run(OCC + list(args), step=step, **kwargs)


def validate_partial_settings(prior):
    if prior and (not isinstance(prior, dict) or set(prior) != set(OIDC_SETTINGS)
                  or any(prior[key] is not value for key, value in OIDC_SETTINGS.items())):
        raise RuntimeError('Configuration user_oidc existante differente : examen requis avant modification.')


def configure_provider(credentials):
    # PHP's stdin stream avoids reopening /proc/self/fd/0 through /dev/stdin
    # under the www-data identity inside Docker. The secret stays on the pipe.
    occ('user_oidc:provider', 'DevAntiq', '--clientid=' + credentials['client_id'],
        '--clientsecret-file=php://stdin', '--discoveryuri=' + ISSUER + '/.well-known/openid-configuration',
        '--scope=openid profile', '--mapping-uid=external_account', '--unique-uid=0',
        '--group-provisioning=0', '--bearer-provisioning=0', '--check-bearer=0',
        data=credentials['client_secret'], step='Nextcloud creation du fournisseur DevAntiq')


def php(code, *args):
    return run(['docker', 'exec', '-i', '-u', 'www-data', 'nextcloud_app', 'php', '-r', BOOT + code, *args], step='controle Nextcloud').stdout


def django(code):
    # Execute trusted source over stdin rather than interpolating a shell command.
    return run(['docker', 'compose', 'exec', '-T', 'members', 'python', 'manage.py', 'shell', '--no-imports', '-c',
                "exec(compile(open('/dev/stdin').read(), 'devantiq-cloud-setup', 'exec'))"], data=code, step='controle DevAntiq').stdout


def validate_uid(value):
    if not value or len(value) > 150 or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError('Identifiant vide ou invalide.')
    return value


def validate_provider(provider, client_id):
    config = provider.get('settings', {})
    if provider.get('clientId') != client_id or config.get('mappingUid') != 'external_account':
        raise RuntimeError('Association du fournisseur Nextcloud inattendue.')
    if any(config.get(key) is not False for key in ('uniqueUid', 'groupProvisioning', 'bearerProvisioning', 'checkBearer')):
        raise RuntimeError('Options de preservation des comptes non confirmees.')


def nextcloud_callback():
    # A fresh php -r bootstrap does not load application code. Nextcloud's
    # router skips routes.php until its app has been loaded in this process.
    path = php("\\OC_App::loadApp('user_oidc'); "
               "echo \\OC::$server->getURLGenerator()->linkToRoute('user_oidc.login.code');").strip()
    if not path:
        raise RuntimeError('Route de retour Nextcloud vide apres chargement du module OIDC.')
    if not re.fullmatch(r'/(?:index\.php/)?apps/user_oidc/code', path):
        raise RuntimeError('Route de retour Nextcloud hors des chemins autorises. Aucun client configure.')
    return 'https://cloud.devantiq.com' + path


def cloud_account(uid):
    return json.loads(php("$u=\\OC::$server->getUserManager()->get($argv[1]); "
        "echo json_encode($u ? ['uid'=>$u->getUID(),'enabled'=>$u->isEnabled(),"
        "'admin'=>\\OC::$server->getGroupManager()->isAdmin($u->getUID())] : null);", uid))


def create_cloud_account(uid):
    # The native random password never leaves this PHP process. No existing
    # password or profile is updated; the new user starts disabled.
    result = json.loads(php("$m=\\OC::$server->getUserManager(); "
        "if($m->userExists($argv[1])){echo json_encode(['created'=>false]); exit;} "
        "$u=$m->createUser($argv[1], 'Aa9!'.bin2hex(random_bytes(48))); "
        "if(!$u){exit(3);} $u->setEnabled(false); "
        "echo json_encode(['created'=>true,'uid'=>$u->getUID(),'enabled'=>$u->isEnabled(),"
        "'admin'=>\\OC::$server->getGroupManager()->isAdmin($u->getUID())]);", uid))
    if result.get('created') is not True:
        raise RuntimeError('Le compte Cloud existe deja : aucune reutilisation ni modification automatique.')
    if result.get('uid') != uid or result.get('enabled') is not False or result.get('admin') is not False:
        raise RuntimeError('Compte cree mais controle du compte standard incomplet : examen requis avant activation.')
    return result


def set_cloud_enabled(uid, enabled):
    result = json.loads(php("$u=\\OC::$server->getUserManager()->get($argv[1]); if(!$u){exit(2);} "
        "$u->setEnabled($argv[2] === 'true'); echo json_encode(['enabled'=>$u->isEnabled()]);",
        uid, 'true' if enabled else 'false'))
    if result.get('enabled') is not enabled:
        raise RuntimeError('Etat du compte Cloud non confirme.')


def main(member, cloud_user, create_user=False):
    if os.geteuid() != 0:
        raise RuntimeError('Executer en root.')
    member, cloud_user = validate_uid(member), validate_uid(cloud_user)
    with urlopen(ISSUER + '/.well-known/openid-configuration', timeout=15) as response:
        if json.load(response).get('issuer') != ISSUER:
            raise RuntimeError('Le fournisseur DevAntiq doit etre installe avant ce raccordement.')
    # Creation requires an explicit option; access grants remain administrative.
    payload = base64.b64encode(json.dumps({'member': member, 'external_id': cloud_user}).encode()).decode()
    context = """import base64, json, sys
from django.contrib.auth.models import User
from portal.models import Access, AccountLink, SSOClient
def stop(code):
    print('DEVANTIQ_CHECK:' + code, flush=True)
    sys.exit(1)
p = json.loads(base64.b64decode('%s'))
u = User.objects.filter(username=p['member']).first()
if u is None:
    stop('MEMBER_NOT_FOUND')
if not u.is_active:
    stop('MEMBER_DISABLED')
a = Access.objects.select_related('application').filter(user=u, application_id='cloud').first()
if a is None:
    stop('CLOUD_NOT_GRANTED')
if not a.application.enabled:
    stop('CLOUD_DISABLED')
if AccountLink.objects.filter(access=a).exclude(external_id=p['external_id']).exists():
    stop('MEMBER_ALREADY_LINKED')
if AccountLink.objects.filter(application_id='cloud', external_id=p['external_id']).exclude(access=a).exists():
    stop('CLOUD_ALREADY_LINKED')
""" % payload
    member_info = json.loads(django(context + "print(json.dumps({'superuser':u.is_superuser}))"))
    cloud_info = cloud_account(cloud_user)
    if create_user:
        if cloud_info is not None:
            raise RuntimeError('Le compte Cloud existe deja : creation annulee, compte existant conserve.')
    else:
        if not cloud_info or cloud_info.get('uid') != cloud_user or cloud_info.get('enabled') is not True:
            raise RuntimeError('Compte Nextcloud absent, desactive ou identifiant non exact.')
        if cloud_info.get('admin') and not member_info['superuser']:
            raise RuntimeError('Un compte administrateur Nextcloud ne peut pas etre associe a un membre ordinaire par ce script.')
    if json.loads(occ('status', '--output=json').stdout).get('maintenance'):
        raise RuntimeError('Nextcloud est en maintenance.')
    # First connector only: never modify an existing SSO configuration silently.
    prior = json.loads(php("echo json_encode(\\OC::$server->getConfig()->getSystemValue('user_oidc', []));"))
    validate_partial_settings(prior)
    credential_file = ROOT / 'data/sso-clients/cloud.json'
    if prior:
        # Only resume our exact settings with the matching private client and
        # a disabled binding. Existing providers are still rejected below.
        if not credential_file.is_file():
            raise RuntimeError('Configuration OIDC partielle sans client prive : examen requis.')
        saved = json.loads(credential_file.read_text())
        if saved.get('issuer') != ISSUER:
            raise RuntimeError('Fournisseur du client prive different : examen requis.')
        django("from portal.models import SSOClient\nb=SSOClient.objects.get(application_id='cloud', oauth_client__client_id="
               + repr(saved['client_id']) + ")\nassert not b.enabled\n")
        print('Reprise des reglages OIDC partiels ; aucun fournisseur existant ne sera remplace.', flush=True)
    apps = json.loads(occ('app:list', '--output=json').stdout)
    was_enabled = 'user_oidc' in apps.get('enabled', {})
    if was_enabled:
        raise RuntimeError('Module OIDC deja actif : utiliser sa configuration existante apres examen.')
    backup = Path('/var/backups/devantiq') / ('cloud-sso-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, mode=0o700)
    with (backup / 'nextcloud-config.tar.gz').open('wb') as output:
        result = subprocess.run(['docker', 'exec', 'nextcloud_app', 'tar', '-czf', '-', '-C', '/var/www/html', 'config'], stdout=output, stderr=subprocess.PIPE)
        if result.returncode:
            raise RuntimeError('Sauvegarde Nextcloud impossible.')
    with sqlite3.connect(ROOT / 'data/members.sqlite3') as source, sqlite3.connect(backup / 'members.sqlite3') as saved:
        source.backup(saved)
    print('Sauvegardes privees : ' + str(backup), flush=True)
    created_user = False
    try:
        print('Installation du module officiel compatible depuis le catalogue Nextcloud...', flush=True)
        if 'user_oidc' in apps.get('disabled', {}):
            occ('app:enable', 'user_oidc')
        else:
            occ('app:install', 'user_oidc')
        version = json.loads(occ('app:list', '--output=json').stdout)['enabled']['user_oidc']
        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
        if not match or not ((8, 4, 0) <= tuple(map(int, match.groups())) < (9, 0, 0)):
            raise RuntimeError('Version user_oidc a examiner : ' + version)
        help_text = occ('user_oidc:provider', '--help', step='Nextcloud verification des options OIDC').stdout
        for option in ('--clientsecret-file', '--mapping-uid', '--group-provisioning', '--unique-uid'):
            if option not in help_text:
                raise RuntimeError('Commande user_oidc incompatible.')
        existing = json.loads(occ('user_oidc:provider', '--output=json', step='Nextcloud inventaire des fournisseurs OIDC').stdout)
        if existing:
            raise RuntimeError('Un fournisseur Nextcloud existe deja : aucune modification de celui-ci.')
        callback = nextcloud_callback()
        if not credential_file.exists():
            run(['docker', 'compose', 'exec', '-T', 'members', 'python', 'manage.py', 'configure_sso_client', 'cloud', callback], step='creation client Cloud')
        credentials = json.loads(credential_file.read_text())
        if credentials.get('redirect_uri') != callback or credentials.get('issuer') != ISSUER:
            raise RuntimeError('Client Cloud existant different : examen requis.')
        # Check database and private file agree before using either.
        django("from portal.models import SSOClient\nb=SSOClient.objects.get(application_id='cloud', oauth_client__client_id=" + repr(credentials['client_id']) + ")\nassert not b.enabled\n")
        occ('config:system:set', 'user_oidc', 'auto_provision', '--type=boolean', '--value=false')
        occ('config:system:set', 'user_oidc', 'use_pkce', '--type=boolean', '--value=true')
        occ('config:system:set', 'user_oidc', 'single_logout', '--type=boolean', '--value=false')
        configure_provider(credentials)
        provider = json.loads(occ('user_oidc:provider', 'DevAntiq', '--output=json',
                                  step='Nextcloud verification du fournisseur DevAntiq').stdout)
        validate_provider(provider, credentials['client_id'])
        actual = json.loads(php("echo json_encode(\\OC::$server->getConfig()->getSystemValue('user_oidc', []));"))
        if actual.get('auto_provision') is not False or actual.get('use_pkce') is not True:
            raise RuntimeError('Preservation des comptes non confirmee.')
        if create_user:
            create_cloud_account(cloud_user)
            created_user = True
            (backup / 'created-account.json').write_text(json.dumps({
                'member': member, 'cloud_user': cloud_user, 'role': 'standard'}))
            set_cloud_enabled(cloud_user, True)
        django(context + """
from django.db import transaction
with transaction.atomic():
    link, created = AccountLink.objects.get_or_create(access=a, defaults={'application_id':'cloud','external_id':p['external_id']})
    link.full_clean()
    if link.external_id != p['external_id']:
        raise ValueError('Association modifiee pendant la preparation.')
    SSOClient.objects.filter(application_id='cloud').update(enabled=True)
print('Association du compte applicatif enregistree.')
"""
        )
        print('Cloud configure. ' + ('Nouveau compte standard cree et associe. ' if created_user else '') +
              'Les autres comptes et leurs fichiers sont conserves.', flush=True)
        print('Recette requise : ouvrir Cloud dans une fenetre privee, se connecter a DevAntiq puis choisir DevAntiq sur la page Nextcloud.')
    except Exception:
        if created_user:
            try:
                set_cloud_enabled(cloud_user, False)
                print('Nouveau compte Cloud desactive apres echec ; conserve pour diagnostic.', flush=True)
            except Exception:
                print('Desactivation du nouveau compte Cloud non confirmee : controle administrateur requis.', flush=True)
        # Keep all native accounts/logins intact; leave the failed connector disabled.
        disabled = occ('app:disable', 'user_oidc', check=False).returncode == 0
        try:
            django("from portal.models import SSOClient\nSSOClient.objects.filter(application_id='cloud').update(enabled=False)")
        finally:
            print('Raccordement non valide. Module OIDC ' + ('desactive' if disabled else 'a desactiver manuellement') + ' ; sauvegardes : ' + str(backup), flush=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pair_base64', help='JSON encoded as base64, containing member and cloud_user')
    args = parser.parse_args()
    try:
        pair = json.loads(base64.b64decode(args.pair_base64, validate=True))
        main(pair['member'], pair['cloud_user'], create_user=pair.get('create_user') is True)
    except Exception as error:
        raise SystemExit(str(error))

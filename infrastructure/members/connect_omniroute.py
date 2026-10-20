"""Configure native shared-admin OIDC through OmniRoute's authenticated API."""
import getpass
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import uuid
import sys
from http.cookies import SimpleCookie
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError

ROOT=Path('/opt/devantiq-members')
ORIGIN='https://omniroute.devantiq.com'


def run(args):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
    if p.returncode: raise RuntimeError('Commande en echec : '+args[0]+' ; sortie privee masquee')
    return p.stdout


def manage(*args):
    return run(['docker','compose','exec','-T','members','python','manage.py',*args])


def safe_api_error(status, payload):
    """Translate only known errors: never echo arbitrary response bodies or secrets."""
    messages = {
        'No password configured. Complete onboarding first.': 'Aucun mot de passe administrateur OmniRoute configure. Terminer la configuration initiale dans OmniRoute.',
        'Password login is disabled when OIDC is active. Please sign in with OIDC.': 'Connexion par mot de passe desactivee par une configuration OIDC existante. Aucun parametre remplace.',
        'Invalid password': 'Mot de passe administrateur OmniRoute incorrect.',
        'Too many failed attempts. Try again later.': 'Connexion temporairement bloquee apres plusieurs essais. Attendre avant de reessayer.',
    }
    codes = {
        'INVALID_ORIGIN':'Origine de la requete refusee par OmniRoute.',
        'PASSWORD_REQUIRED':'OmniRoute exige son mot de passe actuel pour modifier la connexion.',
        'PASSWORD_MISMATCH':'Mot de passe actuel refuse par OmniRoute.',
    }
    try:
        data=json.loads(payload)
        error=data.get('error') if isinstance(data,dict) else None
        if isinstance(error,str) and error in messages: return messages[error]
        if isinstance(error,dict) and error.get('code') in codes: return codes[error['code']]
    except (ValueError,UnicodeError,TypeError): pass
    return 'Refus HTTP '+str(status)+' non identifie ; corps de reponse masque.'


def login_state(data):
    fields=('requireLogin','hasPassword','setupComplete','oidcEnabled','oidcDisablePasswordLogin','nodeCompatible')
    return {key:data[key] for key in fields if isinstance(data.get(key),bool)}


def administrator_password(api, state, backup):
    if state.get('oidcEnabled'):
        raise RuntimeError('OIDC deja configure : examen requis, aucun remplacement.')
    if state.get('hasPassword') is True:
        return getpass.getpass('Mot de passe administrateur OmniRoute (saisie masquee) : ')
    if state.get('hasPassword') is not False or state.get('setupComplete') is not False:
        raise RuntimeError('Etat initial ambigu : aucun mot de passe modifie.')
    print('Initialisation OmniRoute : choisissez un nouveau mot de passe administrateur et conservez-le dans votre gestionnaire de mots de passe.',flush=True)
    password=getpass.getpass('Nouveau mot de passe OmniRoute (12 caracteres minimum) : ')
    confirm=getpass.getpass('Confirmez le nouveau mot de passe : ')
    if len(password)<12 or password!=confirm:
        raise RuntimeError('Mots de passe differents ou trop court. Aucun changement effectue.')
    backup()
    # Recheck after interactive entry; never overwrite a password created meanwhile.
    with api('/api/settings/require-login') as response: fresh=login_state(json.load(response))
    if fresh.get('hasPassword') is not False or fresh.get('oidcEnabled') is not False or fresh.get('setupComplete') is not False:
        raise RuntimeError('Etat OmniRoute change pendant la saisie : initialisation annulee.')
    with api('/api/settings/require-login',{'requireLogin':True,'password':password}) as response:
        response.read()
    with api('/api/settings/require-login') as response: fresh=login_state(json.load(response))
    if fresh.get('hasPassword') is not True or fresh.get('requireLogin') is not True:
        raise RuntimeError('Initialisation non confirmee. Verifier OmniRoute avant de poursuivre.')
    print('Mot de passe administrateur cree et connexion obligatoire activee. Ce mot de passe sera conserve si le raccordement SSO echoue.',flush=True)
    return password


def main(diagnose=False):
    os.umask(0o077)
    inspected=json.loads(run(['docker','inspect','omniroute']))[0]
    if inspected['Image']!='sha256:085c57adf499a8aaa9f35ccde95c0df9c11bd9ecd18d6c9edbf3b68b8079ba9d':
        raise RuntimeError('Image OmniRoute modifiee : nouvelle verification requise')
    ports=inspected['NetworkSettings']['Ports'].get('20128/tcp',[])
    if ports!=[{'HostIp':'127.0.0.1','HostPort':'20128'}]:
        raise RuntimeError('Origine OmniRoute inattendue')
    csrf_source=run(['docker','exec','omniroute','cat','/app/src/shared/constants/dashboardCsrf.ts'])
    match=re.search(r'DASHBOARD_CSRF_HEADER\s*=\s*[\"\']([A-Za-z0-9-]+)[\"\']',csrf_source)
    if not match: raise RuntimeError('Nom du champ CSRF non reconnu')
    headers={'Host':'omniroute.devantiq.com','X-Forwarded-Proto':'https','Origin':ORIGIN}
    def api(path,body=None,method=None):
        req=Request('http://127.0.0.1:20128'+path,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={**headers,'Content-Type':'application/json'},method=method)
        try: return urlopen(req,timeout=20)
        except HTTPError as e:
            raise RuntimeError('API OmniRoute '+path+' : HTTP '+str(e.code)+'. '
                               +safe_api_error(e.code,e.read(8192))) from None
    with api('/api/settings/require-login') as response:
        state=login_state(json.load(response))
    print('Etat de connexion OmniRoute : '+json.dumps(state),flush=True)
    if diagnose:
        print('Diagnostic termine. Aucun essai de mot de passe ni changement de configuration.')
        return
    backup=None
    def ensure_backup():
        nonlocal backup
        if backup is not None: return
        candidate=Path('/var/backups/devantiq')/('omniroute-sso-'+uuid.uuid4().hex)
        candidate.mkdir(parents=True,mode=0o700)
        mount=next(m['Source'] for m in inspected['Mounts'] if m['Destination']=='/app/data')
        database=Path(mount)/'storage.sqlite'
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as source, sqlite3.connect(candidate/'storage.sqlite') as dest:
            source.backup(dest)
        backup=candidate
        print('Sauvegarde privee : '+str(backup),flush=True)
    password=administrator_password(api,state,ensure_backup)
    with api('/api/auth/login',{'password':password}) as response:
        cookies=SimpleCookie()
        for value in response.headers.get_all('Set-Cookie',[]): cookies.load(value)
    if 'auth_token' not in cookies: raise RuntimeError('Session administrateur non obtenue')
    headers['Cookie']='auth_token='+cookies['auth_token'].value
    with api('/api/auth/csrf') as response: csrf=json.load(response).get('token')
    if not csrf: raise RuntimeError('Protection CSRF indisponible')
    headers[match[1]]=csrf
    # Existing settings must not be overwritten if another identity provider is configured.
    with api('/api/settings') as response: previous=json.load(response)
    if previous.get('oidcEnabled'):
        raise RuntimeError('OIDC deja actif : examen requis avant modification')
    subjects=json.loads(manage('shell','--no-imports','-c',
        "import json; from portal.models import Access; print(json.dumps(list(Access.objects.filter(application_id='omniroute',user__is_active=True,application__enabled=True).values_list('user_id',flat=True))))"))
    if not subjects: raise RuntimeError('Attribuer OmniRoute a au moins un membre avant raccordement')
    ensure_backup()
    manage('prepare_omniroute_sso')
    credentials=json.loads((ROOT/'data/sso-clients/omniroute.json').read_text())
    body={'oidcEnabled':True,'oidcDisablePasswordLogin':False,
          'oidcIssuer':credentials['issuer'],'oidcClientId':credentials['client_id'],
          'oidcClientSecret':credentials['client_secret'],'oidcScopes':['openid','profile'],
          'oidcRedirectPath':'/api/auth/oidc/callback','oidcAllowedSubjects':[str(x) for x in subjects],
          'currentPassword':password}
    try:
        with api('/api/settings',body,method='PATCH') as response: response.read()
        manage('prepare_omniroute_sso','--activate')
    except Exception:
        try:
            with api('/api/settings',{'oidcEnabled':False,'currentPassword':password},method='PATCH') as response: response.read()
        except Exception:
            print('Desactivation OIDC non confirmee : verifier OmniRoute. Sauvegarde '+str(backup),flush=True)
        raise
    print('OmniRoute configure pour les membres actuellement autorises. Tester depuis espace membres.')
    print('Les nouveaux membres devront aussi etre ajoutes a la liste des sujets OIDC autorises dans OmniRoute.')


if __name__=='__main__':
    try: main(diagnose='--diagnose' in sys.argv)
    except Exception as e:
        print(str(e) if isinstance(e,RuntimeError) else 'Raccordement interrompu : '+type(e).__name__)
        raise SystemExit(1)

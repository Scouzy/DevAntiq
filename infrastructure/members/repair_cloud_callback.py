"""Targeted repair, executed inside the members Django container."""
import json
import os
from pathlib import Path
import uuid

CLIENT_ID = 'X2MPJjc2soGkajb_guU8ZcDPrVGj0Z_W'
CALLBACK = 'https://cloud.devantiq.com/apps/user_oidc/code'
OLD_CALLBACK = 'https://cloud.devantiq.com/index.php/apps/user_oidc/code'
ISSUER = 'https://devantiq.com/auth/oidc'


def validate(client_id, database_uri, credentials):
    if client_id != CLIENT_ID or credentials.get('client_id') != CLIENT_ID:
        raise ValueError('Client Cloud different de celui observe dans le navigateur.')
    if credentials.get('issuer') != ISSUER:
        raise ValueError('Fournisseur inattendu : aucune modification.')
    if database_uri not in (CALLBACK, OLD_CALLBACK):
        raise ValueError('Adresse en base inattendue : aucune modification.')
    if credentials.get('redirect_uri') not in (CALLBACK, OLD_CALLBACK):
        raise ValueError('Adresse du fichier prive inattendue : aucune modification.')


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def main():
    from django.conf import settings
    from django.db import transaction
    from portal.models import SSOClient
    from oauth2_provider.models import Application

    path = Path(settings.DATA_DIR) / 'sso-clients/cloud.json'
    original = path.read_bytes()
    credentials = json.loads(original)
    backup = path.parent / ('callback-backup-' + uuid.uuid4().hex)
    temporary = path.parent / ('cloud-repair-' + uuid.uuid4().hex + '.json')
    replaced = False
    committed = False
    try:
        with transaction.atomic():
            binding = SSOClient.objects.select_for_update().get(application_id='cloud')
            client = Application.objects.select_for_update().get(pk=binding.oauth_client_id)
            validate(client.client_id, client.redirect_uris, credentials)
            if client.redirect_uris == CALLBACK and credentials['redirect_uri'] == CALLBACK:
                print('Adresse de retour deja correcte. Recommencer une nouvelle connexion Cloud.')
                return
            backup.mkdir(mode=0o700)
            private_write(backup / 'cloud.json', original)
            private_write(backup / 'previous-callback.json', json.dumps({
                'client_id': client.client_id, 'redirect_uris': client.redirect_uris}).encode())
            print('Sauvegarde privee dans le conteneur membres : ' + str(backup))
            print('Adresse precedemment autorisee : ' + client.redirect_uris)
            credentials['redirect_uri'] = CALLBACK
            private_write(temporary, json.dumps(credentials).encode())
            client.redirect_uris = CALLBACK
            client.save(update_fields=['redirect_uris'])
            os.replace(temporary, path)
            replaced = True
        committed = True
        client.refresh_from_db(fields=['redirect_uris'])
        if client.redirect_uris != CALLBACK or json.loads(path.read_bytes())['redirect_uri'] != CALLBACK:
            raise RuntimeError('Verification apres correction en echec.')
    except Exception:
        # A failed transaction must not leave the private file ahead of the DB.
        if replaced and not committed:
            temporary.unlink(missing_ok=True)
            private_write(temporary, original)
            os.replace(temporary, path)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    print('Adresse de retour Cloud corrigee et verifiee : ' + CALLBACK)
    print('Comptes, droits, secret client et activation SSO conserves.')

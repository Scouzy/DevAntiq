"""Run privately on the VPS. Secrets are never passed as shell arguments."""
import getpass
import json
import os
from pathlib import Path
import secrets

path = Path('/opt/devantiq-members/config/runtime.json')
if path.exists():
    print('Configuration privee conservee.')
else:
    host = input('Serveur SMTP : ').strip()
    port = input('Port SMTP [587] : ').strip() or '587'
    user = input('Identifiant SMTP : ').strip()
    sender = input('Adresse expediteur [hello@devantiq.com] : ').strip() or 'hello@devantiq.com'
    password = getpass.getpass('Mot de passe SMTP (masque) : ')
    if not host or port not in ('587', '465') or '@' not in sender:
        raise SystemExit('Serveur, port TLS 587/465 et expediteur valides requis.')
    settings = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(64), 'SMTP_HOST': host,
                'SMTP_PORT': port, 'SMTP_USER': user, 'SMTP_FROM': sender, 'SMTP_PASSWORD': password}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(settings, output)
    os.chown(path, 10001, 10001)
    print('Configuration enregistree hors de la racine publique.')

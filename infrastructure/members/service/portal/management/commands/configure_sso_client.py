"""Register an exact application callback; keep SSO disabled pending app setup."""
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from oauth2_provider.models import Application as OAuthApplication
from portal.models import Application, SSOClient


class Command(BaseCommand):
    help = 'Prepare an OIDC client, disabled until the application adapter has been verified.'

    def add_arguments(self, parser):
        parser.add_argument('application')
        parser.add_argument('callback')

    def handle(self, *args, **options):
        slug, callback = options['application'], options['callback']
        url = urlsplit(callback)
        if (url.scheme != 'https' or url.netloc != f'{slug}.devantiq.com'
                or url.fragment or url.query or not url.path.startswith('/')
                or any(c.isspace() for c in callback)):
            raise CommandError('Callback HTTPS exact du sous-domaine applicatif requis.')
        try:
            app = Application.objects.get(pk=slug)
        except Application.DoesNotExist:
            raise CommandError('Application inconnue.')
        if SSOClient.objects.filter(application=app).exists():
            raise CommandError('Client deja prepare : aucun secret ni callback remplace.')
        secret = secrets.token_urlsafe(48)
        private_dir = settings.DATA_DIR / 'sso-clients'
        private_dir.mkdir(mode=0o700, exist_ok=True)
        private_file = private_dir / (slug + '.json')
        fd = os.open(private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w') as output, transaction.atomic():
                client = OAuthApplication.objects.create(name='DevAntiq ' + app.name,
                    client_id=secrets.token_urlsafe(24), client_secret=secret,
                    client_type='confidential', authorization_grant_type='authorization-code',
                    redirect_uris=callback, algorithm='RS256', skip_authorization=True)
                SSOClient.objects.create(application=app, oauth_client=client)
                json.dump({'issuer': 'https://devantiq.com/auth/oidc', 'client_id': client.client_id,
                           'client_secret': secret, 'redirect_uri': callback}, output)
        except Exception:
            private_file.unlink(missing_ok=True)
            raise
        self.stdout.write('Client prepare et desactive. Parametres dans le fichier prive : ' + str(private_file))

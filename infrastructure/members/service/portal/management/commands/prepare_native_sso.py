from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings
import json
from portal.models import Access, SSOClient
from portal.provisioning import NATIVE_APPS, associate_dedicated_account


class Command(BaseCommand):
    help = 'Prepare dedicated account associations; activate only after adapter checks.'

    def add_arguments(self, parser):
        parser.add_argument('application', choices=NATIVE_APPS)
        parser.add_argument('--activate', action='store_true')

    def handle(self, *args, **options):
        slug = options['application']
        callback = f'https://{slug}.devantiq.com/api/auth/sso/callback'
        if not SSOClient.objects.filter(application_id=slug).exists():
            if options['activate']:
                raise CommandError('Client not prepared')
            call_command('configure_sso_client', slug, callback)
        with transaction.atomic():
            binding = SSOClient.objects.select_for_update().select_related('oauth_client').get(application_id=slug)
            if binding.oauth_client.redirect_uris != callback:
                raise CommandError('Existing callback differs; nothing replaced')
            credentials = json.loads((settings.DATA_DIR / 'sso-clients' / (slug+'.json')).read_text())
            if (credentials.get('client_id') != binding.oauth_client.client_id
                or credentials.get('redirect_uri') != callback
                or credentials.get('issuer') != 'https://devantiq.com/auth/oidc'):
                raise CommandError('Private client file and database differ')
            if binding.enabled and not binding.dedicated_accounts:
                raise CommandError('Existing SSO integration requires review')
            for access in Access.objects.filter(application_id=slug, user__is_active=True):
                associate_dedicated_account(access)
            binding.dedicated_accounts = True
            binding.login_path = '/api/auth/sso/login'
            if options['activate']:
                binding.enabled = True
            binding.save(update_fields=['dedicated_accounts','login_path','enabled'])
        self.stdout.write('Dedicated account associations prepared; activation: ' + str(binding.enabled))

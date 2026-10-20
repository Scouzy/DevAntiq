"""Prepare the explicitly authorized shared administration integration."""
import json
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from portal.models import Access, AccountLink, SSOClient


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--activate', action='store_true')

    def handle(self, *args, **options):
        callback='https://omniroute.devantiq.com/api/auth/oidc/callback'
        if not SSOClient.objects.filter(application_id='omniroute').exists():
            if options['activate']: raise CommandError('Client non prepare')
            call_command('configure_sso_client','omniroute',callback)
        with transaction.atomic():
            binding=SSOClient.objects.select_for_update().select_related('oauth_client').get(application_id='omniroute')
            credentials=json.loads((settings.DATA_DIR/'sso-clients/omniroute.json').read_text())
            if (binding.oauth_client.redirect_uris!=callback or credentials.get('redirect_uri')!=callback
                    or credentials.get('client_id')!=binding.oauth_client.client_id):
                raise CommandError('Configuration existante differente : aucun remplacement')
            for access in Access.objects.filter(application_id='omniroute',user__is_active=True):
                # Unique per-member identity at the IdP; OmniRoute shares the admin role.
                AccountLink.objects.get_or_create(access=access,defaults={
                    'application_id':'omniroute','external_id':'devantiq-'+str(access.user_id)})
            binding.login_path='/api/auth/oidc/login'
            if options['activate']: binding.enabled=True
            binding.save(update_fields=['login_path','enabled'])
        self.stdout.write('OmniRoute prepare. Administration partagee ; acces individuels conserves.')

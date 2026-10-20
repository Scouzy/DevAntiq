from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from oauth2_provider.models import Application as OAuthApplication
from .models import Application, Access, AccountLink, SSOClient, validate_login_path
from .provisioning import associate_dedicated_account


@override_settings(SECURE_SSL_REDIRECT=False)
class LaunchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('member')
        self.app = Application.objects.create(slug='future-app', name='Future', enabled=True)
        self.access = Access.objects.create(user=self.user, application=self.app)
        self.client.force_login(self.user)
        self.url = '/auth/apps/future-app/open/'

    def sso(self):
        oauth = OAuthApplication.objects.create(client_id='future', client_type='confidential',
            authorization_grant_type='authorization-code')
        return SSOClient.objects.create(application=self.app, oauth_client=oauth,
            enabled=True, login_path='/api/auth/sso/login')

    def test_future_catalog_and_gateway_are_dynamic(self):
        self.assertIn('future-app', [app['id'] for app in self.client.get('/api/member-session').json()['applications']])
        self.assertEqual(self.client.get('/internal/authorize',
            HTTP_X_ORIGINAL_URL='https://future-app.devantiq.com/').status_code, 204)
        self.assertEqual(self.client.get(self.url)['Location'], 'https://future-app.devantiq.com/')

    def test_sso_launch_requires_explicit_identity(self):
        self.sso()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        AccountLink.objects.create(access=self.access, application=self.app, external_id='dedicated-member')
        self.assertEqual(self.client.get(self.url)['Location'], 'https://future-app.devantiq.com/api/auth/sso/login')
        self.access.delete()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_disabled_app_and_anonymous_launch_refused(self):
        self.app.enabled = False
        self.app.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertTrue(self.client.get(self.url)['Location'].startswith('/auth/?next='))

    def test_external_or_ambiguous_login_paths_rejected(self):
        for path in ('//evil.test', 'https://evil.test', '/path?next=evil', '/%2f/evil', '/a/../b', '/\\evil'):
            with self.assertRaises(ValidationError):
                validate_login_path(path)
        for path in ('', '/', '/apps/user_oidc/login/1', '/index.php/apps/user_oidc/login/1'):
            validate_login_path(path)

    def test_application_session_checks_identity_and_revocation(self):
        binding = self.sso()
        url = '/auth/apps/future-app/session/'
        self.assertEqual(self.client.get(url).status_code,403)
        AccountLink.objects.create(access=self.access,application=self.app,external_id='dedicated')
        response = self.client.get(url)
        self.assertEqual(response.json(),{'sub':str(self.user.pk),'external_account':'dedicated'})
        self.assertIn('no-store',response['Cache-Control'])
        binding.enabled=False; binding.save()
        self.assertEqual(self.client.get(url).status_code,403)

    def test_regrant_keeps_the_dedicated_identity(self):
        app = Application.objects.get(pk='g1crm')
        access = Access.objects.create(user=self.user,application=app)
        first = associate_dedicated_account(access).external_id
        access.delete()
        access = Access.objects.create(user=self.user,application=app)
        self.assertEqual(associate_dedicated_account(access).external_id,first)

    def test_explicit_existing_link_is_not_replaced(self):
        app = Application.objects.get(pk='g1crm')
        access = Access.objects.create(user=self.user,application=app)
        AccountLink.objects.create(access=access,application=app,external_id='existing')
        self.assertEqual(associate_dedicated_account(access).external_id,'existing')

    def test_new_grants_are_linked_only_for_enabled_dedicated_adapter(self):
        app = Application.objects.get(pk='g1crm')
        oauth = OAuthApplication.objects.create(client_id='dedicated-test', client_type='confidential',
            authorization_grant_type='authorization-code')
        binding = SSOClient.objects.create(application=app,oauth_client=oauth,enabled=False,dedicated_accounts=True)
        access = Access.objects.create(user=self.user,application=app)
        self.assertFalse(AccountLink.objects.filter(access=access).exists())
        access.delete()
        binding.enabled=True; binding.save()
        access=Access.objects.create(user=self.user,application=app)
        self.assertTrue(AccountLink.objects.get(access=access).external_id.startswith('dv-'))

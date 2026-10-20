from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import Access, Application
from .management.commands.verify_gateway import is_protected_redirect


class GatewayRedirectTests(SimpleTestCase):
    def test_login_redirect_accepted_for_all_routes(self):
        for path in ('/', '/agent/', '/metrics'):
            self.assertTrue(is_protected_redirect(302, 'https://devantiq.com/auth/?next=/membres.html', path))

    def test_denial_only_accepted_for_auxiliary_routes(self):
        destination = 'https://devantiq.com/auth/denied/'
        self.assertTrue(is_protected_redirect(302, destination, '/agent/'))
        self.assertTrue(is_protected_redirect(302, destination, '/metrics'))
        self.assertFalse(is_protected_redirect(302, destination, '/'))

    def test_unrelated_redirects_and_content_rejected(self):
        for destination in ('', '/auth/denied/', 'https://example.com/auth/denied/',
                            'https://devantiq.com/auth/denied/?next=https://example.com'):
            self.assertFalse(is_protected_redirect(302, destination, '/metrics'))
        for code in (200, 301, 403, 500):
            self.assertFalse(is_protected_redirect(code, 'https://devantiq.com/auth/denied/', '/metrics'))


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MemberTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user('marie', 'marie@example.test', 'Test-password-1234', first_name='Marie')
        self.app = Application.objects.get(pk='g1crm')
        self.app.enabled = True
        self.app.save()

    def grant(self):
        Access.objects.create(user=self.member, application=self.app)
        self.client.force_login(self.member)

    def authz(self, url='https://g1crm.devantiq.com/api/clients'):
        return self.client.get('/internal/authorize', HTTP_X_ORIGINAL_URL=url)

    def test_anonymous_and_forged_headers_never_grant_access(self):
        self.assertEqual(self.client.get('/api/member-session', HTTP_REMOTE_USER='marie').status_code, 401)
        self.assertEqual(self.authz().status_code, 401)

    def test_session_exposes_only_assigned_rights(self):
        self.grant()
        response = self.client.get('/api/member-session')
        self.assertEqual(response['X-DevAntiq-Session'], 'authenticated')
        self.assertIn('no-store', response['Cache-Control'])
        data = response.json()
        self.assertEqual(len(data['applications']), 9)
        self.assertEqual([a['id'] for a in data['applications'] if a['allowed']], ['g1crm'])
        self.assertTrue(data['csrf'])

    def test_grant_revocation_applies_to_existing_session(self):
        self.grant()
        self.assertEqual(self.authz().status_code, 204)
        self.assertEqual(self.authz('https://n8n.devantiq.com/').status_code, 403)
        Access.objects.filter(user=self.member).delete()
        self.assertEqual(self.authz().status_code, 403)

    def test_disabled_member_and_application_fail_closed(self):
        self.grant()
        self.app.enabled = False; self.app.save()
        self.assertEqual(self.authz().status_code, 403)
        self.member.is_active = False; self.member.save()
        self.assertEqual(self.authz().status_code, 401)
        self.assertEqual(self.client.get('/api/member-session').status_code, 401)

    def test_unknown_hosts_and_aliases_are_denied(self):
        self.grant()
        for url in ['https://evil.test/', 'https://g1crm.devantiq.com.evil.test/',
                    'http://g1crm.devantiq.com/', 'https://crm.devantiq.com/',
                    'https://admin.livemonitor.devantiq.com/', 'https://g1crm.devantiq.com:9000/',
                    'https://user@g1crm.devantiq.com/', 'https://[bad']:
            self.assertEqual(self.authz(url).status_code, 403, url)

    def test_csrf_required_for_login_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/auth/', {'username': 'marie', 'password': 'Test-password-1234'}).status_code, 403)
        client.force_login(self.member)
        self.assertEqual(client.get('/auth/logout/').status_code, 405)
        self.assertEqual(client.post('/auth/logout/').status_code, 403)
        token = client.get('/api/member-session').json()['csrf']
        self.assertEqual(client.post('/auth/logout/', {'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(client.get('/api/member-session').status_code, 401)

    def test_non_admin_cannot_manage_accounts(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/auth/admin/auth/user/').status_code, 302)
        response = self.client.post('/auth/admin/auth/user/add/', {'username': 'intruder', 'is_superuser': True})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username='intruder').exists())

    def test_admin_can_view_members_and_inline_grants(self):
        admin = User.objects.create_superuser('admin', 'admin@example.test', 'Test-password-1234')
        self.client.force_login(admin)
        response = self.client.get(reverse('admin:auth_user_change', args=[self.member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Applications attribuées')
        self.assertTrue(self.client.get('/api/member-session').json()['user']['is_admin'])

    def test_password_reset_does_not_enumerate_accounts(self):
        known = self.client.post('/auth/reset/', {'email': self.member.email})
        unknown = self.client.post('/auth/reset/', {'email': 'absent@example.test'})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known['Location'], unknown['Location'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/auth/reset/', mail.outbox[0].body)

    def test_reset_token_is_single_use_and_invalidates_sessions(self):
        self.grant()
        token = default_token_generator.make_token(self.member)
        uid = urlsafe_base64_encode(force_bytes(self.member.pk))
        other = Client()
        start = other.get(f'/auth/reset/{uid}/{token}/')
        response = other.post(start['Location'], {'new_password1': 'New-complex-password-9876', 'new_password2': 'New-complex-password-9876'})
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password('New-complex-password-9876'))
        self.assertFalse(default_token_generator.check_token(self.member, token))
        self.assertEqual(self.client.get('/api/member-session').status_code, 401)

    def test_login_redirect_cannot_leave_site(self):
        response = self.client.post('/auth/', {'username': 'marie', 'password': 'Test-password-1234', 'next': 'https://evil.test/'})
        self.assertEqual(response['Location'], '/membres.html')

    def test_login_throttle(self):
        for _ in range(12):
            self.client.post('/auth/', {'username': 'marie', 'password': 'wrong'})
        response = self.client.post('/auth/', {'username': 'marie', 'password': 'wrong'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)

    def test_administrator_can_create_member_and_assign_application(self):
        admin = User.objects.create_superuser('admin', 'admin@example.test', 'Test-password-1234')
        self.client.force_login(admin)
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'newmember', 'email': 'new@example.test', 'first_name': 'Nouveau',
            'last_name': 'Membre', 'password1': 'Very-long-test-password-2984',
            'password2': 'Very-long-test-password-2984', '_save': 'Enregistrer',
            'access_set-TOTAL_FORMS': '0', 'access_set-INITIAL_FORMS': '0',
            'access_set-MIN_NUM_FORMS': '0', 'access_set-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 302)
        member = User.objects.get(username='newmember')
        self.assertEqual(member.email, 'new@example.test')
        response = self.client.post(reverse('admin:auth_user_change', args=[member.pk]), {
            'username': member.username, 'email': member.email, 'first_name': 'Nouveau',
            'last_name': 'Membre', 'is_active': 'on', '_save': 'Enregistrer',
            'access_set-TOTAL_FORMS': '1', 'access_set-INITIAL_FORMS': '0',
            'access_set-MIN_NUM_FORMS': '0', 'access_set-MAX_NUM_FORMS': '1000',
            'access_set-0-user': str(member.pk), 'access_set-0-application': 'g1crm',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Access.objects.filter(user=member, application=self.app).exists())

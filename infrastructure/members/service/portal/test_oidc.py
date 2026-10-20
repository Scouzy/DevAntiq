import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from jwcrypto import jwk, jwt
from oauth2_provider.models import Application as OAuthApplication
from .models import Application, Access, AccountLink, SSOClient

KEY = jwk.JWK.generate(kty='RSA', size=2048)
OIDC = {**settings.OAUTH2_PROVIDER, 'OIDC_ENABLED': True,
        'OIDC_RSA_PRIVATE_KEY': KEY.export_to_pem(private_key=True, password=None).decode()}


@override_settings(OAUTH2_PROVIDER=OIDC, SECURE_SSL_REDIRECT=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OIDCTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('member', 'member@example.test', 'test-password')
        self.app = Application.objects.get(pk='cloud')
        self.app.enabled = True
        self.app.save()
        self.access = Access.objects.create(user=self.user, application=self.app)
        self.link = AccountLink.objects.create(access=self.access, application=self.app, external_id='existing-cloud-user')
        self.oauth = OAuthApplication.objects.create(name='Cloud', client_id='test-cloud',
            client_secret='test-secret-long-enough-for-test-only', client_type='confidential',
            authorization_grant_type='authorization-code', algorithm='RS256', skip_authorization=True,
            redirect_uris='https://cloud.devantiq.com/callback')
        self.binding = SSOClient.objects.create(application=self.app, oauth_client=self.oauth, enabled=True)
        self.client.force_login(self.user)
        self.verifier = 'a' * 64
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b'=').decode()

    def authorize(self, **changes):
        params = dict(client_id=self.oauth.client_id, response_type='code', scope='openid profile email',
            redirect_uri=self.oauth.redirect_uris, state='client-state', nonce='client-nonce',
            code_challenge=self.challenge, code_challenge_method='S256')
        params.update(changes)
        return self.client.get('/auth/oidc/authorize/', params, secure=True)

    def code(self):
        response = self.authorize()
        self.assertEqual(response.status_code, 302, response.content)
        query = parse_qs(urlsplit(response['Location']).query)
        self.assertNotIn('error', query)
        self.assertEqual(query['state'], ['client-state'])
        return query['code'][0]

    def exchange(self, code, **changes):
        params = dict(grant_type='authorization_code', code=code, redirect_uri=self.oauth.redirect_uris,
            client_id=self.oauth.client_id, client_secret='test-secret-long-enough-for-test-only', code_verifier=self.verifier)
        params.update(changes)
        return self.client.post('/auth/oidc/token/', params, secure=True)

    def test_complete_flow_preserves_explicit_identity_and_nonce(self):
        code = self.code()
        response = self.exchange(code)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        verified = jwt.JWT(jwt=data['id_token'], key=KEY, check_claims={
            'iss': 'https://devantiq.com/auth/oidc', 'aud': self.oauth.client_id, 'nonce': 'client-nonce'})
        claims = json.loads(verified.claims)
        self.assertEqual(claims['sub'], str(self.user.pk))
        self.assertEqual(claims['external_account'], 'existing-cloud-user')
        self.assertFalse(claims['email_verified'])
        self.assertEqual(self.exchange(code).status_code, 400)
        info = self.client.get('/auth/oidc/userinfo/', HTTP_AUTHORIZATION='Bearer ' + data['access_token'], secure=True)
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.json()['preferred_username'], 'existing-cloud-user')
        self.access.delete()
        self.assertEqual(self.client.get('/auth/oidc/userinfo/', HTTP_AUTHORIZATION='Bearer ' + data['access_token'], secure=True).status_code, 401)

    def test_unlinked_member_is_denied_even_with_matching_email(self):
        self.link.delete()
        self.assertEqual(self.authorize().status_code, 403)

    def test_revocation_between_code_and_exchange(self):
        code = self.code()
        self.access.delete()
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_disabled_member_and_disabled_client(self):
        code = self.code()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_bad_pkce_does_not_issue_tokens(self):
        self.assertEqual(self.exchange(self.code(), code_verifier='b' * 64).status_code, 400)

    def test_central_logout_revokes_pending_codes_and_tokens(self):
        pending = self.code()
        response = self.exchange(self.code())
        token = response.json()['access_token']
        self.client.logout()
        self.assertEqual(self.exchange(pending).status_code, 400)
        self.assertEqual(self.client.get('/auth/oidc/userinfo/', HTTP_AUTHORIZATION='Bearer ' + token, secure=True).status_code, 401)

    def test_client_disabled_before_exchange(self):
        code = self.code()
        self.binding.enabled = False
        self.binding.save()
        self.assertEqual(self.exchange(code).status_code, 400)
        self.assertEqual(self.authorize().status_code, 403)

    def test_identity_link_must_match_application(self):
        from django.core.exceptions import ValidationError
        self.link.application = Application.objects.get(pk='g1crm')
        with self.assertRaises(ValidationError):
            self.link.full_clean()

    def test_openid_scope_alone_does_not_leak_profile(self):
        response = self.authorize(scope='openid')
        code = parse_qs(urlsplit(response['Location']).query)['code'][0]
        response = self.exchange(code)
        self.assertEqual(response.status_code, 200)
        claims = json.loads(jwt.JWT(jwt=response.json()['id_token'], key=KEY).claims)
        self.assertNotIn('external_account', claims)
        self.assertNotIn('email', claims)

    def test_external_redirect_is_rejected(self):
        response = self.authorize(redirect_uri='https://example.com/callback')
        self.assertEqual(response.status_code, 400)

    def test_discovery_and_private_registration_unavailable(self):
        self.client.logout()
        response = self.client.get('/auth/oidc/.well-known/openid-configuration', secure=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['issuer'], 'https://devantiq.com/auth/oidc')
        self.assertEqual(self.client.post('/auth/oidc/register/', {}, secure=True).status_code, 404)

    def test_omniroute_native_flow_still_requires_secret_and_grant(self):
        omni = Application.objects.get(pk='omniroute')
        omni.enabled = True; omni.save()
        self.access.application = omni; self.access.save()
        self.link.application = omni; self.link.save()
        self.binding.application = omni
        self.binding.login_path = '/api/auth/oidc/login'; self.binding.save()
        self.oauth.redirect_uris = 'https://omniroute.devantiq.com/api/auth/oidc/callback'
        self.oauth.save()
        params = dict(client_id=self.oauth.client_id, response_type='code', scope='openid profile',
                      redirect_uri=self.oauth.redirect_uris, state='native-state')
        response = self.client.get('/auth/oidc/authorize/', params, secure=True)
        self.assertEqual(response.status_code, 302, response.content)
        code = parse_qs(urlsplit(response['Location']).query)['code'][0]
        self.assertEqual(self.exchange(code,code_verifier='',client_secret='wrong').status_code,401)
        self.assertEqual(self.exchange(code,code_verifier='').status_code,200)
        self.access.delete()
        self.assertEqual(self.client.get('/auth/oidc/authorize/',params,secure=True).status_code,403)

    def test_cloud_still_requires_pkce(self):
        response = self.client.get('/auth/oidc/authorize/',dict(client_id=self.oauth.client_id,
            response_type='code',scope='openid profile',redirect_uri=self.oauth.redirect_uris,state='s'),secure=True)
        self.assertTrue(response.status_code == 400 or 'error=' in response.get('Location',''))

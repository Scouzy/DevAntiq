import importlib.util
import json
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('cloud_sso', Path(__file__).resolve().parents[1] / 'infrastructure/members/connect_nextcloud.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CloudSetupTests(TestCase):
    def test_provider_secret_uses_php_stream_and_never_arguments(self):
        with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout='', stderr='')) as run:
            module.configure_provider({'client_id': 'test-client', 'client_secret': 'private-secret'})
            argv = run.call_args.args[0]
            self.assertIn('--clientsecret-file=php://stdin', argv)
            self.assertNotIn('--clientsecret-file=/dev/stdin', argv)
            self.assertNotIn('private-secret', ' '.join(argv))
            self.assertEqual(run.call_args.kwargs['input'], 'private-secret')

    def test_partial_settings_require_exact_safe_values(self):
        module.validate_partial_settings({})
        module.validate_partial_settings(dict(module.OIDC_SETTINGS))
        for prior in ({'auto_provision': True}, {**module.OIDC_SETTINGS, 'auto_provision': 0},
                      {**module.OIDC_SETTINGS, 'use_pkce': 'true'},
                      {**module.OIDC_SETTINGS, 'unknown': True}):
            with self.assertRaises(RuntimeError):
                module.validate_partial_settings(prior)

    def test_secret_stream_failure_is_actionable_and_redacted(self):
        with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=1,
                stdout='Client secret file "php://stdin" could not be read or is empty',
                stderr='private-secret')):
            with self.assertRaises(RuntimeError) as error:
                module.configure_provider({'client_id': 'test-client', 'client_secret': 'private-secret'})
            message = str(error.exception)
            self.assertIn('creation du fournisseur DevAntiq', message)
            self.assertIn('ne peut pas lire', message)
            self.assertNotIn('private-secret', message)

    def test_creation_returns_only_a_disabled_standard_account(self):
        record = {'created': True, 'uid': 'devantiq-hgomis', 'enabled': False, 'admin': False}
        with patch.object(module, 'php', return_value=json.dumps(record)) as php:
            self.assertEqual(module.create_cloud_account('devantiq-hgomis'), record)
            self.assertEqual(php.call_args.args[1:], ('devantiq-hgomis',))

    def test_creation_never_accepts_an_existing_account(self):
        with patch.object(module, 'php', return_value='{"created":false}'):
            with self.assertRaisesRegex(RuntimeError, 'aucune reutilisation'):
                module.create_cloud_account('admin')

    def test_creation_rejects_privileged_enabled_or_wrong_identity(self):
        for override in ({'admin': True}, {'enabled': True}, {'uid': 'admin'}):
            record = {'created': True, 'uid': 'devantiq-hgomis', 'enabled': False, 'admin': False, **override}
            with patch.object(module, 'php', return_value=json.dumps(record)):
                with self.assertRaises(RuntimeError):
                    module.create_cloud_account('devantiq-hgomis')

    def test_account_activation_requires_confirmed_state(self):
        for enabled in (True, False):
            with patch.object(module, 'php', return_value=json.dumps({'enabled': enabled})):
                module.set_cloud_enabled('devantiq-hgomis', enabled)
            with patch.object(module, 'php', return_value=json.dumps({'enabled': not enabled})):
                with self.assertRaises(RuntimeError):
                    module.set_cloud_enabled('devantiq-hgomis', enabled)

    def test_callback_loads_app_before_resolving_route(self):
        def resolve(code):
            # Model Nextcloud Router::loadRoutes, which skips unloaded apps.
            if code.index("loadApp('user_oidc')") < code.index('linkToRoute('):
                return '/index.php/apps/user_oidc/code'
            return ''
        with patch.object(module, 'php', side_effect=resolve):
            self.assertEqual(module.nextcloud_callback(),
                             'https://cloud.devantiq.com/index.php/apps/user_oidc/code')

    def test_callback_supports_pretty_urls(self):
        with patch.object(module, 'php', return_value='/apps/user_oidc/code'):
            self.assertEqual(module.nextcloud_callback(),
                             'https://cloud.devantiq.com/apps/user_oidc/code')

    def test_callback_rejects_missing_or_unexpected_routes(self):
        for path in ('', '//other.example/apps/user_oidc/code', '/apps/user_oidc/code?secret=x',
                     'https://cloud.devantiq.com/apps/user_oidc/code', '/other/code'):
            with self.subTest(path=path), patch.object(module, 'php', return_value=path):
                with self.assertRaises(RuntimeError):
                    module.nextcloud_callback()

    def provider(self):
        return {'clientId': 'client', 'settings': {'mappingUid': 'external_account',
            'uniqueUid': False, 'groupProvisioning': False, 'bearerProvisioning': False, 'checkBearer': False}}

    def test_existing_identity_is_preserved(self):
        module.validate_provider(self.provider(), 'client')

    def test_hashing_provisioning_or_wrong_client_is_rejected(self):
        for key in ('uniqueUid', 'groupProvisioning', 'bearerProvisioning', 'checkBearer'):
            value = self.provider()
            value['settings'][key] = True
            with self.assertRaises(RuntimeError):
                module.validate_provider(value, 'client')
        with self.assertRaises(RuntimeError):
            module.validate_provider(self.provider(), 'another-client')

    def test_email_mapping_is_never_accepted(self):
        value = self.provider()
        value['settings']['mappingUid'] = 'email'
        with self.assertRaises(RuntimeError):
            module.validate_provider(value, 'client')

    def test_identifiers_are_not_silently_normalized(self):
        for value in ('', ' alice', 'alice ', 'alice\nadmin'):
            with self.assertRaises(ValueError):
                module.validate_uid(value)
        self.assertEqual(module.validate_uid('Alice.Existing'), 'Alice.Existing')

    def test_secret_is_only_passed_on_stdin_and_errors_are_redacted(self):
        with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='private-secret', stderr='private-secret')) as run:
            with self.assertRaises(RuntimeError) as error:
                module.occ('user_oidc:provider', '--clientsecret-file=/dev/stdin', data='private-secret')
            self.assertNotIn('private-secret', str(error.exception))
            self.assertNotIn('private-secret', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['input'], 'private-secret')

    def test_known_member_errors_are_actionable_without_raw_output(self):
        for code, message in module.CHECK_ERRORS.items():
            with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=1, stdout='DEVANTIQ_CHECK:' + code + '\n', stderr='private-secret')):
                with self.assertRaises(RuntimeError) as error:
                    module.django('trusted script')
                self.assertEqual(str(error.exception), message)
                self.assertNotIn('private-secret', str(error.exception))

    def test_unknown_diagnostics_are_not_disclosed(self):
        with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(
                returncode=1, stdout='DEVANTIQ_CHECK:private-secret\n', stderr='private-secret')):
            with self.assertRaises(RuntimeError) as error:
                module.django('trusted script')
            self.assertNotIn('private-secret', str(error.exception))


if __name__ == '__main__':
    main()

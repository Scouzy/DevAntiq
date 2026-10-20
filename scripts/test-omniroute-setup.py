import importlib.util
import json
from pathlib import Path
import unittest
import io
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('setup',Path(__file__).resolve().parents[1]/'infrastructure/members/connect_omniroute.py')
setup=importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)

class Diagnostics(unittest.TestCase):
    def test_known_setup_failure(self):
        result=setup.safe_api_error(403,json.dumps({'error':'No password configured. Complete onboarding first.'}))
        self.assertIn('configuration initiale',result)

    def test_known_oidc_failure(self):
        result=setup.safe_api_error(403,json.dumps({'error':'Password login is disabled when OIDC is active. Please sign in with OIDC.'}))
        self.assertIn('OIDC existante',result)

    def test_never_print_untrusted_response(self):
        for response in ['private-secret',json.dumps({'error':'private-secret'}),
                         json.dumps({'error':{'code':'INVALID_ORIGIN','message':'private-secret'}}),
                         json.dumps({'error':{'code':['private-secret']}})]:
            self.assertNotIn('private-secret',setup.safe_api_error(403,response))

    def test_only_known_boolean_state(self):
        self.assertEqual(setup.login_state({'hasPassword':False,'password':'secret','oidcEnabled':'secret'}),{'hasPassword':False})

    def test_initial_password_is_backed_up_and_authentication_enabled(self):
        initial={'hasPassword':False,'setupComplete':False,'oidcEnabled':False}
        order=[]
        replies=iter([initial,{'success':True},{'hasPassword':True,'requireLogin':True}])
        def api(path,body=None):
            order.append(('api',body))
            return io.StringIO(json.dumps(next(replies)))
        with patch.object(setup.getpass,'getpass',return_value='test-password-long'):
            result=setup.administrator_password(api,initial,lambda:order.append(('backup',None)))
        self.assertEqual(result,'test-password-long')
        self.assertEqual(order[0][0],'backup')
        self.assertEqual(order[2],('api',{'requireLogin':True,'password':'test-password-long'}))

    def test_existing_password_is_never_replaced(self):
        api=Mock(); backup=Mock()
        with patch.object(setup.getpass,'getpass',return_value='existing'):
            self.assertEqual(setup.administrator_password(api,{'hasPassword':True},backup),'existing')
        api.assert_not_called(); backup.assert_not_called()

    def test_changed_state_prevents_password_write(self):
        api=Mock(return_value=io.StringIO(json.dumps({'hasPassword':True})))
        with patch.object(setup.getpass,'getpass',return_value='test-password-long'):
            with self.assertRaises(RuntimeError):
                setup.administrator_password(api,{'hasPassword':False,'setupComplete':False},Mock())
        self.assertEqual(api.call_count,1)
        self.assertEqual(len(api.call_args.args),1)

    def test_confirmation_mismatch_does_not_touch_server(self):
        api=Mock(); backup=Mock()
        with patch.object(setup.getpass,'getpass',side_effect=['test-password-long','different-password']):
            with self.assertRaises(RuntimeError):
                setup.administrator_password(api,{'hasPassword':False,'setupComplete':False},backup)
        api.assert_not_called(); backup.assert_not_called()

if __name__=='__main__': unittest.main()

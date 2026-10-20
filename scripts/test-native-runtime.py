"""Runtime matching must identify the exact entry, never just its directory."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import copy
import json

spec = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1]/'infrastructure/members/adapters/install_native.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class MatchingTests(unittest.TestCase):
    def test_normal_and_rewritten(self):
        cwd = Path('/opt/g1crm/project').resolve()
        entry = cwd/'server/index.js'
        for argv in (['node', 'server/index.js', ''], ['node', str(entry)], ['node '+str(entry), '']):
            self.assertTrue(installer.matches_entry(argv, cwd, entry))

    def test_reject_other_processes(self):
        cwd = Path('/opt/g1crm/project').resolve()
        entry = cwd/'server/index.js'
        for argv in (['node'], ['node','other.js'], ['node '+str(entry)+'.old'], ['PM2 daemon']):
            self.assertFalse(installer.matches_entry(argv, cwd, entry))

class PM2Tests(unittest.TestCase):
    def setUp(self):
        self.item = {'manager':'pm2','pm2_home':'/root/.pm2','pm2_id':1,
                     'pid':766260,'entry':'/opt/g1crm/project/server/index.js'}
        self.rows = [{'pm_id':1,'pid':766260,'pm2_env':{
            'pm_exec_path':self.item['entry'],'exec_mode':'fork_mode',
            'watch':False,'status':'online'}}]

    def test_matching_live_process(self):
        installer.validate_pm2_listing(self.rows,self.item,require_pid=True)

    def test_reject_changed_or_unsafe_target(self):
        for field,value in [('pm_exec_path','/another/index.js'),('watch',True),('exec_mode','cluster_mode')]:
            rows=copy.deepcopy(self.rows); rows[0]['pm2_env'][field]=value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                installer.validate_pm2_listing(rows,self.item)
        for rows in [[],self.rows*2,[{**self.rows[0],'pid':2}]]:
            with self.assertRaises(RuntimeError):
                installer.validate_pm2_listing(rows,self.item,require_pid=True)

    def test_restart_only_selected_id_without_updating_environment(self):
        with patch.object(installer,'pm2_command',return_value=json.dumps(self.rows)) as command:
            installer.restart_runtime(self.item)
        self.assertEqual([call.args[1:] for call in command.call_args_list], [('jlist',),('restart','1')])

    def test_no_restart_if_id_reassigned(self):
        self.rows[0]['pm2_env']['pm_exec_path']='/another/index.js'
        with patch.object(installer,'pm2_command',return_value=json.dumps(self.rows)) as command:
            with self.assertRaises(RuntimeError): installer.restart_runtime(self.item)
        self.assertEqual(command.call_count,1)

    def test_rollback_can_restart_stopped_target(self):
        self.rows[0]['pid']=0; self.rows[0]['pm2_env']['status']='errored'
        with patch.object(installer,'pm2_command',return_value=json.dumps(self.rows)) as command:
            installer.restart_runtime(self.item)
        self.assertEqual(command.call_args.args[1:],('restart','1'))

    def test_managers_and_pm2_ids_remain_distinct(self):
        items=[self.item,{**self.item,'pm2_id':0},
               {'manager':'systemd','unit':'g1profil-api.service'},
               {'manager':'systemd','unit':'livemonitor-backend.service'}]
        self.assertEqual(len({installer.runtime_key(item) for item in items}),4)
        with patch.object(installer,'run') as command:
            installer.restart_runtime(items[2])
        command.assert_called_once_with(['systemctl','restart','g1profil-api.service'])

if __name__ == '__main__': unittest.main()

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from ui.farm_control import FarmJobs,guardar_pool


class FarmControlTests(unittest.TestCase):
    def test_invalid_proxy_save_does_not_overwrite_existing_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pool.json'
            path.write_text('original')
            with self.assertRaises(ValueError):
                guardar_pool(path,[dict(host='192.0.2.1',port=8000,exit_ip='203.0.113.1',enabled=True)])
            self.assertEqual(path.read_text(),'original')

    def test_proxy_save_preserves_row_order_and_boolean_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pool.json'
            guardar_pool(path,[dict(host='192.0.2.2',port=8000,exit_ip='203.0.113.2',enabled=False),
                               dict(host='192.0.2.1',port=8001,exit_ip='203.0.113.1',enabled=False)])
            rows=json.loads(path.read_text())['proxies']
            self.assertEqual([r['host'] for r in rows],['192.0.2.2','192.0.2.1'])
            self.assertIs(rows[0]['enabled'],False)

    @patch.dict(os.environ,{'OPENAI_API_KEY':'unit-test','PANDA_SIMULATION':''})
    @patch('core.deployment_check.fijar_adb_local')
    @patch('core.deployment_check.preparar_pool',return_value=[{'enabled':True}]*3)
    @patch('ui.farm_control.subprocess.Popen')
    def test_start_and_cooperative_stop_preserve_database_and_prevent_duplicate_process(self,popen,pool,adb):
        popen.return_value.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory:
            jobs=FarmJobs(directory)
            db=Path(directory)/'db.sqlite'
            jobs.start(smoke=True,count=3,cycles=1,db_path=db)
            command=popen.call_args.args[0]
            self.assertIn('--smoke-test',command)
            self.assertIn('--stop-file',command)
            self.assertEqual(popen.call_args.kwargs['env']['TIKTOK_DB_PATH'],str(db))
            with self.assertRaises(RuntimeError):jobs.start(smoke=True,count=3,cycles=1,db_path=db)
            jobs.cancel()
            self.assertTrue(jobs.snapshot()['stopping'])
            popen.return_value.terminate.assert_not_called()

    @patch('ui.farm_control.subprocess.Popen')
    def test_invalid_smoke_cycles_do_not_launch_any_process(self,popen):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                FarmJobs(directory).start(smoke=True,count=3,cycles=0,db_path=Path(directory)/'db')
        popen.assert_not_called()


class FarmPanelTests(unittest.TestCase):
    def test_dashboard_exposes_proxy_save_and_automation_launch(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        try:
            with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(directory)/'ui.db')}):
                jobs=Mock()
                jobs.snapshot.return_value=None
                with patch('ui.farm_control.FarmJobs',return_value=jobs),patch('ui.farm_control.guardar_pool',return_value=[{'enabled':False}]) as save,patch('config.proxies.adb',return_value='List of devices attached\n'),patch('core.adb_pool.socket.create_connection'):
                    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                    self.assertFalse(app.exception)
                    self.assertTrue(any(b.label=='Guardar proxies' for b in app.button))
                    app.button(key='farm_start').click().run()
                    self.assertFalse(app.exception)
                    jobs.start.assert_called_once_with(smoke=True,count=3,cycles=1,db_path=Path(directory)/'ui.db',network_mode='root')
                    next(b for b in app.button if b.label=='Guardar proxies').click().run()
                    self.assertFalse(app.exception)
                    save.assert_called_once()
        finally:
            st.cache_resource.clear()

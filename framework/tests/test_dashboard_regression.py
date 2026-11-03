import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.database import Database
from launch_dashboard import iniciar_dashboard


class DatabaseHotReloadTests(unittest.TestCase):
    def test_dashboard_recovers_stale_database_class(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from core import database as storage
        st.cache_resource.clear()
        original = storage.Database
        try:
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'TIKTOK_DB_PATH':str(Path(folder)/'test.db')}):
                class PreviousDatabase:
                    pass
                storage.Database = PreviousDatabase
                with patch('config.proxies.adb',return_value='List of devices attached\n'), patch('core.adb_pool.socket.create_connection'):
                    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                self.assertFalse(app.exception)
                self.assertTrue(hasattr(storage.Database,'auditoria_proxies'))
        finally:
            storage.Database = original
            st.cache_resource.clear()


class DesktopLauncherTests(unittest.TestCase):
    @patch('launch_dashboard.disponible',return_value=True)
    @patch('launch_dashboard.subprocess.Popen')
    def test_reuses_server(self,popen,health):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(iniciar_dashboard(root),'http://127.0.0.1:8501')
        popen.assert_not_called()

    @patch('launch_dashboard.time.sleep')
    @patch('launch_dashboard.disponible',side_effect=[False,True])
    @patch('launch_dashboard.subprocess.Popen')
    def test_starts_hidden_server_without_console(self,popen,health,sleep):
        with tempfile.TemporaryDirectory() as root:
            iniciar_dashboard(root)
        args=popen.call_args.args[0]
        self.assertIn('127.0.0.1',args)
        self.assertIn('--server.headless',args)
        self.assertFalse(popen.call_args.kwargs.get('shell',False))

    @patch('launch_dashboard.disponible',return_value=False)
    @patch('launch_dashboard.subprocess.Popen')
    def test_start_failure_points_to_log(self,popen,health):
        popen.return_value.poll.return_value=1
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError,'dashboard-server.log'):
                iniciar_dashboard(root)


class DashboardRegressionTests(unittest.TestCase):
    def test_seeded_kpis_pagination_device_and_skip_filter(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        try:
            with tempfile.TemporaryDirectory() as directory:
                with patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(directory)/'ui.db')}):
                    db=Database()
                    for i in range(30):
                        key=db.registrar_interaccion('device-a' if i<26 else 'device-b',
                            run_id='seed',ciclo=i,descripcion_video=f'video {i}',
                            decision_ia={'interactuar':i%2==0},latencia_ms=10)
                        db.finalizar_interaccion(key)
                    with patch('config.proxies.adb',return_value='List of devices attached\ndevice-a device\ndevice-b device\n'),patch('core.adb_pool.socket.create_connection'):
                        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                        self.assertFalse(app.exception)
                        self.assertEqual(app.metric[0].value,'2')
                        self.assertEqual(app.metric[1].value,'30')
                        self.assertEqual(len(next(frame.value for frame in app.dataframe if 'descripcion_video' in frame.value.columns)),25)
                        app.number_input(key='audit_page').set_value(2).run()
                        self.assertFalse(app.exception)
                        self.assertEqual(len(next(frame.value for frame in app.dataframe if 'descripcion_video' in frame.value.columns)),5)
                        app.selectbox(key='audit_device').select('device-b').run()
                        self.assertEqual(app.number_input(key='audit_page').value,1)
                        self.assertEqual(len(next(frame.value for frame in app.dataframe if 'descripcion_video' in frame.value.columns)),4)
                        app.checkbox(key='audit_skip').check().run()
                        self.assertFalse(app.exception)
                        self.assertEqual(len(next(frame.value for frame in app.dataframe if 'descripcion_video' in frame.value.columns)),2)
        finally:
            st.cache_resource.clear()

    def test_diagnostic_button_dispatch_without_touching_devices(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        try:
            with tempfile.TemporaryDirectory() as directory:
                with patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(directory)/'ui.db')}):
                    jobs=Mock()
                    jobs.snapshot.return_value=None
                    with patch('ui.jobs.DiagnosticJobs',return_value=jobs),patch('config.proxies.adb',return_value='List of devices attached\n'),patch('core.adb_pool.socket.create_connection'):
                        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                        next(button for button in app.button if button.label=='Lanzar diagnóstico físico').click().run()
                        self.assertFalse(app.exception)
                        jobs.start.assert_called_once_with('com.zhiliaoapp.musically')
        finally:
            st.cache_resource.clear()

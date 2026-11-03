import json
import multiprocessing as mp
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from core.database import Database
from core.diagnostic_bridge import DiagnosticBridge, escribir_json


def guardar_lote(path,index):
    db=Database(path)
    for cycle in range(10):
        key=db.registrar_interaccion(f'usb-{index}',run_id='parallel',ciclo=cycle,
            descripcion_video='prueba',decision_ia={'interactuar':False},latencia_ms=12)
        db.finalizar_interaccion(key)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(Path(self.temp.name)/'qa.db')

    def tearDown(self):
        self.temp.cleanup()

    def insert(self,cycle=1,**kwargs):
        return self.db.registrar_interaccion('usb',run_id='run',ciclo=cycle,
            descripcion_video='qué bonito',decision_ia={'interactuar':False},latencia_ms=12,**kwargs)

    def test_wal_foreign_keys_and_idempotency(self):
        with self.db.conexion() as con:
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0],'wal')
            self.assertEqual(con.execute('PRAGMA foreign_keys').fetchone()[0],1)
        key=self.insert()
        self.assertEqual(self.insert(),key)
        with self.db.conexion() as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM dispositivos WHERE id_adb='usb'")

    def test_pending_requested_actions_are_not_counted_as_clicks(self):
        key=self.db.registrar_interaccion('usb',run_id='r',ciclo=1,descripcion_video='video',
            decision_ia={'interactuar':True,'dar_like':True,'comentar':True},latencia_ms=123)
        self.assertEqual(self.db.kpis()['exitosas'],0)
        self.db.registrar_accion(key,'like_click')
        self.db.registrar_accion(key,'comment_send_click','qué alegría 🔥')
        self.db.finalizar_interaccion(key)
        self.assertEqual(self.db.kpis()['tasa_likes'],100)
        rows,_=self.db.interacciones()
        self.assertEqual(rows[0]['comentario_texto'],'qué alegría 🔥')

    def test_skip_filter_ignores_api_fallback_and_pagination(self):
        first=self.insert(1)
        self.db.finalizar_interaccion(first)
        self.insert(2,ia_valida=False)
        rows,total=self.db.interacciones(skip_only=True,limit=1)
        self.assertEqual(total,1)
        self.assertEqual(rows[0]['id'],first)
        self.assertEqual(self.db.interacciones(device="usb' OR 1=1 --")[1],0)

    def test_inventory_updates_and_metadata_preserved(self):
        self.db.actualizar_dispositivo('usb',alias='Placa 01',proxy='192.0.2.1:80',
                                      estado='Calentando',conectado=True)
        self.db.sincronizar_inventario({'usb':'device','bad':'unauthorized'})
        row=next(x for x in self.db.dispositivos() if x['id_adb']=='usb')
        self.assertEqual(row['estado'],'Calentando')
        self.assertEqual(row['alias'],'Placa 01')
        self.assertEqual(self.db.kpis()['conectados'],1)
        self.db.sincronizar_inventario({})
        self.assertEqual(self.db.kpis()['conectados'],0)

    def test_thread_concurrency_separate_connections(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda cycle:self.insert(cycle),range(40)))
        self.assertEqual(len(set(ids)),40)
        self.assertEqual(self.db.interacciones()[1],40)

    def test_process_concurrency(self):
        ctx=mp.get_context('spawn')
        processes=[ctx.Process(target=guardar_lote,args=(str(self.db.path),i)) for i in range(4)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(30)
            if process.is_alive():
                process.terminate()
                process.join()
            self.assertEqual(process.exitcode,0)
        self.assertEqual(self.db.interacciones()[1],40)


class BridgeTests(unittest.TestCase):
    @patch('ui.jobs.subprocess.Popen')
    def test_job_exclusion_prompt_response_and_initialization_error(self,popen):
        from ui.jobs import DiagnosticJobs
        process=popen.return_value
        process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory:
            jobs=DiagnosticJobs(directory)
            job=jobs.start('app')
            self.assertIn('--diagnose-device',popen.call_args.args[0])
            self.assertIn('--diagnostic-session',popen.call_args.args[0])
            with self.assertRaises(RuntimeError):
                jobs.start('app')
            escribir_json(job/'prompt.json',{'id':'first','pending':True})
            with self.assertRaises(RuntimeError):
                jobs.answer('old','s')
            jobs.answer('first','s')
            self.assertEqual(json.loads((job/'response.json').read_text())['answer'],'s')
            jobs.cancel()
            self.assertTrue((job/'cancel').exists())
            process.poll.return_value=1
            self.assertEqual(jobs.snapshot()['diagnostics']['status'],'initialization_error')

    def test_question_answer_and_stale_id(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge=DiagnosticBridge(directory)
            def respond(_):
                prompt=json.loads(Path(directory,'prompt.json').read_text())
                escribir_json(Path(directory,'response.json'),{'id':prompt['id'],'answer':'s'})
            with patch('core.diagnostic_bridge.time.sleep',side_effect=respond):
                self.assertEqual(bridge.preguntar('pregunta'),'s')
            prompt=json.loads(Path(directory,'prompt.json').read_text())
            self.assertFalse(prompt['pending'])

    def test_cancel_raises_cooperatively(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge=DiagnosticBridge(directory)
            Path(directory,'cancel').touch()
            with self.assertRaises(KeyboardInterrupt):
                bridge.preguntar('pregunta')

    @patch('sys.argv',['main.py','--ui'])
    @patch('main.verificar_adb',side_effect=AssertionError('UI no necesita ADB'))
    @patch('main.subprocess.call',return_value=0)
    def test_ui_launcher_is_loopback_without_adb(self,call,check):
        from main import main
        self.assertEqual(main(),0)
        self.assertIn('streamlit',call.call_args.args[0])
        self.assertIn('127.0.0.1',call.call_args.args[0])
        check.assert_not_called()


class DashboardTests(unittest.TestCase):
    def test_streamlit_render_empty_and_audit_filters(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(directory)/'ui.db')}):
                from config.proxies import ADBError
                with patch('config.proxies.adb',side_effect=ADBError('ADB no disponible')),patch('core.adb_pool.socket.create_connection'):
                    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                    self.assertEqual(list(app.exception),[])
                    self.assertEqual([x.label for x in app.tabs],
                        ['Panel de Control','Auditoría de IA','Configuración y Pruebas'])
                    self.assertEqual(app.metric[0].value,'0')
                    app.checkbox[0].check().run()
                    self.assertEqual(list(app.exception),[])

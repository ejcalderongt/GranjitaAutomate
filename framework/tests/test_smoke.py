import json
import os
import signal
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot
from core.database import Database
from core.mass_orchestrator import seleccionar_subset,ejecutar_plan_granja,farm_worker


def snapshot(count):
    server=ADBServer('127.0.0.1',5038)
    return PoolSnapshot({f's{i:02d}':DeviceRoute(f's{i:02d}',server,'device',[server])
                        for i in range(count)},{},[server])


class SmokeSelectionTests(unittest.TestCase):
    def test_selects_first_authorized_serials_and_excludes_emulators(self):
        data=snapshot(34)
        data.devices['a-offline']=DeviceRoute('a-offline',data.successful[0],'offline')
        data.devices['emulator-5554']=DeviceRoute('emulator-5554',data.successful[0],'device')
        self.assertEqual(seleccionar_subset(data,3),{'s00','s01','s02'})
        with self.assertRaises(ValueError):
            seleccionar_subset(data,40)

    @patch('sys.argv',['main.py','--smoke-test','3','--package','app.test','--activity','app.Main','--devices','40'])
    def test_cli_implies_farm_and_caps_concurrency(self):
        from main import argumentos
        args=argumentos()
        self.assertTrue(args.start_farm)
        self.assertEqual(args.devices,3)

    @patch('sys.argv',['main.py','--smoke-test','3','--package','app.test','--activity','app.Main','--cycles','0'])
    def test_rejects_unbounded_smoke(self):
        from main import argumentos
        with self.assertRaises(SystemExit):argumentos()

    def run_schedule(self,cancel):
        initial=snapshot(34)
        late=snapshot(35)
        late.devices['a-new']=DeviceRoute('a-new',initial.successful[0],'device',initial.successful)
        stats={'started':[],'retained':False,'handlers':{}}
        class Event:
            flag=False
            def is_set(self):return self.flag
            def set(self):self.flag=True
            def wait(self,seconds):
                stats['retained'] |= any(r['estado']=='retenido_smoke' for r in db.reservas_proxy())
                if cancel and len(stats['started'])==3:
                    stats['handlers'][signal.SIGINT](signal.SIGINT,None)
                return self.flag
        event=Event()
        self_test=self
        class Process:
            exitcode=0
            def __init__(self,**kwargs):
                self.item=kwargs['args'][0]; self.alive=False; self.seen=0; self.pid=100+len(stats['started'])
            def start(self):
                self.alive=True
                stats['started'].append(self.item['route'].serial)
                if self.item['route'].serial=='s00':
                    self_test.assertEqual(self.item['alias'],'Alias histórico')
                    self_test.assertEqual(self.item['legacy_device_id'],'agx-canonical')
            def is_alive(self):
                self.seen+=1
                if self.seen>=5:self.alive=False
                return self.alive
            def join(self,*args):
                if event.flag:self.alive=False
            def terminate(self):self.alive=False;self.exitcode=-15
        ctx=SimpleNamespace(Event=lambda:event,BoundedSemaphore=threading.BoundedSemaphore,
            Lock=threading.Lock,Value=lambda *args:SimpleNamespace(value=0),Process=Process)
        def register(sig,handler):stats['handlers'][sig]=handler
        args=SimpleNamespace(smoke_test=3,devices=3,api_concurrency=2,shutdown_grace=1,package='app')
        with tempfile.TemporaryDirectory() as temp:
            db=Database(Path(temp)/'db.sqlite')
            with db.conexion() as con:
                con.execute('CREATE TABLE legacy_agx_identities(legacy_id TEXT,canonical_id TEXT,hardware_serial TEXT,alias TEXT)')
                con.execute("INSERT INTO legacy_agx_identities VALUES ('agx-canonical','agx-canonical','s00','Alias histórico')")
            with patch('core.mass_orchestrator.ROOT',Path(temp)),patch('core.mass_orchestrator.mp.get_context',return_value=ctx),\
                 patch('core.mass_orchestrator.startup_delay',return_value=0),patch('core.mass_orchestrator.signal.signal',side_effect=register),\
                 patch('core.mass_orchestrator.descubrir_pool',return_value=late),patch('core.mass_orchestrator.cleanup_worker',return_value=None) as cleanup:
                result=ejecutar_plan_granja(args,initial.successful,initial,
                    [('192.0.2.1',8000+i) for i in range(34)],db)
            self.assertEqual(result,0)
            self.assertEqual(stats['started'],['s00','s01','s02'])
            self.assertEqual(cleanup.call_count,3)
            self.assertEqual(db.reservas_proxy(),[])
            run=db.ultimo_smoke()
            self.assertEqual(json.loads(run['subset_json']),['s00','s01','s02'])
            self.assertEqual(run['estado'],'cancelado' if cancel else 'completado')
            with db.conexion() as con:
                summary=json.loads(con.execute('SELECT detalle FROM resumenes_carga WHERE run_id=?',(run['run_id'],)).fetchone()[0])
            self.assertEqual([row['id_adb'] for row in summary],['s00','s01','s02'])
        return stats

    def test_rescan_never_expands_subset_and_releases_leases_at_end(self):
        self.assertTrue(self.run_schedule(False)['retained'])

    def test_sigint_recovers_only_selected_devices(self):
        self.run_schedule(True)


class SmokeNetworkTests(unittest.TestCase):
    def test_same_ip_is_recorded_but_cannot_be_confirmed_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Database(Path(temp)/'db.sqlite')
            for serial in ('a','b'):
                db.registrar_ip('run',serial,'203.0.113.1',smoke=True)
            def confirm(serial):
                try:
                    db.registrar_ip('run',serial,'203.0.113.1',smoke=True,confirmada=True)
                    return True
                except sqlite3.IntegrityError:return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sum(pool.map(confirm,['a','b'])),1)
            self.assertEqual(len(db.ips_ejecucion('run')),2)

    @patch('core.mass_orchestrator.signal.signal')
    @patch('core.mass_orchestrator.Database')
    @patch('core.mass_orchestrator.ProxyAllocator')
    @patch('core.mass_orchestrator.cleanup_worker',return_value=None)
    @patch('core.mass_orchestrator.OpenAI')
    @patch('core.mass_orchestrator.consultar_ip',return_value='203.0.113.1')
    @patch('core.mass_orchestrator.trafico_restringido',return_value=nullcontext(Mock()))
    @patch('core.mass_orchestrator.configurar_proxy_dispositivo')
    @patch('core.mass_orchestrator.shell',side_effect=lambda *a,**kw:'192.0.2.1:8000' if 'http_proxy' in a else 'Status: ok')
    @patch('core.mass_orchestrator.adb',side_effect=lambda *a,**kw: 'usb:1-1' if a[-1]=='get-devpath' else 'device')
    def test_collision_aborts_before_app_and_api(self,adb,shell,proxy,guard,ip,api,cleanup,allocator,database,signals):
        allocator.return_value.validar.return_value=True
        allocator.return_value.confirmar_salida.side_effect=ValueError('Colisión de IP')
        stop=Mock();stop.is_set.return_value=False
        args=SimpleNamespace(smoke_test=3,package='app',activity='.Main',cycles=1,rpm=30)
        route=snapshot(1).devices['s00']
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(SystemExit) as exit:
                farm_worker({'route':route,'proxy':('192.0.2.1',8000),'directory':temp,
                    'reservation_owner':'run'},args,stop,None,None,None,str(Path(temp)/'db.sqlite'))
        self.assertEqual(exit.exception.code,1)
        stop.set.assert_called()
        api.assert_not_called()
        self.assertFalse(any('start' in c.args for c in shell.call_args_list))
        self.assertEqual(database.return_value.registrar_ip.call_count,2)
        cleanup.assert_called_once()


class SmokeDashboardTests(unittest.TestCase):
    def test_live_log_section_and_passive_devices(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(temp)/'db.sqlite')}):
                db=Database()
                db.iniciar_ejecucion('run',['a'],smoke=True)
                db.log_granja('run','a','Espera Dinámica')
                db.log_granja('run','a','Micro-dumps de interfaz',detalle={'attempt':1})
                db.registrar_ip('run','a','203.0.113.1',smoke=True,confirmada=True)
                with patch('config.proxies.adb',return_value='List of devices attached\na device\nb device\n'),patch('core.adb_pool.socket.create_connection'):
                    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                self.assertFalse(app.exception)
                self.assertIn('Smoke Test · Logs Vivos',[x.value for x in app.subheader])
                self.assertTrue(any('Micro-dumps de interfaz' in x.value for x in app.code))
                rows=app.dataframe[0].value
                passive=rows[rows['id_adb']=='b'].iloc[0]
                self.assertEqual(passive['smoke_test'],'Pasiva — fuera del subset')
        finally:st.cache_resource.clear()

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from datetime import datetime,timezone

from config.proxies import ADBError,ProxyAllocator
from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot,descubrir_pool
from core.bootstrap import recuperar_sesiones,recuperar_placa,preparar_pantalla
from core.database import Database
from core.runtime_health import ClienteRecuperable


def wait_in_child(stop,ready):
    ready.send(True)
    ready.close()
    stop.wait(60)


class BootstrapTests(unittest.TestCase):
    def test_34_reconnections_are_dispatched_concurrently(self):
        server=ADBServer('127.0.0.1',5038)
        targets=[f'127.0.0.1:{5500+i}' for i in range(34)]
        barrier=threading.Barrier(34,timeout=3)
        calls=[]
        def connect(*args,**kwargs):
            calls.append(args)
            barrier.wait()
            return 'connected'
        with patch('core.adb_pool.consultar_servidor',side_effect=[{},dict.fromkeys(targets,'device')]),patch('core.adb_pool.proxies.adb',side_effect=connect):
            result=descubrir_pool([server],reconnect=True,targets={server:targets},connect_workers=40)
        self.assertEqual(len(calls),34)
        self.assertEqual(len(result.devices),34)

    def test_bootstrap_initializes_only_missing_local_adb_server(self):
        server=ADBServer('127.0.0.1',5038)
        with patch('core.adb_pool.consultar_servidor',side_effect=[ADBError('down'),{}]),patch('core.adb_pool.proxies.adb') as command:
            descubrir_pool([server],initialize_servers=True)
        command.assert_called_once_with('-H','127.0.0.1','-P','5038','start-server',timeout=3)

    def test_offline_transport_is_reset_without_disconnecting_other_devices(self):
        server=ADBServer('127.0.0.1',5038)
        with patch('core.adb_pool.consultar_servidor',side_effect=[{'127.0.0.1:5555':'offline'},{'127.0.0.1:5555':'device'}]),patch('core.adb_pool.proxies.adb') as command:
            descubrir_pool([server],reconnect=True,targets={server:['127.0.0.1:5555']})
        self.assertEqual([c.args[-2:] for c in command.call_args_list],[('disconnect','127.0.0.1:5555'),('connect','127.0.0.1:5555')])

    def test_cold_start_waits_for_delayed_hardware_before_starting_plan(self):
        from core.mass_orchestrator import _iniciar_granja
        server=ADBServer('127.0.0.1',5038)
        empty=PoolSnapshot({},{},[server])
        ready=PoolSnapshot({'usb':DeviceRoute('usb',server,'device',[server])},{},[server])
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            args=SimpleNamespace(adb_servers=None,devices=1,plan=False,smoke_test=None,
                                 bootstrap_parallelism=40,bootstrap_timeout=2,proxy_pool=Path(folder)/'proxies.json')
            with patch('core.mass_orchestrator.Database',return_value=db),patch('core.mass_orchestrator.cargar_servidores',return_value=[server]),patch('core.mass_orchestrator.cargar_objetivos',return_value={server:['127.0.0.1:5555']}),patch('core.mass_orchestrator.descubrir_pool',side_effect=[empty,ready]) as discover,patch('core.mass_orchestrator.time.sleep'),patch('core.mass_orchestrator.recuperar_sesiones'),patch('core.deployment_check.verificar_despliegue'),patch('core.mass_orchestrator.leer_proxy_pool',return_value=[]),patch('core.mass_orchestrator.ejecutar_plan_granja',return_value=0) as plan,patch.dict('os.environ',{'OPENAI_API_KEY':'unit-test'}):
                self.assertEqual(_iniciar_granja(args),0)
                self.assertEqual(discover.call_count,2)
                plan.assert_called_once()

    def test_stale_lease_is_cleaned_before_releasing_proxy_and_only_temp_xml_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'sessions'
            directory=root/'farm/old/device-000'
            directory.mkdir(parents=True)
            db=Database(Path(folder)/'db.sqlite')
            allocator=ProxyAllocator(db)
            allocator.sincronizar([{'endpoint':'192.0.2.1:8000','host':'192.0.2.1','port':8000}])
            allocator.reservar('physical-01','old')
            data={'serial':'127.0.0.1:5555','device_id':'physical-01','hardware_serial':'physical-01',
                  'host':'127.0.0.1','port':5038,'owner':'old','pid':999999,'supervisor_pid':999998}
            (directory/'supervisor_lease.json').write_text(json.dumps(data))
            (directory/'window_dump.xml').write_text('<old/>')
            (directory/'evidence.xml').write_text('<keep/>')
            def cleanup(*args):
                self.assertEqual(len(db.reservas_proxy()),1)
                return None
            with patch('core.bootstrap.proceso_vivo',return_value=False),patch('core.bootstrap.reconectar_placa'):
                report=recuperar_sesiones(root,SimpleNamespace(package='app'),db,cleanup)
            self.assertEqual(db.reservas_proxy(),[])
            self.assertFalse((directory/'window_dump.xml').exists())
            self.assertTrue((directory/'evidence.xml').exists())
            self.assertIsNone(report['workers'][0]['error'])

    def test_failed_reconnection_keeps_proxy_quarantined(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            allocator=ProxyAllocator(db)
            allocator.sincronizar([{'endpoint':'192.0.2.1:8000','host':'192.0.2.1','port':8000}])
            allocator.reservar('physical-01','old')
            item={'route':DeviceRoute('127.0.0.1:5555',ADBServer('127.0.0.1',5038),'device',hardware_serial='physical-01'),
                  'device_id':'physical-01','reservation_owner':'old','directory':folder}
            cleanup=Mock()
            with patch('core.bootstrap.reconectar_placa',side_effect=ADBError('offline')):
                self.assertIsNotNone(recuperar_placa(item,SimpleNamespace(package='app'),db,cleanup))
            cleanup.assert_not_called()
            self.assertEqual(db.reservas_proxy()[0]['estado'],'cuarentena')
            self.assertEqual(db.dispositivos()[0]['estado'],'Cuarentena')

    def test_wake_only_sends_basic_unlock_commands(self):
        command=Mock()
        preparar_pantalla(DeviceRoute('usb',ADBServer('localhost',5037),'device'),command=command)
        self.assertEqual([c.args[-1] for c in command.call_args_list],['KEYCODE_WAKEUP','KEYCODE_MENU'])

    def test_active_previous_worker_is_never_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'sessions'
            directory=root/'farm/old/device-000'
            directory.mkdir(parents=True)
            (directory/'supervisor_lease.json').write_text(json.dumps({'pid':123}))
            (directory/'window_dump.xml').write_text('<in-use/>')
            cleanup=Mock()
            with patch('core.bootstrap.proceso_vivo',return_value=True):
                result=recuperar_sesiones(root,SimpleNamespace(package='app'),Database(Path(folder)/'db.sqlite'),cleanup)
            cleanup.assert_not_called()
            self.assertTrue((directory/'window_dump.xml').exists())
            self.assertTrue(result['skipped'])

    def test_finished_manifest_cleans_only_known_xml_without_touching_device(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'sessions'
            directory=root/'farm/old/device-000'
            directory.mkdir(parents=True)
            (directory.parent/'manifest.json').write_text(json.dumps({'workers':[{'directory':str(directory),'pid':999}]}))
            (directory/'window_dump.xml').write_text('<old/>')
            (directory/'audit.jsonl').write_text('preserve')
            cleanup=Mock()
            with patch('core.bootstrap.proceso_vivo',return_value=False):
                result=recuperar_sesiones(root,SimpleNamespace(package='app'),Database(Path(folder)/'db.sqlite'),cleanup)
            cleanup.assert_not_called()
            self.assertEqual(result['xml_removed'],1)
            self.assertTrue((directory/'audit.jsonl').exists())


class RecoverableAPITests(unittest.TestCase):
    @patch('__main__.__file__', str(Path(__file__).resolve()), create=True)
    def test_terminating_spawned_worker_does_not_block_shared_stop_flag(self):
        import os
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        database_env = patch.dict(os.environ, {'TIKTOK_DB_PATH': str(Path(folder.name)/'spawn.db')})
        database_env.start()
        self.addCleanup(database_env.stop)
        import multiprocessing as mp
        from core.runtime_health import ParadaRecuperable
        context=mp.get_context('spawn')
        stop=ParadaRecuperable(context)
        receiver,sender=context.Pipe(duplex=False)
        process=context.Process(target=wait_in_child,args=(stop,sender))
        process.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(10))
            self.assertTrue(receiver.recv())
            process.terminate()
            process.join(5)
            self.assertFalse(process.is_alive())
            stop.set()
            self.assertTrue(stop.wait(.1))
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            receiver.close()

    def test_api_exception_releases_admission_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            client=Mock()
            client.chat.completions.create.side_effect=RuntimeError('network')
            limited=ClienteRecuperable(client,db,'worker','run','device',threading.Event(),60,2)
            with self.assertRaises(RuntimeError):limited.create()
            with db.conexion() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM api_slots').fetchone()[0],0)

    def test_api_concurrency_is_bounded_without_process_semaphores(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            lock=threading.Lock()
            state={'active':0,'max':0}
            def request():
                with lock:
                    state['active']+=1
                    state['max']=max(state['max'],state['active'])
                time.sleep(.03)
                with lock:state['active']-=1
            client=Mock()
            client.chat.completions.create.side_effect=request
            clients=[ClienteRecuperable(client,db,str(i),'run',str(i),threading.Event(),100000,2) for i in range(6)]
            with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda c:c.create(),clients))
            self.assertLessEqual(state['max'],2)
            self.assertEqual(client.chat.completions.create.call_count,6)


class IsolatedHealTests(unittest.TestCase):
    def test_failed_worker_restarts_without_stopping_other_device(self):
        self.run_case()

    def test_watchdog_reclaims_dead_worker_api_slot_without_stopping_other_device(self):
        self.run_case(hung=True)

    def run_case(self,hung=False):
        from core.mass_orchestrator import ejecutar_plan_granja
        server=ADBServer('127.0.0.1',5038)
        snapshot=PoolSnapshot({s:DeviceRoute(s,server,'device',[server]) for s in ('s00','s01')},{},[server])
        stats=[]
        stop=threading.Event()
        class Process:
            def __init__(self,**kwargs):
                self.item=kwargs['args'][0];self.pid=90000+len(stats);self.exitcode=0;self.alive=False;self.polls=0
            def start(self):
                self.alive=True
                device=self.item['device_id']
                self.exitcode=1 if device=='s00' and self.item.get('heal_attempt',0)==0 else 0
                stats.append(device)
                self.hung=hung and bool(self.exitcode)
                if self.hung:
                    self.item['started_at']=time.time()-500
                    with db.conexion() as con:
                        con.execute('UPDATE dispositivos SET ultimo_heartbeat=? WHERE id_adb=?',
                            (datetime.fromtimestamp(time.time()-500,timezone.utc).isoformat(),device))
                        con.execute('INSERT INTO api_slots VALUES (?,?,?)',(self.item['worker_token'],'run',time.time()+120))
                else:
                    (Path(self.item['directory'])/'worker_exit.json').write_text(json.dumps({'retryable':True,'work_completed':False}))
            def is_alive(self):
                if self.hung:return self.alive
                self.polls+=1
                if self.polls>=2:self.alive=False
                return self.alive
            def join(self,*args):pass
            def terminate(self):self.alive=False;self.exitcode=-15
        ctx=SimpleNamespace(Event=lambda:stop,BoundedSemaphore=lambda n:None,Lock=lambda:None,
                            Value=lambda *a:None,Process=Process)
        args=SimpleNamespace(smoke_test=2,devices=2,api_concurrency=2,package='app',shutdown_grace=1,
                             auto_heal=True,auto_heal_attempts=1,bootstrap_parallelism=2,worker_timeout=180)
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            def heal(item,*ignored):
                self.assertFalse(stop.is_set())
                with db.conexion() as con:
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM api_slots').fetchone()[0],0)
                ProxyAllocator(db).finalizar(item['device_id'],item['reservation_owner'],cleanup_ok=True)
                return None
            with patch('core.mass_orchestrator.ROOT',Path(folder)),patch('core.mass_orchestrator.mp.get_context',return_value=ctx),patch('core.mass_orchestrator.descubrir_pool',return_value=snapshot),patch('core.mass_orchestrator.cleanup_worker',return_value=None),patch('core.mass_orchestrator.recuperar_placa',side_effect=heal):
                code=ejecutar_plan_granja(args,[server],snapshot,[('192.0.2.1',8000),('192.0.2.2',8000)],db)
            self.assertEqual(code,0)
            self.assertEqual(stats.count('s00'),2)
            self.assertEqual(stats.count('s01'),1)

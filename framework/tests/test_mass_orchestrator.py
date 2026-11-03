import json
import tempfile
import threading
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from config.proxies import ADBError,adb,servidor_adb_actual,usar_servidor_adb
from config.network_guard import canales_gestion,trafico_restringido
from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot,consultar_servidor,descubrir_pool,cargar_servidores
from core.database import Database
from core.mass_orchestrator import (
    ClienteLimitado,FarmStopped,cleanup_worker,ejecutar_plan_granja,farm_worker,pendientes_disponibles,
)


class PoolTests(unittest.TestCase):
    @patch('core.adb_pool.consultar_servidor')
    def test_duplicates_prefer_ready_route_and_preserve_origins(self,query):
        a,b=ADBServer('127.0.0.1',5037),ADBServer('127.0.0.1',5038)
        query.side_effect=lambda server,timeout: {'same':'offline','a':'device'} if server==a else {'same':'device','b':'device'}
        snapshot=descubrir_pool([a,b])
        self.assertEqual(len(snapshot.devices),3)
        self.assertEqual(snapshot.devices['same'].server,b)
        self.assertEqual(snapshot.devices['same'].origins,[a,b])

    @patch('core.adb_pool.consultar_servidor')
    def test_one_server_failure_does_not_hide_other_devices(self,query):
        a,b=ADBServer('127.0.0.1',5037),ADBServer('127.0.0.1',5038)
        query.side_effect=[{'a':'device'},ADBError('down')]
        snapshot=descubrir_pool([a,b])
        self.assertEqual(set(snapshot.devices),{'a'})
        self.assertIn(b.key,snapshot.errors)

    @patch('core.adb_pool.socket.create_connection')
    @patch('config.proxies.adb',return_value='List of devices attached\na device\nb unauthorized\n')
    def test_explicit_host_and_port(self,command,connect):
        server=ADBServer('192.0.2.5',5038)
        self.assertEqual(consultar_servidor(server),{'a':'device','b':'unauthorized'})
        self.assertEqual(command.call_args.args[:4],('-H','192.0.2.5','-P','5038'))

    @patch('core.adb_pool.socket.create_connection',side_effect=OSError('not listening'))
    @patch('config.proxies.adb')
    def test_unavailable_port_is_not_auto_started(self,command,connect):
        with self.assertRaises(ADBError):
            consultar_servidor(ADBServer('127.0.0.1',5039))
        command.assert_not_called()

    def test_config_deduplicates_endpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'servers.json'
            path.write_text(json.dumps({'servers':['127.0.0.1:5037',{'host':'127.0.0.1','port':5037}]}))
            self.assertEqual(len(cargar_servidores(path)),1)

    def test_partial_inventory_distinguishes_server_failure(self):
        a,b=ADBServer('127.0.0.1',5037),ADBServer('127.0.0.1',5038)
        with tempfile.TemporaryDirectory() as temp:
            db=Database(Path(temp)/'db.sqlite')
            db.sincronizar_pool(PoolSnapshot({'a':DeviceRoute('a',a,'device',[a]),
                'b':DeviceRoute('b',b,'device',[b])},{},[a,b]))
            db.sincronizar_pool(PoolSnapshot({'a':DeviceRoute('a',a,'device',[a])},{b.key:'down'},[a]))
            rows={r['id_adb']:r for r in db.dispositivos()}
            self.assertEqual(rows['b']['inventario_estado'],'servidor_no_disponible')
            self.assertEqual(rows['b']['conectado'],0)
            self.assertEqual(rows['a']['adb_port'],5037)
            db.guardar_servidores([a,b])
            self.assertEqual(db.servidores_configurados(),[a,b])


class RoutingTests(unittest.TestCase):
    @patch.dict('os.environ',{'ADB_SERVER_SOCKET':'tcp:127.0.0.1:5999'})
    @patch('config.proxies.verificar_adb',return_value='adb.exe')
    @patch('config.proxies.subprocess.run',return_value=SimpleNamespace(stdout='device'))
    def test_context_routes_all_commands_and_restores(self,run,verify):
        with usar_servidor_adb('192.0.2.1',5038):
            adb('-s','serial','get-state')
        self.assertEqual(run.call_args.args[0],['adb.exe','-H','192.0.2.1','-P','5038','-s','serial','get-state'])
        self.assertIsNone(servidor_adb_actual())
        self.assertNotIn('ADB_SERVER_SOCKET',run.call_args.kwargs['env'])

    @patch('config.proxies.verificar_adb',return_value='adb.exe')
    @patch('config.proxies.subprocess.run',return_value=SimpleNamespace(stdout='ok'))
    def test_thread_local_routing_does_not_leak(self,run,verify):
        def task(port):
            with usar_servidor_adb('127.0.0.1',port):
                adb('-s',str(port),'get-state')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(task,range(5037,5041)))
        for call in run.call_args_list:
            command=call.args[0]
            self.assertEqual(command[4],command[6])
        self.assertIsNone(servidor_adb_actual())

    @patch('core.mass_orchestrator.limpiar_proxy_dispositivo')
    @patch('core.mass_orchestrator.recuperar_firewall')
    @patch('core.mass_orchestrator.shell')
    def test_supervisor_cleanup_uses_original_server(self,shell,recover,clear):
        seen=[]
        shell.side_effect=lambda *args:seen.append(servidor_adb_actual()) or ''
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'proxy_lease.json').write_text('{}')
            route=DeviceRoute('serial',ADBServer('192.0.2.1',5038),'device')
            self.assertIsNone(cleanup_worker({'route':route,'directory':temp},'app'))
        self.assertEqual(seen,[('192.0.2.1',5038)])
        clear.assert_called_once_with('serial')


class ManagementFirewallTests(unittest.TestCase):
    def test_only_detected_adbd_peers_allowed(self):
        root=Mock(return_value='ESTAB 0 0 192.0.2.5:5555 192.0.2.100:49001\nESTAB 0 0 192.0.2.5:40000 203.0.113.1:443')
        self.assertEqual(canales_gestion('192.0.2.5:5555',root),[('192.0.2.100',5555)])
        with self.assertRaises(ADBError):
            canales_gestion('192.0.2.5:5555',Mock(return_value=''))

    @patch('config.network_guard.shell')
    def test_management_exception_is_scoped_and_lease_removed(self,shell):
        def command(device,*args):
            if args==('id','-u'):
                return '0'
            if args==('ss','-tn'):
                return 'ESTAB 0 0 192.0.2.5:5555 192.0.2.100:49001'
            return ''
        shell.side_effect=command
        with tempfile.TemporaryDirectory() as temp:
            with trafico_restringido('192.0.2.5:5555','203.0.113.2',8080,temp,preserve_management=True):
                self.assertTrue(Path(temp,'firewall_lease.json').exists())
            self.assertFalse(Path(temp,'firewall_lease.json').exists())
        exceptions=[c.args for c in shell.call_args_list if '--ctstate' in c.args]
        self.assertTrue(exceptions)
        self.assertTrue(all('--sport' in x and '-d' in x for x in exceptions))


class SchedulerTests(unittest.TestCase):
    def test_slots_never_exceed_limit(self):
        queue=deque(range(40))
        self.assertEqual(len(pendientes_disponibles(queue,{'a':1,'b':2},5)),3)
        self.assertEqual(len(queue),37)

    def test_cancelled_api_wait_never_calls_client(self):
        stop=threading.Event(); stop.set()
        client=Mock()
        limited=ClienteLimitado(client,threading.Semaphore(1),threading.Lock(),SimpleNamespace(value=0),stop,30)
        with self.assertRaises(FarmStopped):
            limited.create(model='gpt-4o-mini')
        client.chat.completions.create.assert_not_called()

    def test_api_error_releases_concurrency_slot(self):
        client=Mock()
        client.chat.completions.create.side_effect=ValueError('API failed')
        gate=threading.BoundedSemaphore(1)
        limited=ClienteLimitado(client,gate,threading.Lock(),SimpleNamespace(value=0),threading.Event(),30)
        with self.assertRaises(ValueError):
            limited.create(model='gpt-4o-mini')
        self.assertTrue(gate.acquire(blocking=False))

    @patch('core.mass_orchestrator.startup_delay',return_value=0)
    @patch('core.mass_orchestrator.signal.signal')
    @patch('core.mass_orchestrator.cleanup_worker',return_value=None)
    @patch('core.mass_orchestrator.descubrir_pool')
    def test_34_serials_each_get_a_process_maximum_4(self,discover,cleanup,signals,delay):
        class Event:
            flag=False
            def is_set(self):return self.flag
            def set(self):self.flag=True
            def wait(self,seconds):return self.flag
        stats={'active':0,'peak':0,'started':0}
        class Process:
            exitcode=0
            def __init__(self,**kwargs):
                self.seen=0; self.alive=False; self.pid=100+stats['started']
            def start(self):
                self.alive=True; stats['active']+=1; stats['started']+=1
                stats['peak']=max(stats['peak'],stats['active'])
            def is_alive(self):
                if self.alive:
                    self.seen+=1
                    if self.seen>=5:
                        self.alive=False; stats['active']-=1
                return self.alive
            def join(self,*args):pass
            def terminate(self):self.alive=False
        ctx=SimpleNamespace(Event=Event,BoundedSemaphore=threading.BoundedSemaphore,
            Lock=threading.Lock,Value=lambda *args:SimpleNamespace(value=0),Process=Process)
        server=ADBServer('127.0.0.1',5038)
        snapshot=PoolSnapshot({f's{i}':DeviceRoute(f's{i}',server,'device',[server]) for i in range(34)},{},[server])
        discover.return_value=snapshot
        args=SimpleNamespace(devices=4,api_concurrency=2,stagger=0,shutdown_grace=1,package='app')
        with tempfile.TemporaryDirectory() as temp,patch('core.mass_orchestrator.ROOT',Path(temp)),patch('core.mass_orchestrator.mp.get_context',return_value=ctx):
            db=Database(Path(temp)/'db.sqlite')
            code=ejecutar_plan_granja(args,[server],snapshot,[('192.0.2.1',8000+i) for i in range(34)],db)
        self.assertEqual(code,0)
        self.assertEqual(stats['started'],34)
        self.assertEqual(stats['peak'],4)
        self.assertEqual(cleanup.call_count,34)

    @patch('core.mass_orchestrator.comprobar_cuenta',return_value={'authenticated':True,'reason':'test'})
    @patch('core.mass_orchestrator.esperar_feed',return_value={'ready':True})
    @patch('core.mass_orchestrator.signal.signal')
    @patch('core.mass_orchestrator.Database')
    @patch('core.mass_orchestrator.cleanup_worker',return_value=None)
    @patch('core.mass_orchestrator.ejecutar_feed')
    @patch('core.mass_orchestrator.OpenAI')
    @patch('core.mass_orchestrator.consultar_ip',return_value='203.0.113.9')
    @patch('core.mass_orchestrator.trafico_restringido',return_value=nullcontext(Mock()))
    @patch('core.mass_orchestrator.configurar_proxy_dispositivo')
    @patch('core.mass_orchestrator.shell',return_value='Status: ok')
    @patch('core.mass_orchestrator.adb',return_value='device')
    def test_worker_keeps_origin_during_feed_and_cleanup(self,adb,shell,proxy,guard,ip,client,feed,cleanup,database,signals,wait,auth):
        seen=[]
        feed.side_effect=lambda *args,**kwargs:seen.append(servidor_adb_actual())
        stop=Mock(); stop.is_set.return_value=False; stop.wait.return_value=False
        args=SimpleNamespace(package='app',activity='.Main',cycles=1,rpm=30)
        route=DeviceRoute('serial',ADBServer('192.0.2.1',5038),'device')
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(SystemExit) as exit:
                farm_worker({'route':route,'proxy':('203.0.113.2',8000),'directory':temp},args,
                    stop,None,None,None,str(Path(temp)/'db.sqlite'))
        self.assertEqual(exit.exception.code,0)
        self.assertEqual(seen,[('192.0.2.1',5038)])
        self.assertIsNone(servidor_adb_actual())

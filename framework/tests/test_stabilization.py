import multiprocessing as mp
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from config.proxies import ProxyAllocator
from core.database import Database
from core.selectors import contiene_feed,esperar_feed
from core.mass_orchestrator import startup_delay,ejecutar_plan_granja
from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot


def entries(count):
    return [dict(endpoint=f'192.0.2.1:{8000+i}',host='192.0.2.1',port=8000+i,enabled=True)
            for i in range(count)]


def reserve_process(path,index,queue):
    result=ProxyAllocator(Database(path)).reservar(f'device-{index}','run')
    queue.put(result is not None)


class ProxyReservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(Path(self.temp.name)/'test.sqlite')
        self.allocator=ProxyAllocator(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_40_threads_only_three_distinct_active_proxies(self):
        self.allocator.sincronizar(entries(3))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda i:self.allocator.reservar(f'device-{i}','run'),range(40)))
        assigned=[x['endpoint'] for x in results if x]
        self.assertEqual(len(assigned),3)
        self.assertEqual(len(set(assigned)),3)

    @patch('__main__.__file__', str(Path(__file__).resolve()), create=True)
    def test_reservation_exclusion_between_processes(self):
        database_env = patch.dict(os.environ, {'TIKTOK_DB_PATH': str(self.db.path)})
        database_env.start()
        self.addCleanup(database_env.stop)
        self.allocator.sincronizar(entries(1))
        ctx=mp.get_context('spawn')
        queue=ctx.Queue()
        processes=[ctx.Process(target=reserve_process,args=(str(self.db.path),i,queue)) for i in range(4)]
        for process in processes:process.start()
        outcomes=[queue.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(30)
            self.assertEqual(process.exitcode,0)
        queue.close()
        self.assertEqual(sum(outcomes),1)

    def test_idempotency_owner_and_quarantine(self):
        self.allocator.sincronizar(entries(1))
        first=self.allocator.reservar('a','run')
        self.assertEqual(self.allocator.reservar('a','run'),first)
        self.assertIsNone(self.allocator.reservar('a','other'))
        self.allocator.finalizar('a','run',cleanup_ok=False)
        self.assertIsNone(self.allocator.reservar('b','run'))
        self.allocator.finalizar('a','other',cleanup_ok=True)
        self.assertEqual(self.allocator.disponibles(),0)
        self.allocator.finalizar('a','run',cleanup_ok=True)
        self.assertIsNotNone(self.allocator.reservar('b','run'))

    def test_known_and_observed_public_ip_collisions(self):
        data=entries(2)
        for item in data:item['exit_ip']='203.0.113.1'
        self.allocator.sincronizar(data)
        self.assertEqual(self.allocator.disponibles(),1)
        self.allocator.reservar('a','run')
        self.assertIsNone(self.allocator.reservar('b','run'))
        self.allocator.finalizar('a','run',cleanup_ok=True)
        for item in data:item['exit_ip']=None
        self.allocator.sincronizar(data)
        self.allocator.reservar('a','run'); self.allocator.reservar('b','run')
        self.allocator.confirmar_salida('a','run','203.0.113.1')
        with self.assertRaisesRegex(ValueError,'Colisión'):
            self.allocator.confirmar_salida('b','run','203.0.113.1')


class FakeClock:
    now=0
    stopped=False
    def monotonic(self):return self.now
    def is_set(self):return self.stopped
    def wait(self,delay):
        self.now+=delay
        return self.stopped


class DynamicWaitTests(unittest.TestCase):
    READY='<hierarchy><node package="app" resource-id="app:id/player_container" bounds="[0,0][100,200]"/></hierarchy>'

    def test_container_requires_expected_package_and_visible_area(self):
        self.assertTrue(contiene_feed(self.READY,'app'))
        self.assertFalse(contiene_feed(self.READY,'wrong'))
        self.assertFalse(contiene_feed('<hierarchy><node package="app" text="Para Ti"/></hierarchy>','app'))

    @patch('core.selectors.adb')
    def test_ready_on_second_microdump(self,adb):
        clock=FakeClock()
        adb.side_effect=['dumped to: file','<hierarchy/>','dumped to: file',self.READY]
        with patch('core.selectors.time.monotonic',side_effect=clock.monotonic):
            result=esperar_feed('usb','app',stop=clock)
        self.assertTrue(result['ready'])
        self.assertEqual(result['attempts'],2)
        self.assertLess(result['elapsed'],15)

    @patch('core.selectors.adb')
    def test_five_attempts_15_seconds_then_slow_state(self,adb):
        clock=FakeClock()
        adb.side_effect=['dumped to: file','<hierarchy/>']*5
        slow=Mock()
        with patch('core.selectors.time.monotonic',side_effect=clock.monotonic):
            result=esperar_feed('usb','app',stop=clock,on_slow=slow)
        self.assertFalse(result['ready'])
        self.assertEqual(result['attempts'],5)
        self.assertEqual(clock.now,15)
        slow.assert_called_once()

    @patch('core.selectors.adb')
    def test_cancelled_wait_performs_no_dump(self,adb):
        clock=FakeClock();clock.stopped=True
        with self.assertRaises(InterruptedError):
            esperar_feed('usb','app',stop=clock)
        adb.assert_not_called()

    def test_startup_jitter_is_always_two_to_five_seconds(self):
        self.assertTrue(all(2<=startup_delay()<=5 for _ in range(100)))


class CapacityAndUITests(unittest.TestCase):
    @patch('core.mass_orchestrator.signal.signal')
    @patch('core.mass_orchestrator.descubrir_pool')
    def test_no_proxy_pauses_all_devices_without_starting_processes(self,discover,signals):
        server=ADBServer('127.0.0.1',5038)
        snapshot=PoolSnapshot({f's{i}':DeviceRoute(f's{i}',server,'device',[server]) for i in range(2)},{},[server])
        discover.return_value=snapshot
        captured={}
        class Event:
            stopped=False
            def is_set(self):return self.stopped
            def set(self):self.stopped=True
            def wait(self,seconds):
                captured['states']=[r['estado'] for r in db.dispositivos()]
                captured['alerts']=db.alertas()
                self.stopped=True
                return True
        ctx=SimpleNamespace(Event=Event,BoundedSemaphore=lambda n:None,Lock=lambda:None,
                            Value=lambda *a:None,Process=Mock())
        args=SimpleNamespace(devices=40,api_concurrency=4,stagger=0,shutdown_grace=1,package='app')
        with tempfile.TemporaryDirectory() as temp,patch('core.mass_orchestrator.ROOT',Path(temp)),patch('core.mass_orchestrator.mp.get_context',return_value=ctx):
            db=Database(Path(temp)/'db.sqlite')
            self.assertEqual(ejecutar_plan_granja(args,[server],snapshot,[],db),0)
        ctx.Process.assert_not_called()
        self.assertEqual(captured['states'],['Espera - Sin Proxy']*2)
        self.assertIn('Falta de recursos de red',captured['alerts'][0]['mensaje'])

    def test_dashboard_shows_network_alert_and_slow_state(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(temp)/'db.sqlite')}):
                db=Database()
                db.alerta('network_resources','Falta de recursos de red')
                db.actualizar_dispositivo('a',estado='Carga Lenta - Reintentando')
                with patch('config.proxies.adb',return_value='List of devices attached\na device\n'),patch('core.adb_pool.socket.create_connection'):
                    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                    self.assertFalse(app.exception)
                    self.assertIn('Falta de recursos de red',app.error[0].value)
                    self.assertIn('Carga Lenta - Reintentando',app.dataframe[0].value.iloc[0]['estado'])
        finally:
            st.cache_resource.clear()

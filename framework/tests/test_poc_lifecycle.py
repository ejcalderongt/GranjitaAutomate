import asyncio
from contextlib import asynccontextmanager, closing, nullcontext
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, call, patch

from core.poc_runner import POCSettings, ejecutar_poc
from core.telemetry import inicializar_db_telemetria
from ui.poc_dashboard import presentar_ventana, POCController


class WindowPresentationTests(TestCase):
    def test_raise_is_deferred_and_topmost_is_restored(self):
        root=Mock()
        root.winfo_exists.return_value=True
        root.attributes.side_effect=lambda *args:0 if len(args)==1 else None
        root.after_idle.return_value='idle'
        root.after.return_value='restore'
        release=presentar_ventana(root)
        root.lift.assert_not_called()
        root.after_idle.call_args.args[0]()
        root.lift.assert_called_once()
        root.focus_set.assert_called_once()
        self.assertIn(call('-topmost',True),root.attributes.call_args_list)
        self.assertEqual(root.after.call_args.args[0],600)
        root.after.call_args.args[1]()
        self.assertEqual(root.attributes.call_args,call('-topmost',0))
        release()
        root.after_cancel.assert_any_call('restore')

    def test_destroyed_window_is_not_raised(self):
        root=Mock()
        root.winfo_exists.return_value=False
        presentar_ventana(root)
        root.after_idle.call_args.args[0]()
        root.lift.assert_not_called()

    def test_stop_is_idempotent_and_does_not_schedule_repeated_cancellation(self):
        controller=POCController(Mock())
        controller.loop=Mock()
        controller.loop.is_running.return_value=True
        controller.cancel();controller.cancel()
        self.assertTrue(controller.stop.is_set())
        controller.loop.call_soon_threadsafe.assert_called_once()


class POCLifecycleTests(IsolatedAsyncioTestCase):
    async def run_fixture(self, root, *, cancel_cleanup=False, cleanup_ok=True,mobile=False,rotation_fails=False):
        from core.database import Database
        path=inicializar_db_telemetria(root/'qa.db')
        selectors=root/'selectors.json'
        selectors.write_text(json.dumps({'login':'#login','authenticated':'#account','active_video':'article'}))
        settings=POCSettings(cycles=1,selectors_path=selectors,rotate_mobile=mobile)
        stop,login=threading.Event(),threading.Event()
        login.set()
        runtime,context,page=Mock(),Mock(),Mock()
        page.goto=AsyncMock(return_value=Mock(status=200))
        page.locator.return_value.inner_text=AsyncMock(return_value='{"ip":"8.8.8.8"}')
        page.locator.return_value.is_visible=AsyncMock(return_value=False)
        page.is_closed.return_value=False
        events=[]
        cleanup_started=asyncio.Event()
        order=[]
        from config.proxies import ProxyRotationError
        manager=Mock()
        async def rotate(*args):
            order.append('rotation')
            if rotation_fails:
                raise ProxyRotationError('rotation_http_503')
            return '8.8.8.8'
        manager.ejecutar_ciclo_rotacion_segura=AsyncMock(side_effect=rotate)
        manager.browser_proxy.return_value={'server':'http://localhost:8080'}
        manager.validar_ip_navegador=AsyncMock()
        async def browser(*args,**kwargs):
            order.append('browser')
            return runtime,context,page,None

        @asynccontextmanager
        async def api_context():
            yield Mock()

        async def cleanup(*args):
            with closing(sqlite3.connect(path)) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos_poc WHERE evento='cierre_exitoso'").fetchone()[0],0)
            cleanup_started.set()
            if cancel_cleanup:
                await asyncio.sleep(.03)
            return cleanup_ok

        with patch('core.database.Database',return_value=Database(root/'main.db')), \
             patch('core.mass_orchestrator.bloquear_granja',return_value=nullcontext()), \
             patch('core.poc_runner.proxy_desde_entorno',return_value={'server':'http://localhost:8080'}), \
             patch('config.proxies.ProxyManager',return_value=manager), \
             patch('core.poc_runner.iniciar_contexto_async',new=AsyncMock(side_effect=browser)) as start, \
             patch('tiktok_warmer.test_connection.resolver_geo_por_proxy',new=AsyncMock(return_value={'continente':'EU','provider_used':'ip-api.com'})), \
             patch('core.async_web_orchestrator.elemento_unico_async',new=AsyncMock()), \
             patch('core.async_web_orchestrator.ciclo_feed_async',new=AsyncMock(return_value=True)), \
             patch('openai.AsyncOpenAI',return_value=api_context()), \
             patch('core.poc_runner.cerrar_contexto_async',new=AsyncMock(side_effect=cleanup)):
            task=asyncio.create_task(ejecutar_poc(settings,stop,login,lambda kind,data:events.append((kind,data)),path))
            if cancel_cleanup:
                await asyncio.wait_for(cleanup_started.wait(),5)
                stop.set();task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            else:
                await task
            if rotation_fails:
                start.assert_not_awaited()
            else:
                start.assert_awaited_once()
            if mobile and not rotation_fails:
                self.assertEqual(order[:2],['rotation','browser'])
                manager.validar_ip_navegador.assert_awaited_once()
        with closing(sqlite3.connect(path)) as con:
            rows=con.execute('SELECT evento,estado FROM eventos_poc ORDER BY id').fetchall()
        return rows,events

    async def test_mobile_rotation_failure_stops_before_patchright_and_keeps_ui_recoverable(self):
        with tempfile.TemporaryDirectory() as folder:
            rows,events=await self.run_fixture(Path(folder),mobile=True,rotation_fails=True)
        result=next(data for kind,data in events if kind=='result')
        self.assertTrue(result['failed'])
        self.assertTrue(result['clean'])
        self.assertIn(('prueba_fallida','fallido'),rows)

    async def test_mobile_rotation_precedes_browser_and_browser_identity_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            rows,events=await self.run_fixture(Path(folder),mobile=True)
        self.assertEqual(rows[-1],('cierre_exitoso','completado'))

    async def test_login_reuses_context_and_shutdown_is_persisted_after_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            rows,events=await self.run_fixture(Path(folder))
        self.assertEqual([row[0] for row in rows],['admision','navegador_listo','esperando_login',
            'continuacion_solicitada','login_verificado','cierre_exitoso'])
        result=next(data for kind,data in events if kind=='result')
        self.assertTrue(result['clean'])
        self.assertTrue(result['telemetry_saved'])

    async def test_cancellation_during_cleanup_waits_for_persisted_shutdown(self):
        with tempfile.TemporaryDirectory() as folder:
            rows,events=await self.run_fixture(Path(folder),cancel_cleanup=True)
        self.assertEqual(rows[-1],('cierre_exitoso','completado'))
        self.assertTrue(next(data for kind,data in events if kind=='result')['telemetry_saved'])

    async def test_failed_cleanup_is_never_reported_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            rows,events=await self.run_fixture(Path(folder),cleanup_ok=False)
        self.assertNotIn(('cierre_exitoso','completado'),rows)
        self.assertEqual(rows[-1],('cierre_fallido','fallido'))
        self.assertFalse(next(data for kind,data in events if kind=='result')['clean'])

    async def test_unresponsive_context_does_not_block_later_closures(self):
        from core.browser import cerrar_contexto_async
        async def hanging_close():
            await asyncio.Future()
        runtime=Mock();runtime.stop=AsyncMock()
        bridge=Mock()
        self.assertFalse(await cerrar_contexto_async(Mock(close=hanging_close),runtime,bridge,close_timeout=.01))
        runtime.stop.assert_awaited_once()
        bridge.close.assert_called_once()

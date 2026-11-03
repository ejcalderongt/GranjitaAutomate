import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.load_testing import regular_retencion_de_carga
from core.telemetry import inicializar_db_telemetria, registrar_metrica_ciclo_async


class LoadTestingTests(unittest.IsolatedAsyncioTestCase):
    async def test_pre_swipe_metrics_are_committed_before_gesture(self):
        from core.async_web_orchestrator import ciclo_feed_async
        page=Mock()
        page.locator.return_value.is_visible=AsyncMock(return_value=False)
        page.locator.return_value.first.wait_for=AsyncMock()
        page.screenshot=AsyncMock()
        phase_seen=[]
        with tempfile.TemporaryDirectory() as folder:
            db=inicializar_db_telemetria(Path(folder)/'qa.db')
            async def gesture(*args,**kwargs):
                with closing(sqlite3.connect(db)) as con:
                    phase_seen.append(con.execute('SELECT fase FROM metricas_rendimiento').fetchone()[0])
            with patch('core.async_web_orchestrator.ROOT',Path(folder)), \
                 patch('core.async_web_orchestrator.elemento_unico_async',new=AsyncMock()), \
                 patch('core.async_web_orchestrator.extraer_contexto_video_movil',new=AsyncMock(return_value={'descripcion':'','sonido_original':''})), \
                 patch('core.async_web_orchestrator.analizar_contenido_tiktok_async',new=AsyncMock(return_value={'dar_like':False,'comentar':False,'compartir':False,'comentario':''})), \
                 patch('core.web_actions.ejecutar_desplazamiento_tactil',new=AsyncMock(side_effect=gesture)):
                result=await ciclo_feed_async(page,'test_account',{'login':'login','authenticated':'auth','active_video':'video'},Mock(),
                    telemetry=SimpleNamespace(run_id='run',append=Mock()),record=AsyncMock(),qa_db_path=db)
            self.assertTrue(result)
            self.assertEqual(phase_seen,['pre_swipe'])

    async def test_old_table_is_migrated_without_losing_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.db'
            with closing(sqlite3.connect(path)) as con:
                con.execute('''CREATE TABLE metricas_rendimiento (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp_utc TEXT NOT NULL,
                    account_id TEXT NOT NULL,ciclo_numero INTEGER NOT NULL,proxy_ip TEXT NOT NULL,
                    geo_provider TEXT NOT NULL,latencia_dom_ms REAL,latencia_openai_ms REAL,
                    tiempo_retencion_ejecutado_seg REAL,estado_retencion TEXT,estado_ciclo TEXT NOT NULL,error_log TEXT)''')
                con.execute("INSERT INTO metricas_rendimiento(timestamp_utc,account_id,ciclo_numero,proxy_ip,geo_provider,estado_ciclo) VALUES ('old','test',1,'REDACTED','UNKNOWN','passed')")
                con.commit()
            inicializar_db_telemetria(path)
            with closing(sqlite3.connect(path)) as con:
                self.assertEqual(con.execute('SELECT run_id,cycle_id,estado_ciclo FROM metricas_rendimiento').fetchone(),('legacy','legacy-1','passed'))

    async def test_cycle_cancellation_is_stored_without_api_or_swipe(self):
        from core.async_web_orchestrator import ciclo_feed_async
        page,active = Mock(),Mock()
        page.locator.return_value.is_visible=AsyncMock(return_value=False)
        page.locator.return_value.first.wait_for=AsyncMock()
        stop=threading.Event();stop.set()
        with tempfile.TemporaryDirectory() as folder:
            db=inicializar_db_telemetria(Path(folder)/'qa.db')
            with patch('core.async_web_orchestrator.elemento_unico_async',new=AsyncMock(return_value=active)), \
                 patch('core.async_web_orchestrator.extraer_contexto_video_movil',new=AsyncMock(return_value={'descripcion':'text','sonido_original':''})), \
                 patch('core.async_web_orchestrator.analizar_contenido_tiktok_async',new=AsyncMock()) as ai, \
                 patch('core.web_actions.ejecutar_desplazamiento_tactil',new=AsyncMock()) as swipe:
                result=await ciclo_feed_async(page,'test_account',{'login':'login','authenticated':'auth','active_video':'video'},Mock(),
                    telemetry=SimpleNamespace(run_id='run',append=Mock()),record=AsyncMock(),stop=stop,qa_db_path=db)
            self.assertIsNone(result)
            ai.assert_not_awaited();swipe.assert_not_awaited()
            with closing(sqlite3.connect(db)) as con:
                row=con.execute('SELECT estado_ciclo,estado_retencion FROM metricas_rendimiento').fetchone()
            self.assertEqual(row,('cancelled','cancelado'))

    async def test_sqlite_failure_prevents_unrecorded_advance(self):
        from core.async_web_orchestrator import ciclo_feed_async
        page=Mock()
        page.locator.return_value.is_visible=AsyncMock(return_value=False)
        page.locator.return_value.first.wait_for=AsyncMock()
        with patch('core.async_web_orchestrator.elemento_unico_async',new=AsyncMock()), \
             patch('core.async_web_orchestrator.extraer_contexto_video_movil',new=AsyncMock(return_value={'descripcion':'text','sonido_original':''})), \
             patch('core.telemetry.registrar_metrica_ciclo_async',new=AsyncMock(side_effect=sqlite3.OperationalError('locked'))), \
             patch('core.async_web_orchestrator.analizar_contenido_tiktok_async',new=AsyncMock()) as ai, \
             patch('core.web_actions.ejecutar_desplazamiento_tactil',new=AsyncMock()) as swipe:
            result=await ciclo_feed_async(page,'test_account',{'login':'login','authenticated':'auth','active_video':'video'},Mock(),
                telemetry=SimpleNamespace(run_id='run',append=Mock()),record=AsyncMock(),qa_db_path=Path('unused.db'))
        self.assertFalse(result)
        ai.assert_not_awaited();swipe.assert_not_awaited()

    async def test_formula_is_deterministic_and_does_not_oversleep_fixed_interval(self):
        result = await regular_retencion_de_carga({'descripcion':'a','sonido_original':''},0)
        self.assertEqual(result['tiempo_programado'],.05)
        self.assertEqual(result['estado_retencion'],'completado')
        self.assertGreaterEqual(result['tiempo_ejecutado'],.049)
        self.assertLess(result['tiempo_ejecutado'],.4)

    async def test_async_and_cross_thread_cancellation_are_responsive(self):
        for event in (asyncio.Event(), threading.Event()):
            task = asyncio.create_task(regular_retencion_de_carga({'descripcion':'a'*5000},30,event))
            await asyncio.sleep(.02)
            started = time.monotonic()
            event.set()
            result = await asyncio.wait_for(task,.5)
            self.assertEqual(result['estado_retencion'],'cancelado')
            self.assertEqual(result['tiempo_programado'],30)
            self.assertLess(time.monotonic()-started,.4)

    async def test_invalid_timing_and_task_cancellation(self):
        for value in (-1,31,float('inf'),float('nan'),True):
            with self.assertRaises(ValueError):
                await regular_retencion_de_carga({},value)
        task = asyncio.create_task(regular_retencion_de_carga({},30))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_upsert_preserves_single_cycle_and_omits_sensitive_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = inicializar_db_telemetria(Path(folder)/'qa.db')
            args = dict(account_id='test_account',ciclo_numero=1,proxy_ip='203.0.113.18',geo_provider='UNKNOWN',
                        db_path=path,run_id='qa_run',cycle_id='cycle01')
            await registrar_metrica_ciclo_async(**args,fase='mapeo',estado_ciclo='running',latencia_dom=1.5)
            await registrar_metrica_ciclo_async(**args,fase='finalizado',estado_ciclo='failed',latencia_dom=1.5,
                error_log=TimeoutError('password=secret https://user:secret@host/'),tiempo_retencion=.05)
            with closing(sqlite3.connect(path)) as con:
                con.row_factory=sqlite3.Row
                rows=[dict(row) for row in con.execute('SELECT * FROM metricas_rendimiento')]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['estado_ciclo'],'failed')
            self.assertEqual(rows[0]['error_log'],'TimeoutError')
            self.assertNotIn('secret',str(rows))
            self.assertNotIn('203.0.113.18',str(rows))
            self.assertEqual(rows[0]['proxy_ip'],'REDACTED')
            path.unlink()  # Ninguna conexión de telemetría queda retenida.

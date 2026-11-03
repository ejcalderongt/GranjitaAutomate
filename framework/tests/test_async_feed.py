import asyncio
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from playwright.async_api import async_playwright
from core.ai_agent import evaluar_video_con_ia, decision_sin_acciones
from core.scraper import extraer_contexto_video_movil
from core.browser import cerrar_contexto_async


class MagicAsyncContext:
    def __init__(self, value):
        self.value, self.closed = value, False

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        self.closed = True


def client_for(decision):
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
        message=SimpleNamespace(content=json.dumps(decision), refusal=None))]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


class AsyncFeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_admission_cancellation_releases_sqlite_slot(self):
        from core.database import Database
        from core.async_api_admission import AsyncClienteRecuperable
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder)/'test.db')
            started = asyncio.Event()
            async def wait_forever(**kwargs):
                started.set()
                await asyncio.Future()
            raw = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=wait_forever)))
            client = AsyncClienteRecuperable(raw, db, 'token', 'run', threading.Event(), 60, 1, AsyncMock())
            task = asyncio.create_task(client.create())
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with db.conexion() as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM api_slots').fetchone()[0],0)

    async def test_owned_client_is_closed_and_missing_context_skips_api(self):
        owned = client_for(decision_sin_acciones())
        manager = MagicAsyncContext(owned)
        with patch('core.ai_agent.AsyncOpenAI', return_value=manager) as factory:
            await evaluar_video_con_ia({'descripcion':'texto de prueba'})
            factory.assert_called_once()
        self.assertTrue(manager.closed)
        with patch('core.ai_agent.AsyncOpenAI') as factory:
            self.assertEqual(await evaluar_video_con_ia({'descripcion':'Sin descripción'}),decision_sin_acciones())
            factory.assert_not_called()

    async def test_real_dom_scopes_metadata_without_screenshot(self):
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_content('''<article id="other"><h3 data-e2e="video-author-uniqueid">otro</h3></article>
                  <article id="active"><h3 data-e2e="video-author-uniqueid">@local</h3>
                  <div data-e2e="video-desc">paisaje de prueba</div><div data-e2e="video-music">sonido local</div></article>''')
                with patch.object(page, 'screenshot', new=AsyncMock()) as screenshot:
                    data = await extraer_contexto_video_movil(page, scope=page.locator('#active'))
                self.assertEqual(data, {'autor':'@local','descripcion':'paisaje de prueba','sonido_original':'sonido local'})
                screenshot.assert_not_awaited()
            finally:
                await browser.close()

    async def test_field_error_does_not_skip_other_metadata(self):
        broken, description, audio = Mock(), Mock(), Mock()
        broken.is_visible = AsyncMock(side_effect=TimeoutError())
        description.is_visible = audio.is_visible = AsyncMock(return_value=True)
        description.inner_text = AsyncMock(return_value='descripción local')
        audio.inner_text = AsyncMock(return_value='audio local')
        page = Mock()
        page.locator.side_effect = [SimpleNamespace(first=broken), SimpleNamespace(first=description), SimpleNamespace(first=audio)]
        data = await extraer_contexto_video_movil(page)
        self.assertEqual(data['autor'], 'Desconocido')
        self.assertEqual(data['descripcion'], 'descripción local')
        self.assertEqual(data['sonido_original'], 'audio local')

    async def test_async_model_validates_eight_words_and_keeps_client_owned_by_caller(self):
        decision = {'dar_like':False,'compartir':False,'comentar':True,'comentario':'uno dos tres cuatro cinco seis siete ocho'}
        client = client_for(decision)
        client.close = AsyncMock()
        self.assertEqual(await evaluar_video_con_ia({'descripcion':'texto'},client=client), decision)
        client.chat.completions.create.assert_awaited_once()
        self.assertEqual(client.chat.completions.create.call_args.kwargs['response_format']['type'], 'json_schema')
        client.close.assert_not_awaited()

    async def test_refusal_timeout_and_invalid_response_return_auditable_fallback(self):
        for case in ('refusal', 'timeout', 'json'):
            client = client_for(decision_sin_acciones())
            response = client.chat.completions.create.return_value
            if case == 'refusal':
                response.choices[0].message.refusal = 'refused'
            elif case == 'timeout':
                client.chat.completions.create.side_effect = TimeoutError('secret never logged')
            else:
                response.choices[0].message.content = 'not JSON'
            errors = []
            self.assertEqual(await evaluar_video_con_ia({'descripcion':'texto'},client=client,on_error=errors.append), decision_sin_acciones())
            self.assertEqual(len(errors),1)

    async def test_cancellation_is_not_swallowed_as_model_decision(self):
        client = client_for(decision_sin_acciones())
        client.chat.completions.create.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await evaluar_video_con_ia({'descripcion':'texto'},client=client)

    async def test_cleanup_attempts_runtime_and_bridge_after_context_error(self):
        context = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError()))
        runtime = SimpleNamespace(stop=AsyncMock())
        bridge = SimpleNamespace(close=Mock())
        self.assertFalse(await cerrar_contexto_async(context,runtime,bridge))
        runtime.stop.assert_awaited_once()
        bridge.close.assert_called_once()

    async def test_cycle_model_failure_continues_swipe_and_marks_fallback(self):
        from core.async_web_orchestrator import ciclo_feed_async
        from core.decision_telemetry import DecisionTelemetry
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_content('<button id="authenticated">cuenta</button><article><div data-e2e="video-desc">texto de prueba local</div></article>')
                client = client_for(decision_sin_acciones())
                client.chat.completions.create.side_effect = TimeoutError()
                with tempfile.TemporaryDirectory() as folder:
                    telemetry = DecisionTelemetry('test_account','run_test',root=Path(folder))
                    from core.telemetry import inicializar_db_telemetria
                    qa_db = inicializar_db_telemetria(Path(folder)/'qa.db')
                    with patch('core.async_web_orchestrator.ROOT',Path(folder)), \
                         patch('core.web_actions.ejecutar_desplazamiento_tactil',new=AsyncMock()) as swipe:
                        self.assertFalse(await ciclo_feed_async(page,'test_account',
                            {'login':'#missing','authenticated':'#authenticated','active_video':'article'},
                            client,telemetry=telemetry,record=AsyncMock(),execute=True,qa_db_path=qa_db))
                    swipe.assert_awaited_once()
                    rows = [json.loads(line) for line in telemetry.path.read_text(encoding='utf-8').splitlines()]
                    self.assertEqual(next(row for row in rows if row['event']=='decision')['decision_origin'],'fallback')
                    self.assertEqual(sum(row['event']=='ai_error' for row in rows),1)
                    self.assertFalse(any(row['event'] in ('like_click','comment_send_click') for row in rows))
            finally:
                await browser.close()

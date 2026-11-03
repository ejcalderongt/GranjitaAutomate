import asyncio
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from playwright.async_api import async_playwright
from core.consent import gestionar_pantallas_previas_ue


class ConsentQATests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_cookie_dialog_and_confirms_disappearance(self):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_content('''<div role="dialog">cookies
                    <button onclick="this.parentElement.remove()">Aceptar todo</button></div>
                    <button id="other">Accept</button>''')
                self.assertEqual(await gestionar_pantallas_previas_ue(page), 'aceptado')
                self.assertEqual(await page.locator('#other').count(), 1)
            finally:
                await browser.close()

    async def test_no_cookie_dialog_never_clicks_generic_accept_and_is_bounded(self):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_content('<button onclick="document.body.dataset.clicked=1">Accept</button>')
                started = time.monotonic()
                self.assertEqual(await gestionar_pantallas_previas_ue(page), 'no_detectado')
                self.assertLess(time.monotonic()-started, 5.8)
                self.assertIsNone(await page.locator('body').get_attribute('data-clicked'))
                event = asyncio.Event(); event.set()
                self.assertEqual(await gestionar_pantallas_previas_ue(page,cancellation_event=event), 'cancelado')
            finally:
                await browser.close()

    async def test_new_ai_receives_metadata_but_cannot_publish(self):
        from core.async_web_orchestrator import ciclo_feed_async
        from core.telemetry import inicializar_db_telemetria
        page = Mock()
        page.locator.return_value.is_visible = AsyncMock(return_value=False)
        page.locator.return_value.first.wait_for = AsyncMock()
        page.screenshot = AsyncMock()
        metadata = {'autor':'autor','descripcion':'texto de prueba','sonido_original':'audio'}
        with tempfile.TemporaryDirectory() as folder:
            db = inicializar_db_telemetria(Path(folder)/'qa.db')
            with patch('core.async_web_orchestrator.ROOT',Path(folder)), \
                 patch('core.async_web_orchestrator.elemento_unico_async',new=AsyncMock()), \
                 patch('core.async_web_orchestrator.extraer_contexto_video_movil',new=AsyncMock(return_value=metadata)), \
                 patch('core.async_web_orchestrator.analizar_contenido_tiktok_async',new=AsyncMock(return_value={
                     'interactuar':True,'dar_like':True,'comentario':'qué buena idea'})) as ai, \
                 patch('core.load_testing.regular_retencion_de_carga',new=AsyncMock(return_value={
                     'tiempo_ejecutado':0,'estado_retencion':'completado','tiempo_programado':0})), \
                 patch('core.web_actions.ejecutar_desplazamiento_tactil',new=AsyncMock()) as swipe:
                self.assertTrue(await ciclo_feed_async(page,'test_account',
                    {'login':'login','authenticated':'auth','active_video':'video'},Mock(),
                    telemetry=SimpleNamespace(run_id='run',append=Mock()),record=AsyncMock(),
                    execute=True,qa_db_path=db))
                self.assertEqual(ai.call_args.kwargs['datos_video'],metadata)
                self.assertEqual(ai.call_args.kwargs['run_id'],'run')
                swipe.assert_awaited_once()
                page.click.assert_not_called()
                page.locator.return_value.click.assert_not_called()


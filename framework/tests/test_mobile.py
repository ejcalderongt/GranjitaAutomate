import random
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from playwright.async_api import async_playwright, TimeoutError

from core.web_actions import ejecutar_desplazamiento_tactil, ejecutar_toque_tactil
from web_qa import evaluar, leer_componente


class MobileTests(unittest.IsolatedAsyncioTestCase):
    async def test_dynamic_content_and_real_cdp_scroll(self):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                context = await browser.new_context(
                    viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                page = await context.new_page()
                await page.set_content('''
                    <meta name="viewport" content="width=device-width,initial-scale=1">
                    <style>body{margin:0} #panel{height:800px;overflow:auto}
                    article{height:650px}</style>
                    <div id="panel"></div>
                    <script>
                    window.events=[];
                    ['touchstart','touchmove','touchend'].forEach(t=>
                        document.addEventListener(t,()=>events.push(t),{passive:true}));
                    setTimeout(()=>document.querySelector('#panel').innerHTML =
                        '<article>Contenido claro y comprensible.</article>'.repeat(8),100);
                    </script>
                ''')
                snapshot = await leer_componente(page, 'article')
                self.assertIn('Contenido claro', snapshot['text'])
                await ejecutar_desplazamiento_tactil(page, selector='#panel', rng=random.Random(42))
                await page.wait_for_function("document.querySelector('#panel').scrollTop > 20")
                events = await page.evaluate('events')
                self.assertEqual(events[0], 'touchstart')
                self.assertIn('touchmove', events)
                self.assertEqual(events[-1], 'touchend')
                current = await leer_componente(page, 'article')
                self.assertGreater(current['index'], 0)
                await page.set_content('''
                    <meta name="viewport" content="width=device-width,initial-scale=1">
                    <button onclick="window.pulsado=true">Acción de prueba</button>
                ''')
                await ejecutar_toque_tactil(page, page.locator('button'))
                await page.wait_for_function('window.pulsado === true')
                self.assertTrue(await page.evaluate('window.pulsado'))
                with self.assertRaises(TimeoutError):
                    await leer_componente(page, '.missing', timeout=0.1)
            finally:
                await browser.close()

    async def test_structured_decision_and_refusal(self):
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='stop', message=SimpleNamespace(refusal=None,
                content='{"legible":true,"interactuar":true,"motivo":"Texto claro"}'))]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self.assertTrue((await evaluar(client, 'Texto de prueba')).interactuar)
        self.assertEqual(create.call_args.kwargs['model'], 'gpt-4o-mini')
        create.return_value.choices[0].message.refusal = 'No disponible'
        with self.assertRaises(ValueError):
            await evaluar(client, 'Texto de prueba')


if __name__ == '__main__':
    unittest.main()


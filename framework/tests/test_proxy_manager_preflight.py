import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from config.proxies import ProxyManager


class PreflightCauseTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, browser_cleanup_fails=False):
        bridge = MagicMock()
        manager = SimpleNamespace(endpoint_para_chromium=AsyncMock(
            return_value=({'server': 'http://localhost:12345'}, bridge)))
        response = MagicMock(status_code=200)
        response.json.return_value = {'ip': '8.8.8.8'}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=SimpleNamespace(get=AsyncMock(return_value=response)))
        client.__aexit__ = AsyncMock(return_value=False)
        page = SimpleNamespace(goto=AsyncMock(side_effect=httpx.ReadTimeout('private details')))
        cleanup = AsyncMock(side_effect=RuntimeError('private details')) if browser_cleanup_fails else AsyncMock(return_value=True)
        with patch.object(ProxyManager, 'desde_panda', return_value=manager), \
                patch('httpx.AsyncClient', return_value=client), \
                patch('core.browser.iniciar_contexto_async', AsyncMock(return_value=(object(), object(), page, bridge))), \
                patch('core.browser.cerrar_contexto_async', cleanup), \
                self.assertLogs('qa.panda.masivo', level='INFO') as logs:
            with self.assertRaisesRegex(RuntimeError, '^Proxy no verificable$'):
                await ProxyManager.verificar_preflight(run_id='test-safe-cause')
        bridge.close.assert_called_once()
        self.assertEqual(page.goto.await_count, 3)
        text = '\n'.join(logs.output)
        self.assertNotIn('private details', text)
        self.assertNotIn('8.8.8.8', text)
        return text

    async def test_verificar_preflight_logs_causa_ipify(self):
        text = await self.exercise()
        self.assertIn('proxy_preflight_timeout_ipify', text)
        self.assertIn('bridge_closed=true', text)

    async def test_verificar_preflight_bridge_closed_on_failure(self):
        await self.exercise(browser_cleanup_fails=True)

    async def test_ip_lookup_falls_back_from_timeout_to_json(self):
        manager = SimpleNamespace(
            endpoint_para_chromium=AsyncMock(return_value=({'server': 'http://localhost:12345'}, None)),
            _panda_country='ES')
        client = MagicMock()
        direct_response = SimpleNamespace(status_code=200, text='8.8.8.8\n')
        client.__aenter__ = AsyncMock(return_value=SimpleNamespace(get=AsyncMock(return_value=direct_response)))
        client.__aexit__ = AsyncMock(return_value=False)
        page = SimpleNamespace(
            goto=AsyncMock(side_effect=[TimeoutError('private details'), SimpleNamespace(status=200)]),
            locator=MagicMock(return_value=SimpleNamespace(inner_text=AsyncMock(return_value='{"ip":"1.1.1.1"}'))))
        geo = AsyncMock(return_value={'geo_status': 'resolved', 'pais': 'ES'})
        with patch.object(ProxyManager, 'desde_panda', return_value=manager), \
                patch('httpx.AsyncClient', return_value=client), \
                patch('core.browser.iniciar_contexto_async', AsyncMock(return_value=(object(), object(), page, None))), \
                patch('core.browser.cerrar_contexto_async', AsyncMock(return_value=True)), \
                patch('core.geo_resolver.obtener_geolocalizacion_con_bypass', geo), \
                self.assertLogs('qa.panda.masivo', level='INFO') as logs:
            await ProxyManager.verificar_preflight(run_id='test-ip-fallback')

        self.assertEqual([item.args[0] for item in page.goto.await_args_list],
                         ['https://ipv4.icanhazip.com', 'https://api.ipify.org?format=json'])
        self.assertTrue(all(item.kwargs['timeout'] == 15000 for item in page.goto.await_args_list))
        geo.assert_awaited_once()
        self.assertEqual(geo.await_args.args[0], '1.1.1.1')
        self.assertNotIn('private details', '\n'.join(logs.output))

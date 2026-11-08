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

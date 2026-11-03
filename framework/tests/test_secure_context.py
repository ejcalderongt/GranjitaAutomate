from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.browser import cerrar_contexto_seguro, iniciar_contexto_seguro, proxy_desde_entorno


class SecureContextTests(unittest.TestCase):
    def test_context_failure_still_stops_browser_and_bridge(self):
        context, runtime = MagicMock(), MagicMock()
        context.close.side_effect = RuntimeError('close failed')
        self.assertFalse(cerrar_contexto_seguro(context, runtime))
        runtime.stop.assert_called_once()

    def test_external_port_has_no_upstream_credentials_or_environment_fallback(self):
        with patch('core.browser.iniciar_navegador_tiktok') as start:
            iniciar_contexto_seguro('account', 32123)
        self.assertEqual(start.call_args.args[1], {'server': 'http://127.0.0.1:32123'})
        with self.assertRaises(ValueError):
            iniciar_contexto_seguro('account', True)
        with self.assertRaises(ValueError):
            iniciar_contexto_seguro('account', 8081, proxy={'server': 'http://other:80'})

    def test_explicit_pool_proxy_wins_over_environment(self):
        supplied = {'server': 'socks5://pool:8080', 'username': 'u', 'password': 'p'}
        with patch('core.browser.proxy_desde_entorno') as environment, \
             patch('core.browser.iniciar_navegador_tiktok') as start:
            iniciar_contexto_seguro('account', proxy=supplied)
        environment.assert_not_called()
        self.assertEqual(start.call_args.args[1], supplied)

    def test_environment_precedence_keeps_process_over_local_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'tiktok_warmer').mkdir()
            (root/'.env').write_text('PROXY_USERNAME=root\n')
            (root/'tiktok_warmer/.env').write_text('PROXY_URL=socks5://example.org:8080\nPROXY_USERNAME=local\nPROXY_PASSWORD=password\n')
            with patch('core.browser.ROOT', root), patch.dict('os.environ', {'PROXY_USERNAME': 'process'}, clear=True):
                result = proxy_desde_entorno()
            self.assertEqual(result['username'], 'process')
            self.assertEqual(result['server'], 'socks5://example.org:8080')

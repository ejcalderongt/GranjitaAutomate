import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from tiktok_warmer.core.browser import configurar_proxy
from tiktok_warmer import test_connection as diagnostic


class ProxyPreflightTests(unittest.TestCase):
    def test_credentials_are_split_and_endpoint_redacted(self):
        options = configurar_proxy('http://user:p%40ss@proxy.example:8080')
        self.assertEqual(options, {'server': 'http://proxy.example:8080', 'username': 'user', 'password': 'p@ss'})
        with self.assertRaises(ValueError):
            configurar_proxy('http://proxy-cheap.com')

    def test_geolocation_failure_closes_browser_and_records_partial_success(self):
        playwright, context, page = MagicMock(), MagicMock(), MagicMock()
        page.goto.side_effect = [MagicMock(status=200), RuntimeError('secret should never persist')]
        page.locator.return_value.inner_text.return_value = '{"ip":"8.8.8.8"}'
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(diagnostic, 'PROJECT', Path(folder)), \
             patch.object(diagnostic, 'dotenv_values', return_value={}), \
             patch.dict(diagnostic.os.environ, {'PROXY_URL': 'http://example.org:8080'}, clear=True), \
             patch.object(diagnostic, 'resolver_geo_por_proxy', new=AsyncMock(return_value={
                 'pais':'UNKNOWN','continente':'UNKNOWN','provider_used':'FAILED_ALL',
                 'fallback_used':True,'attempts':[],'geo_status':'unavailable'})), \
             patch.object(diagnostic, 'iniciar_navegador_tiktok', return_value=(playwright, context, page)):
            code, report = diagnostic.probar_infraestructura(headless=True)
            self.assertEqual(code, 2)
            self.assertTrue(report['proxy_connectivity'])
            self.assertFalse(report['region_verified'])
            self.assertEqual(report['status'], 'partial')
            self.assertEqual(report['error_code'], 'geo_unavailable')
            context.close.assert_called_once()
            playwright.stop.assert_called_once()
            saved = next(Path(folder).rglob('resultado.json')).read_text()
            self.assertNotIn('secret should never persist', saved)

    def test_password_placeholder_never_opens_browser(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(diagnostic, 'PROJECT', Path(folder)), \
             patch.object(diagnostic, 'dotenv_values', return_value={}), \
             patch.dict(diagnostic.os.environ, {'PROXY_PASSWORD': 'MI_CONTRASENA_REAL'}, clear=True), \
             patch.object(diagnostic, 'iniciar_navegador_tiktok') as browser:
            code, report = diagnostic.probar_infraestructura()
            self.assertEqual(report['error_code'], 'proxy_password_pending')
            self.assertEqual(code, 2)
            browser.assert_not_called()

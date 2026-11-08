import unittest
from config.proxies import ProxyManager


class ProxySchemeTests(unittest.TestCase):
    def manager(self, scheme):
        return ProxyManager.desde_panda(settings={
            'PANDA_PROXY_SCHEME': scheme, 'PANDA_PROXY_HOST': 'example.com',
            'PANDA_PROXY_PORT': '8080', 'PANDA_PROXY_USER': 'test',
            'PANDA_PROXY_PASS': 'test', 'PANDA_PROXY_COUNTRY': 'ES'})

    def test_scheme_accepts_http(self):
        self.assertEqual(self.manager('http').browser_proxy()['server'], 'http://example.com:8080')

    def test_scheme_accepts_https(self):
        self.assertEqual(self.manager('https').browser_proxy()['server'], 'https://example.com:8080')

    def test_scheme_accepts_socks5_and_socks5h_unchanged(self):
        for scheme in ('socks5', 'socks5h'):
            self.assertEqual(self.manager(scheme).browser_proxy()['server'], 'socks5://example.com:8080')

    def test_scheme_rejects_unknown(self):
        with self.assertRaisesRegex(ValueError, '^Proxy invalido$'):
            self.manager('ftp')

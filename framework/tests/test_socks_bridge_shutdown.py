import socket
import unittest
from urllib.parse import urlsplit

from tiktok_warmer.core.socks_bridge import SocksBridge


class BridgeShutdownTests(unittest.TestCase):
    def test_close_accept_callback_race_repeated(self):
        for _ in range(20):
            bridge = SocksBridge('socks5://127.0.0.1:1', 'test', 'test')
            endpoint = urlsplit(bridge.start())
            client = socket.create_connection((endpoint.hostname, endpoint.port), timeout=2)
            try:
                bridge.close()
                self.assertFalse(bridge.thread.is_alive())
                self.assertTrue(bridge.loop.is_closed())
            finally:
                client.close()

    def test_close_with_idle_client_waiting_for_handshake(self):
        bridge = SocksBridge('socks5://127.0.0.1:1', 'test', 'test')
        endpoint = urlsplit(bridge.start())
        client = socket.create_connection((endpoint.hostname, endpoint.port), timeout=2)
        try:
            bridge.close()
            bridge.close()
            self.assertFalse(bridge.thread.is_alive())
            self.assertTrue(bridge.loop.is_closed())
            with self.assertRaises(OSError):
                socket.create_connection((endpoint.hostname, endpoint.port), timeout=1)
        finally:
            client.close()

    def test_close_before_start_is_safe(self):
        bridge = SocksBridge('socks5://127.0.0.1:1', 'test', 'test')
        bridge.close()

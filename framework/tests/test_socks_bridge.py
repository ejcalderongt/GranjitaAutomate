import socket
import threading
import unittest

from tiktok_warmer.core.socks_bridge import SocksBridge


def read_exact(sock, size):
    result = b''
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise ConnectionError('EOF')
        result += chunk
    return result


class SocksBridgeTests(unittest.TestCase):
    def test_http_connect_authenticates_upstream_and_closes_listener(self):
        observed = {}
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(5)

        def upstream():
            try:
                with listener.accept()[0] as conn:
                    conn.settimeout(5)
                    observed['greeting'] = read_exact(conn, 3)
                    conn.sendall(b'\x05\x02')
                    header = read_exact(conn, 2)
                    observed['user'] = read_exact(conn, header[1])
                    observed['password'] = read_exact(conn, read_exact(conn, 1)[0])
                    conn.sendall(b'\x01\x00')
                    observed['command'] = read_exact(conn, 4)
                    observed['host'] = read_exact(conn, read_exact(conn, 1)[0])
                    read_exact(conn, 2)
                    conn.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00')
                    conn.sendall(read_exact(conn, 4))
            except Exception as exc:
                observed['error'] = type(exc).__name__
            finally:
                listener.close()

        worker = threading.Thread(target=upstream, daemon=True)
        worker.start()
        bridge = SocksBridge('socks5://127.0.0.1:' + str(listener.getsockname()[1]), 'test', 'secret')
        try:
            endpoint = bridge.start()
            port = int(endpoint.rsplit(':', 1)[1])
            with socket.create_connection(('127.0.0.1', port), timeout=5) as client:
                client.sendall(b'CONNECT example.org:443 HTTP/1.1\r\nHost: example.org:443\r\n\r\n')
                response = b''
                while not response.endswith(b'\r\n\r\n'):
                    response += read_exact(client, 1)
                self.assertIn(b'200', response.split(b'\r\n')[0])
                client.sendall(b'ping')
                self.assertEqual(read_exact(client, 4), b'ping')
        finally:
            bridge.close()
            worker.join(5)
        self.assertFalse(bridge.thread.is_alive())
        self.assertEqual(observed.get('host'), b'example.org')
        self.assertEqual(observed.get('user'), b'test')
        self.assertEqual(observed.get('password'), b'secret')
        self.assertNotIn('error', observed)

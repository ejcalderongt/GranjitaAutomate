import socket
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from granjita.core import Adb, AdbError, Store, parse_devices


class FakeSocket:
    def __init__(self, data):
        self.data = data

    def recv(self, size):
        chunk, self.data = self.data[:min(size, 3)], self.data[min(size, 3):]
        return chunk

    def sendall(self, data):
        pass

    def settimeout(self, timeout):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class CoreTests(unittest.TestCase):
    def test_fragmented_protocol_and_validation(self):
        device = parse_devices('example device model:Android_Board transport_id:1')[0]
        with patch.object(Adb, 'connect', return_value=FakeSocket(b'OKAYOKAYGRANJITA_OK\r\n12\r\n')):
            result = Adb().validate(device)
        self.assertEqual(result['status'], 'Validado')
        self.assertEqual(result['android'], '12')
        self.assertEqual(result['model'], 'Android Board')

    def test_unauthorized_never_runs_shell(self):
        with patch.object(Adb, 'connect') as connect:
            result = Adb().validate(dict(serial='example', state='unauthorized', model=''))
        connect.assert_not_called()
        self.assertEqual(result['status'], 'Requiere autorización')

    def test_timeout_is_not_validated(self):
        with patch.object(Adb, 'connect', side_effect=socket.timeout('Tiempo agotado')):
            result = Adb().validate(dict(serial='example', state='device', model=''))
        self.assertEqual(result['status'], 'Error de validación')

    def test_failed_protocol_is_reported(self):
        with self.assertRaisesRegex(AdbError, 'error'):
            Adb().request(FakeSocket(b'FAIL0005error'), 'host:devices-l')

    def test_inventory_disconnection_alias_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'test.sqlite3')
            item = dict(serial='example', model='Board', android='12', status='Validado', detail='OK')
            store.save_scan([item])
            store.alias('example', 'Placa 01')
            store.save_scan([])
            self.assertEqual(store.devices()[0]['status'], 'Desconectado')
            store.save_scan([item])
            self.assertEqual(store.devices()[0]['alias'], 'Placa 01')
            self.assertEqual(len(store.history('example')), 3)
            backup = Path(folder) / 'backup.sqlite3'
            store.backup(backup)
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT alias FROM devices').fetchone()[0], 'Placa 01')
            with self.assertRaises(ValueError):
                store.backup(store.path)


if __name__ == '__main__':
    unittest.main()

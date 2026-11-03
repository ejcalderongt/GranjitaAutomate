import asyncio
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from config.proxies import ProxyManager


class ProxyExitsTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, values):
        manager = object.__new__(ProxyManager)
        manager._proxy = {'server': 'socks5://proxy.invalid:1'}
        manager._proxy_client = SimpleNamespace(get=AsyncMock(side_effect=values))
        return manager

    def response(self, value):
        return SimpleNamespace(status_code=200, json=lambda: {'ip': value})

    async def test_distinct_and_repeated_values(self):
        for values, distinct in ((['exit-a', 'exit-b', 'exit-c'], 3), (['exit-a']*3, 1)):
            manager = self.manager([self.response(v) for v in values])
            with patch('config.proxies.ipaddress.ip_address', side_effect=lambda v: SimpleAddress(v)):
                result = await manager.contar_salidas_distintas(muestras=3, timeout=1)
            self.assertEqual(result, {'distinct': distinct, 'total': 3, 'errors': 0, 'timeouts': 0})
            self.assertEqual(manager._proxy_client.get.await_count, 3)

    async def test_errors_timeouts_and_no_implicit_retries(self):
        manager = self.manager([RuntimeError('unavailable'), asyncio.TimeoutError(), self.response('exit-a')])
        with patch('config.proxies.ipaddress.ip_address', side_effect=SimpleAddress):
            result = await manager.contar_salidas_distintas(muestras=3, timeout=1)
        self.assertEqual(result, {'distinct': 1, 'total': 3, 'errors': 1, 'timeouts': 1})
        self.assertEqual(manager._proxy_client.get.await_count, 3)

    async def test_invalid_ranges(self):
        manager = self.manager([])
        for value in (0, 33, True, 1.5):
            with self.assertRaisesRegex(ValueError, '^Muestras fuera de rango$'):
                await manager.contar_salidas_distintas(muestras=value, timeout=1)
        for value in (0, 61, True, float('nan'), float('inf')):
            with self.assertRaisesRegex(ValueError, '^Timeout fuera de rango$'):
                await manager.contar_salidas_distintas(muestras=1, timeout=value)

    async def test_no_database_or_audit_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'existing.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE existing (value INT)')
                db.execute('INSERT INTO existing VALUES (1)')
            db.close()
            before = path.read_bytes()
            manager = self.manager([self.response('exit-a')])
            with patch.object(manager, '_audit', new=AsyncMock()) as audit, \
                    patch.object(manager, '_prepare', new=AsyncMock()) as prepare, \
                    patch('config.proxies.sqlite3.connect', side_effect=AssertionError('Database accessed')), \
                    patch('config.proxies.ipaddress.ip_address', side_effect=SimpleAddress):
                await manager.contar_salidas_distintas(muestras=1, timeout=1)
                audit.assert_not_called()
                prepare.assert_not_called()
            self.assertEqual(path.read_bytes(), before)

    async def test_missing_configuration(self):
        manager = self.manager([])
        manager._proxy = {}
        with self.assertRaisesRegex(ValueError, '^Proxy no configurado$'):
            await manager.contar_salidas_distintas(muestras=1, timeout=1)

    async def test_cancelled_error_propagates(self):
        manager = self.manager([asyncio.CancelledError()])
        with self.assertRaises(asyncio.CancelledError):
            await manager.contar_salidas_distintas(muestras=1, timeout=1)


class SimpleAddress:
    is_global = True

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

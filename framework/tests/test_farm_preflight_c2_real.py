from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from config.farm_preflight import evaluate_c2_real
from config.farm_policy import FarmPolicy


class C2RealTests(unittest.IsolatedAsyncioTestCase):
    async def evaluate(self, row, **extra):
        manager = SimpleNamespace(_panda_country='ES', verificar_preflight=AsyncMock())
        ctx = {'identity_probe': AsyncMock(return_value=row), 'proxy_preflight_verified': True, 'run_id': 'fixture', **extra}
        return await evaluate_c2_real(['a', 'b', 'c'], FarmPolicy(country='ES'), ctx, manager)

    async def test_match_mismatch_and_missing(self):
        good = {'sim_country': 'es', 'locale': 'es_ES', 'timezone': 'Europe/Madrid'}
        self.assertEqual((await self.evaluate(good)).status, 'PASS')
        for field, value in (('sim_country', 'fr'), ('locale', 'fr_FR'), ('timezone', 'Europe/Paris')):
            self.assertEqual((await self.evaluate({**good, field: value})).status, 'FAIL')
        self.assertEqual((await self.evaluate({})).status, 'WARN')

    async def test_probe_exception_and_geo_unavailable(self):
        manager = SimpleNamespace(_panda_country='ES', verificar_preflight=AsyncMock(side_effect=RuntimeError()))
        result = await evaluate_c2_real(['a'], FarmPolicy(country='ES'),
            {'identity_probe': AsyncMock(side_effect=RuntimeError()), 'run_id': 'fixture'}, manager)
        self.assertEqual(result.status, 'WARN')

    async def test_reuses_accredited_proxy_result_without_duplicate_probe(self):
        manager = SimpleNamespace(_panda_country='ES', verificar_preflight=AsyncMock())
        ctx = {'proxy_preflight_verified': True, 'identity_probe': AsyncMock(return_value={})}
        await evaluate_c2_real(['a'], FarmPolicy(country='ES'), ctx, manager)
        manager.verificar_preflight.assert_not_called()

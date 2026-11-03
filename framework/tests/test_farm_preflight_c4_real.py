import asyncio
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from config import farm_preflight as f
from config.farm_policy import FarmPolicy


class C4RealTests(unittest.IsolatedAsyncioTestCase):
    async def evaluate(self, result, policy=None):
        manager = SimpleNamespace(contar_salidas_distintas=AsyncMock(return_value=result))
        item = await f.evaluate_c4_real([], policy or FarmPolicy(), {}, manager)
        manager.contar_salidas_distintas.assert_awaited_once_with(muestras=3, timeout=15)
        return item

    async def test_pass_insufficient_and_rotation_errors(self):
        good = {'distinct': 3, 'total': 3, 'errors': 0, 'timeouts': 0}
        self.assertEqual((await self.evaluate(good)).status, 'PASS')
        self.assertEqual((await self.evaluate({**good, 'distinct': 1})).status, 'FAIL')
        policy = replace(FarmPolicy(), proxy_min_distinct_exit_ips=1)
        self.assertEqual((await self.evaluate({**good, 'distinct': 1, 'errors': 1}, policy)).status, 'WARN')
        self.assertEqual((await self.evaluate(good, replace(FarmPolicy(), proxy_sticky_ttl=1))).status, 'WARN')

    async def test_missing_method_exception_and_global_timeout(self):
        for manager in (None, SimpleNamespace(contar_salidas_distintas=AsyncMock(side_effect=RuntimeError()))):
            self.assertEqual((await f.evaluate_c4_real([], FarmPolicy(), {}, manager)).status, 'WARN')
        async def slow(**kwargs):
            await asyncio.sleep(1)
        with patch.object(f, 'C4_TIMEOUT_GLOBAL_SEGUNDOS', 0.001):
            result = await f.evaluate_c4_real([], FarmPolicy(), {}, SimpleNamespace(contar_salidas_distintas=slow))
        self.assertEqual(result.status, 'WARN')

    async def test_sampling_is_capped_at_contract_limit(self):
        manager = SimpleNamespace(contar_salidas_distintas=AsyncMock(return_value=dict(distinct=32, total=32, errors=0, timeouts=0)))
        await f.evaluate_c4_real([], FarmPolicy(stage=34), {}, manager)
        manager.contar_salidas_distintas.assert_awaited_once_with(muestras=32, timeout=15)

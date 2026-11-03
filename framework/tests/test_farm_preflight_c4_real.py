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

    async def test_aggregate_fallback_preserves_errors_and_status(self):
        result = dict(distinct=2,total=3,errors=1,timeouts=0)
        item = await self.evaluate(result)
        self.assertEqual(item.status, 'FAIL')
        self.assertEqual(item.counters['errors'], 1)
        self.assertEqual(item.counters['attempts'], 3)
        self.assertFalse(item.counters['data_available'])
        self.assertEqual(sum(item.counters['errors_by_kind'].values()), 0)
        self.assertEqual(item.counters['distinct_per_attempt'], [])
        self.assertEqual(item.counters['latency_ms_by_attempt'], [])
        item = await self.evaluate(dict(distinct=3,total=3,errors=0,timeouts=0))
        self.assertEqual(item.status, 'PASS')
        self.assertFalse(item.counters['data_available'])

    async def test_closed_mapping_and_consistent_per_attempt_details(self):
        details = [dict(code='success',new_exit=True,latency_ms=0)]
        details += [dict(code=code,new_exit=False,latency_ms=1) for code in f.C4_ERROR_MAP]
        details += [dict(code='timeout',new_exit=False,latency_ms=2)]
        result = dict(distinct=1,total=len(details),errors=6,timeouts=1)
        manager = SimpleNamespace(contar_salidas_distintas=AsyncMock(return_value=result))
        # A larger stage permits the bounded injected sample set.
        item = await f.evaluate_c4_real([], FarmPolicy(stage=10), {'c4_attempt_details':details}, manager)
        self.assertTrue(item.counters['data_available'])
        self.assertEqual(item.counters['errors_by_kind'], dict.fromkeys(f.C4_ERROR_KINDS, 1))
        self.assertEqual(len(item.counters['distinct_per_attempt']), result['total'])
        self.assertEqual(len(item.counters['latency_ms_by_attempt']), result['total'])

    async def test_invalid_details_are_unavailable_not_guessed(self):
        result = dict(distinct=3,total=3,errors=0,timeouts=0)
        for details in ([{'unexpected':'unapproved'}], [dict(code='success',new_exit=True,latency_ms=-1)]*3):
            manager = SimpleNamespace(contar_salidas_distintas=AsyncMock(return_value=result))
            item = await f.evaluate_c4_real([], FarmPolicy(), {'c4_attempt_details':details}, manager)
            self.assertEqual(item.status, 'PASS')
            self.assertFalse(item.counters['data_available'])

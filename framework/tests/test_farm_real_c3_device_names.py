import asyncio
import sqlite3
import unittest
from unittest.mock import AsyncMock, patch

from config import farm_preflight as farm
from config.farm_policy import FarmPolicy


class RealC3DeviceNamesTests(unittest.TestCase):
    def run_case(self, holds):
        devices = ['13', '15', '22']
        policy = FarmPolicy()
        ctx = {'synthetic': False, 'real_connectors_ready': True,
               'run_id': 'numeric-panda-c3',
               'c3': {device: {'hold_seconds': value}
                      for device, value in zip(devices, holds) if value is not None}}
        def mocked(constraint):
            return AsyncMock(return_value=farm.real_verdict(
                constraint, 'WARN', 'acreditar datos'))
        with sqlite3.connect(':memory:') as db, \
                patch.object(farm, 'evaluate_c1_real', mocked('C1')), \
                patch.object(farm, 'evaluate_c2_real', mocked('C2')), \
                patch.object(farm, 'evaluate_c4_real', mocked('C4')), \
                patch.object(farm, 'evaluate_c5_real', mocked('C5')):
            verdicts = asyncio.run(farm.run_farm_preflight(devices, policy, ctx, db))
            self.assertEqual([v.constraint for v in verdicts], ['C1', 'C2', 'C3', 'C4', 'C5'])
            self.assertEqual(list(ctx['c3']), [d for d, h in zip(devices, holds) if h is not None])
            return verdicts[2], farm.decide(verdicts, policy)

    def test_numeric_panda_ids_reach_c3_without_config_error(self):
        verdict, decision = self.run_case([8, 12, 22])
        self.assertEqual(verdict.status, 'PASS')
        self.assertEqual(verdict.counters['checked'], 3)
        self.assertEqual(decision, 'proceed_with_warnings')

    def test_mapping_preserves_missing_and_out_of_range_holds(self):
        verdict, decision = self.run_case([8, None, 23])
        self.assertEqual(verdict.status, 'FAIL')
        self.assertEqual(verdict.counters['missing'], 1)
        self.assertEqual(verdict.counters['failed'], 1)
        self.assertEqual(decision, 'abort')

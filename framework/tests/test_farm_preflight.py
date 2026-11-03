import asyncio
from dataclasses import replace
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from config.farm_policy import FarmPolicy
from config import farm_preflight as f


FIXTURE = Path(__file__).parent/'fixtures/farm_stage3.json'


class FarmPreflightTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ctx = f.load_synthetic_fixture(FIXTURE)
        self.ctx['run_id'] = 'fixture-run'
        self.devices = self.ctx['devices']
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)

    async def test_pass_all_and_persistence_without_contamination(self):
        self.db.execute('CREATE TABLE existing (value TEXT)')
        self.db.execute("INSERT INTO existing VALUES ('unchanged')")
        self.db.commit()
        before = self.db.execute("SELECT sql FROM sqlite_master WHERE name='existing'").fetchone()
        f.migrate(self.db)
        f.migrate(self.db)
        verdicts = await f.run_farm_preflight(self.devices, FarmPolicy(), self.ctx, self.db)
        self.assertEqual({v.constraint: v.status for v in verdicts}, self.ctx['expected'])
        self.assertEqual(f.decide(verdicts, FarmPolicy()), 'proceed')
        for table, count in (('farm_preflight_runs', 1), ('farm_preflight_verdicts', 5), ('farm_stage_metrics', 1)):
            self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0], count)
        self.assertEqual(self.db.execute('SELECT * FROM existing').fetchall(), [('unchanged',)])
        self.assertEqual(self.db.execute("SELECT sql FROM sqlite_master WHERE name='existing'").fetchone(), before)
        self.assertEqual(self.db.execute('SELECT decision FROM farm_preflight_runs').fetchone()[0], 'proceed')

    async def test_each_constraint_can_fail(self):
        changes = (('c1', 'authorized', False), ('c2', 'direct_leak', True),
                   ('c3', 'hold_seconds', 1), ('c4', 'available', False), ('c5', 'logout_count', 1))
        for number, (key, field, value) in enumerate(changes, 1):
            ctx = f.load_synthetic_fixture(FIXTURE)
            ctx[key]['p01'][field] = value
            verdict = await getattr(f, 'evaluate_c'+str(number))(self.devices, FarmPolicy(), ctx)
            self.assertEqual(verdict.status, 'FAIL')

    async def test_each_constraint_warns_on_missing_data(self):
        for number in range(1, 6):
            ctx = f.load_synthetic_fixture(FIXTURE)
            del ctx['c'+str(number)]['p01']
            item = await getattr(f, 'evaluate_c'+str(number))(self.devices, FarmPolicy(), ctx)
            self.assertEqual(item.status, 'WARN')

    async def test_boolean_strings_do_not_produce_pass(self):
        for number, key in ((1, 'authorized'), (2, 'geo_resolved'), (4, 'available')):
            ctx = f.load_synthetic_fixture(FIXTURE)
            ctx['c'+str(number)]['p01'][key] = 'true'
            item = await getattr(f, 'evaluate_c'+str(number))(self.devices, FarmPolicy(), ctx)
            self.assertNotEqual(item.status, 'PASS')

    async def test_nonzero_metrics_persist_even_when_policy_aborts(self):
        self.ctx['c5']['p01']['captcha_count'] = 1
        self.ctx['c5']['p02']['softblock_count'] = 2
        self.ctx['c5']['p03']['logout_count'] = 3
        verdicts = await f.run_farm_preflight(self.devices, FarmPolicy(), self.ctx, self.db)
        self.assertEqual(f.decide(verdicts, FarmPolicy()), 'abort')
        self.assertEqual(self.db.execute('SELECT captcha_count, softblock_count, logout_count FROM farm_stage_metrics').fetchone(), (1, 2, 3))

    async def test_decide_warn_and_fail_policy(self):
        verdicts = await f.run_farm_preflight(self.devices, FarmPolicy(), self.ctx, self.db)
        warning = replace(verdicts[0], status='WARN')
        mixed = [warning, *verdicts[1:]]
        self.assertEqual(f.decide(mixed, FarmPolicy()), 'proceed_with_warnings')
        self.assertEqual(f.decide(mixed, FarmPolicy(abort_on_warn=True)), 'abort')
        mixed[0] = replace(warning, status='FAIL')
        self.assertEqual(f.decide(mixed, FarmPolicy()), 'abort')
        self.assertEqual(f.decide(mixed, FarmPolicy(abort_on_fail=False)), 'proceed_with_warnings')
        with self.assertRaises(ValueError):
            f.decide(mixed[:1], FarmPolicy())

    async def test_cancelled_run_has_no_valid_partial_verdicts(self):
        with patch.object(f, 'evaluate_c2', side_effect=asyncio.CancelledError()):
            with self.assertRaises(asyncio.CancelledError):
                await f.run_farm_preflight(self.devices, FarmPolicy(), self.ctx, self.db)
        self.assertEqual(self.db.execute('SELECT decision FROM farm_preflight_runs').fetchone()[0], 'cancelled')
        self.assertEqual(self.db.execute('SELECT count(*) FROM farm_preflight_verdicts').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM farm_stage_metrics').fetchone()[0], 0)

    async def test_live_context_rejected_before_migration(self):
        self.ctx['synthetic'] = False
        with self.assertRaises(ValueError):
            await f.run_farm_preflight(self.devices, FarmPolicy(), self.ctx, self.db)
        self.assertEqual(self.db.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'farm_%'").fetchone()[0], 0)

    def test_reason_rejects_unstructured_or_sensitive_content(self):
        with self.assertRaises(ValueError):
            f.ConstraintVerdict('C1', 'FAIL', 'unstructured detail', {})

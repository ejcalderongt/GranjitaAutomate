import sqlite3
import unittest

from config.farm_policy import FarmPolicy
from config.farm_preflight import migrate, evaluate_c5_real


class C5RealTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        migrate(self.db)

    def seed(self, count=0, synthetic=0, decision='proceed', stage=3):
        self.db.execute('INSERT INTO farm_preflight_runs VALUES (?,?,?,?,?,?,?)',
                        ('fixture', 'fixture', stage, 'start', 'finish', decision, synthetic))
        self.db.execute('INSERT INTO farm_preflight_verdicts (run_id,"constraint",status) VALUES (?,?,?)', ('fixture', 'C5', 'PASS'))
        self.db.execute('INSERT INTO farm_stage_metrics (run_id,stage,captcha_count,softblock_count,logout_count) VALUES (?,?,?,?,?)',
                        ('fixture', stage, count, 0, 0))
        self.db.commit()

    async def test_no_metrics_warns_and_does_not_write(self):
        changes = self.db.total_changes
        self.assertEqual((await evaluate_c5_real([], FarmPolicy(), {}, self.db)).status, 'WARN')
        self.assertEqual(self.db.total_changes, changes)

    async def test_real_history_pass_and_excess_fail(self):
        self.seed(count=1)
        self.assertEqual((await evaluate_c5_real([], FarmPolicy(), {}, self.db)).status, 'FAIL')
        self.assertEqual((await evaluate_c5_real([], FarmPolicy(max_captchas=1), {}, self.db)).status, 'PASS')
        self.assertEqual((await evaluate_c5_real([], FarmPolicy(max_captchas=1, min_metric_samples=2), {}, self.db)).status, 'WARN')

    async def test_synthetic_history_never_accredits_real_metrics(self):
        self.seed(synthetic=1)
        self.assertEqual((await evaluate_c5_real([], FarmPolicy(), {}, self.db)).status, 'WARN')

    async def test_other_stage_is_excluded(self):
        self.seed(stage=10)
        self.assertEqual((await evaluate_c5_real([], FarmPolicy(), {}, self.db)).status, 'WARN')

    async def test_missing_schema_warns_without_migration(self):
        db = sqlite3.connect(':memory:')
        try:
            self.assertEqual((await evaluate_c5_real([], FarmPolicy(), {}, db)).status, 'WARN')
            self.assertEqual(db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0], 0)
        finally:
            db.close()

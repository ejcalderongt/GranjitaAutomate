import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch, AsyncMock
from core.stage_scaling import StageLimits, evaluate_stage, load_stage_limits, stage_plan
from config.farm_preflight import migrate


class StageScalingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        migrate(self.db)

    def history(self, stage, counts=(0, 0, 0), synthetic=0, c4='PASS'):
        self.db.execute('INSERT INTO farm_preflight_runs VALUES (?,?,?,?,?,?,?)',
                        ('case', 'case', stage, 'start', 'finish', 'proceed', synthetic))
        self.db.execute('INSERT INTO farm_stage_metrics(run_id,stage,captcha_count,softblock_count,logout_count) VALUES (?,?,?,?,?)', ('case', stage, *counts))
        self.db.execute('INSERT INTO farm_preflight_verdicts(run_id,"constraint",status) VALUES (?,?,?)', ('case', 'C4', c4))
        self.db.commit()

    def test_success_3(self):
        self.history(3);self.assertEqual(evaluate_stage(self.db, 3).next_stage, 10)
    def test_success_10(self):
        self.history(10);self.assertEqual(evaluate_stage(self.db, 10).next_stage, 34)
    def test_success_34(self):
        self.history(34);self.assertEqual(evaluate_stage(self.db, 34).decision, 'complete')
    def test_captcha_abort(self):
        self.history(3, (1, 0, 0));self.assertEqual(evaluate_stage(self.db, 3).decision, 'abort')
    def test_softblock_abort(self):
        self.history(10, (0, 1, 0));self.assertEqual(evaluate_stage(self.db, 10).decision, 'abort')
    def test_logout_abort(self):
        self.history(34, (0, 0, 1));self.assertEqual(evaluate_stage(self.db, 34).decision, 'abort')
    def test_null_blocks(self):
        self.history(3, (None, 0, 0));self.assertIsNone(evaluate_stage(self.db, 3).next_stage)
    def test_incident_with_null_aborts(self):
        self.history(3, (None, 1, 0));self.assertEqual(evaluate_stage(self.db, 3).decision, 'abort')
    def test_synthetic_not_promoted(self):
        self.history(3, synthetic=1);self.assertIsNone(evaluate_stage(self.db, 3).next_stage)
    def test_proxy_gate(self):
        self.history(3, c4='WARN');self.assertEqual(evaluate_stage(self.db, 3).reason, 'proxy_stage_not_accredited')
    def test_sample_limit(self):
        self.history(3);self.assertIsNone(evaluate_stage(self.db, 3, StageLimits(2)).next_stage)
    def test_schema_missing(self):
        with sqlite3.connect(':memory:') as db:self.assertEqual(evaluate_stage(db, 3).decision, 'blocked')
    def test_limits_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'limits.json'
            path.write_text(json.dumps({str(s): {'min_samples': 2} for s in (3, 10, 34)}))
            self.assertEqual(load_stage_limits(path)[10].min_samples, 2)
            path.write_text('{"3":{"min_samples":0}}')
            with self.assertRaises(ValueError):load_stage_limits(path)
    def test_cli_stage_never_calls_native(self):
        import main_panda_masivo as main
        with tempfile.TemporaryDirectory() as folder, patch.object(main, 'ROOT', Path(folder)), patch.object(main, 'ejecutar_flujo_nativo', new=AsyncMock()) as native:
            args=NS(stage=3, stage_limits=None, db=Path(folder)/'missing.db')
            self.assertEqual(asyncio.run(main.main_async(args)), 2)
            native.assert_not_awaited()
            report=json.loads(next((Path(folder)/'runs').glob('stage_plan_*.json')).read_text())
            self.assertFalse(report['executes_next_stage'])

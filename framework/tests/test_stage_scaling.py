import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
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

    def run_cli_plan(self, root, db_path, stage, limits):
        import main_panda_masivo as main
        before = set((root/'runs').glob('stage_plan_*.json'))
        argv = ['main_panda_masivo.py', '--stage', str(stage), '--stage-limits', str(limits), '--db', str(db_path)]
        with patch.object(main, 'ROOT', root), patch.object(sys, 'argv', argv), \
                patch.object(main, 'ejecutar_flujo_nativo', new=AsyncMock()) as native:
            code = main.main()
            native.assert_not_awaited()
        created = set((root/'runs').glob('stage_plan_*.json')) - before
        self.assertEqual(len(created), 1)
        report = json.loads(created.pop().read_text(encoding='ascii'))
        self.assertFalse(report['executes_next_stage'])
        return code, report

    def test_cli_simulates_promotion_from_3_and_ten_successful_plates(self):
        self.history(3)
        self.db.execute('INSERT INTO farm_preflight_runs VALUES (?,?,?,?,?,?,?)',
                        ('stub-10', 'stub-10', 10, 'start', 'finish', 'proceed', 0))
        self.db.execute('INSERT INTO farm_preflight_verdicts(run_id,"constraint",status) VALUES (?,?,?)',
                        ('stub-10', 'C4', 'PASS'))
        self.db.executemany('''INSERT INTO farm_stage_metrics
            (run_id,stage,captcha_count,softblock_count,logout_count) VALUES (?,?,?,?,?)''',
                            [('stub-10', 10, 0, 0, 0) for _ in range(10)])
        self.db.commit()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db_path = root/'history.db'
            with closing(sqlite3.connect(db_path)) as db:
                self.db.backup(db)
            limits = root/'limits.json'
            limits.write_text('{"3":{"min_samples":1},"10":{"min_samples":10},"34":{"min_samples":1}}', encoding='ascii')
            code, stage3 = self.run_cli_plan(root, db_path, 3, limits)
            self.assertEqual((code, stage3['decision'], stage3['next_stage']), (0, 'promote', 10))
            code, stage10 = self.run_cli_plan(root, db_path, 10, limits)
            self.assertEqual((code, stage10['decision'], stage10['samples']), (0, 'promote', 10))
            self.assertEqual(stage10['stage_limits']['10']['min_samples'], 10)
            self.db.execute('DELETE FROM farm_stage_metrics WHERE id=(SELECT MAX(id) FROM farm_stage_metrics)')
            self.db.commit()
            with closing(sqlite3.connect(db_path)) as db:
                self.db.backup(db)
            code, blocked = self.run_cli_plan(root, db_path, 10, limits)
            self.assertEqual((code, blocked['reason'], blocked['next_stage']), (2, 'incomplete_metrics', None))

    def test_cli_captcha_at_stage_3_aborts_without_promoting(self):
        self.history(3, (1, 0, 0))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db_path = root/'history.db'
            with closing(sqlite3.connect(db_path)) as db:
                self.db.backup(db)
            limits = root/'limits.json'
            limits.write_text('{"3":{"min_samples":1},"10":{"min_samples":10},"34":{"min_samples":1}}', encoding='ascii')
            code, report = self.run_cli_plan(root, db_path, 3, limits)
            self.assertEqual((code, report['decision'], report['reason'], report['next_stage']),
                             (2, 'abort', 'observed_incident', None))

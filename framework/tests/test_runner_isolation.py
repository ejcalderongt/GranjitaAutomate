from pathlib import Path
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_tests
from core import decision_telemetry


class RunnerIsolationTests(unittest.TestCase):
    def test_real_runner_from_clean_cwd_keeps_journals_out_of_project_logs(self):
        root=Path(__file__).resolve().parents[1]
        before=run_tests.log_files(root/'logs')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            fixture=path/'fixture_isolation.py'
            fixture.write_text('''import unittest
from pathlib import Path
from core.decision_telemetry import DecisionTelemetry
class FixtureTests(unittest.TestCase):
    def test_journal(self):
        journal=DecisionTelemetry('fixture_account','fixture_run')
        journal.append('fixture_event',cycle_id='fixture_cycle')
        self.assertNotEqual(journal.path.parents[2],Path.cwd())
''',encoding='ascii')
            env=os.environ.copy()
            env.pop('OPENAI_API_KEY',None)
            env['PYTHONDONTWRITEBYTECODE']='1'
            result=subprocess.run([sys.executable,'-B',str(root/'scripts/run_tests.py'),'-s',str(path),'-p','fixture_isolation.py','-q','--buffer'],
                cwd=path,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0)
            self.assertFalse((path/'logs').exists())
        self.assertEqual(run_tests.log_files(root/'logs'),before)

    def test_redirect_lifetime_and_production_default_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            production=root/'production'
            with patch.object(decision_telemetry,'ROOT',production):
                def fake_main(**kwargs):
                    self.assertNotEqual(decision_telemetry.ROOT,production)
                    journal=decision_telemetry.DecisionTelemetry('fixture_account','fixture_inside')
                    self.assertTrue(journal.path.is_relative_to(root/'runs'))
                    return SimpleNamespace(result=SimpleNamespace(wasSuccessful=lambda:True))
                with patch('unittest.main',side_effect=fake_main):
                    self.assertEqual(run_tests.run_isolated_unittest(['-q'],root),0)
                self.assertEqual(decision_telemetry.ROOT,production)
                journal=decision_telemetry.DecisionTelemetry('fixture_account','fixture_outside')
                self.assertTrue(journal.path.is_relative_to(production/'logs'))

    def test_redirect_restores_after_exception(self):
        before=decision_telemetry.ROOT
        with tempfile.TemporaryDirectory() as folder,patch('unittest.main',side_effect=RuntimeError('fixture')):
            with self.assertRaisesRegex(RuntimeError,'^fixture$'):
                run_tests.run_isolated_unittest(['-q'],Path(folder))
        self.assertEqual(decision_telemetry.ROOT,before)

    def test_guard_rejects_new_log(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'logs'
            before=run_tests.log_files(path)
            path.mkdir()
            (path/'fixture.jsonl').write_text('{}\n',encoding='ascii')
            with self.assertRaisesRegex(AssertionError,'^Suite created files in project logs; use tmp_path$'):
                run_tests.guard_logs(path,before)

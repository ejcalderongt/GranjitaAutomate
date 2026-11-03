from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.evidence_invariants import snapshot,compare,file_hash,compare_protected


class EvidenceInvariantsTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'telemetria_panda.db'
        self.db=sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE existing(value TEXT);
            INSERT INTO existing VALUES ('retained');
            CREATE TABLE farm_preflight_runs(id TEXT PRIMARY KEY,run_id TEXT,finished_at TEXT,decision TEXT);
            CREATE TABLE farm_preflight_verdicts(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,status TEXT);
            CREATE TABLE farm_stage_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,captcha_count INT);
            INSERT INTO farm_preflight_runs VALUES ('old','old','finished','proceed');
            INSERT INTO farm_preflight_verdicts(run_id,status) VALUES ('old','PASS');
            INSERT INTO farm_stage_metrics(run_id,captcha_count) VALUES ('old',0);
        ''')
        self.db.commit()

    def simulate(self):
        self.db.execute("INSERT INTO farm_preflight_runs VALUES ('current','current',NULL,NULL)")
        self.db.execute("INSERT INTO farm_preflight_verdicts(run_id,status) VALUES ('current','PASS')")
        self.db.execute("INSERT INTO farm_stage_metrics(run_id,captcha_count) VALUES ('current',0)")
        self.db.execute("UPDATE farm_preflight_runs SET finished_at='finished',decision='proceed' WHERE id='current'")
        self.db.commit()

    def test_t1_expected_farm_sequence_advances_pass(self):
        before=snapshot(self.path)
        self.simulate()
        report=compare(before,snapshot(self.path),'current')
        self.assertEqual(report['status'],'PASS')
        self.assertTrue(report['full_hash_changed'])
        self.assertTrue(report['non_farm_tables_unchanged'])
        self.assertEqual({row['name'] for row in report['sqlite_sequence_advance']['expected_farm_advances']},
                         {'farm_preflight_verdicts','farm_stage_metrics'})
        self.assertEqual(report['sqlite_sequence_advance']['unexpected_changes'],[])

    def test_t2_other_application_sequence_change_fails(self):
        self.db.execute('CREATE TABLE otra_app(id INTEGER PRIMARY KEY AUTOINCREMENT,value TEXT)')
        self.db.commit()
        before=snapshot(self.path)
        self.simulate()
        self.db.execute("INSERT INTO otra_app(value) VALUES ('unexpected')")
        self.db.commit()
        report=compare(before,snapshot(self.path),'current')
        self.assertEqual(report['status'],'FAIL')
        self.assertFalse(report['non_farm_tables_unchanged'])
        self.assertEqual(report['sqlite_sequence_advance']['unexpected_changes'][0]['name'],'otra_app')

    def test_t3_unexpected_farm_update_delete_or_foreign_insert_fails(self):
        for statement in ("UPDATE farm_preflight_verdicts SET status='FAIL' WHERE run_id='old'",
                          "DELETE FROM farm_preflight_verdicts WHERE run_id='old'",
                          "INSERT INTO farm_preflight_verdicts(run_id,status) VALUES ('old','PASS')"):
            before=snapshot(self.path)
            self.db.execute(statement)
            self.db.commit()
            report=compare(before,snapshot(self.path),'current')
            self.assertEqual(report['status'],'FAIL')
            self.assertTrue(report['farm_violations'])
            self.assertEqual(report['sqlite_sequence_advance']['unexpected_changes'],[])

    def test_t4_database_without_sequence_passes(self):
        path=Path(self.folder.name)/'without_sequence.db'
        db=sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE existing(value TEXT)')
            db.commit()
        finally:
            db.close()
        before=snapshot(path)
        report=compare(before,snapshot(path),'current')
        self.assertEqual(report['status'],'PASS')
        self.assertTrue(report['sqlite_sequence_absent'])
        self.assertTrue(report['sqlite_sequence_advance']['absent'])

    def test_t5_other_protected_database_hash_is_immutable(self):
        path=Path(self.folder.name)/'protected.db'
        db=sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE existing(value TEXT)')
            db.commit()
            before={'protected':file_hash(path)}
            self.assertEqual(compare_protected(before,{'protected':file_hash(path)})['status'],'PASS')
            db.execute("INSERT INTO existing VALUES ('changed')")
            db.commit()
            self.assertEqual(compare_protected(before,{'protected':file_hash(path)})['status'],'FAIL')
        finally:
            db.close()

import asyncio
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from config import farm_preflight
from config.farm_policy import FarmPolicy
from scripts.evidence_invariants import compare, snapshot, declare_run_writes


class FarmPreflightCLIRealTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.path=self.root/'telemetria_panda.db'
        self.qa_path=self.root/'telemetry_qa.db'
        self.db=sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        farm_preflight.migrate(self.db)
        self.db.executescript('''
            CREATE TABLE auditorias_panda(run_id TEXT,ciclo INT,id_placa TEXT,value TEXT,
                PRIMARY KEY(run_id,ciclo,id_placa));
            INSERT INTO auditorias_panda VALUES ('old',1,'p01','retained');
        ''')
        self.db.commit()
        self.qa=sqlite3.connect(self.qa_path)
        self.addCleanup(self.qa.close)
        self.qa.executescript('''
            CREATE TABLE eventos_ia_qa(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,value TEXT);
            CREATE TABLE other_app(id INTEGER PRIMARY KEY AUTOINCREMENT,value TEXT);
            CREATE TABLE auditorias_panda(id INTEGER PRIMARY KEY,value TEXT);
            INSERT INTO eventos_ia_qa(run_id,value) VALUES ('old','retained');
            INSERT INTO auditorias_panda VALUES (1,'retained');
        ''')
        self.qa.commit()
        self.run_id='current'

    def history(self,counts):
        for index,values in enumerate(counts):
            run='history_'+str(index)
            self.db.execute('INSERT INTO farm_preflight_runs '
                '(id,run_id,stage,started_at,finished_at,decision,synthetic) '
                'VALUES (?,?,3,?,?,?,0)',(run,run,'start','finish','proceed'))
            self.db.execute('INSERT INTO farm_preflight_verdicts '
                '(run_id,"constraint",status,reason,counters_json) VALUES (?,?,?,?,?)',
                (run,'C5','WARN','fixture','{}'))
            self.db.execute('INSERT INTO farm_stage_metrics '
                '(run_id,stage,captcha_count,softblock_count,logout_count,recorded_at) '
                'VALUES (?,3,?,?,?,?)',(run,*values,'now'))
        self.db.commit()

    def insert_current(self,qa=False,owner=None):
        if qa:
            for _ in range(3):
                self.qa.execute('INSERT INTO eventos_ia_qa(run_id,value) VALUES (?,?)',
                                (owner or self.run_id,'new'))
            self.qa.commit()
        else:
            for index in range(3):
                self.db.execute('INSERT INTO auditorias_panda VALUES (?,1,?,?)',
                                (owner or self.run_id,'p'+str(index+1).zfill(2),'new'))
            self.db.commit()

    def report(self,before,qa=False,mode='physical_run'):
        database='telemetry_qa.db' if qa else 'telemetria_panda.db'
        return compare(before,snapshot(self.qa_path if qa else self.path),self.run_id,
            mode=mode,database=database,
            expected_writes=declare_run_writes(before,database,self.run_id,['p01','p02','p03'])
                if mode=='physical_run' else None)

    def test_c5_nulls_when_inspection_omitted(self):
        self.history([(None,None,None)])
        result=asyncio.run(farm_preflight.evaluate_c5_real([],FarmPolicy(),{},self.db))
        self.assertEqual(result.status,'WARN')
        self.assertEqual(result.counters['samples'],0)
        self.assertEqual(result.reason,
            'C5 DATOS_INCOMPLETOS | alternativa: recoger metricas reales suficientes de la etapa')

    def test_farm_metrics_written_during_native_run_with_nulls(self):
        import main_panda_masivo as main
        from tests.test_panda_massive_cli_integration import combined_rig
        with combined_rig(self.root/'complete') as rig:
            self.assertEqual(asyncio.run(main.main_async(rig.args)),0)
            with closing(sqlite3.connect(rig.args.db)) as db:
                rows=db.execute('SELECT m.stage,m.captcha_count,m.softblock_count,m.logout_count '
                    'FROM farm_stage_metrics m JOIN farm_preflight_runs r ON m.run_id=r.run_id').fetchall()
            self.assertEqual(rows,[(3,None,None,None)])
            self.assertEqual(rig.events[-1],'native')

    def test_farm_metrics_not_written_for_cancelled_run(self):
        import main_panda_masivo as main
        from tests.test_panda_massive_cli_integration import combined_rig
        with combined_rig(self.root/'cancelled') as rig:
            rig.cancel=True
            self.assertEqual(asyncio.run(main.main_async(rig.args)),130)
            with closing(sqlite3.connect(rig.args.db)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM farm_stage_metrics').fetchone()[0],0)

    def test_expected_writes_declared_for_auditorias_and_eventos_ia_qa(self):
        self.history([(0,0,0)])
        for qa in (False,True):
            before=snapshot(self.qa_path if qa else self.path)
            self.insert_current(qa=qa)
            report=self.report(before,qa=qa)
            table='eventos_ia_qa' if qa else 'auditorias_panda'
            self.assertEqual(report['status'],'PASS')
            self.assertEqual(report['expected_writes'][table]['INSERT'],3)
            self.assertEqual(report['observed_writes'][table]['INSERT'],3)
            self.assertEqual(len(report['observed_writes'][table]['keys']),3)
            self.assertTrue(all(len(key)==64 for key in report['observed_writes'][table]['keys']))
            declared={table:{'INSERT':3,'UPDATE':0,'DELETE':0,'keys':['0'*64,'1'*64,'2'*64]}}
            self.assertEqual(compare(before,snapshot(self.qa_path if qa else self.path),self.run_id,
                mode='physical_run',database='telemetry_qa.db' if qa else 'telemetria_panda.db',
                expected_writes=declared)['status'],'FAIL')
            self.assertEqual(compare(before,snapshot(self.qa_path if qa else self.path),self.run_id,
                mode='outside_run',database='telemetry_qa.db' if qa else 'telemetria_panda.db')['status'],'FAIL')
        import main_panda_masivo as main
        from tests.test_panda_massive_cli_integration import combined_rig
        with combined_rig(self.root/'declared') as rig:
            self.assertEqual(asyncio.run(main.main_async(rig.args)),0)
            reports=list((self.root/'declared'/'runs').glob('native_run_*.json'))
            self.assertEqual(len(reports),1)
            evidence=json.loads(reports[0].read_text(encoding='ascii'))
            for database,table in (('telemetria_panda.db','auditorias_panda'),
                                   ('telemetry_qa.db','eventos_ia_qa')):
                self.assertEqual(evidence['expected_writes'][database][table]['INSERT'],3)
                self.assertEqual(evidence['database_audits'][database]['observed_writes'][table]['INSERT'],3)

    def test_evidence_invariants_detects_extra_writes_outside_run_id(self):
        before=snapshot(self.path)
        self.insert_current(owner='foreign')
        report=self.report(before)
        self.assertEqual(report['status'],'FAIL')
        self.assertTrue(any(row['kind']=='foreign_run_insert' for row in report['write_violations']))

    def test_evidence_invariants_detects_row_modification_of_previous_run(self):
        before=snapshot(self.path)
        self.insert_current()
        self.db.execute("UPDATE auditorias_panda SET value='changed' WHERE run_id='old'")
        self.db.commit()
        report=self.report(before)
        self.assertEqual(report['status'],'FAIL')
        self.assertTrue(any(row['kind']=='previous_row_updated' for row in report['write_violations']))
        self.db.execute("DELETE FROM auditorias_panda WHERE run_id='old'")
        self.db.commit()
        report=self.report(before)
        self.assertEqual(report['status'],'FAIL')
        self.assertTrue(any(row['kind']=='previous_row_deleted' for row in report['write_violations']))

    def test_evidence_invariants_detects_undeclared_sqlite_sequence_advance(self):
        self.db.execute('CREATE TABLE other_app(id INTEGER PRIMARY KEY AUTOINCREMENT,value TEXT)')
        self.db.commit()
        before=snapshot(self.path)
        self.insert_current()
        self.db.execute("INSERT INTO other_app(value) VALUES ('unexpected')")
        self.db.commit()
        report=self.report(before)
        self.assertEqual(report['status'],'FAIL')
        self.assertTrue(report['sqlite_sequence_advance']['unexpected_changes'])

    def test_c5_pass_requires_complete_samples(self):
        self.history([(None,None,None),(0,0,0)])
        policy=replace(FarmPolicy(),min_metric_samples=2)
        result=asyncio.run(farm_preflight.evaluate_c5_real([],policy,{},self.db))
        self.assertEqual(result.status,'WARN')
        self.assertEqual(result.counters['samples'],1)
        self.history_additional_complete()
        result=asyncio.run(farm_preflight.evaluate_c5_real([],policy,{},self.db))
        self.assertEqual(result.status,'PASS')
        self.db.execute('UPDATE farm_stage_metrics SET captcha_count=1 WHERE captcha_count=0')
        self.db.commit()
        self.assertEqual(asyncio.run(farm_preflight.evaluate_c5_real([],policy,{},self.db)).status,'FAIL')

    def history_additional_complete(self):
        self.db.execute("INSERT INTO farm_stage_metrics (run_id,stage,captcha_count,softblock_count,"
                        "logout_count,recorded_at) VALUES ('history_1',3,0,0,0,'now')")
        self.db.commit()

    def test_telemetry_qa_hash_allowed_only_with_declared_run_id(self):
        before=snapshot(self.qa_path)
        self.insert_current(qa=True)
        report=self.report(before,qa=True)
        self.assertEqual(report['status'],'PASS')
        self.assertNotEqual(report['file_hash_before'],report['file_hash_after'])
        self.assertTrue(report['tables_unchanged_hashes'])
        unchanged=snapshot(self.qa_path)
        self.assertEqual(self.report(unchanged,qa=True)['status'],'FAIL')

    def test_telemetry_qa_hash_denied_outside_run(self):
        before=snapshot(self.qa_path)
        self.insert_current(qa=True)
        self.assertEqual(self.report(before,qa=True,mode='outside_run')['status'],'FAIL')

    def test_telemetry_qa_row_modification_denied(self):
        before=snapshot(self.qa_path)
        self.insert_current(qa=True)
        self.qa.execute("UPDATE eventos_ia_qa SET value='changed' WHERE run_id='old'")
        self.qa.commit()
        self.assertEqual(self.report(before,qa=True)['status'],'FAIL')

    def test_telemetry_qa_extra_table_denied(self):
        before=snapshot(self.qa_path)
        self.insert_current(qa=True)
        self.qa.execute("UPDATE auditorias_panda SET value='changed' WHERE id=1")
        self.qa.commit()
        self.assertEqual(self.report(before,qa=True)['status'],'FAIL')

    def test_telemetry_qa_sequence_denied_if_not_eventos_ia_qa(self):
        before=snapshot(self.qa_path)
        self.insert_current(qa=True)
        self.qa.execute("INSERT INTO other_app(value) VALUES ('unexpected')")
        self.qa.commit()
        report=self.report(before,qa=True)
        self.assertEqual(report['status'],'FAIL')
        self.assertEqual(report['sqlite_sequence_advance']['unexpected_changes'][0]['name'],'other_app')

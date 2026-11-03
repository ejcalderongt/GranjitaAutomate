import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import main_panda_masivo as m
from config.farm_policy import FarmPolicy
from config.farm_preflight import migrate


class FarmRealCLITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.db_path = self.root/'history.db'
        db = sqlite3.connect(self.db_path)
        try:
            migrate(db)
            db.execute('INSERT INTO farm_preflight_runs VALUES (?,?,?,?,?,?,?)', ('history', 'history', 3, 'start', 'finish', 'proceed', 0))
            db.execute('INSERT INTO farm_preflight_verdicts (run_id,"constraint",status) VALUES (?,?,?)', ('history', 'C5', 'PASS'))
            db.execute('INSERT INTO farm_stage_metrics (run_id,stage,captcha_count,softblock_count,logout_count) VALUES (?,?,?,?,?)', ('history', 3, 0, 0, 0))
            db.commit()
        finally:
            db.close()
        self.manager = SimpleNamespace(_panda_country='ES', contar_salidas_distintas=AsyncMock(return_value=dict(distinct=3,total=3,errors=0,timeouts=0)))
        self.ctx = {'synthetic': False, 'real_connectors_ready': True, 'devices': ['p01','p02','p03'],
            'integrity_probe': AsyncMock(return_value=dict(root_detected=False,emulator_detected=False,automation_detected=False,play_integrity=True)),
            'identity_probe': AsyncMock(return_value=dict(sim_country='es',locale='es_ES',timezone='Europe/Madrid')),
            'proxy_preflight_verified': True, 'proxy_manager': self.manager,
            'c3': {d: {'hold_seconds': 8} for d in ('p01','p02','p03')}}

    def invoke(self):
        with patch.object(m, 'ROOT', self.root), patch.object(m, 'DB_PATH', self.db_path), \
                patch.object(m, 'load_farm_policy', return_value=FarmPolicy(country='ES')), \
                patch.object(m, 'ejecutar_preflight_proxy_solo', new=AsyncMock(return_value=0)) as proxy, \
                patch.object(m.ProxyManager, 'desde_panda', return_value=self.manager), \
                patch.object(m, 'build_real_context', new=AsyncMock(return_value=self.ctx)) as build, \
                patch.object(m, 'load_synthetic_fixture') as fixture, \
                patch.object(m, 'Database') as native_db, patch.object(m, 'PandaClient') as panda, \
                patch('sys.argv', ['main_panda_masivo.py','--preflight-farm','--preflight-proxy']):
            code = m.main()
            proxy.assert_awaited_once()
            build.assert_awaited_once()
            for stub in (fixture, native_db, panda):
                stub.assert_not_called()
        report = json.loads(next((self.root/'runs').glob('*.json')).read_text())
        self.assertFalse(report['synthetic'])
        return code, report

    def test_pass_and_adapter_evidence(self):
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report['decision'], 'proceed')
        self.assertEqual(len(report['adapters']), 5)
        self.assertTrue(all(value['status']=='PASS' for value in report['adapters'].values()))

    def test_objective_fail(self):
        self.ctx['integrity_probe'] = AsyncMock(return_value={'root_detected': True})
        code, report = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(report['decision'], 'abort')

    def test_only_missing_integrity_warns(self):
        self.ctx['integrity_probe'] = AsyncMock(return_value=dict(root_detected=False,emulator_detected=False,automation_detected=False,play_integrity=None))
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report['decision'], 'proceed_with_warnings')
        self.assertEqual([v['constraint'] for v in report['verdicts'] if v['status']=='WARN'], ['C1'])

    def test_cancelled_run_has_empty_verdicts(self):
        self.ctx['integrity_probe'] = AsyncMock(side_effect=asyncio.CancelledError())
        code, report = self.invoke()
        self.assertEqual(code, 130)
        self.assertTrue(report['cancelled'])
        self.assertEqual(report['verdicts'], [])

    def test_legacy_flow_does_not_construct_real_adapters(self):
        args = SimpleNamespace(preflight_farm=False,preflight_proxy=False,execute_read_only=False,
                               concurrency=1,cycles=1,hold_seconds=8,expected_count=3,rpm=30,inventory='fixture')
        with patch.object(m, 'cargar_placas_activas_desde_csv', side_effect=RuntimeError('sentinel')), \
                patch.object(m, 'load_farm_policy') as policy, patch.object(m, 'build_real_context') as build, \
                patch.object(m, 'load_synthetic_fixture') as fixture:
            with self.assertRaisesRegex(RuntimeError, '^sentinel$'):
                asyncio.run(m.main_async(args))
            for stub in (policy,build,fixture):
                stub.assert_not_called()

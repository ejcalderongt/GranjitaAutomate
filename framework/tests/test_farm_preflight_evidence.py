import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from config import farm_preflight as f
from config.farm_policy import FarmPolicy


class DiagnosticEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def base_verdicts(self):
        ctx = f.load_synthetic_fixture(Path(__file__).parent/'fixtures/farm_stage3.json')
        ctx['run_id'] = 'fixture'
        db = sqlite3.connect(':memory:')
        try:
            return await f.run_farm_preflight(ctx['devices'], FarmPolicy(), ctx, db)
        finally:
            db.close()

    async def test_synthetic_evidence_contains_typed_fields_without_inventing_observations(self):
        verdicts = await self.base_verdicts()
        with tempfile.TemporaryDirectory() as folder:
            path = f.write_evidence(Path(folder), 'fixture', FarmPolicy(), verdicts, 0,
                                    ctx={'synthetic': True, 'private': 'PRIVATE_SENTINEL'})
            text = path.read_text()
            report = json.loads(text)
        self.assertTrue(report['synthetic'])
        self.assertEqual(report['decision'], 'proceed')
        self.assertEqual(report['diagnostic_fields_available'], {'C1':False,'C2':False,'C4':False})
        counters = {v['constraint']:v['counters'] for v in report['verdicts']}
        self.assertTrue(set(f.C1_DIAGNOSTIC_KEYS) <= set(counters['C1']))
        self.assertTrue(set(f.C2_DIAGNOSTIC_KEYS) <= set(counters['C2']))
        self.assertFalse(counters['C4']['data_available'])
        self.assertNotIn('PRIVATE_SENTINEL', text)
        self.assertNotIn('es_ES', text)

    async def test_unavailable_and_available_error_details_roundtrip(self):
        original = await self.base_verdicts()
        result = dict(distinct=1,total=2,errors=1,timeouts=0)
        attempts = [dict(code='success',new_exit=True,latency_ms=0),dict(code='json_invalid',new_exit=False,latency_ms=2)]
        for details, available in ((None,False),(attempts,True)):
            counters = {**result, **f.c4_diagnostics(result, details)}
            item = f.ConstraintVerdict('C4','FAIL','C4 DATOS_NO_CUMPLEN | alternativa: revisar fixture',counters)
            verdicts = [*original[:3],item,original[4]]
            with tempfile.TemporaryDirectory() as folder:
                path = f.write_evidence(Path(folder),'fixture',FarmPolicy(),verdicts,2,ctx={'synthetic':False})
                report = json.loads(path.read_text())
            self.assertFalse(report['synthetic'])
            observed = report['verdicts'][3]['counters']
            self.assertEqual(observed['errors'],1)
            self.assertIs(observed['data_available'],available)
            self.assertEqual(sum(observed['errors_by_kind'].values()),int(available))

    async def test_decide_is_independent_of_diagnostic_counters(self):
        original = await self.base_verdicts()
        for status in ('PASS','WARN','FAIL'):
            base = [replace(original[0],status=status),*original[1:]]
            enriched = [replace(v,counters={**f.diagnostic_defaults(v.constraint,v.counters),**v.counters}) for v in base]
            for policy in (FarmPolicy(),FarmPolicy(abort_on_warn=True),FarmPolicy(abort_on_fail=False)):
                self.assertEqual(f.decide(base,policy),f.decide(enriched,policy))

    async def test_no_farm_flag_keeps_policy_and_adapters_unused(self):
        import main_panda_masivo as m
        args = SimpleNamespace(preflight_farm=False,preflight_proxy=False,execute_read_only=False,
            concurrency=1,cycles=1,hold_seconds=8,expected_count=3,rpm=30,inventory='fixture')
        with patch.object(m,'cargar_placas_activas_desde_csv',side_effect=RuntimeError('sentinel')), \
                patch.object(m,'load_farm_policy') as policy, patch.object(m,'build_real_context') as real, \
                patch.object(m,'load_synthetic_fixture') as fixture:
            with self.assertRaisesRegex(RuntimeError,'^sentinel$'):
                await m.main_async(args)
            for stub in (policy,real,fixture):
                stub.assert_not_called()

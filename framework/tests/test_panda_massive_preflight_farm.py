import asyncio
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import main_panda_masivo as m
from config.farm_policy import FarmPolicy, EXIT_MESSAGES
from config.farm_preflight import load_synthetic_fixture


FIXTURE = Path(__file__).parent/'fixtures/farm_stage3.json'


class FarmCLITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.ctx = load_synthetic_fixture(FIXTURE)

    def call(self, ctx=None, policy=None, extra=()):
        with ExitStack() as stack:
            stack.enter_context(patch.object(m, 'ROOT', self.root))
            stack.enter_context(patch.object(m, 'DB_PATH', self.root/'qa.db'))
            stack.enter_context(patch.object(m, 'load_farm_policy', return_value=policy or FarmPolicy()))
            stack.enter_context(patch.object(m, 'load_synthetic_fixture', return_value=ctx or self.ctx))
            stack.enter_context(patch('sys.argv', ['main_panda_masivo.py', '--preflight-farm', *extra]))
            for name in ('Database', 'PandaClient', 'cargar_placas_activas_desde_csv', 'bloquear_granja'):
                stub = stack.enter_context(patch.object(m, name, side_effect=AssertionError('Native path called')))
            stack.enter_context(patch.object(m, 'obtener_inventario', new=AsyncMock(side_effect=AssertionError('Native path called'))))
            with self.assertLogs(m.log, level='INFO') as logs:
                code = m.main()
        reports = [json.loads(p.read_text()) for p in (self.root/'runs').glob('farm_preflight_*.json')]
        return code, reports[-1], logs.output

    def test_cli_pass(self):
        # Success has no required log, so capture main without assertLogs.
        with patch.object(m.log, 'info'):
            with patch.object(m, 'ROOT', self.root), patch.object(m, 'DB_PATH', self.root/'qa.db'), \
                    patch.object(m, 'load_farm_policy', return_value=FarmPolicy()), \
                    patch.object(m, 'load_synthetic_fixture', return_value=self.ctx), \
                    patch.object(m, 'Database') as db, patch.object(m, 'PandaClient') as panda, \
                    patch('sys.argv', ['main_panda_masivo.py', '--preflight-farm']):
                self.assertEqual(m.main(), 0)
                db.assert_not_called()
                panda.assert_not_called()
        report = json.loads(next((self.root/'runs').glob('*.json')).read_text())
        self.assertTrue(report['synthetic'])
        self.assertEqual(report['decision'], 'proceed')

    def test_cli_fail_prints_reasons(self):
        self.ctx['c1']['p01']['authorized'] = False
        code, report, logs = self.call()
        self.assertEqual(code, 2)
        self.assertEqual(report['decision'], 'abort')
        self.assertTrue(any('C1 DATOS_NO_CUMPLEN | alternativa:' in line for line in logs))
        self.assertTrue(any(EXIT_MESSAGES[2] in line for line in logs))

    def test_cli_warn_abort_prints_reasons(self):
        del self.ctx['c2']['p01']
        code, report, logs = self.call(policy=FarmPolicy(abort_on_warn=True))
        self.assertEqual(code, 3)
        self.assertEqual(report['verdicts'][1]['status'], 'WARN')
        self.assertTrue(any(EXIT_MESSAGES[3] in line for line in logs))

    def test_incompatible_execution_flags_fail_before_proxy(self):
        with patch.object(m, 'ejecutar_preflight_proxy_solo', new=AsyncMock()) as proxy:
            code, _, _ = self.call(extra=('--execute-read-only', '--preflight-proxy'))
            self.assertEqual(code, 1)
            proxy.assert_not_called()

    def test_wrapper_cancellation_and_empty_evidence(self):
        args = SimpleNamespace(concurrency=1, cycles=1, hold_seconds=8, expected_count=3,
                               preflight_proxy=False, execute_read_only=False, db=self.root/'qa.db')
        for error in (KeyboardInterrupt(), asyncio.CancelledError()):
            with patch.object(m, 'ROOT', self.root), patch.object(m, 'load_farm_policy', return_value=FarmPolicy()), \
                    patch.object(m, 'load_synthetic_fixture', side_effect=error):
                self.assertEqual(asyncio.run(m.ejecutar_preflight_farm_solo(args)), 130)
        for path in (self.root/'runs').glob('*.json'):
            report = json.loads(path.read_text())
            self.assertTrue(report['cancelled'])
            self.assertEqual(report['verdicts'], [])

    def test_main_cancel_does_not_access_exit_table(self):
        table = Mock()
        table.__contains__ = Mock(side_effect=AssertionError('Exit table accessed'))
        with patch.object(m, 'EXIT_MESSAGES', table), patch.object(m, 'main_async', new=AsyncMock(return_value=130)), \
                patch('sys.argv', ['main_panda_masivo.py']), self.assertLogs(m.log, level='INFO') as logs:
            self.assertEqual(m.main(), 130)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('Proceso cancelado Recursos liberados', logs.output[0])

    def test_main_messages_and_unknown_return(self):
        for code in (1, 2, 3, 4, 99):
            with patch.object(m, 'main_async', new=AsyncMock(return_value=code)), \
                    patch('sys.argv', ['main_panda_masivo.py']), self.assertLogs(m.log, level='INFO') as logs:
                self.assertEqual(m.main(), 1 if code == 99 else code)
            self.assertTrue(any(EXIT_MESSAGES[1 if code == 99 else code] in line for line in logs.output))
            if code == 99:
                self.assertTrue(any('Codigo de salida no reconocido' in line for line in logs.output))

    def test_main_raised_cancellation_preserved(self):
        for error in (KeyboardInterrupt(), asyncio.CancelledError()):
            with patch.object(m, 'main_async', new=AsyncMock(side_effect=error)), \
                    patch('sys.argv', ['main_panda_masivo.py']), self.assertLogs(m.log, level='INFO') as logs:
                self.assertEqual(m.main(), 130)
            self.assertTrue(any('Proceso cancelado Recursos liberados' in line for line in logs.output))

    def test_no_farm_flag_preserves_native_flow_without_policy_or_migration(self):
        args = SimpleNamespace(preflight_farm=False, preflight_proxy=False, execute_read_only=False,
            concurrency=1, cycles=1, hold_seconds=8, expected_count=3, rpm=30,
            inventory=self.root/'absent.csv', panda_url='synthetic', db=self.root/'absent.db')
        plates = [{'panda_id': d, 'serial': 'serial-'+d} for d in self.ctx['devices']]
        live = [{'numero_panda': p['panda_id'], 'serial_fisico': p['serial'], 'estado': 'vinculado'} for p in plates]
        client = Mock(preparar=AsyncMock(return_value={}))
        with patch.object(m, 'cargar_placas_activas_desde_csv', return_value=plates), \
                patch.object(m, 'Database') as db, patch.object(m, 'obtener_inventario', new=AsyncMock(return_value=(None, live, None))) as inv, \
                patch.object(m, 'PandaClient', return_value=client), patch.object(m, 'load_farm_policy') as policy, \
                patch.object(m, 'load_synthetic_fixture') as fixture, patch.object(m, 'run_farm_preflight') as farm, \
                patch.object(m, 'load_project_environment') as env:
            self.assertEqual(asyncio.run(m.main_async(args)), 0)
            db.assert_called_once()
            inv.assert_awaited_once()
            client.preparar.assert_awaited_once()
            for stub in (policy, fixture, farm, env):
                stub.assert_not_called()
        self.assertFalse(args.db.exists())

    def test_proxy_only_early_return_unchanged(self):
        args = SimpleNamespace(preflight_proxy=True, execute_read_only=False)
        with patch.object(m, 'ejecutar_preflight_proxy_solo', new=AsyncMock(return_value=0)) as proxy, \
                patch.object(m, 'validar_parametros') as validate, patch.object(m, 'load_farm_policy') as policy:
            self.assertEqual(asyncio.run(m.main_async(args)), 0)
            proxy.assert_awaited_once()
            validate.assert_not_called()
            policy.assert_not_called()

    def test_combined_flags_order_and_proxy_failure_stop(self):
        events = []
        args = SimpleNamespace(preflight_farm=True, preflight_proxy=True, execute_read_only=False,
                               db=self.root/'qa.db')
        async def proxy(_):
            events.append('proxy')
            return 4
        with patch.object(m, 'ROOT', self.root), patch.object(m, 'validar_parametros', side_effect=lambda _: events.append('validate')), \
                patch.object(m, 'ejecutar_preflight_proxy_solo', new=proxy), patch.object(m, 'load_farm_policy') as policy:
            self.assertEqual(asyncio.run(m.main_async(args)), 4)
            policy.assert_not_called()
        self.assertEqual(events, ['validate', 'proxy'])

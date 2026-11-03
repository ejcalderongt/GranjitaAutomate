import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.farm_policy import FarmPolicy, load_farm_policy, stage_limits, EXIT_MESSAGES, POLICY_VARIABLES
from core.project_env import load_project_environment


class FarmPolicyTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            policy = load_farm_policy(Path(folder)/'absent')
        self.assertEqual(policy, FarmPolicy())

    def test_ranges(self):
        for values in ({'stage': 4}, {'hold_min': 22}, {'hold_max': 23},
                       {'hold_min': float('nan')}, {'abort_on_fail': 1}, {'country': 'invalid'}):
            with self.subTest(values=list(values)):
                with self.assertRaisesRegex(ValueError, '^Politica de granja invalida$'):
                    FarmPolicy(**values)

    @patch.dict(os.environ, {}, clear=True)
    def test_load_explicit_file_and_reject_bad_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'.env'
            path.write_text('PANDA_POLICY_STAGE=10\nPANDA_POLICY_ABORT_ON_WARN=true\n')
            self.assertEqual(load_farm_policy(path).stage, 10)
            self.assertTrue(load_farm_policy(path).abort_on_warn)
            for name, value in (('PANDA_POLICY_STAGE', 'bad'), ('PANDA_POLICY_ABORT_ON_WARN', 'maybe')):
                with patch.dict(os.environ, {name: value}):
                    with self.assertRaisesRegex(ValueError, '^Politica de granja invalida$'):
                        load_farm_policy(path)

    def test_exit_messages_exact_and_immutable(self):
        self.assertEqual(dict(EXIT_MESSAGES), {
            0: 'Lote finalizado sin abortos de politica de granja',
            1: 'Configuracion invalida: revisa las variables PANDA_POLICY_* y vuelve a intentar',
            2: 'Lote abortado por constraint en FAIL: revisa las razones mostradas y corrige antes de reintentar',
            3: 'Lote abortado por constraint en WARN con ABORT_ON_WARN activo: desactiva esa bandera o corrige el WARN',
            4: 'Lote abortado antes de tocar Panda o Android por preflight fallido: revisa el preflight de proxy y de granja',
        })
        with self.assertRaises(TypeError):
            EXIT_MESSAGES[0] = 'changed'

    def test_stage_limits(self):
        for stage in (3, 10, 34):
            limits = stage_limits(FarmPolicy(stage=stage))
            self.assertEqual(limits['device_limit'], stage)
            self.assertLess(limits['hold_min'], limits['hold_max'])


def allowlist_test(name):
    @patch.dict(os.environ, {}, clear=True)
    def test(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'.env'
            path.write_text(name+'=sample\nUNRELATED=ignored\n', encoding='ascii')
            load_project_environment(path)
            self.assertEqual(os.environ[name], 'sample')
            self.assertNotIn('UNRELATED', os.environ)
            with patch.dict(os.environ, {name: 'existing'}):
                load_project_environment(path)
                self.assertEqual(os.environ[name], 'existing')
    return test


for variable in POLICY_VARIABLES:
    setattr(FarmPolicyTests, 'test_allowlist_'+variable.lower(), allowlist_test(variable))

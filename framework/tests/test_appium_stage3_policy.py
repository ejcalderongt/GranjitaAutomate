import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import farm_preflight as farm
from config.farm_policy import FarmPolicy, load_farm_policy, stage_limits


class AppiumStage3PolicyTests(unittest.TestCase):
    def check_packages(self, packages):
        async def probe(device):
            return {'root_detected': False, 'emulator_detected': False,
                    'automation_detected': True, 'play_integrity': None,
                    'automation_packages': packages}
        return asyncio.run(farm.evaluate_c1_real(
            ['p01', 'p02', 'p03'], FarmPolicy(), {'integrity_probe': probe}))

    def test_c1_real_ignores_appium_packages(self):
        verdict = self.check_packages(['io.appium.uiautomator2.server',
                                       'io.appium.uiautomator2.server.test'])
        self.assertEqual(verdict.status, 'WARN')
        self.assertEqual(verdict.counters['negative_automation_apps'], 0)
        self.assertEqual(verdict.counters['appium_present'], 3)
        self.assertEqual(verdict.counters['appium_ignored'], 3)

    def test_other_automation_still_fails(self):
        for package in ('com.genfarmer.uiautomator', 'com.genymobile.scrcpy'):
            with self.subTest(package=package):
                verdict = self.check_packages(['io.appium.uiautomator2.server', package])
                self.assertEqual(verdict.status, 'FAIL')
                self.assertEqual(verdict.counters['negative_automation_apps'], 3)

    def test_magisk_warns_without_hiding_other_packages(self):
        magisk = 'com.topjohnwu.magisk'
        warning = self.check_packages([magisk])
        self.assertEqual(warning.status, 'WARN')
        self.assertEqual(warning.counters['warning_magisk_package'], 3)
        self.assertEqual(warning.counters['negative_automation_apps'], 0)
        self.assertEqual(self.check_packages([magisk, 'com.genfarmer.uiautomator']).status, 'FAIL')

    @patch.dict(os.environ, {}, clear=True)
    def test_stage3_c4_min_1(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'empty.env'
            for stage, minimum in ((3, 1), (10, 3), (34, 5)):
                path.write_text('PANDA_POLICY_STAGE=' + str(stage) + '\n', encoding='ascii')
                with patch.dict(os.environ, {}, clear=True):
                    policy = load_farm_policy(path)
                self.assertEqual(policy.proxy_min_distinct_exit_ips, minimum)
                self.assertEqual(FarmPolicy(stage=stage).proxy_min_distinct_exit_ips, minimum)
                self.assertEqual(stage_limits(policy)['proxy_min_distinct_exit_ips'], minimum)

    def test_explicit_minimum_is_preserved(self):
        self.assertEqual(FarmPolicy(stage=3, proxy_min_distinct_exit_ips=3).proxy_min_distinct_exit_ips, 3)

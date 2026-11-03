import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from config import farm_preflight as f
from config.farm_policy import FarmPolicy


class C1RealTests(unittest.IsolatedAsyncioTestCase):
    async def test_pass_warn_and_objective_fail(self):
        good = dict(root_detected=False, emulator_detected=False, automation_detected=False, play_integrity=True)
        devices = ['a', 'b', 'c']
        for row, status in ((good, 'PASS'), ({}, 'WARN'), ({**good, 'root_detected': True}, 'FAIL'),
                            ({**good, 'emulator_detected': True}, 'FAIL'),
                            ({**good, 'automation_detected': True}, 'FAIL'),
                            ({**good, 'play_integrity': False}, 'FAIL')):
            result = await f.evaluate_c1_real(devices, FarmPolicy(), {'integrity_probe': AsyncMock(return_value=row)})
            self.assertEqual(result.status, status)
            self.assertEqual(result.counters['checked'], 3)
            self.assertLessEqual(len(result.reason), 200)

    async def test_missing_channel_exception_and_timeout(self):
        for ctx in ({}, {'integrity_probe': AsyncMock(side_effect=RuntimeError())}):
            result = await f.evaluate_c1_real(['a'], FarmPolicy(), ctx)
            self.assertEqual(result.status, 'WARN')
        async def slow(device):
            await asyncio.sleep(1)
        with patch.object(f, 'DEVICE_PROBE_TIMEOUT_SECONDS', 0.001):
            result = await f.evaluate_c1_real(['a'], FarmPolicy(), {'integrity_probe': slow})
        self.assertEqual(result.status, 'WARN')

    async def test_cancellation_is_not_a_warning(self):
        with self.assertRaises(asyncio.CancelledError):
            await f.evaluate_c1_real(['a'], FarmPolicy(), {'integrity_probe': AsyncMock(side_effect=asyncio.CancelledError())})

    async def test_diagnostic_categories_and_missing_authorization(self):
        row = dict(root_detected=True, emulator_detected=True, automation_detected=True,
                   play_integrity=False, authorized=None, connected='unknown')
        item = await f.evaluate_c1_real(['a','b','c'], FarmPolicy(), {'integrity_probe': AsyncMock(return_value=row)})
        self.assertEqual(item.status, 'FAIL')
        for key in ('negative_uid_privileged','negative_emulator_hint','negative_automation_apps',
                    'integrity_probe_available','missing_authorized','missing_connected'):
            self.assertEqual(item.counters[key], 3)
        self.assertEqual(item.counters['integrity_probe_errors'], 0)
        self.assertEqual(item.counters['skipped'], 0)

    async def test_probe_availability_errors_and_skipped(self):
        contexts = ({}, {'integrity_probe': AsyncMock(side_effect=RuntimeError())},
                    {'integrity_probe': AsyncMock(return_value={})})
        for index, ctx in enumerate(contexts):
            item = await f.evaluate_c1_real(['a'], FarmPolicy(), ctx)
            self.assertEqual(item.counters['integrity_probe_available'], 0)
            self.assertEqual(item.counters['integrity_probe_errors'], 1)
            self.assertEqual(item.counters['skipped'], int(index == 0))
        row = dict(root_detected=False,emulator_detected=False,automation_detected=False,
                   play_integrity=True,authorized=True,connected=True)
        item = await f.evaluate_c1_real(['a','b','c'], FarmPolicy(), {'integrity_probe': AsyncMock(return_value=row)})
        self.assertEqual(item.status, 'PASS')
        self.assertEqual(item.counters['missing_authorized'], 0)
        self.assertEqual(item.counters['missing_connected'], 0)

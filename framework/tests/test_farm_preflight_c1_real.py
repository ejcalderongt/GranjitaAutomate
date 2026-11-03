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

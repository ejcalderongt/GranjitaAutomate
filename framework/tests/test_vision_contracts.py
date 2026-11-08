import asyncio
import base64
import json
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from core.vision_contracts import VisionRequest, VisionResponse, VisionError, VisionAgent, RateGate

IMAGE = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
VALID = json.dumps(dict(captcha=False, softblock=None, logged_out=False, summary='Visible feed'))
def result(text, finish='stop'):
    return NS(choices=[NS(finish_reason=finish, message=NS(content=text, refusal=None))])
def agent(*responses):
    create = AsyncMock(side_effect=list(responses))
    return VisionAgent(rpm=600000, client=NS(chat=NS(completions=NS(create=create)))), create

class VisionContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid(self):
        a, call = agent(result(VALID))
        self.assertIsInstance(await a.observe(VisionRequest(IMAGE, True)), VisionResponse)
        self.assertEqual(call.await_count, 1)
    async def test_invalid_then_valid(self):
        a, call = agent(result('{'), result(VALID))
        self.assertIsInstance(await a.observe(VisionRequest(IMAGE, True)), VisionResponse)
        self.assertEqual(call.await_count, 2)
    async def test_invalid_twice(self):
        a, call = agent(result('oops'), result('oops'))
        self.assertEqual(await a.observe(VisionRequest(IMAGE, True)), VisionError('invalid_response', 2))
    async def test_truncated(self):
        a, _ = agent(result(VALID, 'length'), result(VALID, 'length'))
        self.assertEqual((await a.observe(VisionRequest(IMAGE, True))).code, 'invalid_response')
    async def test_extra_keys(self):
        a, _ = agent(result(VALID[:-1]+',"extra":1}'), result(VALID[:-1]+',"extra":1}'))
        self.assertIsInstance(await a.observe(VisionRequest(IMAGE, True)), VisionError)
    async def test_duplicate_keys(self):
        a, _ = agent(result('{"captcha":true,"captcha":false}'), result('{}'))
        self.assertIsInstance(await a.observe(VisionRequest(IMAGE, True)), VisionError)
    async def test_flag_type(self):
        with self.assertRaises(ValueError): VisionResponse(1, False, False, '')
    async def test_bad_image(self):
        with self.assertRaises(ValueError): VisionRequest('https://example.test/a.png')
    async def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(await VisionAgent().observe(VisionRequest(IMAGE, True)), VisionError('missing_key'))
    async def test_authorization(self):
        a, call = agent()
        self.assertEqual(await a.observe(VisionRequest(IMAGE)), VisionError('unauthorized'))
        call.assert_not_called()
    async def test_api_error(self):
        a, call = agent(RuntimeError('secret'))
        self.assertEqual(await a.observe(VisionRequest(IMAGE, True)), VisionError('api_error', 1))
    async def test_cancel_propagates(self):
        a, _ = agent(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError): await a.observe(VisionRequest(IMAGE, True))
    async def test_limits(self):
        for value in (0, 6, True):
            with self.assertRaises(ValueError): VisionAgent(concurrency=value)
        for value in (0, float('inf'), True):
            with self.assertRaises(ValueError): RateGate(value)
    async def test_concurrency(self):
        active = peak = 0
        both = asyncio.Event()
        async def create(**kwargs):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            if active == 2:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=2)
            active -= 1
            return result(VALID)
        a = VisionAgent(rpm=600000, concurrency=2, client=NS(chat=NS(completions=NS(create=create))))
        results = await asyncio.gather(*(a.observe(VisionRequest(IMAGE, True)) for _ in range(6)))
        self.assertEqual(peak, 2)
        self.assertTrue(all(isinstance(r, VisionResponse) for r in results))
    async def test_gate_reserves_starts(self):
        gate = RateGate(6000)
        starts = []
        async def wait():
            await gate.wait(); starts.append(asyncio.get_running_loop().time())
        await asyncio.gather(*(wait() for _ in range(3)))
        self.assertTrue(all(b-a >= .008 for a, b in zip(starts, starts[1:])))

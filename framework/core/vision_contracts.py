"""Bounded observation service. No capture, device access or telemetry writes."""
import asyncio
import base64
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openai import AsyncOpenAI


@dataclass(frozen=True)
class VisionRequest:
    image_data: str
    upload_authorized: bool = False
    model: str = 'gpt-4o-mini'

    def __post_init__(self):
        if (type(self.upload_authorized) is not bool or self.model not in ('gpt-4o-mini', 'gpt-4o')
                or not isinstance(self.image_data, str) or len(self.image_data) > 8_000_000):
            raise ValueError('Invalid vision request')
        prefix = 'data:image/png;base64,'
        if not self.image_data.startswith(prefix):
            raise ValueError('PNG data URI required')
        raw = base64.b64decode(self.image_data[len(prefix):], validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid PNG')


@dataclass(frozen=True)
class VisionResponse:
    captcha: bool | None
    softblock: bool | None
    logged_out: bool | None
    summary: str

    def __post_init__(self):
        if any(v is not None and type(v) is not bool for v in
               (self.captcha, self.softblock, self.logged_out)):
            raise ValueError('Invalid observation flags')
        if not isinstance(self.summary, str) or len(self.summary) > 500:
            raise ValueError('Invalid summary')


@dataclass(frozen=True)
class VisionError:
    code: Literal['unauthorized', 'missing_key', 'invalid_response', 'api_error']
    attempts: int = 0

    def __post_init__(self):
        if self.code not in ('unauthorized', 'missing_key', 'invalid_response', 'api_error') or type(self.attempts) is not int or not 0 <= self.attempts <= 2:
            raise ValueError('Invalid vision error')


class RateGate:
    def __init__(self, rpm: float):
        if type(rpm) not in (int, float) or not math.isfinite(rpm) or rpm <= 0:
            raise ValueError('Invalid RPM')
        self.interval = 60 / rpm
        self.lock = asyncio.Lock()
        self.next_start = 0.0

    async def wait(self):
        async with self.lock:
            loop = asyncio.get_running_loop()
            while self.next_start > loop.time():
                await asyncio.sleep(self.next_start - loop.time())
            self.next_start = loop.time() + self.interval


class VisionAgent:
    def __init__(self, *, rpm=30, concurrency=1, client=None):
        if type(concurrency) is not int or not 1 <= concurrency <= 5:
            raise ValueError('Invalid concurrency')
        self.gate = RateGate(rpm)
        self.slots = asyncio.Semaphore(concurrency)
        self.client = client

    async def observe(self, request: VisionRequest) -> VisionResponse | VisionError:
        if not request.upload_authorized:
            return VisionError('unauthorized')
        if self.client is None and not os.getenv('OPENAI_API_KEY'):
            return VisionError('missing_key')
        if self.client is not None:
            return await self._observe(request, self.client)
        async with AsyncOpenAI(timeout=25, max_retries=0) as client:
            return await self._observe(request, client)

    async def _observe(self, request, client):
        prompt = (Path(__file__).parent / 'prompts/vision_system.txt').read_text(encoding='ascii')
        for attempt in range(1, 3):
            try:
                async with self.slots:
                    await self.gate.wait()
                    async with asyncio.timeout(25):
                        response = await client.chat.completions.create(
                            model=request.model, max_completion_tokens=300,
                            response_format={'type': 'json_object'},
                            messages=[{'role': 'system', 'content': prompt},
                                      {'role': 'user', 'content': [{'type': 'image_url',
                                       'image_url': {'url': request.image_data}}]}])
            except asyncio.CancelledError:
                raise
            except Exception:
                return VisionError('api_error', attempt)
            try:
                choice = response.choices[0]
                if choice.finish_reason != 'stop' or choice.message.refusal:
                    raise ValueError('Incomplete observation')
                def pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError('Duplicate key')
                        result[key] = value
                    return result
                data = json.loads(choice.message.content, object_pairs_hook=pairs)
                if not isinstance(data, dict) or set(data) != {'captcha', 'softblock', 'logged_out', 'summary'}:
                    raise ValueError('Invalid observation schema')
                return VisionResponse(**data)
            except (ValueError, TypeError, AttributeError, IndexError):
                if attempt == 2:
                    return VisionError('invalid_response', attempt)

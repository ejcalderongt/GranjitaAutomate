import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from core.vision_contract import EXAMPLE, VisibleUIReport, validate_response, verdict


class VisionContractV1Tests(unittest.TestCase):
    def test_null_is_rejected_without_conversion(self):
        for field in ('captcha', 'softblock', 'logged_out'):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    VisibleUIReport.model_validate({**EXAMPLE, field: None})

    def test_missing_or_zero_confidence_is_rejected(self):
        for value in (None, 0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    VisibleUIReport.model_validate({**EXAMPLE,
                        'confidence': {**EXAMPLE['confidence'], 'captcha': value}})

    def test_unevaluable_and_nonfeed_do_not_pass_as_clean(self):
        self.assertEqual(verdict(VisibleUIReport.model_validate(EXAMPLE)), 'PASS')
        self.assertEqual(verdict(VisibleUIReport.model_validate({**EXAMPLE, 'evaluable': False})),
                         'BLOQUEO_CONTRATO')
        self.assertEqual(verdict(VisibleUIReport.model_validate({**EXAMPLE, 'feed_visible': False})),
                         'BLOQUEO_PANTALLA')

    def test_incidents_never_pass_even_with_feed_visible(self):
        for field in ('captcha', 'softblock', 'logged_out'):
            with self.subTest(field=field):
                self.assertEqual(verdict(VisibleUIReport.model_validate({**EXAMPLE, field: True})),
                                 'BLOQUEO_REAL')

    def test_truncation_or_refusal_rejects_valid_looking_json(self):
        for reason, refusal in (('length', None), ('stop', 'refused')):
            with self.subTest(reason=reason, refusal=refusal):
                response = SimpleNamespace(choices=[SimpleNamespace(
                    finish_reason=reason, message=SimpleNamespace(
                        content=VisibleUIReport.model_validate(EXAMPLE).model_dump_json(), refusal=refusal))])
                with self.assertRaises(ValueError):
                    validate_response(response)


class VisionUsageLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_contract_keeps_raw_text_and_known_usage(self):
        from scripts import validar_vision_v1 as runner
        content = json.dumps({**EXAMPLE, 'captcha': None})
        raw = {'usage': {'prompt_tokens': 100, 'completion_tokens': 30,
                         'prompt_tokens_details': {'cached_tokens': 0}}}
        response = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason='stop',
                                     message=SimpleNamespace(content=content, refusal=None))],
            model_dump=lambda **kwargs: raw)
        api = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=AsyncMock(return_value=response))))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / 'image.png'
            image.write_bytes(b'synthetic-image')
            with patch.object(runner, 'ROOT', root):
                result = await runner.inspect(api, root, image, 'A2_i1', 'fewshot', phase='A')
            saved = json.loads((root / 'A2_i1.json').read_text())
            self.assertFalse(result['contract_valid'])
            self.assertTrue(saved['cost_confirmed'])
            self.assertGreater(saved['estimated_usd'], 0)
            self.assertEqual(saved['raw_text'], content)
            self.assertIsNone(json.loads(saved['raw_text'])['captcha'])

import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from core.ai_agent import analizar_contenido_tiktok_async, DecisionTikTok


SAFE = {'interactuar': False, 'dar_like': False, 'comentario': ''}


def sdk(result):
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        finish_reason='stop', message=SimpleNamespace(refusal=None, content=json.dumps(result)))]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


class AITextQATests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name)/'qa.db'

    async def call(self, client=None, **kwargs):
        return await analizar_contenido_tiktok_async(
            '<div>una receta<script>SECRET_SCRIPT</script><input value="SECRET_TOKEN"></div>',
            'receta de pan', client=client, db_path=self.db, run_id='qa-run', **kwargs)

    def rows(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute('SELECT * FROM eventos_ia_qa')]

    async def test_success_strict_schema_and_private_audit(self):
        expected = {'interactuar': True, 'dar_like': True, 'comentario': 'qué rico ese pan 😋'}
        client = sdk(expected)
        self.assertEqual(await self.call(client), expected)
        args = client.chat.completions.create.call_args.kwargs
        self.assertEqual(args['model'], 'gpt-4o-mini')
        self.assertTrue(args['response_format']['json_schema']['strict'])
        self.assertNotIn('SECRET', args['messages'][1]['content'])
        row, = self.rows()
        self.assertEqual((row['run_id'], row['estado'], row['api_llamada']), ('qa-run', 'éxito', 1))
        self.assertGreaterEqual(row['latencia_ms'], 0)
        self.assertNotIn(expected['comentario'], json.dumps(row))
        self.assertNotIn('receta', json.dumps(row))

    async def test_timeout_and_invalid_reply_are_safe_and_audited(self):
        client = sdk(SAFE)
        client.chat.completions.create.side_effect = TimeoutError('SECRET_ERROR')
        self.assertEqual(await self.call(client), SAFE)
        self.assertEqual(self.rows()[0]['error_codigo'], 'timeout')
        invalid = sdk({'interactuar': False, 'dar_like': True, 'comentario': 'hola'})
        self.assertEqual(await self.call(invalid), SAFE)
        self.assertEqual(self.rows()[-1]['estado'], 'fallo_api')
        self.assertNotIn('SECRET_ERROR', json.dumps(self.rows()))

    async def test_missing_key_does_not_call_sdk(self):
        with patch.dict(os.environ, {}, clear=True), patch('core.project_env.load_project_environment'), \
                patch('core.ai_agent.AsyncOpenAI') as factory:
            self.assertEqual(await self.call(), SAFE)
            factory.assert_not_called()
        row, = self.rows()
        self.assertEqual(row['error_codigo'], 'api_key_ausente')
        self.assertEqual(row['api_llamada'], 0)
        self.assertIsNone(row['latencia_ms'])

    async def test_owned_client_is_closed(self):
        client = sdk(SAFE)
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-not-a-key'}), \
                patch('core.project_env.load_project_environment'), \
                patch('core.ai_agent.AsyncOpenAI', return_value=manager):
            self.assertEqual(await self.call(), SAFE)
        manager.__aexit__.assert_awaited_once()

    async def test_cancellation_propagates_and_records(self):
        client = sdk(SAFE)
        entered = asyncio.Event()
        async def pending(**kwargs):
            entered.set()
            await asyncio.Future()
        client.chat.completions.create.side_effect = pending
        task = asyncio.create_task(self.call(client))
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.rows()[0]['estado'], 'cancelado')

    async def test_database_failure_blocks_api(self):
        client = sdk(SAFE)
        with patch('core.telemetry.inicializar_db_telemetria', side_effect=sqlite3.OperationalError):
            self.assertEqual(await self.call(client), SAFE)
        client.chat.completions.create.assert_not_awaited()

    async def test_refusal_and_truncated_reply(self):
        for reason, refusal in [('length', None), ('stop', 'refused')]:
            client = sdk(SAFE)
            reply = client.chat.completions.create.return_value.choices[0]
            reply.finish_reason, reply.message.refusal = reason, refusal
            self.assertEqual(await self.call(client), SAFE)

    def test_local_comment_constraints(self):
        for comment in ['MAYÚSCULAS', 'uno dos tres cuatro cinco seis siete ocho nueve', 'bien 😋 😋']:
            with self.assertRaises(ValueError):
                DecisionTikTok(interactuar=True, dar_like=True, comentario=comment)

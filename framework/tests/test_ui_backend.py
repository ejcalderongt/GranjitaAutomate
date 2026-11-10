import asyncio
from contextlib import closing
import json
from pathlib import Path
import tempfile
import sqlite3
import time
import unittest
from fastapi.testclient import TestClient
from core.device_aliases import ALIAS_DB, INVENTORY, seed_aliases
from ui.lab_api import create_app


class LabBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'runs').mkdir()
        self.client = TestClient(create_app(self.root), base_url='http://127.0.0.1')
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def evidence(self, **extra):
        data = {'decision': 'abort', 'synthetic': False,
                'verdicts': [{'constraint': 'C1', 'status': 'FAIL',
                              'reason': 'SECRET', 'counters': {'checked': 3, 'private': 'SECRET'}}], **extra}
        name = 'farm_preflight_test.json'
        (self.root / 'runs' / name).write_text(json.dumps(data), encoding='ascii')
        return name

    def test_status(self):
        data = self.client.get('/api/status').json()
        self.assertEqual(data['status'], 'idle')
        self.assertFalse(data['real_execution_authorized'])

    def test_status_joins_fixed_aliases_without_visual_numbers(self):
        source = self.root / INVENTORY
        source.parent.mkdir(parents=True)
        row = 'numero_panda,device_ref,alias,estado\n23,0123456789abcdef,Original,vinculado\n'
        source.write_text(row, encoding='ascii')
        seed_aliases(self.root)
        with closing(sqlite3.connect(self.root / ALIAS_DB)) as db, db:
            db.execute('UPDATE device_aliases SET alias_personalizado=?', ('Custom',))
            db.execute('INSERT INTO device_aliases VALUES (?,?)', ('fedcba9876543210', 'Outside inventory'))
        source.write_text(row.replace('23,', '24,'), encoding='ascii')
        seed_aliases(self.root)
        result = self.client.get('/api/status').json()
        self.assertEqual(result['inventory_status'], 'registered')
        self.assertEqual(result['inventory'], [{'plate': 'p01', 'device_ref': '0123456789abcdef', 'alias': 'Custom'}])

    def test_evidence_filtered(self):
        self.evidence(password='SECRET')
        text = self.client.get('/api/evidence').text
        self.assertNotIn('SECRET', text)
        self.assertIn('checked', text)

    def test_evidence_detail(self):
        name = self.evidence()
        self.assertEqual(self.client.get('/api/evidence/' + name).status_code, 200)

    def test_private_file_not_listed(self):
        (self.root / 'runs/private.json').write_text('{"password":"SECRET"}')
        self.assertEqual(self.client.get('/api/evidence').json(), [])
        self.assertEqual(self.client.get('/api/evidence/private.json').status_code, 404)

    def test_invalid_json(self):
        (self.root / 'runs/farm_preflight_bad.json').write_text('{')
        self.assertEqual(self.client.get('/api/evidence').json(), [])

    def test_invalid_shape_is_not_served(self):
        path = self.root / 'runs/farm_preflight_shape.json'
        for data in ([], {'decision': 'abort', 'verdicts': [None]},
                     {'decision': 'abort', 'verdicts': [{'counters': []}]}):
            path.write_text(json.dumps(data))
            self.assertEqual(self.client.get('/api/evidence').json(), [])

    def test_foreign_origin(self):
        self.assertEqual(self.client.get('/api/status', headers={'Origin': 'https://other.test'}).status_code, 403)

    def test_host_rebinding(self):
        self.assertEqual(self.client.get('/api/status', headers={'Host': 'other.test'}).status_code, 403)

    def test_unpermitted_action(self):
        for action in ('real', 'vision', 'adb', 'pause'):
            self.assertEqual(self.client.post('/api/actions/' + action, headers={'X-Lab-Action': 'synthetic'}).status_code, 403)

    def test_missing_action_header(self):
        self.assertEqual(self.client.post('/api/actions/verify').status_code, 403)

    def test_synthetic_check(self):
        self.assertEqual(self.client.post('/api/actions/verify', headers={'X-Lab-Action': 'synthetic'}).status_code, 200)
        for _ in range(100):
            state = self.client.get('/api/status').json()
            if state['status'] != 'running': break
            time.sleep(.01)
        self.assertEqual(state['status'], 'completed')
        self.assertTrue(state['last_check']['synthetic'])

    def test_stop_and_duplicate(self):
        async def wait(): await asyncio.sleep(60)
        with TestClient(create_app(self.root, checker=wait), base_url='http://127.0.0.1') as client:
            headers = {'X-Lab-Action': 'synthetic'}
            client.post('/api/actions/verify', headers=headers)
            self.assertEqual(client.post('/api/actions/verify', headers=headers).status_code, 409)
            self.assertEqual(client.post('/api/actions/stop', headers=headers).json()['status'], 'cancelled')

    def test_index_and_assets(self):
        self.assertIn('Laboratorio', self.client.get('/').text)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        self.assertEqual(self.client.get('/static/private.txt').status_code, 404)

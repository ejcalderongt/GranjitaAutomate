import unittest
from unittest.mock import patch

from core.panda_api import PandaClient, PandaError
from scripts.aplicar_aliases_panda import reconcile, targets


class PandaAliasTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = [
            {'serial': 'route-a', 'onlySerial': 'hardware-a', 'sort': 24, 'name': 'Old'},
            {'serial': 'route-b', 'onlySerial': 'hardware-b', 'sort': 6, 'name': 'Second'},
        ]
        self.desired = [('p01', 'hardware-a', 7, 'First'), ('p02', 'hardware-b', 6, 'Second')]
        self.sent = []
        self.client = PandaClient(request=self.request)

    async def request(self, payload):
        if payload['action'] == 'list':
            return self.rows
        self.sent.append(payload)
        row = next(row for row in self.rows if row['serial'] == payload['devices'])
        row.update(payload['data'])

    async def test_applies_to_current_transport_and_is_idempotent(self):
        result = await reconcile(self.client, self.desired, apply=True)
        self.assertTrue(all(row['aligned'] for row in result.values()))
        await reconcile(self.client, self.desired, apply=True)
        self.assertEqual(self.sent, [
            {'action': 'updateDevices', 'devices': 'route-a', 'data': {'sort': 7, 'name': 'First'}},
        ])

    async def test_check_never_writes(self):
        result = await reconcile(self.client, self.desired)
        self.assertFalse(result['p01']['aligned'])
        self.assertFalse(self.sent)

    async def test_collision_on_later_plate_stops_before_any_write(self):
        self.rows[1]['sort'] = 11
        self.rows.append({'serial': 'route-c', 'onlySerial': 'hardware-c', 'sort': 6})
        with self.assertRaisesRegex(PandaError, 'p02: numero 06 ocupado'):
            await reconcile(self.client, self.desired, apply=True)
        self.assertFalse(self.sent)

    async def test_ack_without_readback_match_fails(self):
        async def ignore_update(payload):
            if payload['action'] == 'list':
                return self.rows

        with self.assertRaisesRegex(PandaError, 'reasignacion sin confirmar'):
            await reconcile(PandaClient(request=ignore_update), self.desired, apply=True)

    async def test_rejects_broadcast_target(self):
        with self.assertRaises(ValueError):
            await self.client.update_device_alias('all', 7, 'First')
        self.assertFalse(self.sent)

    def test_mismatched_sqlite_and_dpapi_reference_blocks_startup(self):
        aliases = [{'plate': 'p01', 'device_ref': 'alias-ref', 'alias': 'First'}]
        mapping = {'plates': [{'plate': 'p01', 'device_ref': 'map-ref',
                               'device_serial_plain': 'hardware-a'}]}
        with patch('scripts.aplicar_aliases_panda.read_aliases', return_value=aliases), \
                patch('scripts.aplicar_aliases_panda.load_latest_map', return_value=mapping):
            with self.assertRaisesRegex(PandaError, 'p01: alias no vinculado'):
                targets(None)

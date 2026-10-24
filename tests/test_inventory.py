from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import sqlite3

from granjita.core import Store
from granjita.inventory import FleetStore, collect_inventory, scan_fleet


def device(port=5037, serial='example'):
    return dict(port=port, serial=serial, model='Board', android='12', status='Validado', detail='OK', state='device')


def report(devices, failed=()):
    return dict(servers=[dict(port=p, pid=None, status='No disponible' if p in failed else 'ADB responde', count=sum(d['port']==p for d in devices),detail='',at='2026-10-23T12:00:00-06:00') for p in [5037,5038]],devices=devices,warning='')


class InventoryTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.path = Path(self.folder.name) / 'inventory.sqlite3'

    def tearDown(self):
        self.folder.cleanup()

    def test_migration_keeps_alias_history_and_backup(self):
        legacy = Store(self.path)
        legacy.save_scan([device()])
        legacy.alias('example', 'Placa de prueba')
        store = FleetStore(self.path)
        rows = store.fleet_devices()
        self.assertEqual(rows[0]['alias'], 'Placa de prueba')
        self.assertEqual(len(store.device_history(rows[0]['id'])), 1)
        self.assertTrue(self.path.with_name('inventory-antes-v2.sqlite3').exists())
        again = FleetStore(self.path)
        self.assertEqual(len(again.fleet_devices()), 1)
        with again.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_failed_server_does_not_disconnect_its_devices(self):
        store = FleetStore(self.path)
        store.save_fleet(report([device(),device(5038,'other')]))
        store.save_fleet(report([device()],failed=(5038,)))
        rows = {r['port']:r for r in store.fleet_devices()}
        self.assertEqual(rows[5037]['status'], 'Validado')
        self.assertEqual(rows[5038]['status'], 'Servidor sin verificar')
        store.save_fleet(report([device()]))
        self.assertEqual(store.fleet_devices()[1]['status'], 'Desconectado')

    def test_same_transport_on_two_servers_not_silently_merged(self):
        store = FleetStore(self.path)
        store.save_fleet(report([device(),device(5038)]))
        rows = store.fleet_devices()
        self.assertEqual(len({r['id'] for r in rows}), 2)
        store.link_connection(5038,'example',rows[0]['id'])
        self.assertEqual(len({r['id'] for r in store.fleet_devices()}), 1)

    def test_observation_history_changes_and_identity_survive_restart(self):
        store = FleetStore(self.path)
        store.save_fleet(report([device()]))
        identifier = store.fleet_devices()[0]['id']
        observation = dict(field='Android',value='12',state='Disponible',source='getprop',at='2026-10-23')
        store.save_inventory(identifier,5037,'example',[observation])
        store.save_inventory(identifier,5037,'example',[dict(observation,value='13')])
        rows,snapshot,count = FleetStore(self.path).inventory(identifier)
        self.assertEqual(count, 2)
        self.assertTrue(rows[0]['changed'])
        self.assertEqual(rows[0]['value'], '13')

    def test_inventory_permission_root_and_proxy_redaction(self):
        def fake_shell(adb, serial, command):
            if command == 'getprop':
                return '[ro.build.version.release]: [12]\n[ro.product.model]: [Board]'
            if command.startswith('id;'):
                return 'uid=2000(shell)\n__GRANJITA_RC=0'
            if command.startswith('command -v su;'):
                return '\n__GRANJITA_RC=1'
            if command.startswith('ip -o'):
                return 'Permission denied\n__GRANJITA_RC=1'
            if command.startswith('dumpsys connectivity;'):
                return 'SecurityException: permission required\n__GRANJITA_RC=0'
            if command.startswith('settings get global http_proxy;'):
                return 'user:password@proxy.example:80\n__GRANJITA_RC=0'
            return 'null\n__GRANJITA_RC=0'
        with patch('granjita.inventory.shell', side_effect=fake_shell):
            rows = {o['field']:o for o in collect_inventory(5037,'example')}
        self.assertEqual(rows['IP por interfaz']['state'], 'Restringido')
        self.assertEqual(rows['Redes activas y DNS']['state'], 'Restringido')
        self.assertIn('No observado', rows['Evaluación de root']['value'])
        self.assertNotIn('password', rows['Proxy global']['value'])
        self.assertEqual(rows['Android']['value'], '12')

    def test_scan_aggregates_and_preserves_source(self):
        def devices(adb):
            if adb.port == 5038:
                raise OSError('No responde')
            return [dict(serial='example',model='Board',state='device')]
        with patch('granjita.inventory.Adb.devices',devices), patch('granjita.inventory.Adb.validate',lambda adb,d:dict(d,status='Validado',android='12',detail='OK')):
            result = scan_fleet([5037,5038], discover=False)
        self.assertEqual(result['devices'][0]['port'],5037)
        self.assertEqual(result['servers'][1]['status'],'No disponible')

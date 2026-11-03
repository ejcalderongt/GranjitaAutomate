import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.proxies import ADBError,servidor_adb_actual
from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot,descubrir_pool,cargar_objetivos
from core.database import Database
from core.panda_identity import resolver_pool_panda,confirmar_identidad,leer_identidad_fisica


class PandaIdentityTests(unittest.TestCase):
    def setUp(self):
        self.server=ADBServer('127.0.0.1',5038)
        self.route=DeviceRoute('127.0.0.1:5555',self.server,'device',[self.server])

    @patch('core.panda_identity.leer_identidad_fisica',return_value='physical-01')
    def test_tcp_is_keyed_by_physical_identity_and_preserves_transport(self,read):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            with db.conexion() as con:
                con.execute('CREATE TABLE legacy_agx_identities(legacy_id TEXT,canonical_id TEXT,hardware_serial TEXT,alias TEXT)')
                con.execute("INSERT INTO legacy_agx_identities VALUES ('old','canonical','physical-01','Panda histórico')")
            result=resolver_pool_panda(PoolSnapshot({self.route.serial:self.route},{},[self.server]),db)
            self.assertEqual(result.devices['physical-01'].serial,'127.0.0.1:5555')
            db.sincronizar_pool(result)
            self.assertEqual(db.dispositivos()[0]['id_adb'],'physical-01')
            self.assertEqual(db.dispositivos()[0]['alias'],'Panda histórico')

    @patch('core.panda_identity.leer_identidad_fisica',return_value='new-physical')
    def test_new_physical_device_is_registered_without_historical_auth(self,read):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            result=resolver_pool_panda(PoolSnapshot({self.route.serial:self.route},{},[self.server]),db)
            db.sincronizar_pool(result)
            row=db.dispositivos()[0]
            self.assertEqual(row['id_adb'],'new-physical')
            self.assertIn('Nueva',row['alias'])
            self.assertEqual(row['cuenta_estado'],'sin_verificar')

    @patch('core.panda_identity.leer_identidad_fisica',return_value='different-device')
    def test_address_reused_by_another_device_is_rejected(self,read):
        self.route.hardware_serial='expected-device'
        with self.assertRaisesRegex(ADBError,'cambió'):
            confirmar_identidad(self.route)

    @patch('core.panda_identity.shell')
    def test_two_serial_sources_must_agree_and_server_is_pinned(self,shell):
        def command(serial,*args,**kwargs):
            self.assertEqual(servidor_adb_actual(),('127.0.0.1',5038))
            return {'ro.kernel.qemu':'0','ro.serialno':'physical-01','ro.boot.serialno':'different-02'}[args[-1]]
        shell.side_effect=command
        with self.assertRaisesRegex(ADBError,'discrepan'):
            leer_identidad_fisica(self.route)
        self.assertIsNone(servidor_adb_actual())

    @patch('core.panda_identity.leer_identidad_fisica',return_value='physical-01')
    def test_different_routes_claiming_same_identity_are_not_scheduled_twice(self,read):
        other=DeviceRoute('127.0.0.1:5556',self.server,'device',[self.server])
        with tempfile.TemporaryDirectory() as folder:
            result=resolver_pool_panda(PoolSnapshot({r.serial:r for r in (self.route,other)},{},[self.server]),Database(Path(folder)/'db.sqlite'))
            self.assertNotIn('physical-01',result.devices)
            self.assertTrue(result.identity_errors)


class PandaReconnectTests(unittest.TestCase):
    @patch('core.adb_pool.proxies.adb')
    @patch('core.adb_pool.consultar_servidor',side_effect=ADBError('server down'))
    def test_unavailable_panda_server_is_not_started_by_connect(self,query,adb):
        server=ADBServer('127.0.0.1',5038)
        result=descubrir_pool([server],reconnect=True,targets={server:['127.0.0.1:5555']})
        adb.assert_not_called()
        self.assertIn(server.key,result.errors)

    @patch('core.adb_pool.proxies.adb',return_value='connected')
    @patch('core.adb_pool.consultar_servidor')
    def test_connect_uses_explicit_server_then_rechecks_device_state(self,query,adb):
        server=ADBServer('127.0.0.1',5038)
        query.side_effect=[{}, {'127.0.0.1:5555':'device'}]
        result=descubrir_pool([server],reconnect=True,targets={server:['127.0.0.1:5555']})
        adb.assert_called_once_with('-H','127.0.0.1','-P','5038','connect','127.0.0.1:5555',timeout=3)
        self.assertEqual(result.devices['127.0.0.1:5555'].status,'device')

    @patch('core.adb_pool.proxies.adb')
    @patch('core.adb_pool.consultar_servidor',return_value={'127.0.0.1:5555':'unauthorized'})
    def test_unauthorized_transport_does_not_trigger_reconnect(self,query,adb):
        server=ADBServer('127.0.0.1',5038)
        result=descubrir_pool([server],reconnect=True,targets={server:['127.0.0.1:5555']})
        adb.assert_not_called()
        self.assertEqual(result.devices['127.0.0.1:5555'].status,'unauthorized')

    @patch('core.adb_pool.proxies.adb',return_value='unable to connect')
    @patch('core.adb_pool.consultar_servidor',return_value={})
    def test_successful_process_exit_does_not_invent_connected_device(self,query,adb):
        server=ADBServer('127.0.0.1',5038)
        result=descubrir_pool([server],reconnect=True,targets={server:['127.0.0.1:5555']})
        self.assertEqual(result.devices,{})
        self.assertTrue(result.reconnect_errors)

    def test_configured_targets_reject_shell_fragments(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'servers.json'
            path.write_text(json.dumps({'servers':[{'host':'127.0.0.1','port':5038,'devices':['127.0.0.1:5555;bad']}]}))
            with self.assertRaises(ValueError):
                cargar_objetivos([ADBServer('127.0.0.1',5038)],path)

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.deployment_check import preparar_pool, fijar_adb_local
from config.proxies import ADBError
from core.selectors import esperar_feed
from core.deployment_check import seleccionar_proxies_smoke, simular_entorno
from core.database import Database
from config.proxies import ProxyAllocator
from types import SimpleNamespace


class DeploymentTests(unittest.TestCase):
    def test_farm_capacity_is_a_concurrency_cap_not_required_inventory_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pool.json'
            path.write_text(json.dumps({'proxies':[{'host':'8.8.8.8','port':8000,'exit_ip':'9.9.9.9','enabled':True}]}))
            self.assertEqual(len(preparar_pool(path,40,required=1)),1)
    def test_first_proxies_cannot_be_replaced_by_later_enabled_entries(self):
        entries=[{'enabled':False},{'enabled':True},{'enabled':True},{'enabled':True}]
        with self.assertRaises(ValueError):
            seleccionar_proxies_smoke(entries,3)
        entries[0]['enabled']=True
        self.assertEqual(seleccionar_proxies_smoke(entries,3),entries[:3])

    def test_fixed_proxy_reservation_preserves_order_and_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'db.sqlite')
            pool=ProxyAllocator(db)
            pool.sincronizar([{'endpoint':f'192.0.2.{i}:8000','host':f'192.0.2.{i}',
                              'port':8000} for i in (2,1)])
            self.assertEqual(pool.reservar('a','run',endpoint='192.0.2.2:8000')['host'],'192.0.2.2')
            self.assertIsNone(pool.reservar('b','run',endpoint='192.0.2.2:8000'))
            self.assertIsNone(pool.reservar('a','run',endpoint='192.0.2.1:8000'))

    def test_summary_distinguishes_unmeasured_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'db.sqlite')
            for value in (100,300):
                db.log_granja('run','a','Latencia de carga UI',detalle={'latencia_ms':value})
            db.guardar_resumen_carga('run',{'a','b','c'})
            with db.conexion() as con:
                result=json.loads(con.execute('SELECT detalle FROM resumenes_carga').fetchone()[0])
            self.assertEqual(result[0]['media_ms'],200)
            self.assertIsNone(result[1]['media_ms'])
            self.assertEqual(result[2]['muestras'],0)

    def test_simulation_does_not_call_adb_or_write_production_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('core.database.ROOT',Path(directory)),patch('config.proxies.adb') as adb:
                self.assertEqual(simular_entorno(SimpleNamespace(smoke_test=3)),0)
                adb.assert_not_called()
            db=Database(Path(directory)/'data/simulation.db')
            self.assertEqual(len(db.dispositivos()),34)
            self.assertTrue(all(not row['conectado'] for row in db.dispositivos()))
            self.assertFalse((Path(directory)/'data/granja_tiktok.db').exists())

    def test_empty_pool_creates_disabled_template(self):
        for content in (None, '', '{"proxies": []}'):
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'pool.json'
                if content is not None:
                    path.write_text(content)
                with self.assertRaisesRegex(ValueError, 'Plantilla creada'):
                    preparar_pool(path,3)
                data=json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(len(data['proxies']),3)
                self.assertTrue(all(not p['enabled'] for p in data['proxies']))
                with self.assertRaises(ValueError):
                    preparar_pool(path,3)

    def test_malformed_pool_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pool.json'
            path.write_text('{broken')
            with self.assertRaises(ValueError):
                preparar_pool(path,3)
            self.assertEqual(path.read_text(),'{broken')

    def test_adb_missing_path_does_not_fall_back_to_path(self):
        with patch.dict(os.environ,{'ADB_PATH':r'C:\missing-panda-sdk\adb.exe'}):
            with self.assertRaises(ADBError):
                fijar_adb_local()

    def test_login_detected_before_waiting_for_feed(self):
        xml='<hierarchy><node package="app" text="Log in" clickable="true" bounds="[0,0][100,100]" /></hierarchy>'
        progress=[]
        with patch('core.selectors.adb',side_effect=['dumped to file',xml]):
            result=esperar_feed('usb','app',on_progress=progress.append)
        self.assertFalse(result['ready'])
        self.assertEqual(progress[-1]['state'],'login_required')

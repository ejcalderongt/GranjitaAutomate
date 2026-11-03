import json
from pathlib import Path
import tempfile
import unittest

from config.proxies import leer_proxy_pool,ProxyAllocator
from core.database import Database
from core.deployment_check import preparar_pool
from ui.farm_control import guardar_pool


class LaboratoryNetworkTests(unittest.TestCase):
    def pool(self,path):
        data={'mode':'laboratory','lab_host':'192.168.1.199','proxies':[
            dict(host='192.168.1.199',port=port,exit_ip='8.8.8.8',enabled=True) for port in (8001,8002,8003)]}
        path.write_text(json.dumps(data))
        return data

    def test_lab_preflight_accepts_private_host_and_shared_real_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json'
            self.pool(path)
            self.assertEqual(len(preparar_pool(path,3)),3)
            self.assertTrue(all(p['lab_shared_exit'] for p in leer_proxy_pool(path)))

    def test_production_cannot_enable_lab_mode_per_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json'
            data=self.pool(path)
            data.pop('mode');data.pop('lab_host')
            for row in data['proxies']:row['lab_shared_exit']=True
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):preparar_pool(path,3)

    def test_lab_host_must_be_private_and_all_endpoints_must_match(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json'
            data=self.pool(path)
            data['lab_host']='8.8.8.8'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):leer_proxy_pool(path)
            data=self.pool(path)
            data['proxies'][1]['host']='192.168.1.200'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):leer_proxy_pool(path)

    def test_shared_exit_reservations_remain_exclusive_per_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json'
            self.pool(path)
            db=Database(Path(folder)/'db.sqlite')
            allocator=ProxyAllocator(db)
            allocator.sincronizar(leer_proxy_pool(path))
            self.assertEqual(allocator.disponibles(),3)
            for i in range(3):
                self.assertIsNotNone(allocator.reservar(str(i),'run'))
                allocator.confirmar_salida(str(i),'run','8.8.8.8')
                db.registrar_ip('run',str(i),'8.8.8.8',smoke=True,confirmada=True,laboratory=True)
            self.assertIsNone(allocator.reservar('extra','run'))
            self.assertTrue(all(row['modo']=='laboratory' for row in db.ips_ejecucion('run')))
            with self.assertRaises(ValueError):allocator.confirmar_salida('0','run','9.9.9.9')

    def test_mode_change_with_active_lease_is_rejected_transactionally(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json'
            self.pool(path)
            db=Database(Path(folder)/'db.sqlite')
            allocator=ProxyAllocator(db)
            entries=leer_proxy_pool(path)
            allocator.sincronizar(entries)
            allocator.reservar('device','run')
            entries[0]['lab_shared_exit']=False
            with self.assertRaises(ValueError):allocator.sincronizar(entries)
            self.assertEqual(allocator.disponibles(),2)

    def test_dashboard_save_keeps_explicit_lab_mode_and_duplicate_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json'
            data=self.pool(path)
            guardar_pool(path,data['proxies'])
            self.assertEqual(json.loads(path.read_text())['mode'],'laboratory')
            self.assertEqual(len(preparar_pool(path,3)),3)

    def test_global_mode_change_is_blocked_even_for_a_different_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pool.json';self.pool(path)
            allocator=ProxyAllocator(Database(Path(folder)/'db.sqlite'))
            allocator.sincronizar(leer_proxy_pool(path))
            allocator.reservar('device','run')
            with self.assertRaises(ValueError):
                allocator.sincronizar([{'endpoint':'8.8.8.8:8000','host':'8.8.8.8','port':8000,'enabled':True}])

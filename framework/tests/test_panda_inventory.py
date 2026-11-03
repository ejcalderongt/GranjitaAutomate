from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot
from core.database import Database
from core.panda_inventory import verificar_rutas,conciliar,guardar_inventario


class PandaInventoryTests(unittest.TestCase):
    def test_links_exact_hardware_preserves_alias_and_records_number(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            db.actualizar_dispositivo('physical-02',alias='Alias existente',estado='Pendiente Cuenta')
            server=ADBServer('127.0.0.1',5038)
            route=DeviceRoute('192.0.2.2:5555',server,'device',[server])
            with patch('core.panda_inventory.leer_identidad_fisica',return_value='physical-02'):
                snapshot=verificar_rutas(PoolSnapshot({route.serial:route},{},[server]),db)
            rows=conciliar([{'sort':2,'onlySerial':'physical-02','serial':route.serial,'name':'Nombre Panda'}],snapshot,db)
            self.assertEqual(rows[0]['estado'],'vinculado')
            guardar_inventario(db,snapshot,rows,'test-run')
            row=db.dispositivos()[0]
            self.assertEqual(row['panda_numero'],'02')
            self.assertEqual(row['alias'],'Alias existente')
            self.assertEqual(row['cuenta_estado'],'pendiente')
            self.assertEqual(row['estado'],'Pendiente Cuenta')

    def test_ip_reuse_cannot_join_a_different_physical_device(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            route=DeviceRoute('192.0.2.2:5555',ADBServer('localhost'),'device',hardware_serial='physical-other')
            rows=conciliar([{'sort':2,'onlySerial':'physical-old','serial':route.serial}],
                PoolSnapshot({'physical-other':route},{},[]),db)
            self.assertEqual(rows[0]['estado'],'conflicto_identidad')
            self.assertIsNone(rows[0]['serial_fisico'])

    def test_duplicate_visual_number_is_not_linked(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'db.sqlite')
            rows=conciliar([{'sort':2,'onlySerial':'a'},{'sort':2,'onlySerial':'b'}],PoolSnapshot({},{},[]),db)
            self.assertTrue(all(row['estado']=='ambiguo' for row in rows))

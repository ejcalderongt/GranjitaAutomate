from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from granjita.inventory import FleetStore
from granjita.physical import ordered_rows, sync_position


def row(identifier, serial, status='Validado', port=5037):
    return dict(id=identifier, hardware_serial=serial, status=status, port=port,serial='192.0.2.1:5555',display_name=identifier,identity_state='Serial leído')


class PhysicalTests(TestCase):
    def test_fixed_order_survives_offline_and_duplicate_transport(self):
        positions=[dict(hardware_serial='SERIAL01',rack='R01',slot=1,panda_number=101),dict(hardware_serial='SERIAL02',rack='R01',slot=2,panda_number=102)]
        rows=[row('a','SERIAL01','Desconectado'),row('b','SERIAL02'),row('b','SERIAL02',port=5038)]
        fixed=ordered_rows(rows,positions)
        self.assertEqual([r['id'] for r in fixed],['a','b'])
        self.assertEqual([r['id'] for r in ordered_rows(rows,positions,True)],['b','a'])
        self.assertEqual(fixed[0]['slot'],1)

    def test_positions_persist_and_collisions_do_not_overwrite(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite3';s=FleetStore(path)
            with s.connect() as db:
                for identifier,serial in [('a','SERIAL01'),('b','SERIAL02')]:
                    db.execute('INSERT INTO inventory_devices VALUES (?,?,?)',(identifier,'','test'))
                    db.execute('INSERT INTO device_identity VALUES (?,?,?,?,?,?)',(identifier,serial,'Test','Test','Serial leído','test'))
            s.assign_position('SERIAL01','r01',20,120)
            reopened=FleetStore(path)
            self.assertEqual(reopened.positions()[0]['slot'],20)
            for args in [('SERIAL02','R01',20,121),('SERIAL02','R02',1,120),('UNKNOWN1','R02',1,121)]:
                with self.assertRaises(ValueError):reopened.assign_position(*args)
            self.assertEqual(len(reopened.positions()),1)
            self.assertTrue(path.with_name('test-antes-v4.sqlite3').exists())

    def test_sync_checks_collision_and_verifies_readback(self):
        r=dict(row('a','SERIAL01'),rack='R01',slot=20,panda_number=120)
        current=[dict(onlySerial='SERIAL01',serial=r['serial'],name='old',sort=51)]
        with patch('granjita.physical.verify_identity'),patch('granjita.panda_api.list_devices',side_effect=[current,[dict(current[0],name='R01-P20',sort=120)]]),patch('granjita.panda_api.update_device') as update:
            self.assertIn('confirmó',sync_position(r))
            update.assert_called_once_with(r['serial'],'R01-P20',120)
        with patch('granjita.physical.verify_identity'),patch('granjita.panda_api.list_devices',return_value=current+[dict(onlySerial='OTHER',sort=120)]),patch('granjita.panda_api.update_device') as update:
            with self.assertRaises(ValueError):sync_position(r)
            update.assert_not_called()

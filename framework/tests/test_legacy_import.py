import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from core.database import Database
from core.legacy_import import importar


class LegacyImportTests(unittest.TestCase):
    def test_panda_names_recovered_by_physical_serial_and_preserved_on_reimport(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=self.fixture(root)
            with closing(sqlite3.connect(source/'data/granjita.sqlite3')) as con, con:
                con.execute("UPDATE inventory_devices SET alias=''")
            (source/'data/panda-inventory.json').write_text(json.dumps({
                'at':'2026-10-24','devices':[{'onlySerial':'usb-real','name':'Nombre Panda histórico'},
                                           {'onlySerial':'unknown','name':'No asignar'}]}),encoding='utf-8')
            target=root/'new/db.sqlite'
            first=importar(source,target)
            second=importar(source,target)
            self.assertEqual(first['historical_aliases_added'],2)
            self.assertEqual(second['historical_aliases_added'],0)
            self.assertEqual(second['historical_rows_added'],0)
            self.assertEqual(Database(target).identidad_agx('usb-real')['alias'],'Nombre Panda histórico')
            self.assertEqual(len(Database(target).dispositivos()),1)

    def fixture(self,root):
        source=root/'AGX'
        (source/'data').mkdir(parents=True)
        with closing(sqlite3.connect(source/'data/granjita.sqlite3')) as con, con:
            con.executescript('''
                CREATE TABLE device_identity(device_id TEXT,hardware_serial TEXT,at TEXT);
                CREATE TABLE device_identity_aliases(alias_id TEXT,canonical_id TEXT);
                CREATE TABLE inventory_devices(id TEXT,alias TEXT);
                CREATE TABLE device_app_observations(id INTEGER,hardware_serial TEXT,app_id TEXT,scope TEXT,at TEXT,payload TEXT);
                INSERT INTO device_identity VALUES ('canonical','usb-real','2026-10-26'),('old','old-serial','2026-10-25');
                INSERT INTO device_identity_aliases VALUES ('old','canonical');
                INSERT INTO inventory_devices VALUES ('canonical','Panda histórico');
            ''')
            con.execute('INSERT INTO device_app_observations VALUES (1,?,?,?,?,?)',
                ('usb-real','tiktok','declaration','2026-10-27',json.dumps({'presence':'present'})))
        return source

    def test_import_is_idempotent_and_does_not_claim_live_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=self.fixture(root)
            target=root/'new/db.sqlite'
            first=importar(source,target)
            second=importar(source,target)
            self.assertEqual(first['devices_added'],1)
            self.assertEqual(second['devices_added'],0)
            self.assertEqual(second['historical_rows_added'],0)
            db=Database(target)
            row=db.dispositivos()[0]
            self.assertEqual(row['id_adb'],'usb-real')
            self.assertEqual(row['cuenta_estado'],'sin_verificar')
            self.assertFalse(row['conectado'])
            self.assertEqual(db.legado_agx()[0]['cuenta_declarada'],'present')
            self.assertEqual(db.identidad_agx('usb-real'),{'canonical_id':'canonical','alias':'Panda histórico'})
            self.assertEqual(db.identidad_agx('192.0.2.1:5555'),{})
            db.registrar_interaccion('usb-real',run_id='new-live-run',ciclo=1,
                descripcion_video='contexto',decision_ia={'interactuar':False},latencia_ms=10)
            interactions,_=db.interacciones()
            self.assertEqual(interactions[0]['legacy_device_id'],'canonical')
            self.assertEqual(interactions[0]['id_adb'],'usb-real')
            self.assertTrue((Path(first['archive'])/'granjita.sqlite3').exists())
            self.assertTrue((Path(second['archive'])/'framework-before.sqlite3').exists())

    def test_existing_device_state_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=self.fixture(root)
            db=Database(root/'new/db.sqlite')
            db.actualizar_dispositivo('usb-real',alias='Alias actual',proxy='1.1.1.1:8000',estado='Navegando',conectado=True)
            db.registrar_auth('usb-real',False,'login actual')
            importar(source,db.path)
            row=db.dispositivos()[0]
            self.assertEqual(row['alias'],'Alias actual')
            self.assertEqual(row['estado'],'Pendiente Cuenta')
            self.assertEqual(row['proxy'],'1.1.1.1:8000')
            self.assertTrue(row['conectado'])

    def test_cyclic_alias_does_not_import_operational_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=self.fixture(root)
            with closing(sqlite3.connect(source/'data/granjita.sqlite3')) as con, con:
                con.execute("INSERT INTO device_identity_aliases VALUES ('canonical','old')")
            target=root/'new/db.sqlite'
            with self.assertRaisesRegex(ValueError,'Ciclo'):
                importar(source,target)
            self.assertEqual(Database(target).dispositivos(),[])

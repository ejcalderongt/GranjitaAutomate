import sqlite3
import unittest
from scripts.reasignar_conflictos import plan_changes


class ReassignmentPlanTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''CREATE TABLE connections(port,serial,device_id,status);
CREATE TABLE device_identity(device_id,hardware_serial,state,manufacturer,model);
INSERT INTO connections VALUES(5037,'transport','old','Identidad en conflicto');
INSERT INTO device_identity VALUES('old','OLD-SERIAL','Serial leído','Samsung','Model');
INSERT INTO device_identity VALUES('target','NEW-SERIAL','Serial leído','Samsung','Model');''')
        self.device=dict(port=5037,serial='transport',status='Validado',hardware_serial='NEW-SERIAL',manufacturer='Samsung',hardware_model='Model')
        self.panda=[dict(serial='transport',onlySerial='NEW-SERIAL',sort=1)]

    def tearDown(self):
        self.db.close()

    def plan(self):
        return plan_changes(self.db,dict(devices=[self.device]),self.panda)

    def test_existing_unique_target_without_mutation(self):
        self.assertEqual(self.plan()[0]['target_id'],'target')
        self.assertEqual(self.db.execute('SELECT device_id FROM connections').fetchone()[0],'old')

    def test_duplicate_target_rejected(self):
        self.db.execute("INSERT INTO device_identity VALUES('duplicate','NEW-SERIAL','Serial leído','Samsung','Model')")
        with self.assertRaises(ValueError):self.plan()

    def test_panda_mismatch_rejected(self):
        self.panda[0]['onlySerial']='OTHER'
        with self.assertRaises(ValueError):self.plan()

    def test_metadata_mismatch_rejected(self):
        self.device['manufacturer']='Other'
        with self.assertRaises(ValueError):self.plan()

    def test_no_conflicts_no_changes(self):
        self.db.execute("UPDATE connections SET status='Validado'")
        self.assertEqual(self.plan(),[])

    def test_historical_alias_is_not_a_second_active_target(self):
        self.db.execute('CREATE TABLE device_identity_aliases(alias_id,canonical_id)')
        self.db.execute("INSERT INTO device_identity VALUES('historical','NEW-SERIAL','Serial leído','Samsung','Model')")
        self.db.execute("INSERT INTO device_identity_aliases VALUES('historical','target')")
        self.assertEqual(self.plan()[0]['target_id'],'target')

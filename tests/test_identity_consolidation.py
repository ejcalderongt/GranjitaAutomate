from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from granjita.inventory import FleetStore
from granjita.identity_consolidation import plan_consolidations,apply_consolidations
from test_inventory import report,device


class ConsolidationTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=FleetStore(Path(self.tmp.name)/'fleet.sqlite3')
        a=dict(device(5037,'192.0.2.1:5555'),hardware_serial='TESTSERIAL',manufacturer='samsung',hardware_model='Board')
        b=dict(a,port=5038)
        self.store.save_fleet(report([a,b]))
        self.live=report([b]);self.store.save_fleet(self.live)
        self.panda=[dict(sort=4,onlySerial='TESTSERIAL',serial=b['serial'])]

    def plan(self):
        with self.store.connect() as db:return plan_consolidations(db,self.live,self.panda,[4])

    def test_consolidation_preserves_fiches_identity_snapshots_and_history(self):
        before=self.store.fleet_devices()
        for row in before:self.store.save_inventory(row['id'],row['port'],row['serial'],[])
        plan=self.plan();canonical=plan[0]['canonical_id']
        apply_consolidations(self.store,plan)
        with self.store.connect() as db:
            self.assertEqual(db.execute('select count(*) from inventory_devices').fetchone()[0],2)
            self.assertEqual(db.execute('select count(*) from device_identity').fetchone()[0],2)
            self.assertEqual(db.execute('select count(*) from snapshots').fetchone()[0],2)
            self.assertEqual(db.execute('select count(*) from device_identity_aliases').fetchone()[0],1)
        self.assertEqual(len(self.store.identity_family(canonical)),2)
        self.assertEqual(self.store.inventory(canonical)[2],2)
        self.assertTrue(all(r['identity_state']=='Serial leído' and r['id']==canonical for r in self.store.fleet_devices()))
        self.store.save_fleet(self.live)
        self.assertEqual(self.plan(),[])

    def test_simultaneous_distinct_transports_are_not_merged(self):
        self.live['devices'].append(dict(self.live['devices'][0],serial='192.0.2.2:5555'))
        with self.assertRaises(ValueError):self.plan()

    def test_metadata_disagreement_is_not_merged(self):
        with self.store.connect() as db:db.execute("update device_identity set model='Different' where device_id=(select device_id from device_identity limit 1)")
        with self.assertRaises(ValueError):self.plan()

    def test_changed_connection_rolls_back_entire_plan(self):
        plans=self.plan()
        with self.store.connect() as db:db.execute("update connections set device_id='changed' where port=5038")
        with self.assertRaises(ValueError):apply_consolidations(self.store,plans)
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from device_identity_aliases').fetchone()[0],0)

    def test_old_inventory_snapshot_migrates_before_alias_table_exists(self):
        row=self.store.fleet_devices()[0]
        observations=[dict(field='Serie hardware',value='TESTSERIAL',state='Disponible',source='test',at='2026-10-26T00:00:00-06:00')]
        self.store.save_inventory(row['id'],row['port'],row['serial'],observations)
        with self.store.connect() as db:
            for table in ['device_app_observations','device_app_assignments','device_identity_aliases','device_identity','physical_positions','checkpoint_files','device_checkpoints','recovery_events']:
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=2')
        restored=FleetStore(self.store.path)
        self.assertTrue(any(r['hardware_serial']=='TESTSERIAL' for r in restored.fleet_devices()))
        with restored.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)

    def test_alias_history_and_rename_resolve_to_canonical(self):
        plans=self.plan();apply_consolidations(self.store,plans)
        family=self.store.identity_family(plans[0]['canonical_id'])
        historical=family[1]
        self.store.rename_device(historical,'Placa física')
        self.assertTrue(all(r['display_name']=='Placa física' for r in self.store.fleet_devices()))
        self.assertEqual(self.store.identity_family(historical),family)
        self.assertTrue(self.store.device_history(historical))

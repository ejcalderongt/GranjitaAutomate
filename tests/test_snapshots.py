from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import json
from granjita.inventory import FleetStore
from granjita.snapshots import capture,restore,digest,filename,latest

ROW=dict(id='device1',hardware_serial='SERIAL01',port=5037,serial='192.0.2.1:5555',status='Validado',identity_state='Serial leído',display_name='Prueba')

class SnapshotTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=FleetStore(Path(self.temp.name)/'test.sqlite3')
    def capture(self,files=None,observations=None):
        files={'state.json':b'{"step":1}'} if files is None else files
        with patch('granjita.snapshots.verify_identity'),patch('granjita.snapshots.query',return_value='1'),patch('granjita.snapshots.list_files',return_value=list(files)),patch('granjita.snapshots.read_file',side_effect=lambda row,name:files[name]),patch('granjita.snapshots.collect_inventory',return_value=observations or []),patch('granjita.snapshots.DATA',Path(self.temp.name)):
            return capture(self.store,ROW)
    def test_snapshot_is_atomic_and_preserves_binary_and_manifest(self):
        identifier,state=self.capture()
        self.assertEqual(state,'Completo')
        snapshot=latest(self.store,'SERIAL01')
        self.assertEqual(snapshot['id'],identifier)
        self.assertEqual(digest(snapshot['manifest'].encode()),snapshot['sha256'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT content FROM checkpoint_files').fetchone()[0],b'{"step":1}')
    def restore(self,current):
        with patch('granjita.snapshots.verify_identity'),patch('granjita.snapshots.query',return_value='1'),patch('granjita.snapshots.safe_directory'),patch('granjita.snapshots.read_file',return_value=current),patch('granjita.snapshots.write_missing') as write,patch('granjita.snapshots.collect_inventory',return_value=[]):
            result=restore(self.store,ROW)
            return result,write.call_count
    def test_missing_is_recovered_but_changed_is_not_overwritten(self):
        self.capture()
        self.assertEqual(self.restore(None)[1],1)
        result,count=self.restore(b'new state')
        self.assertEqual(count,0);self.assertIn('1 diferentes conservados',result)
        self.assertEqual(self.restore(b'{"step":1}')[1],0)
    def test_corrupt_file_blocks_all_writes(self):
        self.capture()
        with self.store.connect() as db:db.execute('UPDATE checkpoint_files SET content=?',(b'corrupt',))
        with self.assertRaises(ValueError):self.restore(None)
    def test_identity_failure_precedes_capture(self):
        with patch('granjita.snapshots.verify_identity',side_effect=ValueError('wrong board')):
            with self.assertRaises(ValueError):capture(self.store,ROW)
        self.assertIsNone(latest(self.store,'SERIAL01'))
    def test_paths_are_bounded_to_managed_names(self):
        for name in ['../state.json','a/b.txt','secret.xml','x;bad.txt','/sdcard/x.json']:
            with self.assertRaises(ValueError):filename(name)
    def test_partial_does_not_replace_complete_baseline(self):
        good,_=self.capture()
        _,state=self.capture(observations=[dict(field='Android',state='Error',value='offline')])
        self.assertEqual(state,'Parcial');self.assertEqual(latest(self.store,'SERIAL01')['id'],good)
    def test_incomplete_boot_does_not_write(self):
        self.capture()
        with patch('granjita.snapshots.verify_identity'),patch('granjita.snapshots.query',return_value='0'),patch('granjita.snapshots.write_missing') as write:
            self.assertIn('Esperando',restore(self.store,ROW))
            write.assert_not_called()

    def test_corrupt_manifest_is_rejected(self):
        self.capture()
        with self.store.connect() as db:db.execute("UPDATE device_checkpoints SET manifest='{}'")
        with patch('granjita.snapshots.verify_identity'):
            with self.assertRaises(ValueError):restore(self.store,ROW)

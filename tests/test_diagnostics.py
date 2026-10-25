from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
from granjita import diagnostics as d


class DiagnosticsTests(TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'traces.sqlite3'
        patcher=patch('granjita.diagnostics.DB_PATH',self.path);patcher.start();self.addCleanup(patcher.stop)
    def test_parallel_children_keep_run_parent_and_task(self):
        @d.traced('test.child')
        def child(row):return 'PRIVATE RESPONSE'
        with d.span('test.parent',task_id='TASK01') as run:
            with ThreadPoolExecutor(max_workers=2) as pool:list(d.context_map(pool,child,[dict(id='DEVICE01',hardware_serial='SERIAL01',port=5037,serial='192.0.2.1:5555')]*2))
        rows=d.read_events(run,include_tests=True)
        self.assertEqual(len({r['run_id'] for r in rows}),1)
        self.assertTrue(all(r['task_id']=='TASK01' for r in rows))
        children=[r for r in rows if r['process']=='test.child' and r['phase']=='start']
        self.assertEqual(len(children),2)
        self.assertTrue(all(r['parent_id'] for r in children))
        self.assertNotIn('PRIVATE RESPONSE',json.dumps(rows))
    def test_failure_has_frames_but_not_message_or_secrets(self):
        secret='VeryPrivatePassword123'
        with self.assertRaises(RuntimeError):
            with d.span('test.failure'):
                d.emit('test.failure','input',password=secret,comment=secret,token=secret)
                raise RuntimeError('Authorization token='+secret)
        rows=d.read_events(include_tests=True)
        self.assertNotIn(secret,json.dumps(rows))
        error=next(r for r in rows if r['status']=='error')
        self.assertEqual(error['metadata']['error_class'],'RuntimeError')
        self.assertIn('frames',error['metadata']);self.assertIn('fingerprint',error['metadata'])
        self.assertGreaterEqual(error['duration_ms'],0)
    def test_feedback_links_to_execution_and_roundtrips(self):
        with d.span('test.operation') as run:pass
        d.add_feedback(run,'Se observó espera larga','Terminar en menos tiempo')
        self.assertEqual(d.feedback(run)[0]['note'],'Se observó espera larga')
        with self.assertRaises(ValueError):d.add_feedback('missing','nota','')
    def test_trace_failure_does_not_fail_operation(self):
        @d.traced('test.no_storage')
        def operation():return 42
        with patch('granjita.diagnostics.database',side_effect=OSError('disk unavailable')):
            self.assertEqual(operation(),42)
        self.assertGreater(d.health()['dropped'],0)
    def test_unit_test_events_are_excluded_from_default_view(self):
        with d.span('test.source'):pass
        self.assertTrue(d.read_events(include_tests=True))
        import sys
        self.assertTrue(all(r['source']=='test' for r in d.read_events(include_tests=True)),repr(sys.argv))
        self.assertEqual(d.read_events(),[])

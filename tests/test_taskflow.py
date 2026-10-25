from unittest import TestCase
from unittest.mock import patch,MagicMock
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime,timedelta
from granjita.taskflow import validate_parameters,window_state,GT,run_flow
from granjita.automation import JobStore,PACKAGE,ELEMENT


def parameters(count=2,start=None,end=None):return dict(count=count,scroll_after_like=True,start_at=start,end_at=end)

class TaskFlowTests(TestCase):
    def test_window_and_bounds(self):
        start=datetime(2026,10,24,18,tzinfo=GT);end=start+timedelta(minutes=10)
        p=parameters(start=start.isoformat(),end=end.isoformat())
        self.assertEqual(window_state(p,start-timedelta(seconds=1)),'waiting')
        self.assertEqual(window_state(p,start),'ready')
        self.assertEqual(window_state(p,end),'expired')
        for invalid in [parameters(count=13),parameters(count=True),parameters(start=end.isoformat(),end=start.isoformat()),parameters(start=start.isoformat(),end=(end+timedelta(days=2)).isoformat())]:
            with self.assertRaises(ValueError):validate_parameters(invalid)
    def test_flow_verifies_two_targets_and_scrolls(self):
        session=MagicMock();session.text.side_effect=['ME GUSTA: NO','ME GUSTA: SI','ME GUSTA: SI','ME GUSTA: SI']
        calls=[];source_counter=[0];texts=iter(['ME GUSTA: NO','ME GUSTA: SI','ME GUSTA: SI','ME GUSTA: SI'])
        def call(method,path,data=None):
            calls.append(path)
            if path=='/appium/device/current_package':return PACKAGE
            if path=='/screenshot':return 'cHJ1ZWJh'
            if path=='/element':return {ELEMENT:'button'}
            if path.endswith('/rect'):return dict(x=1,y=10,width=20,height=10)
            if path.endswith('/enabled'):return True
            if path.endswith('/text'):return next(texts)
            if path=='/source':
                source_counter[0]+=1
                return f'<hierarchy><node content-desc="lab_like_01" bounds="{source_counter[0]}" /></hierarchy>'
            if path=='/execute/sync':return True
            return {}
        session.call.side_effect=call
        context=MagicMock();context.__enter__.return_value=session
        events=[]
        with TemporaryDirectory() as folder,patch('granjita.taskflow.DATA',Path(folder)),patch('granjita.taskflow.Session',return_value=context):
            result=run_flow({},'test',parameters(),audit=lambda kind,data:events.append((kind,data)))
        self.assertEqual(calls.count('/element/button/click'),1)
        self.assertEqual([data['target'] for kind,data in events if kind=='verified'],['lab_like_01','lab_like_02'])
        self.assertEqual(sum(kind=='scroll' for kind,data in events),2)
        self.assertIn('1 likes nuevos',result)
    def test_expired_window_does_not_open_session(self):
        start=datetime(2020,1,1,tzinfo=GT)
        with patch('granjita.taskflow.Session') as session:
            with self.assertRaises(Exception):run_flow({},'test',parameters(start=start.isoformat(),end=(start+timedelta(minutes=1)).isoformat()))
            session.assert_not_called()
    def test_metrics_count_each_card_once(self):
        row=dict(id='d',display_name='Test',hardware_serial='TESTSERIAL',port=5037,serial='192.0.2.1:5555')
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3');task=jobs.create([row],'','lab_like_flow',parameters())[0]
            for target,outcome in [('lab_like_01','applied'),('lab_like_02','already_marked')]:
                jobs.like_event(task['id'],'started',dict(target=target))
                jobs.like_event(task['id'],'verified',dict(target=target,outcome=outcome))
            jobs.like_event(task['id'],'started',dict(target='lab_like_01'))
            metrics=jobs.like_metrics()
            self.assertEqual(metrics['scheduled'],1);self.assertEqual(metrics['processed'],2)
            self.assertEqual(metrics['applied'],1);self.assertEqual(metrics['already_marked'],1)
    def test_worker_expires_without_opening_device(self):
        from granjita.automation_ui import BatchWorker
        row=dict(id='d',display_name='Test',hardware_serial='TESTSERIAL',port=5037,serial='192.0.2.1:5555')
        start=datetime(2020,1,1,tzinfo=GT)
        p=parameters(start=start.isoformat(),end=(start+timedelta(minutes=1)).isoformat())
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3');tasks=jobs.create([row],'','lab_like_flow',p)
            with patch('granjita.automation_ui.run_flow') as execute:
                BatchWorker(jobs,tasks).run()
                execute.assert_not_called()
            self.assertEqual(jobs.tasks()[0]['status'],'Expirado')
            self.assertEqual(jobs.like_metrics()['processed'],0)

    def test_scheduled_worker_starts_only_when_window_ready(self):
        from granjita.automation_ui import BatchWorker
        row=dict(id='d',display_name='Test',hardware_serial='TESTSERIAL',port=5037,serial='192.0.2.1:5555')
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3');tasks=jobs.create([row],'','lab_like_flow',parameters())
            with patch('granjita.automation_ui.window_state',side_effect=['waiting','ready','ready']),patch('granjita.automation_ui.run_flow',return_value='Verificado') as execute:
                BatchWorker(jobs,tasks).run()
                execute.assert_called_once()
            self.assertEqual(jobs.tasks()[0]['status'],'Completado')
            statuses=[e['data']['status'] for e in jobs.like_report()[0]['events'] if e['kind']=='task_status']
            self.assertEqual(statuses,['Programado','Ejecutando','Completado'])

    def test_verification_reacquires_only_for_reading(self):
        from granjita.taskflow import verify_marked
        from granjita.automation import AutomationError
        session=MagicMock()
        session.call.side_effect=[AutomationError('stale element'),{ELEMENT:'new-button'},'ME GUSTA: SI']
        with patch('granjita.taskflow.time.sleep'):
            verify_marked(session,'old-button','lab_like_03')
        self.assertFalse(any('/click' in call.args[1] for call in session.call.call_args_list))

    def test_unstable_button_never_reaches_click(self):
        from granjita.taskflow import stable_target
        session=MagicMock();session.call.return_value={ELEMENT:'button'}
        with self.assertRaises(Exception):stable_target(session,'lab_like_02',lambda:None,timeout=0)
        self.assertFalse(any('/click' in call.args[1] for call in session.call.call_args_list))
    def test_stabilization_waits_until_coordinates_stop_changing(self):
        from granjita.taskflow import stable_target
        session=MagicMock();rects=iter([dict(x=1,y=10,width=20,height=10),dict(x=1,y=20,width=20,height=10),dict(x=1,y=20,width=20,height=10)])
        def call(method,path,data=None):
            if path=='/element':return {ELEMENT:'button'}
            if path.endswith('/rect'):return next(rects)
            if path.endswith('/enabled'):return True
        session.call.side_effect=call
        with patch('granjita.taskflow.time.sleep'):
            self.assertEqual(stable_target(session,'lab_like_03',lambda:None),'button')
        self.assertEqual(sum(c.args[1].endswith('/rect') for c in session.call.call_args_list),3)

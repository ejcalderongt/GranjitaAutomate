from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from granjita.automation import JobStore

ROW=dict(id='device',display_name='Test',hardware_serial='TESTSERIAL',port=5037,serial='192.0.2.1:5555',rack='R01',slot=1)

class LikeMetricsTests(TestCase):
    def test_counts_tasks_not_events_and_keeps_destination(self):
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3')
            tasks=jobs.create([ROW,ROW,ROW,ROW],'','lab_like')
            for t in tasks[:3]:jobs.like_event(t['id'],'started',{})
            jobs.like_event(tasks[0]['id'],'verified',dict(outcome='applied'))
            jobs.like_event(tasks[0]['id'],'verified',dict(outcome='applied'))
            jobs.like_event(tasks[1]['id'],'verified',dict(outcome='already_marked'))
            jobs.update(tasks[3]['id'],'Cancelado','Sin iniciar')
            metrics=jobs.like_metrics()
            self.assertEqual(metrics['processed'],3)
            self.assertEqual(metrics['applied'],1)
            self.assertEqual(metrics['already_marked'],1)
            self.assertEqual(metrics['unconfirmed'],1)
            context=jobs.like_report()[0]['context']
            self.assertEqual(context['hardware_serial'],'TESTSERIAL')
            self.assertEqual(context['target'],'lab_like_01')
            self.assertEqual(context['rack'],'R01')
    def test_historical_success_is_not_invented_as_new_like(self):
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3')
            task=jobs.create([ROW],'','lab_like')[0]
            with jobs.db() as db:db.execute('DELETE FROM like_context')
            jobs.update(task['id'],'Completado','Like local aplicado y verificado.')
            metrics=jobs.like_metrics()
            self.assertEqual(metrics['historical_unmeasured'],1)
            self.assertEqual(metrics['applied'],0)
            with self.assertRaises(ValueError):jobs.like_event(task['id'],'started',{})

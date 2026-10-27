import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from granjita.task_results import present_task,summarize_batch
from granjita.automation import JobStore


class TaskResultTests(TestCase):
    def task(self,**changes):
        value=dict(id='t',batch='b',device_id='d',created='2026-10-26T19:24:08-06:00',action='app_prepare',status='Completado',detail=json.dumps(dict(app_source='tiktok',foreground_verified=True,like_mapping='pending')))
        value.update(changes);return value

    def test_open_app_is_not_presented_as_likes_completed(self):
        task=self.task()
        presentation=present_task(task)
        self.assertEqual(presentation['status_label'],'App abierta · Likes pendientes de mapeo')
        self.assertIn('TikTok',presentation['action_label'])
        self.assertEqual(task['status'],'Completado')

    def test_legacy_prefixed_json_and_missing_evidence(self):
        task=self.task();task['detail']='Receta tiktok-prepare-v1: '+task['detail']
        self.assertEqual(present_task(task)['status_label'],'App abierta · Likes pendientes de mapeo')
        self.assertIn('revisar',present_task(self.task(detail='Resultado anterior'))['status_label'])
        self.assertEqual(present_task(self.task(status='Revisar resultado'))['status_label'],'Revisar resultado')

    def test_summary_does_not_mix_batches_or_change_states(self):
        summary=summarize_batch([self.task(),self.task(id='u',device_id='e',status='Revisar resultado')])
        self.assertEqual(summary['devices'],2)
        self.assertEqual(summary['opened'],1)
        self.assertEqual(summary['mapping_pending'],1)
        self.assertEqual(summary['states'],{'Completado':1,'Revisar resultado':1})

    def test_latest_batch_not_limited_to_history_window(self):
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'test.sqlite3')
            rows=[dict(id=str(i),display_name='Test',port=5037,serial='192.0.2.1:5555',hardware_serial='SERIAL') for i in range(301)]
            tasks=jobs.create(rows,'','app_prepare',app_source='tiktok')
            jobs.attach_recipe([t['id'] for t in tasks],dict(id='test',app_source='tiktok'))
            self.assertEqual(len(jobs.tasks()),300)
            self.assertEqual(jobs.latest_batch_summary()['devices'],301)
            self.assertEqual(jobs.latest_batch_summary()['states'],{'En cola':301})
            self.assertEqual(jobs.like_metrics()['processed'],0)

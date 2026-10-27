import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from granjita.app_sources import prepare_app,source_profile,require_like_mapping,foreground_package
from granjita.automation import JobStore
from granjita.recipes import load_recipe,execute_recipe
from granjita.core import ROOT

ROW=dict(id='test',display_name='Test',port=5038,serial='192.0.2.1:5555',hardware_serial='TESTSERIAL',status='Validado',identity_state='Serial leído')
PACKAGE='com.zhiliaoapp.musically'
FOCUS='mResumedActivity: ActivityRecord{abc u0 '+PACKAGE+'/.MainActivity t1}'


class AppSourceTests(unittest.TestCase):
    def test_already_open_is_not_launched(self):
        def shell(adb,serial,command):
            if command=='pm path '+PACKAGE:return 'package:/data/app/tiktok/base.apk'
            if command.startswith('pm path '):return ''
            if command=='dumpsys activity activities':return FOCUS
            self.fail('Unexpected command '+command)
        with patch('granjita.automation.validate_target'),patch('granjita.inventory.shell',side_effect=shell):
            result=prepare_app(ROW,'tiktok')
        self.assertFalse(result['launched']);self.assertTrue(result['foreground_verified'])

    def test_closed_app_launched_without_install_or_like(self):
        calls=[];focus=iter(['mResumedActivity: other/.Main',FOCUS])
        def shell(adb,serial,command):
            calls.append(command)
            if command=='pm path '+PACKAGE:return 'package:/data/app/base.apk'
            if command.startswith('pm path '):return ''
            if command=='dumpsys activity activities':return next(focus)
            if command.startswith('cmd package resolve-activity'):return 'priority=0\n'+PACKAGE+'/.MainActivity'
            if command.startswith('am start -W -n '):return 'Status: ok'
            self.fail('Unexpected command '+command)
        with patch('granjita.automation.validate_target'),patch('granjita.inventory.shell',side_effect=shell):
            self.assertTrue(prepare_app(ROW,'tiktok')['launched'])
        self.assertEqual(sum(c.startswith('am start ') for c in calls),1)
        self.assertFalse(any('input ' in c or 'install ' in c for c in calls))

    def test_missing_app_never_launched(self):
        with patch('granjita.automation.validate_target'),patch('granjita.inventory.shell',return_value='') as shell:
            with self.assertRaisesRegex(Exception,'no está instalada'):prepare_app(ROW,'tiktok')
        self.assertEqual(shell.call_count,2)

    def test_ambiguous_variants_rejected(self):
        with patch('granjita.automation.validate_target'),patch('granjita.inventory.shell',return_value='package:/base.apk'):
            with self.assertRaisesRegex(Exception,'varias variantes'):prepare_app(ROW,'tiktok')

    def test_unknown_mapping_cannot_create_like_tasks(self):
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'test.sqlite3')
            with self.assertRaises(ValueError):jobs.create([ROW],'','lab_like_flow',{},app_source='tiktok')
            self.assertEqual(jobs.tasks(),[])
            tasks=jobs.create([ROW],'','app_prepare',app_source='tiktok')
            self.assertEqual(tasks[0]['app_source'],'tiktok')
            self.assertEqual(jobs.like_metrics()['scheduled'],0)

    def test_profiles_and_legacy_recipe(self):
        self.assertEqual(load_recipe(ROOT/'recipes/lab-like-flow.json')['_app_source_snapshot']['id'],'laboratorio')
        self.assertEqual(load_recipe(ROOT/'recipes/tiktok-prepare.json')['app_source'],'tiktok')
        with self.assertRaises(ValueError):source_profile('../../bad')
        with self.assertRaises(ValueError):require_like_mapping('tiktok')
        self.assertEqual(require_like_mapping('laboratorio')['like_adapter'],'lab_like_v1')

    def test_cli_refuses_unmapped_source_before_creating_jobs(self):
        recipe=load_recipe(ROOT/'recipes/lab-like-flow.json');recipe['app_source']='tiktok'
        with patch('granjita.recipes.JobStore') as jobs:
            with self.assertRaises(ValueError):execute_recipe(recipe,[ROW])
            jobs.assert_not_called()

    def test_foreground_ignores_historical_activities(self):
        self.assertIsNone(foreground_package('Hist #0: '+PACKAGE+'/.MainActivity'))
        self.assertEqual(foreground_package(FOCUS),PACKAGE)

    def test_cancel_before_device_queries(self):
        with patch('granjita.automation.validate_target') as validate:
            with self.assertRaises(Exception):prepare_app(ROW,'tiktok',lambda:True)
            validate.assert_not_called()

    def test_independent_postcheck_never_opens_the_app(self):
        from granjita.app_sources import verify_app_open
        for focus,wanted in [(FOCUS,'open'),('mResumedActivity: com.other.app/.Main','not_foreground'),('','unconfirmed')]:
            with patch('granjita.automation.validate_target'),patch('granjita.inventory.shell',return_value=focus) as shell:
                result=verify_app_open(ROW,'tiktok',task_id='test')
            self.assertEqual(result['state'],wanted)
            self.assertEqual(shell.call_count,1)
            self.assertEqual(shell.call_args.args[2],'dumpsys activity activities')
            self.assertFalse(result['interaction_ready'])

    def test_postcheck_records_history_without_changing_original_task(self):
        from granjita.automation_ui import VerificationWorker
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'test.sqlite3')
            tasks=jobs.create([ROW],'','app_prepare',app_source='tiktok')
            jobs.update(tasks[0]['id'],'Completado','original result')
            with patch('granjita.automation_ui.verify_app_open',return_value=dict(state='not_foreground',at='2026-10-26T20:00:00-06:00')) as verify:
                VerificationWorker(jobs,tasks).run()
                verify.assert_called_once()
            self.assertEqual(jobs.tasks()[0]['status'],'Completado')
            self.assertEqual(jobs.tasks()[0]['detail'],'original result')
            self.assertEqual(jobs.latest_batch_summary()['verification_states'],{'not_foreground':1})
            with patch('granjita.automation_ui.verify_app_open',return_value=dict(state='open',at='2026-10-26T20:01:00-06:00')):
                VerificationWorker(jobs,tasks).run()
            self.assertEqual(jobs.latest_batch_summary()['verification_states'],{'open':1})
            with jobs.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM app_verifications').fetchone()[0],2)
            self.assertEqual(jobs.like_metrics()['processed'],0)

    def test_postcheck_skips_cancelled_tasks_and_records_unreachable(self):
        from granjita.automation_ui import VerificationWorker
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'test.sqlite3')
            tasks=jobs.create([ROW,dict(ROW,id='other')],'','app_prepare',app_source='tiktok')
            jobs.update(tasks[0]['id'],'Cancelado')
            jobs.update(tasks[1]['id'],'Revisar resultado')
            with patch('granjita.automation_ui.verify_app_open',side_effect=RuntimeError('unreachable')) as verify:
                VerificationWorker(jobs,tasks).run()
                self.assertEqual(verify.call_count,1)
            self.assertEqual(jobs.latest_batch_summary()['verification_states'],{'not_executed':1,'error':1})

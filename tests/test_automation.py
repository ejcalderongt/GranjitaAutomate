from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from granjita.automation import JobStore,capabilities,validate_target,AutomationError,run_lab,PACKAGE


def target():
    return dict(id='test-id',display_name='Placa de prueba',port=5038,serial='192.0.2.1:5555',hardware_serial='TESTSERIAL01',status='Validado',identity_state='Serial leído')


class AutomationTests(TestCase):
    def test_capabilities_bind_to_correct_server_and_lab(self):
        caps=capabilities(target(),8301)
        self.assertEqual(caps['appium:adbPort'],5038)
        self.assertTrue(caps['appium:suppressKillServer'])
        self.assertEqual(caps['appium:appPackage'],PACKAGE)
        self.assertEqual(caps['appium:systemPort'],8301)

    def test_identity_is_rechecked_before_control(self):
        with patch('granjita.automation.shell',return_value='[ro.serialno]: [OTHERSERIAL]'):
            with self.assertRaises(AutomationError):
                validate_target(target())
        with self.assertRaises(AutomationError):
            validate_target(dict(target(),identity_state='Serial repetido: revisar'))

    def test_tasks_persist_and_do_not_auto_retry_uncertain_work(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'jobs.sqlite3'
            jobs=JobStore(path)
            tasks=jobs.create([target(),dict(target(),id='other-id')],'Prueba local')
            jobs.update(tasks[0]['id'],'Ejecutando')
            recovered=JobStore(path).tasks()
            self.assertEqual({t['status'] for t in recovered},{'Resultado incierto','Interrumpido'})
            self.assertEqual(len({t['id'] for t in recovered}),2)

    def test_comment_validation_precedes_session(self):
        with patch('granjita.automation.Session') as session:
            with self.assertRaises(AutomationError):
                run_lab(target(),'','test')
        session.assert_not_called()

    def test_recipe_snapshot_is_immutable_and_hashed(self):
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3')
            task=jobs.create([target()],'Prueba')[0]
            spec={'id':'lab-v1','parameters':{'comment':'Original'}}
            jobs.attach_recipe([task['id']],spec)
            spec['parameters']['comment']='Modificado'
            with jobs.db() as db:
                row=db.execute('SELECT * FROM task_recipes').fetchone()
                self.assertIn('Original',row['spec'])
                self.assertNotIn('Modificado',row['spec'])
                self.assertEqual(len(row['sha256']),64)

    def test_cancelled_task_performs_no_clicks(self):
        with patch('granjita.automation.Session') as session:
            with self.assertRaises(AutomationError):
                run_lab(target(),'Prueba','test',lambda:True)
        session.assert_not_called()

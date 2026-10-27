from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from granjita.inventory import FleetStore
from granjita.panda_ui import PandaDialog
from granjita.automation_ui import AutomationDialog
from granjita.automation import JobStore

APP=QApplication.instance() or QApplication([])


def settle(dialog):
    deadline=time.monotonic()+5
    while dialog.worker is not None and time.monotonic()<deadline:
        APP.processEvents()
        time.sleep(.01)
    if dialog.worker is not None:
        dialog.worker.wait(3000)
        APP.processEvents()
        raise AssertionError('La interfaz no liberó el trabajador.')


class GuiWorkerTests(TestCase):
    def tearDown(self):
        for widget in APP.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        APP.processEvents()

    def test_panda_dialog_finishes_and_displays_result(self):
        with TemporaryDirectory() as folder:
            store=FleetStore(Path(folder)/'inventory.sqlite3')
            with patch('granjita.panda_ui.DATA',Path(folder)),patch('granjita.panda_ui.list_devices',return_value=[dict(sort=1,name='Prueba',onlySerial='TESTSERIAL',serial='192.0.2.1:5555',mode=2)]):
                dialog=PandaDialog(store)
                settle(dialog)
                self.assertEqual(dialog.table.rowCount(),1)
                self.assertTrue(dialog.button.isEnabled())
                dialog.close()

    def exercise_lab(self,folder,run=False):
        row=dict(id='test-id',display_name='Prueba',port=5037,serial='192.0.2.1:5555',hardware_serial='TESTSERIAL',status='Validado',identity_state='Serial leído')
        jobs=JobStore(Path(folder)/'jobs.sqlite3')
        store=SimpleNamespace(fleet_devices=lambda:[row])
        with patch('granjita.automation_ui.JobStore',return_value=jobs),patch('granjita.automation_ui.runtime',return_value={}),patch('granjita.automation_ui.appium_status',return_value='Disponible'),patch('granjita.automation_ui.automate_status',return_value='Instalado'),patch('granjita.automation_ui.run_lab',return_value='Prueba verificada'),patch('granjita.automation_ui.run_flow',return_value='Flujo verificado'):
            dialog=AutomationDialog(store)
            if run:
                dialog.run_batch()
            else:
                dialog.probe()
            settle(dialog)
            if run:
                self.assertEqual(jobs.tasks()[0]['status'],'Completado')
            else:
                self.assertEqual(dialog.state.text(),'Instalado')
            dialog.close()

    def test_automate_probe_finishes_in_dialog(self):
        with TemporaryDirectory() as folder:
            self.exercise_lab(folder)

    def test_batch_finishes_in_dialog(self):
        with TemporaryDirectory() as folder:
            self.exercise_lab(folder,True)
    def test_startup_recovery_is_scheduled_after_scan_thread_finishes(self):
        from granjita.app import Window
        from unittest.mock import MagicMock
        with TemporaryDirectory() as folder:
            store=FleetStore(Path(folder)/'inventory.sqlite3')
            with patch('granjita.app.QTimer.singleShot') as schedule:
                window=Window(store)
                schedule.reset_mock()
                window.fresh=True
                window.worker=MagicMock()
                window.finished()
                self.assertIsNone(window.worker)
                self.assertFalse(window.startup_pending)
                self.assertEqual(schedule.call_args.args[0],0)
                self.assertEqual(schedule.call_args.args[1],window.recover_startup)
                schedule.reset_mock()
                window.worker=MagicMock()
                window.finished()
                schedule.assert_not_called()
            window.close()
    def test_builder_selects_count_and_captures_schedule(self):
        from datetime import timedelta
        from granjita.taskflow import clock_now
        from PySide6.QtCore import QDateTime,Qt
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3')
            rows=[dict(id=f'd{i}',display_name=f'Placa {i}',port=5037,serial=f'192.0.2.{i}:5555',hardware_serial=f'SERIAL{i:03}',status='Validado',identity_state='Serial leído') for i in range(1,13)]
            store=SimpleNamespace(fleet_devices=lambda:rows)
            with patch('granjita.automation_ui.JobStore',return_value=jobs):
                dialog=AutomationDialog(store)
                dialog.limit.setValue(10);dialog.select_count();dialog.count.setValue(4)
                self.assertEqual(len(dialog.checked()),10)
                self.assertIn('10 seleccionados',dialog.fleet_stats.text())
                dialog.mode.setCurrentIndex(1)
                now=clock_now()
                dialog.start_at.setDateTime(QDateTime.fromString((now+timedelta(minutes=1)).isoformat(),Qt.DateFormat.ISODate))
                dialog.end_at.setDateTime(QDateTime.fromString((now+timedelta(minutes=2)).isoformat(),Qt.DateFormat.ISODate))
                recipe=dialog.build_recipe()
                self.assertEqual(recipe['parameters']['count'],4)
                self.assertTrue(recipe['parameters']['scroll_after_like'])
                self.assertTrue(recipe['parameters']['start_at'].endswith('-06:00'))
                self.assertIsNotNone(recipe['parameters']['end_at'])
                dialog.close()

    def test_app_source_prepare_is_audited_without_counting_likes(self):
        import json
        from granjita.recipes import load_recipe
        from granjita.core import ROOT
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3')
            row=dict(id='test-id',display_name='Prueba',port=5037,serial='192.0.2.1:5555',hardware_serial='TESTSERIAL',status='Validado',identity_state='Serial leído')
            store=SimpleNamespace(fleet_devices=lambda:[row])
            with patch('granjita.automation_ui.JobStore',return_value=jobs),patch('granjita.automation_ui.verify_app_open',return_value=dict(state='open',foreground_verified=True)),patch('granjita.automation_ui.prepare_app',return_value=dict(foreground_verified=True,interaction_ready=False)) as prepare:
                dialog=AutomationDialog(store)
                dialog.app_source.setCurrentIndex(dialog.app_source.findData('tiktok'))
                self.assertFalse(dialog.run_button.isEnabled())
                self.assertEqual(dialog.build_recipe()['app_source'],'tiktok')
                dialog.prepare_selected_app();settle(dialog)
                self.assertEqual(jobs.tasks()[0]['action'],'app_prepare')
                self.assertEqual(jobs.tasks()[0]['status'],'Completado')
                self.assertEqual(jobs.like_metrics()['scheduled'],0)
                with jobs.db() as db:
                    spec=json.loads(db.execute('SELECT spec FROM task_recipes').fetchone()[0])
                self.assertEqual(spec['app_source'],'tiktok')
                self.assertEqual(spec['_app_source_snapshot']['mapping_status'],'pending')
                self.assertEqual(spec['action'],'app_prepare')
                self.assertEqual(prepare.call_args.args[1],'tiktok')
                self.assertFalse(dialog.run_button.isEnabled())
                dialog.app_source.setCurrentIndex(dialog.app_source.findData('laboratorio'))
                self.assertTrue(dialog.run_button.isEnabled())
                dialog.recipe=load_recipe(ROOT/'recipes/tiktok-prepare.json');dialog.display_recipe()
                self.assertEqual(dialog.build_recipe()['action'],'app_prepare')
                dialog.close()

    def test_logs_button_and_finished_batch_summary(self):
        with TemporaryDirectory() as folder:
            jobs=JobStore(Path(folder)/'jobs.sqlite3')
            row=dict(id='test',display_name='Test',port=5037,serial='192.0.2.1:5555',hardware_serial='TESTSERIAL',status='Validado',identity_state='Serial leído')
            store=SimpleNamespace(fleet_devices=lambda:[row])
            with patch('granjita.automation_ui.JobStore',return_value=jobs),patch('granjita.automation_ui.verify_app_open',return_value=dict(state='open',foreground_verified=True)),patch('granjita.automation_ui.prepare_app',return_value=dict(app_source='tiktok',foreground_verified=True,like_mapping='pending')):
                dialog=AutomationDialog(store)
                dialog.app_source.setCurrentIndex(dialog.app_source.findData('tiktok'))
                dialog.prepare_selected_app();settle(dialog)
                self.assertIn('LOTE TERMINADO',dialog.batch_summary.text())
                self.assertIn('Apps abiertas: 1 de 1',dialog.batch_summary.text())
                self.assertIn('VERIFICACIÓN POSTERIOR TERMINADA',dialog.batch_summary.text())
                self.assertIn('Abiertas ahora: 1',dialog.batch_summary.text())
                self.assertTrue(dialog.verify_button.isEnabled())
                self.assertIn('LOTE TERMINADO',dialog.state.text())
                with patch('granjita.diagnostics.clear_traces',return_value=dict(removed=12)) as clear:
                    dialog.clear_logs_button.click()
                    clear.assert_called_once()
                self.assertIn('Logs limpios',dialog.state.text())
                self.assertEqual(len(jobs.tasks()),1)
                dialog.close()

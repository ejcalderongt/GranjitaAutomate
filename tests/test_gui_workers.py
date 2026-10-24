from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
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
        with patch('granjita.automation_ui.JobStore',return_value=jobs),patch('granjita.automation_ui.runtime',return_value={}),patch('granjita.automation_ui.appium_status',return_value='Disponible'),patch('granjita.automation_ui.automate_status',return_value='Instalado'),patch('granjita.automation_ui.run_lab',return_value='Prueba verificada'):
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

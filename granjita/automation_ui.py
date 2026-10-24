"""Panel de pruebas por lote, aislado de aplicaciones sociales reales."""
import threading
import time
from PySide6.QtCore import QThread,Signal,Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QTableWidgetItem,QHeaderView,QLineEdit,QMessageBox,QPlainTextEdit,QAbstractItemView)
from .automation import JobStore,run_lab,appium_status,runtime,automate_status,open_automate


class BatchWorker(QThread):
    changed=Signal()
    def __init__(self,jobs,tasks):
        super().__init__()
        self.jobs,self.tasks=jobs,tasks
        self.cancel=threading.Event()
        self.pause=threading.Event()

    def run(self):
        for task in self.tasks:
            while self.pause.is_set() and not self.cancel.is_set():
                time.sleep(.2)
            if self.cancel.is_set():
                self.jobs.update(task['id'],'Cancelado','No se inició la tarea.')
                self.changed.emit()
                continue
            self.jobs.update(task['id'],'Ejecutando')
            self.changed.emit()
            try:
                result=run_lab(task['row'],task['comment'],task['id'],self.cancel.is_set)
                self.jobs.update(task['id'],'Completado',result)
            except Exception as exc:
                self.jobs.update(task['id'],'Revisar resultado',str(exc))
            self.changed.emit()


class ProbeWorker(QThread):
    result=Signal(str)
    def __init__(self,row,launch=False):
        super().__init__()
        self.row,self.launch=row,launch
    def run(self):
        try:
            result=open_automate(self.row) if self.launch else automate_status(self.row)
        except Exception as exc:
            result=str(exc)
        self.result.emit(result)


class AutomationDialog(QDialog):
    def __init__(self,store,preferred=None,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Laboratorio de automatización · v1')
        self.resize(1200,800)
        self.jobs=JobStore()
        self.worker=None
        self.rows=[]
        identifiers=set()
        for row in store.fleet_devices():
            if row['status']=='Validado' and row['identity_state']=='Serial leído' and row['id'] not in identifiers:
                self.rows.append(row)
                identifiers.add(row['id'])
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Laboratorio · Appium + UiAutomator2 + adaptador Automate'))
        intro=QLabel('Este lote instala/abre Granjita Lab y verifica un like, un comentario y un scroll LOCALES. No abre X ni publica en redes.\nSelección por identidad física; ejecución secuencial, una sesión por vez. Pausa y cancelación se aplican entre pasos/dispositivos.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        try:
            runtime()
            tools='Appium y driver preparados'
        except Exception as exc:
            tools=str(exc)
        self.state=QLabel(tools+' · '+appium_status())
        layout.addWidget(self.state)
        self.devices=QTableWidget(len(self.rows),4)
        self.devices.setHorizontalHeaderLabels(['Usar','Placa','Serial físico','Servidor ADB'])
        self.devices.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.devices.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.devices.setMaximumHeight(210)
        selected=preferred['id'] if preferred else self.rows[0]['id'] if self.rows else None
        for i,row in enumerate(self.rows):
            check=QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if row['id']==selected else Qt.CheckState.Unchecked)
            self.devices.setItem(i,0,check)
            for j,value in enumerate([row['display_name'],row['hardware_serial'],str(row['port'])],1):
                self.devices.setItem(i,j,QTableWidgetItem(value))
        layout.addWidget(self.devices)
        self.comment=QLineEdit('Gracias por completar la prueba del laboratorio.')
        self.comment.setMaxLength(280)
        layout.addWidget(QLabel('Comentario local de prueba:'))
        layout.addWidget(self.comment)
        buttons=QHBoxLayout()
        for text,callback in [('Ejecutar prueba local',self.run_batch),('Pausar / continuar',self.toggle_pause),('Cancelar lote',self.cancel_batch),('Diagnosticar Automate',self.probe),('Abrir Automate',lambda:self.probe(True))]:
            button=QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.results=QTableWidget(0,5)
        self.results.setHorizontalHeaderLabels(['Placa','Puerto','Estado','Actualizado','Resultado'])
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.itemSelectionChanged.connect(self.details)
        layout.addWidget(self.results,1)
        self.stats=QLabel()
        layout.addWidget(self.stats)
        self.detail=QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(120)
        layout.addWidget(self.detail)
        self.refresh()

    def checked(self):
        return [r for i,r in enumerate(self.rows) if self.devices.item(i,0).checkState()==Qt.CheckState.Checked]

    def run_batch(self):
        if self.worker:
            return
        rows=self.checked()
        if not rows:
            QMessageBox.information(self,'Selecciona una placa','Marca al menos una placa sin conflicto.')
            return
        if not self.comment.text().strip():
            return
        if len(rows)>1 and not any(t['status']=='Completado' for t in self.jobs.tasks()):
            QMessageBox.information(self,'Primero una prueba piloto','Completa una prueba en una sola placa antes de ejecutar un lote.')
            return
        tasks=self.jobs.create(rows,self.comment.text().strip())
        self.worker=BatchWorker(self.jobs,tasks)
        self.worker.changed.connect(self.refresh)
        self.worker.finished.connect(self.finished)
        self.state.setText(f'Ejecutando lote local de {len(tasks)} placa(s).')
        self.refresh()
        self.worker.start()

    def refresh(self):
        self.tasks=self.jobs.tasks()
        if hasattr(self,'stats'):
            completed=sum(t['status']=='Completado' for t in self.tasks)
            pending=sum(t['status'] in ('En cola','Ejecutando') for t in self.tasks)
            self.stats.setText(f'Últimas {len(self.tasks)} tareas · {completed} completadas · {pending} en curso/cola · {len(self.tasks)-completed-pending} para revisar o interrumpidas')
        self.results.setRowCount(len(self.tasks))
        for i,task in enumerate(self.tasks):
            for j,value in enumerate([task['name'],str(task['port']),task['status'],task['updated'][11:19],task['detail']]):
                item=QTableWidgetItem(value)
                item.setToolTip(value)
                self.results.setItem(i,j,item)

    def details(self):
        index=self.results.currentRow()
        if 0<=index<len(self.tasks):
            task=self.tasks[index]
            self.detail.setPlainText(f"Tarea: {task['id']}\nLote: {task['batch']}\n{task['status']}\n{task['detail']}")

    def toggle_pause(self):
        if isinstance(self.worker,BatchWorker):
            if self.worker.pause.is_set():
                self.worker.pause.clear()
                self.state.setText('Continuando el lote local.')
            else:
                self.worker.pause.set()
                self.state.setText('Pausa solicitada: se aplicará al terminar la placa en curso.')

    def cancel_batch(self):
        if isinstance(self.worker,BatchWorker):
            self.worker.cancel.set()
            self.state.setText('Cancelación solicitada. Se conservarán los resultados de los pasos ya ejecutados.')

    def probe(self,launch=False):
        if self.worker:
            return
        rows=self.checked()
        if len(rows)!=1:
            QMessageBox.information(self,'Selecciona una placa','Para Automate selecciona exactamente una placa.')
            return
        self.worker=ProbeWorker(rows[0],launch)
        self.worker.result.connect(self.state.setText)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def finished(self):
        if isinstance(self.worker,BatchWorker):
            self.state.setText('Lote local finalizado. Consulta el estado y la evidencia de cada tarea.')
        self.worker.deleteLater()
        self.worker=None
        self.refresh()

    def closeEvent(self,event):
        if self.worker:
            QMessageBox.information(self,'Proceso en curso','Cancela el lote y espera a que termine la sesión antes de cerrar.')
            event.ignore()
        else:
            event.accept()

    def reject(self):
        if self.worker:
            QMessageBox.information(self,'Proceso en curso','Cancela y espera a que termine la sesión antes de cerrar el panel.')
            return
        super().reject()

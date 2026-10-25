"""Panel de pruebas por lote, aislado de aplicaciones sociales reales."""
import threading
import time
import copy
from pathlib import Path
from datetime import timedelta
from PySide6.QtCore import QThread,Signal,Qt,QTimer,QDateTime
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QTableWidgetItem,QHeaderView,QLineEdit,QMessageBox,QPlainTextEdit,QAbstractItemView,QFileDialog,QWidget,QGroupBox,QFormLayout,QSpinBox,QCheckBox,QComboBox,QDateTimeEdit,QTabWidget)
from .taskflow import run_flow,validate_parameters,window_state,clock_now
from .automation import JobStore,run_lab,run_like,appium_status,runtime,automate_status,open_automate


class BatchWorker(QThread):
    changed=Signal()
    def __init__(self,jobs,tasks):
        super().__init__()
        self.jobs,self.tasks=jobs,tasks
        self.cancel=threading.Event()
        self.pause=threading.Event()

    def run(self):
        for task in self.tasks:
            parameters=task.get('parameters')
            if parameters and window_state(parameters)=='waiting':
                self.jobs.update(task['id'],'Programado','Esperando horario de Guatemala; mantener el programa abierto.')
                self.changed.emit()
            while parameters and window_state(parameters)=='waiting' and not self.cancel.is_set():
                self.cancel.wait(.2)
            while self.pause.is_set() and not self.cancel.is_set() and (not parameters or window_state(parameters)!='expired'):
                time.sleep(.2)
            if self.cancel.is_set():
                self.jobs.update(task['id'],'Cancelado','No se inició la tarea.')
                self.changed.emit()
                continue
            if parameters and window_state(parameters)=='expired':
                self.jobs.update(task['id'],'Expirado','No se inició: terminó la ventana de ejecución.')
                self.changed.emit();continue
            self.jobs.update(task['id'],'Ejecutando')
            self.changed.emit()
            try:
                if task.get('action')=='lab_like_flow':
                    result=run_flow(task['row'],task['id'],parameters,lambda:self.stop_check(parameters),audit=lambda kind,data:self.jobs.like_event(task['id'],kind,data))
                else:result=run_like(task['row'],task['id'],self.cancel.is_set,audit=lambda kind,data:self.jobs.like_event(task['id'],kind,data)) if task.get('action')=='lab_like' else run_lab(task['row'],task['comment'],task['id'],self.cancel.is_set)
                self.jobs.update(task['id'],'Completado',result)
            except Exception as exc:
                self.jobs.update(task['id'],'Revisar resultado',str(exc))
            self.changed.emit()


    def stop_check(self,parameters):
        while self.pause.is_set() and not self.cancel.is_set() and window_state(parameters)!='expired':
            self.cancel.wait(.2)
        return self.cancel.is_set()


class FleetWorker(QThread):
    result=Signal(dict)
    error=Signal(str)
    def __init__(self,ports):
        super().__init__();self.ports=ports
    def run(self):
        from .inventory import scan_fleet
        try:self.result.emit(scan_fleet(self.ports))
        except Exception as exc:self.error.emit(str(exc))


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
        self.setWindowTitle('Tareas y recetas · GranjitaAutomate 2.9')
        self.resize(1160,820)
        self.store=store
        self.jobs=JobStore()
        self.worker=None
        self.rows=[]
        self.online=0
        self.loaded_devices=False
        self.confirmed=False
        self.checked_at=None
        layout=QVBoxLayout(self)
        title=QLabel('Crear tarea');title.setStyleSheet('font-size:23px;font-weight:600;');layout.addWidget(title)
        self.fleet_stats=QLabel();self.fleet_stats.setStyleSheet('background:#e8f3ed;padding:12px;font-size:15px;');layout.addWidget(self.fleet_stats)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        task_page=QWidget();task_layout=QVBoxLayout(task_page);self.tabs.addTab(task_page,'Tarea')
        selection=QHBoxLayout()
        self.limit=QSpinBox();self.limit.setRange(1,999);self.limit.setValue(10)
        selection.addWidget(QLabel('Cantidad de dispositivos:'));selection.addWidget(self.limit)
        for label,callback in [('Seleccionar cantidad',self.select_count),('Todos',self.select_all),('Ninguno',self.select_none),('Actualizar conexiones',self.refresh_connections)]:
            button=QPushButton(label);button.clicked.connect(callback);selection.addWidget(button)
        task_layout.addLayout(selection)
        self.devices=QTableWidget(0,4)
        self.devices.setHorizontalHeaderLabels(['Usar','Dispositivo / posición','Serial físico','Origen ADB'])
        self.devices.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.devices.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.devices.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.devices.setMinimumHeight(160);self.devices.setMaximumHeight(240)
        self.devices.itemChanged.connect(lambda item:self.selection_summary())
        task_layout.addWidget(self.devices)
        config=QGroupBox('Receta');form=QFormLayout(config)
        self.task_name=QLineEdit('Likes y scroll de laboratorio');self.task_name.setMaxLength(1000)
        self.count=QSpinBox();self.count.setRange(1,12);self.count.setValue(3)
        self.scroll=QCheckBox('Desplazar después de cada like');self.scroll.setChecked(True)
        self.mode=QComboBox();self.mode.addItems(['Ejecutar ahora','Horario de inicio y fin'])
        self.start_at=QDateTimeEdit(QDateTime.fromString((clock_now()+timedelta(seconds=120)).isoformat(),Qt.DateFormat.ISODate));self.start_at.setCalendarPopup(True);self.start_at.setDisplayFormat('dd/MM/yyyy HH:mm:ss')
        self.end_at=QDateTimeEdit(QDateTime.fromString((clock_now()+timedelta(hours=1)).isoformat(),Qt.DateFormat.ISODate));self.end_at.setCalendarPopup(True);self.end_at.setDisplayFormat('dd/MM/yyyy HH:mm:ss')
        form.addRow('Nombre',self.task_name);form.addRow('Máximo de likes por dispositivo',self.count)
        form.addRow('',self.scroll);form.addRow('Cuándo',self.mode)
        form.addRow('Desde · Guatemala (UTC−6)',self.start_at);form.addRow('Hasta · Guatemala (UTC−6)',self.end_at)
        self.schedule_form=form
        self.mode.currentIndexChanged.connect(self.update_schedule)
        self.update_schedule();task_layout.addWidget(config)
        self.intro=QLabel('Destino: Granjita Lab · hasta 12 tarjetas locales. Se verifica cada resultado; los likes ya marcados no se duplican.')
        self.intro.setWordWrap(True);task_layout.addWidget(self.intro)
        self.recipe_info=QLabel();self.recipe_info.setWordWrap(True);task_layout.addWidget(self.recipe_info)
        self.count.valueChanged.connect(self.selection_summary);self.scroll.toggled.connect(self.selection_summary);self.mode.currentIndexChanged.connect(self.selection_summary)
        self.start_at.dateTimeChanged.connect(self.selection_summary);self.end_at.dateTimeChanged.connect(self.selection_summary)
        recipe_bar=QHBoxLayout()
        for label,callback in [('Guardar receta JSON',self.save_recipe),('Cargar receta',self.load_recipe)]:
            button=QPushButton(label);button.clicked.connect(callback);recipe_bar.addWidget(button)
        recipe_bar.addStretch();task_layout.addLayout(recipe_bar)
        history=QWidget();history_layout=QVBoxLayout(history);self.tabs.addTab(history,'Resultados y auditoría')
        self.like_stats=QLabel();self.like_stats.setWordWrap(True);self.like_stats.setStyleSheet('font-size:15px;padding:10px;background:#e8f3ed;');history_layout.addWidget(self.like_stats)
        self.results=QTableWidget(0,5);self.results.setHorizontalHeaderLabels(['Dispositivo','Puerto','Estado','Actualizado GT','Resultado'])
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.itemSelectionChanged.connect(self.details);history_layout.addWidget(self.results,1)
        self.stats=QLabel();history_layout.addWidget(self.stats)
        export=QPushButton('Exportar auditoría JSON');export.clicked.connect(self.export_likes);history_layout.addWidget(export)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(160);history_layout.addWidget(self.detail)
        tools_page=QWidget();tools_layout=QVBoxLayout(tools_page);self.tabs.addTab(tools_page,'Herramientas')
        self.comment=QLineEdit('Gracias por completar la prueba del laboratorio.');self.comment.setMaxLength(280)
        tools_layout.addWidget(QLabel('Prueba anterior de comentario (solo para recetas lab_smoke):'));tools_layout.addWidget(self.comment)
        for label,callback in [('Cargar flujo de un solo like',self.basic_like),('Diagnosticar Automate',self.probe),('Abrir Automate',lambda:self.probe(True))]:
            button=QPushButton(label);button.clicked.connect(callback);tools_layout.addWidget(button)
        tools_layout.addStretch()
        self.state=QLabel('Actualiza conexiones antes de ejecutar.');self.state.setWordWrap(True);layout.addWidget(self.state)
        controls=QHBoxLayout()
        self.run_button=QPushButton('Ejecutar tarea');self.run_button.setStyleSheet('background:#246b4d;color:white;font-weight:600;padding:10px;')
        self.run_button.clicked.connect(self.run_batch);controls.addWidget(self.run_button)
        for label,callback in [('Pausar / continuar',self.toggle_pause),('Cancelar',self.cancel_batch)]:
            button=QPushButton(label);button.clicked.connect(callback);controls.addWidget(button)
        layout.addLayout(controls)
        from .recipes import load_recipe
        from .core import ROOT
        self.recipe=load_recipe(ROOT/'recipes/lab-like-flow.json')
        self.populate_devices(preferred)
        self.refresh()
        self.connection_timer=QTimer(self);self.connection_timer.setInterval(30000)
        self.connection_timer.timeout.connect(lambda:self.refresh_connections() if self.worker is None and hasattr(self.store,'setting') else None)
        self.connection_timer.start()
        if hasattr(store,'setting'):QTimer.singleShot(0,self.refresh_connections)

    def populate_devices(self,preferred=None):
        from .physical import ordered_rows
        previous={r['hardware_serial'] for r in self.checked()} if self.rows else set()
        if preferred:previous.add(preferred['hardware_serial'])
        raw=self.store.fleet_devices()
        candidates=ordered_rows(raw,self.store.positions()) if hasattr(self.store,'positions') else raw
        self.online=len({r['hardware_serial'] for r in raw if r['status']=='Validado' and r.get('hardware_serial')})
        self.rows=[r for r in candidates if r['status']=='Validado' and r['identity_state']=='Serial leído']
        if not self.loaded_devices and not previous and self.rows:previous={self.rows[0]['hardware_serial']}
        self.loaded_devices=True
        self.devices.blockSignals(True);self.devices.setRowCount(len(self.rows))
        for i,row in enumerate(self.rows):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if row['hardware_serial'] in previous else Qt.CheckState.Unchecked);self.devices.setItem(i,0,check)
            name=f"{row['rack']}-P{row['slot']:02d} · {row['display_name']}" if row.get('rack') else row['display_name']
            for j,value in enumerate([name,row['hardware_serial'],str(row['port'])],1):self.devices.setItem(i,j,QTableWidgetItem(value))
        self.devices.blockSignals(False);self.selection_summary()

    def selection_summary(self,*args):
        selected=len(self.checked())
        self.fleet_stats.setText(f"{self.online} en línea · {len(self.rows)} aptos para ejecutar · {selected} seleccionados" + (' · Comprobado '+self.checked_at+' GT' if self.confirmed and self.checked_at else ' · Pendiente de comprobación actual'))
        if hasattr(self,'recipe_info'):
            mode='Horario GT · mantener abierto el programa' if self.mode.currentIndex() else 'Inicio inmediato'
            self.recipe_info.setText(f"{selected} dispositivos × {self.count.value()} tarjetas = hasta {selected*self.count.value()} verificaciones · {mode} · Ejecución secuencial")

    def select_count(self):
        if self.worker:return
        self.devices.blockSignals(True)
        for i in range(len(self.rows)):self.devices.item(i,0).setCheckState(Qt.CheckState.Checked if i<self.limit.value() else Qt.CheckState.Unchecked)
        self.devices.blockSignals(False);self.selection_summary()
    def select_all(self):
        self.limit.setValue(max(1,len(self.rows)));self.select_count()
    def select_none(self):
        if self.worker:return
        for i in range(len(self.rows)):self.devices.item(i,0).setCheckState(Qt.CheckState.Unchecked)
    def update_schedule(self):
        enabled=self.mode.currentIndex()==1
        self.start_at.setEnabled(enabled);self.end_at.setEnabled(enabled)
        self.schedule_form.setRowVisible(self.start_at,enabled);self.schedule_form.setRowVisible(self.end_at,enabled)

    def refresh_connections(self,launch_after=False):
        if self.worker:return
        if not hasattr(self.store,'setting'):
            self.confirmed=True
            if launch_after:self.launch_task()
            return
        self.launch_after_refresh=bool(launch_after)
        self.state.setText('Comprobando dispositivos y seriales en todos los servidores ADB…')
        self.worker=FleetWorker([int(p) for p in self.store.setting('ports','5037,5038').split(',')])
        self.worker.result.connect(self.fleet_loaded);self.worker.error.connect(self.fleet_error)
        self.worker.finished.connect(self.on_worker_finished);self.worker.start();self.refresh()
    def fleet_loaded(self,report):
        self.store.save_fleet(report);self.confirmed=True;self.checked_at=clock_now().strftime('%H:%M:%S');self.populate_devices()
        self.state.setText('Conexiones comprobadas · '+clock_now().strftime('%H:%M:%S')+' GT')
    def fleet_error(self,error):
        self.confirmed=False;self.launch_after_refresh=False;self.selection_summary();self.state.setText('No se pudo comprobar: '+error)

    def build_recipe(self):
        import copy
        spec=copy.deepcopy(self.recipe)
        if spec['action']=='lab_like_flow':
            from .taskflow import GT
            def stamp(widget):return widget.dateTime().toPython().replace(tzinfo=GT).isoformat()
            parameters=dict(count=self.count.value(),scroll_after_like=self.scroll.isChecked(),start_at=stamp(self.start_at) if self.mode.currentIndex() else None,end_at=stamp(self.end_at) if self.mode.currentIndex() else None)
            validate_parameters(parameters)
            spec['name']=self.task_name.text().strip() or 'Tarea de likes'
            spec['parameters']=parameters
        elif spec['action']=='lab_smoke':spec['parameters']['comment']=self.comment.text().strip()
        return spec

    def save_recipe(self):
        if self.worker:return
        try:spec=self.build_recipe()
        except Exception as exc:QMessageBox.warning(self,'Receta inválida',str(exc));return
        path,_=QFileDialog.getSaveFileName(self,'Guardar receta','mi-receta-likes.json','JSON (*.json)')
        if not path:return
        import json
        spec.pop('_profile_snapshot',None)
        try:Path(path).write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8');self.state.setText('Receta guardada.')
        except Exception as exc:QMessageBox.warning(self,'No se pudo guardar',str(exc))

    def checked(self):
        return [r for i,r in enumerate(self.rows) if self.devices.item(i,0).checkState()==Qt.CheckState.Checked]

    def run_batch(self):
        if self.worker:return
        if not self.checked():QMessageBox.information(self,'Selecciona dispositivos','Marca al menos un dispositivo apto.');return
        try:
            self.pending_spec=self.build_recipe()
            if self.pending_spec['action']=='lab_like_flow' and window_state(self.pending_spec['parameters'])=='expired':raise ValueError('El horario ya terminó.')
        except Exception as exc:QMessageBox.warning(self,'Revisa la tarea',str(exc));return
        self.pending_serials={r['hardware_serial'] for r in self.checked()}
        self.refresh_connections(True)

    def launch_task(self):
        if not self.confirmed:return
        rows=[r for r in self.rows if r['hardware_serial'] in self.pending_serials]
        if len(rows)!=len(self.pending_serials):
            self.state.setText('Cambió la disponibilidad de la selección. Revisa dispositivos y vuelve a ejecutar.');return
        spec=self.pending_spec
        action='lab_like_flow' if spec['action']=='lab_like_flow' else 'lab_like' if spec['action']=='lab_like' else 'lab_like_comment_scroll'
        parameters=spec['parameters'] if action=='lab_like_flow' else None
        if parameters and window_state(parameters)=='expired':self.state.setText('El horario terminó durante la validación.');return
        if len(rows)>1 and not any(t['status']=='Completado' for t in self.jobs.tasks()):
            QMessageBox.information(self,'Prueba piloto','Completa primero una tarea en una placa.');return
        tasks=self.jobs.create(rows,spec['parameters'].get('comment',''),action,parameters)
        self.jobs.attach_recipe([t['id'] for t in tasks],spec)
        self.worker=BatchWorker(self.jobs,tasks);self.worker.changed.connect(self.refresh);self.worker.finished.connect(self.on_worker_finished)
        self.state.setText(f"Tarea registrada: {len(tasks)} dispositivos · {spec['name']}");self.tabs.setCurrentIndex(1)
        self.refresh();self.worker.start()

    def load_recipe(self):
        if self.worker:
            return
        from .recipes import load_recipe
        from .core import ROOT
        path,_=QFileDialog.getOpenFileName(self,'Cargar receta de laboratorio',str(ROOT/'recipes'),'Receta JSON (*.json)')
        if not path:
            return
        try:
            self.recipe=load_recipe(Path(path))
        except Exception as exc:
            QMessageBox.warning(self,'Receta no válida',str(exc))
            return
        self.display_recipe()

    def basic_like(self):
        if self.worker:return
        from .recipes import load_recipe
        from .core import ROOT
        self.recipe=load_recipe(ROOT/'recipes/lab-like.json')
        self.display_recipe()

    def display_recipe(self):
        action=self.recipe['action']
        if action=='lab_like_flow':
            parameters=self.recipe['parameters'];self.task_name.setText(self.recipe['name']);self.count.setValue(parameters['count']);self.scroll.setChecked(parameters['scroll_after_like'])
            self.mode.setCurrentIndex(1 if parameters['start_at'] else 0)
            if parameters['start_at']:
                self.start_at.setDateTime(QDateTime.fromString(parameters['start_at'],Qt.DateFormat.ISODate).toTimeZone(self.start_at.dateTime().timeZone()))
                self.end_at.setDateTime(QDateTime.fromString(parameters['end_at'],Qt.DateFormat.ISODate).toTimeZone(self.end_at.dateTime().timeZone()))
        if action!='lab_like_flow':
            self.count.setValue(1);self.scroll.setChecked(False);self.mode.setCurrentIndex(0)
        self.count.setEnabled(action=='lab_like_flow');self.scroll.setEnabled(action=='lab_like_flow');self.mode.setEnabled(action=='lab_like_flow')
        self.comment.setEnabled(action=='lab_smoke');self.comment.setText(self.recipe['parameters'].get('comment',''))
        self.intro.setText('Destino: Granjita Lab · Likes y scroll auditados por tarjeta.' if action=='lab_like_flow' else 'Receta anterior: '+self.recipe['name']+' · cargar lab-like-flow.json para configurar repeticiones y horario.')
        self.selection_summary();self.tabs.setCurrentIndex(0)

    def refresh(self):
        self.run_button.setEnabled(self.worker is None)
        self.tabs.widget(0).setEnabled(self.worker is None)
        self.tasks=self.jobs.tasks()
        metrics=self.jobs.like_metrics()
        self.like_stats.setText(f"Likes · Programados: {metrics['scheduled']} · Procesados: {metrics['processed']} · Aplicados: {metrics['applied']} · Ya marcados: {metrics['already_marked']} · Sin confirmar: {metrics['unconfirmed']} · Históricos sin medición: {metrics['historical_unmeasured']}")
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

    def export_likes(self):
        if self.worker:return
        path,_=QFileDialog.getSaveFileName(self,'Exportar auditoría de likes','auditoria-likes.json','JSON (*.json)')
        if not path:return
        import json
        from .core import now
        try:
            Path(path).write_text(json.dumps(dict(schema_version=1,at=now(),metrics=self.jobs.like_metrics(),tasks=self.jobs.like_report()),ensure_ascii=False,indent=2),encoding='utf-8')
            self.state.setText('Auditoría exportada: '+path)
        except Exception as exc:
            QMessageBox.warning(self,'No se pudo exportar',str(exc))

    def details(self):
        index=self.results.currentRow()
        if 0<=index<len(self.tasks):
            task=self.tasks[index]
            self.detail.setPlainText(f"Tarea: {task['id']}\nLote: {task['batch']}\n{task['status']}\n{task['detail']}")
            if task['action'] in ('lab_like','lab_like_flow'):
                import json
                report=next((r for r in self.jobs.like_report() if r['id']==task['id']),None)
                if report:self.detail.appendPlainText(json.dumps(dict(context=report['context'],outcome=report['outcome'],recipe_sha256=report['recipe_sha256'],events=report['events']),ensure_ascii=False,indent=2))

    def toggle_pause(self):
        if isinstance(self.worker,BatchWorker):
            if self.worker.pause.is_set():
                self.worker.pause.clear()
                self.state.setText('Continuando el lote local.')
            else:
                self.worker.pause.set()
                self.state.setText('Pausa solicitada: se aplicará antes de la siguiente acción; el horario de fin sigue vigente.')

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
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_finished(self):
        self.worker.wait()
        if isinstance(self.worker,BatchWorker):
            self.state.setText('Lote local finalizado. Consulta el estado y la evidencia de cada tarea.')
        self.worker.deleteLater()
        self.worker=None
        self.refresh()
        if getattr(self,'launch_after_refresh',False):
            self.launch_after_refresh=False
            QTimer.singleShot(0,self.launch_task)

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

"""Panel de tareas locales y preparación verificada de aplicaciones origen."""
import threading
import time
import copy
from pathlib import Path
from datetime import timedelta
from PySide6.QtCore import QThread,Signal,Qt,QTimer,QDateTime
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QTableWidgetItem,QHeaderView,QLineEdit,QMessageBox,QPlainTextEdit,QAbstractItemView,QFileDialog,QWidget,QGroupBox,QFormLayout,QSpinBox,QCheckBox,QComboBox,QDateTimeEdit,QTabWidget)
from .app_sources import source_profile,require_like_mapping,prepare_app,verify_app_open,SOURCES
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
                if task.get('action')=='app_prepare':
                    import json
                    result=json.dumps(prepare_app(task['row'],task['app_source'],self.cancel.is_set,task_id=task['id']),ensure_ascii=False)
                elif task.get('action')=='lab_like_flow':
                    result=run_flow(task['row'],task['id'],parameters,lambda:self.stop_check(parameters),audit=lambda kind,data:self.audit_event(task['id'],kind,data))
                else:result=run_like(task['row'],task['id'],self.cancel.is_set,audit=lambda kind,data:self.audit_event(task['id'],kind,data)) if task.get('action')=='lab_like' else run_lab(task['row'],task['comment'],task['id'],self.cancel.is_set)
                self.jobs.update(task['id'],'Completado',result)
            except Exception as exc:
                self.jobs.update(task['id'],'Revisar resultado',str(exc))
            self.changed.emit()


    def audit_event(self,task_id,kind,data):
        self.jobs.like_event(task_id,kind,data)
        if kind=='verified':self.changed.emit()

    def stop_check(self,parameters):
        while self.pause.is_set() and not self.cancel.is_set() and window_state(parameters)!='expired':
            self.cancel.wait(.2)
        return self.cancel.is_set()


class VerificationWorker(QThread):
    changed=Signal()
    def __init__(self,jobs,tasks):
        super().__init__();self.jobs,self.tasks=jobs,tasks;self.cancel=threading.Event()
    def run(self):
        from .core import now
        saved={t['id']:t for t in self.jobs.batch_tasks(self.tasks[0]['batch'])} if self.tasks else {}
        for task in self.tasks:
            if task.get('action')!='app_prepare':continue
            previous=saved.get(task['id'],{})
            if previous.get('status') in ('Cancelado','Expirado','Interrumpido','No ejecutado'):
                result=dict(state='not_executed',at=now())
            elif self.cancel.is_set():result=dict(state='cancelled',at=now())
            else:
                try:result=verify_app_open(task['row'],task['app_source'],task_id=task['id'])
                except Exception as exc:result=dict(state='error',error_class=type(exc).__name__,at=now())
            self.jobs.record_app_verification(task['id'],result)
            self.changed.emit()


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
        self.setWindowTitle('Automatización · GranjitaAutomate 2.19')
        self.resize(1160,900)
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
        hero=QWidget();hero.setStyleSheet('QWidget { background:#e5f5e9; border-radius:8px; }')
        hero_layout=QHBoxLayout(hero)
        self.achieved_likes=QLabel('0');self.achieved_likes.setStyleSheet('font-size:44px;font-weight:700;color:#166534;background:transparent;')
        self.achieved_likes.setToolTip('Total histórico de likes nuevos verificados por tarea y tarjeta. Excluye ya marcados, resultados inciertos e históricos sin medición.')
        hero_layout.addWidget(self.achieved_likes)
        hero_caption=QLabel('Likes logrados\nTotal verificado · Granjita Lab');hero_caption.setStyleSheet('font-size:15px;background:transparent;');hero_layout.addWidget(hero_caption)
        hero_layout.addStretch()
        history_button=QPushButton('Ver historial de likes');history_button.setToolTip('Consulta cuándo, en qué dispositivo y en qué tarjeta se verificó cada resultado.');history_button.clicked.connect(lambda:self.tabs.setCurrentWidget(self.likes_page));hero_layout.addWidget(history_button)
        layout.addWidget(hero)
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
        self.devices.setMinimumHeight(130);self.devices.setMaximumHeight(200)
        self.devices.itemChanged.connect(lambda item:self.selection_summary())
        task_layout.addWidget(self.devices)
        config=QGroupBox('Receta');form=QFormLayout(config)
        self.app_source=QComboBox()
        for identifier in SOURCES:self.app_source.addItem(source_profile(identifier)['name'],identifier)
        self.app_source.setToolTip('Aplicación donde se ejecutará la tarea. Cada app necesita su propio mapeo del botón y del estado de like.')
        self.prepare_button=QPushButton('Abrir y comprobar app')
        self.prepare_button.setToolTip('Abre la app elegida en los dispositivos seleccionados si no está en primer plano. Registra el resultado sin pulsar likes ni modificar datos.')
        self.prepare_button.clicked.connect(self.prepare_selected_app)
        source_row=QHBoxLayout();source_row.addWidget(self.app_source);source_row.addWidget(self.prepare_button)
        form.addRow('App origen',source_row)
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
        self.batch_summary=QLabel();self.batch_summary.setWordWrap(True);self.batch_summary.setStyleSheet('font-size:16px;padding:12px;background:#fff4d6;');layout.insertWidget(layout.indexOf(self.tabs),self.batch_summary)
        self.batch_summary.setToolTip('Resumen del último lote guardado. Abrir una app no equivale a ejecutar likes ni confirmar una sesión iniciada.')
        self.like_stats=QLabel();self.like_stats.setWordWrap(True);self.like_stats.setStyleSheet('font-size:15px;padding:10px;background:#e8f3ed;');history_layout.addWidget(self.like_stats)
        self.results=QTableWidget(0,7);self.results.setHorizontalHeaderLabels(['Dispositivo','App / acción','Puerto','Resultado de la acción','Verificación posterior','Actualizado GT','Detalle'])
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.itemSelectionChanged.connect(self.details);history_layout.addWidget(self.results,1)
        self.stats=QLabel();history_layout.addWidget(self.stats)
        export=QPushButton('Exportar auditoría JSON');export.clicked.connect(self.export_likes);history_layout.addWidget(export)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(160);history_layout.addWidget(self.detail)
        self.likes_page=QWidget();likes_layout=QVBoxLayout(self.likes_page);self.tabs.addTab(self.likes_page,'Historial de likes')
        likes_layout.addWidget(QLabel('Destino y resultado de cada tarjeta procesada. Un resultado sin destino conocido se conserva como No disponible.'))
        filter_bar=QHBoxLayout()
        self.likes_filter=QLineEdit();self.likes_filter.setPlaceholderText('Buscar por dispositivo, tarjeta o tarea…');self.likes_filter.textChanged.connect(self.render_like_history);filter_bar.addWidget(self.likes_filter,1)
        self.likes_outcome=QComboBox();self.likes_outcome.addItems(['Todos','Logrados','Ya marcados','Sin confirmar','Históricos sin medición']);self.likes_outcome.currentIndexChanged.connect(self.render_like_history);filter_bar.addWidget(self.likes_outcome)
        likes_layout.addLayout(filter_bar)
        self.likes_table=QTableWidget(0,5);self.likes_table.setHorizontalHeaderLabels(['Fecha / hora GT','Dispositivo','Dónde','Resultado','Tarea'])
        self.likes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.likes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.likes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.likes_table.itemSelectionChanged.connect(self.like_history_details);likes_layout.addWidget(self.likes_table,1)
        self.likes_detail=QPlainTextEdit();self.likes_detail.setReadOnly(True);self.likes_detail.setMaximumHeight(160);likes_layout.addWidget(self.likes_detail)
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
        self.verify_button=QPushButton('Verificar último lote')
        self.verify_button.setToolTip('Relee identidad y app en primer plano en otro trabajador, sin volver a abrirla. Guarda una comprobación nueva con fecha/hora.')
        self.verify_button.clicked.connect(self.verify_last_batch);controls.addWidget(self.verify_button)
        self.clear_logs_button=QPushButton('Limpiar logs')
        self.clear_logs_button.setToolTip('Respalda las trazas y limpia los eventos visibles para una nueva prueba. Conserva tareas, recetas, likes, feedback y el log bruto de Appium. Disponible al terminar el lote.')
        self.clear_logs_button.clicked.connect(self.clear_logs);controls.addWidget(self.clear_logs_button)
        layout.addLayout(controls)
        from .recipes import load_recipe
        from .core import ROOT
        self.recipe=load_recipe(ROOT/'recipes/lab-like-flow.json')
        self.app_source.currentIndexChanged.connect(self.source_changed)
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
            if hasattr(self,'app_source') and source_profile(self.app_source.currentData())['mapping_status']!='verified':
                self.recipe_info.setText(f"{selected} dispositivos · Apertura y comprobación de {self.app_source.currentText()} disponibles ahora · Likes pendientes de validar")
            else:self.recipe_info.setText(f"{selected} dispositivos × {self.count.value()} tarjetas = hasta {selected*self.count.value()} verificaciones · {mode} · Ejecución secuencial")

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
        enabled=self.mode.currentIndex()==1 and source_profile(self.app_source.currentData())['mapping_status']=='verified'
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

    def source_changed(self,*args):
        if not hasattr(self,'run_button'):return
        source=source_profile(self.app_source.currentData())
        preparing=getattr(self,'recipe',{}).get('action')=='app_prepare'
        mapped=source['mapping_status']=='verified'
        self.run_button.setEnabled(self.worker is None and (mapped or preparing))
        self.run_button.setText('Ejecutar preparación' if preparing else 'Ejecutar tarea' if mapped else 'Likes pendientes de mapeo')
        self.run_button.setToolTip('La apertura no confirma sesión iniciada, publicación visible ni un like verificado.')
        flow=getattr(self,'recipe',{}).get('action')=='lab_like_flow' and mapped
        self.count.setEnabled(flow);self.scroll.setEnabled(flow);self.mode.setEnabled(flow)
        self.update_schedule();self.selection_summary()
        self.intro.setText('Destino: '+source['name']+(' · Likes mapeados y verificados por tarjeta.' if source['mapping_status']=='verified' else ' · Apertura disponible. Likes pendientes de mapear y validar en una publicación de prueba.'))

    def prepare_selected_app(self):
        if self.worker:return
        if not self.checked():QMessageBox.information(self,'Selecciona dispositivos','Marca al menos un dispositivo apto.');return
        import copy
        self.pending_spec=copy.deepcopy(self.recipe)
        self.pending_spec.update(action='app_prepare',app_source=self.app_source.currentData(),parameters={},name='Abrir y comprobar '+source_profile(self.app_source.currentData())['name'],context=dict(environment='device_app',audience='dispositivos seleccionados',intent='comprobar aplicación en primer plano'))
        self.pending_spec['_app_source_snapshot']=source_profile(self.app_source.currentData())
        self.pending_serials={r['hardware_serial'] for r in self.checked()}
        self.refresh_connections(True)

    def build_recipe(self):
        import copy
        spec=copy.deepcopy(self.recipe)
        spec['app_source']=self.app_source.currentData()
        spec['_app_source_snapshot']=source_profile(spec['app_source'])
        if spec['action']=='app_prepare':
            spec.update(parameters={},name='Abrir y comprobar '+source_profile(spec['app_source'])['name'])
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
        spec.pop('_app_source_snapshot',None)
        try:Path(path).write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8');self.state.setText('Receta guardada.')
        except Exception as exc:QMessageBox.warning(self,'No se pudo guardar',str(exc))

    def checked(self):
        return [r for i,r in enumerate(self.rows) if self.devices.item(i,0).checkState()==Qt.CheckState.Checked]

    def run_batch(self):
        if self.worker:return
        if not self.checked():QMessageBox.information(self,'Selecciona dispositivos','Marca al menos un dispositivo apto.');return
        try:
            if self.recipe['action']!='app_prepare':require_like_mapping(self.app_source.currentData())
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
        action='app_prepare' if spec['action']=='app_prepare' else 'lab_like_flow' if spec['action']=='lab_like_flow' else 'lab_like' if spec['action']=='lab_like' else 'lab_like_comment_scroll'
        parameters=spec['parameters'] if action=='lab_like_flow' else None
        if parameters and window_state(parameters)=='expired':self.state.setText('El horario terminó durante la validación.');return
        if action!='app_prepare' and len(rows)>1 and not any(t['status']=='Completado' and t['action']!='app_prepare' for t in self.jobs.tasks()):
            QMessageBox.information(self,'Prueba piloto','Completa primero una tarea en una placa.');return
        if action!='app_prepare':require_like_mapping(spec.get('app_source','laboratorio'))
        tasks=self.jobs.create(rows,spec['parameters'].get('comment',''),action,parameters,app_source=spec.get('app_source','laboratorio'))
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
        self.app_source.setCurrentIndex(self.app_source.findData(self.recipe.get('app_source','laboratorio')))
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
        self.source_changed();self.selection_summary();self.tabs.setCurrentIndex(0)

    def refresh(self):
        self.source_changed()
        self.tabs.widget(0).setEnabled(self.worker is None)
        self.tasks=self.jobs.tasks()
        metrics=self.jobs.like_metrics()
        self.achieved_likes.setText(f"{metrics['applied']:,}")
        self.history_entries=self.jobs.like_history()
        self.render_like_history()
        self.like_stats.setText(f"Likes históricos · Tareas registradas: {metrics['scheduled']} · Procesados: {metrics['processed']} · Aplicados: {metrics['applied']} · Ya marcados: {metrics['already_marked']} · Sin confirmar: {metrics['unconfirmed']} · Históricos sin medición: {metrics['historical_unmeasured']}")
        if hasattr(self,'stats'):
            completed=sum(t['status']=='Completado' for t in self.tasks)
            pending=sum(t['status'] in ('En cola','Ejecutando') for t in self.tasks)
            cancelled=sum(t['status']=='Cancelado' for t in self.tasks)
            self.stats.setText(f'Últimas {len(self.tasks)} tareas · {completed} completadas · {pending} en curso/cola · {cancelled} canceladas · {len(self.tasks)-completed-pending-cancelled} para revisar/interrumpidas/expiradas')
        batch=self.jobs.latest_batch_summary()
        from .task_results import batch_text,compact_batch
        card=compact_batch(batch,isinstance(self.worker,VerificationWorker))
        self.batch_summary.setText(card['html']);self.batch_summary.setToolTip(batch_text(batch))
        self.batch_summary.setStyleSheet('font-size:16px;padding:10px;background:'+('#e5f5e9' if batch and batch['finished'] and batch['completion_label'].endswith('Correcto') and not card['review'] else '#fff4d6')+';')
        self.clear_logs_button.setEnabled(self.worker is None)
        self.verify_button.setEnabled(self.worker is None and bool(batch and batch['preparation'] and batch['finished']))
        self.results.setRowCount(len(self.tasks))
        for i,task in enumerate(self.tasks):
            from .task_results import present_task
            presentation=present_task(task)
            for j,value in enumerate([task['name'],presentation['action_label'],str(task['port']),presentation['status_label'],presentation['verification_label'],task['updated'][11:19],task['detail']]):
                item=QTableWidgetItem(value)
                item.setToolTip(value)
                self.results.setItem(i,j,item)

    def verify_last_batch(self):
        if self.worker:return
        batch=self.jobs.latest_batch_summary()
        if not batch or not batch['finished']:return
        from .physical import ordered_rows
        from .task_results import present_task
        rows={r['id']:r for r in ordered_rows(self.store.fleet_devices(),self.store.positions() if hasattr(self.store,'positions') else [])}
        tasks=[]
        for saved in self.jobs.batch_tasks(batch['batch']):
            if saved['action']!='app_prepare':continue
            row=rows.get(saved['device_id'])
            if row is None:row=dict(id=saved['device_id'],status='Sin verificar',port=saved['port'],serial=saved['serial'],hardware_serial='')
            tasks.append(dict(saved,row=row,app_source=present_task(saved)['source']))
        self.start_postcheck(tasks)

    def start_postcheck(self,tasks):
        if not tasks:return
        self.worker=VerificationWorker(self.jobs,tasks)
        self.worker.changed.connect(self.refresh);self.worker.finished.connect(self.on_worker_finished)
        self.state.setText('Verificando ejecución… Releyendo cada app sin abrirla de nuevo.')
        self.refresh();self.worker.start()

    def clear_logs(self):
        if self.worker:return
        try:
            from .diagnostics import clear_traces
            result=clear_traces()
            self.state.setText(f"Logs limpios: {result['removed']} eventos archivados. La siguiente ejecución generará trazas nuevas; el historial de tareas se conserva.")
        except Exception as exc:QMessageBox.warning(self,'No se limpiaron los logs',str(exc))

    def render_like_history(self,*args):
        if not hasattr(self,'history_entries'):return
        import json
        outcomes={1:'applied',2:'already_marked',3:'unconfirmed',4:'historical_unmeasured'}
        wanted=outcomes.get(self.likes_outcome.currentIndex())
        query=self.likes_filter.text().lower()
        self.visible_likes=[r for r in self.history_entries if (not wanted or r['outcome']==wanted) and query in json.dumps(r,ensure_ascii=False).lower()]
        self.likes_table.setRowCount(len(self.visible_likes))
        labels={'applied':'Logrado','already_marked':'Ya marcado','unconfirmed':'Sin confirmar','historical_unmeasured':'Histórico sin medición'}
        from PySide6.QtGui import QColor
        for i,row in enumerate(self.visible_likes):
            from datetime import datetime
            at=datetime.fromisoformat(row['at']).strftime('%d/%m/%Y %H:%M:%S')
            for j,value in enumerate([at,row['device'],row['destination'],labels.get(row['outcome'],row['outcome']),row['task_id']]):
                item=QTableWidgetItem(value);item.setToolTip(value)
                if row['outcome']=='applied':item.setBackground(QColor('#dcfce7'))
                self.likes_table.setItem(i,j,item)

    def like_history_details(self):
        index=self.likes_table.currentRow()
        if 0<=index<len(self.visible_likes):
            import json
            self.likes_detail.setPlainText(json.dumps(self.visible_likes[index],ensure_ascii=False,indent=2))

    def export_likes(self):
        if self.worker:return
        path,_=QFileDialog.getSaveFileName(self,'Exportar auditoría de likes','auditoria-likes.json','JSON (*.json)')
        if not path:return
        import json
        from .core import now
        try:
            Path(path).write_text(json.dumps(dict(schema_version=1,at=now(),metrics=self.jobs.like_metrics(),tasks=self.jobs.like_report(),history=self.jobs.like_history()),ensure_ascii=False,indent=2),encoding='utf-8')
            self.state.setText('Auditoría exportada: '+path)
        except Exception as exc:
            QMessageBox.warning(self,'No se pudo exportar',str(exc))

    def details(self):
        index=self.results.currentRow()
        if 0<=index<len(self.tasks):
            task=self.tasks[index]
            self.detail.setPlainText(f"Tarea: {task['id']}\nLote: {task['batch']}\n{task['status']}\n{task['detail']}")
            if task.get('verification_payload'):self.detail.appendPlainText('Verificación posterior: '+task['verification_payload'])
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
        if isinstance(self.worker,VerificationWorker):
            self.worker.cancel.set();return
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
        finished=self.worker
        finished.wait()
        tasks=finished.tasks if isinstance(finished,BatchWorker) else []
        finished.deleteLater();self.worker=None
        if tasks and any(t.get('action')=='app_prepare' for t in tasks):
            self.start_postcheck(tasks);return
        if isinstance(finished,(BatchWorker,VerificationWorker)):
            from .task_results import compact_batch
            self.state.setText(compact_batch(self.jobs.latest_batch_summary())['status'])
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

"""Consulta local de trazas y feedback asociado a una ejecución."""
import json
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QFileDialog,QMessageBox
from . import diagnostics


class DiagnosticsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Logs y trazas')
        self.resize(1150,820)
        layout=QVBoxLayout(self)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        bar=QHBoxLayout()
        self.filter=QLineEdit();self.filter.setPlaceholderText('Filtrar por proceso, tarea, serial, estado o identificador de ejecución…')
        self.filter.setToolTip('Busca entre los últimos 1000 eventos de la aplicación. Las pruebas unitarias no se incluyen.')
        self.filter.textChanged.connect(self.render);bar.addWidget(self.filter,1)
        for title,callback,tip in [('Actualizar',self.refresh,'Vuelve a consultar las trazas locales.'),('Exportar ejecución',self.export,'Exporta hasta 10000 eventos de la ejecución seleccionada y su feedback. No incluye capturas ni logs brutos de Appium.')]:
            button=QPushButton(title);button.setToolTip(tip);button.clicked.connect(callback);bar.addWidget(button)
        layout.addLayout(bar)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Hora GT','Proceso / paso','Fase','Resultado','Tiempo ms','Tarea / dispositivo'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.details);layout.addWidget(self.table,1)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(200);layout.addWidget(self.detail)
        self.note=QLineEdit();self.note.setMaxLength(2000);self.note.setPlaceholderText('Feedback: ¿qué observaste?')
        self.note.setToolTip('Se guarda asociado a la ejecución seleccionada. Describe el síntoma sin contraseñas ni tokens.');layout.addWidget(self.note)
        self.expected=QLineEdit();self.expected.setMaxLength(2000);self.expected.setPlaceholderText('¿Qué esperabas que ocurriera?')
        self.expected.setToolTip('Resultado esperado para comparar con la evidencia y proponer una mejora.');layout.addWidget(self.expected)
        save=QPushButton('Registrar feedback de esta ejecución');save.setToolTip('Guarda la observación en SQLite. No cambia recetas ni repite acciones automáticamente.');save.clicked.connect(self.save_feedback);layout.addWidget(save)
        self.rows=[];self.events=[];self.refresh()
    def refresh(self):
        try:
            self.events=diagnostics.read_events(limit=1000)
            errors=[r for r in self.events if r['status']=='error']
            durations=[r['duration_ms'] for r in self.events if r['phase']=='end' and r['duration_ms'] is not None]
            roots=sum(r['phase']=='end' and r['parent_id'] is None for r in self.events)
            frequent={}
            for r in errors:
                key=r['metadata'].get('category','other');frequent[key]=frequent.get(key,0)+1
            top=', '.join(f'{k}: {v}' for k,v in sorted(frequent.items(),key=lambda item:-item[1])[:3]) or 'sin errores en esta muestra'
            health=diagnostics.health()
            self.summary.setText(f"Últimos {len(self.events)} eventos · {roots} procesos raíz terminados · {len(errors)} eventos de error · Promedio por paso: {sum(durations)/len(durations):.0f} ms · {top}" if durations else f'Últimos {len(self.events)} eventos · {top}')
            if health['dropped']:self.summary.setText(self.summary.text()+f" · Atención: {health['dropped']} eventos no pudieron guardarse durante esta sesión")
            self.render()
        except Exception as exc:self.summary.setText('No se pudieron consultar las trazas: '+type(exc).__name__)
    def render(self):
        query=self.filter.text().lower()
        self.rows=[r for r in self.events if query in json.dumps(r,ensure_ascii=False).lower()]
        self.table.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            identity=r.get('task_id') or r['metadata'].get('hardware_serial') or r['metadata'].get('transport') or '—'
            for j,value in enumerate([r['at'][11:23],r['process'],r['phase'],r['status'],f"{r['duration_ms']:.1f}" if r['duration_ms'] is not None else '—',identity]):
                item=QTableWidgetItem(str(value));item.setToolTip(str(value));self.table.setItem(i,j,item)
    def selected(self):
        index=self.table.currentRow();return self.rows[index] if 0<=index<len(self.rows) else None
    def details(self):
        row=self.selected()
        if row:self.detail.setPlainText(json.dumps(dict(event=row,feedback=diagnostics.feedback(row['run_id'])),ensure_ascii=False,indent=2))
    def save_feedback(self):
        row=self.selected()
        if not row:self.summary.setText('Selecciona primero un evento de la ejecución.');return
        try:
            diagnostics.add_feedback(row['run_id'],self.note.text(),self.expected.text())
            self.note.clear();self.expected.clear();self.details();self.summary.setText('Feedback guardado para la ejecución '+row['run_id'])
        except Exception as exc:QMessageBox.warning(self,'No se guardó el feedback',str(exc))
    def export(self):
        row=self.selected()
        if not row:self.summary.setText('Selecciona un evento de la ejecución que quieres exportar.');return
        path,_=QFileDialog.getSaveFileName(self,'Exportar traza de ejecución','traza-ejecucion.json','JSON (*.json)')
        if not path:return
        try:
            from pathlib import Path
            events=diagnostics.read_events(row['run_id'],limit=10000)
            payload=dict(schema_version=1,at=diagnostics.stamp(),run_id=row['run_id'],limit=10000,possibly_truncated=len(events)==10000,events=events,feedback=diagnostics.feedback(row['run_id']))
            Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            self.summary.setText('Traza exportada: '+path)
        except Exception as exc:QMessageBox.warning(self,'No se exportó la traza',str(exc))

"""Panel de snapshots 4.2; el contenido privado permanece en SQLite local."""
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QPlainTextEdit
from .snapshots import reconcile_snapshots, eligible


class SnapshotWorker(QThread):
    progress=Signal(int,str)
    result=Signal(list)
    def __init__(self,store,rows=None,capture_only=False):
        super().__init__()
        self.store,self.rows,self.capture_only=store,rows,capture_only
    def run(self):
        try:self.result.emit(reconcile_snapshots(self.store,self.rows,self.progress.emit,self.capture_only))
        except Exception as exc:self.result.emit([dict(detail='Error general: '+str(exc))])


class SnapshotDialog(QDialog):
    def __init__(self,store,selected=None,parent=None):
        super().__init__(parent)
        self.store,self.selected,self.worker=store,selected,None
        self.setWindowTitle('Snapshots · Subfase 4.2')
        self.resize(1000,700)
        layout=QVBoxLayout(self)
        caption=QLabel('Snapshot lógico: inventario y archivos .json/.txt en /sdcard/Download/Granjita (máximo 32 archivos de 16 KiB).\nAl restaurar solo se recuperan archivos ausentes; los diferentes se conservan para revisión. No es una imagen completa de Android.')
        caption.setWordWrap(True);layout.addWidget(caption)
        self.buttons=[]
        for title,callback in [('Crear snapshot seleccionada',lambda:self.start(True,False)),('Crear snapshots de todas las elegibles',lambda:self.start(True,True)),('Verificar / recuperar seleccionada',lambda:self.start(False,False))]:
            button=QPushButton(title);button.clicked.connect(callback);layout.addWidget(button);self.buttons.append(button)
        self.state=QLabel('Selecciona un snapshot para consultar manifiesto y resultados.');self.state.setWordWrap(True);layout.addWidget(self.state)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Fecha GT','Serial físico','Estado','Snapshot'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.details);layout.addWidget(self.table)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);layout.addWidget(self.detail)
        self.refresh()
    def refresh(self):
        with self.store.connect() as db:
            self.snapshots=[dict(r) for r in db.execute('SELECT * FROM device_checkpoints ORDER BY rowid DESC LIMIT 150')]
        self.table.setRowCount(len(self.snapshots))
        for i,r in enumerate(self.snapshots):
            for j,value in enumerate([r['at'],r['hardware_serial'],r['status'],r['id']]):self.table.setItem(i,j,QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        with self.store.connect() as db:
            events=[dict(r) for r in db.execute('SELECT hardware_serial,at,status,detail FROM recovery_events ORDER BY id DESC LIMIT 30')]
        import json
        self.detail.setPlainText(json.dumps(events,ensure_ascii=False,indent=2))
    def details(self):
        i=self.table.currentRow()
        if not 0<=i<len(self.snapshots):return
        row=self.snapshots[i]
        with self.store.connect() as db:
            events=[dict(r) for r in db.execute('SELECT at,status,detail FROM recovery_events WHERE snapshot_id=? ORDER BY id DESC LIMIT 20',(row['id'],))]
        import json
        self.detail.setPlainText(json.dumps(dict(manifest=json.loads(row['manifest']),sha256=row['sha256'],events=events),ensure_ascii=False,indent=2))
    def start(self,capture,all_rows):
        if self.worker:return
        rows=eligible(self.store)
        if not all_rows:rows=[r for r in rows if self.selected and r['id']==self.selected['id']]
        if not rows:self.state.setText('No hay placas elegibles con identidad única y validada.');return
        for button in self.buttons:button.setEnabled(False)
        self.worker=SnapshotWorker(self.store,rows,capture)
        self.worker.progress.connect(lambda n,text:self.state.setText(f'{n} · {text}'))
        self.worker.result.connect(lambda results:self.state.setText('\n'.join(r['detail'] for r in results)[-1500:]))
        self.worker.finished.connect(self.on_finished);self.worker.start()
    def on_finished(self):
        self.worker.wait();self.worker.deleteLater();self.worker=None
        for button in self.buttons:button.setEnabled(True)
        self.refresh()
    def reject(self):
        if not self.worker:super().reject()
    def closeEvent(self,event):event.ignore() if self.worker else event.accept()

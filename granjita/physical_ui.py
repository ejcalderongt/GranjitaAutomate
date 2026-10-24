from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QSpinBox,QPushButton,QCheckBox,QFormLayout
from .physical import verify_identity, sync_position


class PositionWorker(QThread):
    result=Signal(str)
    def __init__(self, row, sync=False):
        super().__init__()
        self.row=row
        self.sync=sync
    def run(self):
        try:
            if self.sync:
                result=sync_position(self.row)
            else:
                verify_identity(self.row)
                result='IDENTITY_OK'
            self.result.emit(result)
        except Exception as exc:
            self.result.emit('Error: '+str(exc))


class PositionDialog(QDialog):
    def __init__(self,store,row,parent=None):
        super().__init__(parent)
        self.store,self.row,self.worker=store,dict(row),None
        self.setWindowTitle('Posición física permanente')
        self.resize(650,400)
        layout=QVBoxLayout(self)
        label=QLabel(f"{row['display_name']}\nSerial físico: {row.get('hardware_serial') or 'sin verificar'}\nSelecciona el rack y confirma físicamente la posición antes de guardar.")
        label.setWordWrap(True);layout.addWidget(label)
        form=QFormLayout()
        self.rack=QLineEdit(row.get('rack','R01'))
        self.slot=QSpinBox();self.slot.setRange(1,999);self.slot.setValue(row.get('slot',1))
        self.number=QSpinBox();self.number.setRange(1,999999);self.number.setValue(row.get('panda_number',1))
        form.addRow('Rack (R01, R02…)',self.rack)
        form.addRow('Posición física',self.slot)
        form.addRow('Número permanente en Panda',self.number)
        layout.addLayout(form)
        self.confirm=QCheckBox('Verifiqué que este serial corresponde a esta posición del rack')
        layout.addWidget(self.confirm)
        self.save=QPushButton('Verificar serial y guardar posición')
        self.save.clicked.connect(self.assign);layout.addWidget(self.save)
        self.sync=QPushButton('Aplicar nombre y número guardados en Panda')
        self.sync.clicked.connect(lambda:self.start(True));layout.addWidget(self.sync)
        self.state=QLabel('Guardar fija el orden local. Aplicar a Panda usa el mapa guardado, sin cambiar Android. Los números deben estar libres.')
        self.state.setWordWrap(True);layout.addWidget(self.state)
    def assign(self):
        if not self.confirm.isChecked():
            self.state.setText('Falta confirmar la correspondencia física.');return
        self.pending=(self.rack.text(),self.slot.value(),self.number.value())
        self.start(False)
    def start(self,sync):
        if self.worker:return
        if sync:
            positions=[p for p in self.store.positions() if p['hardware_serial']==self.row.get('hardware_serial')]
            if len(positions)!=1:
                self.state.setText('Guarda primero una posición verificada.');return
            self.row.update(positions[0])
        self.save.setEnabled(False);self.sync.setEnabled(False)
        self.state.setText('Verificando identidad y respuesta…')
        self.worker=PositionWorker(dict(self.row),sync)
        self.worker.result.connect(self.loaded)
        self.worker.finished.connect(self.done_worker)
        self.worker.start()
    def loaded(self,result):
        if result=='IDENTITY_OK':
            try:
                self.store.assign_position(self.row['hardware_serial'],*self.pending)
                result='Posición guardada. Se conserva al desconectar y volver a abrir el programa.'
            except Exception as exc:result='Error: '+str(exc)
        self.state.setText(result)
    def done_worker(self):
        self.worker.wait();self.worker.deleteLater();self.worker=None
        self.save.setEnabled(True);self.sync.setEnabled(True)
    def reject(self):
        if not self.worker:super().reject()
    def closeEvent(self,event):
        event.ignore() if self.worker else event.accept()

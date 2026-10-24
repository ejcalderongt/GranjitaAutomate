"""Comparación de inventarios Panda/Granjita mediante API de solo lectura."""
import json
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
from .panda_api import list_devices
from .core import DATA,now


class PandaWorker(QThread):
    result=Signal(list)
    error=Signal(str)
    def run(self):
        try:
            self.result.emit(list_devices())
        except Exception as exc:
            self.error.emit(str(exc))


class PandaDialog(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent)
        self.store=store
        self.worker=None
        self.setWindowTitle('API Panda · inventario y correspondencias')
        self.resize(1100,650)
        layout=QVBoxLayout(self)
        self.state=QLabel('API local de Panda · Consulta de lectura; no cambia nombres ni grupos.')
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.button=QPushButton('Consultar API Panda')
        self.button.clicked.connect(self.refresh)
        layout.addWidget(self.button)
        self.table=QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(['Número','Nombre Panda','Serial físico Panda','Conexión','Modo','Ficha local'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        if self.worker:
            return
        self.button.setEnabled(False)
        self.state.setText('Consultando ws://127.0.0.1:22222/ …')
        self.worker=PandaWorker()
        self.worker.result.connect(self.loaded)
        self.worker.error.connect(lambda value:self.state.setText('API no disponible: '+value))
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def loaded(self,rows):
        DATA.mkdir(exist_ok=True)
        (DATA/'panda-inventory.json').write_text(json.dumps(dict(at=now(),devices=rows),ensure_ascii=False,indent=2),encoding='utf-8')
        local=self.store.fleet_devices()
        self.table.setRowCount(len(rows))
        modes={0:'USB',1:'Wi-Fi',2:'OTG',3:'Accesibilidad'}
        for i,row in enumerate(rows):
            matches={d['id'] for d in local if row.get('onlySerial') and d.get('hardware_serial')==row['onlySerial']}
            match='Corresponde' if len(matches)==1 else 'Varias fichas: revisar' if matches else 'No correlacionado'
            values=[str(row.get('sort','')),row.get('name',''),row.get('onlySerial',''),row.get('serial',''),modes.get(row.get('mode'),'Desconocido'),match]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(i,j,item)
        self.state.setText(f'API respondió · {len(rows)} conexiones reportadas · {now()} · Las correspondencias no fusionan ni renombran fichas.')

    def on_worker_finished(self):
        self.worker.deleteLater()
        self.worker=None
        self.button.setEnabled(True)

    def reject(self):
        if not self.worker:
            super().reject()

    def closeEvent(self,event):
        event.ignore() if self.worker else event.accept()

import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog, QFileDialog, QCheckBox, QProgressBar)

from .core import Adb, Store, ROOT


class ScanWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, port):
        super().__init__()
        self.port = port

    def run(self):
        try:
            self.completed.emit(Adb(self.port).scan(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.worker = None
        self.fresh = False
        self.setWindowTitle('GranjitaAutomate · v1.0')
        self.resize(1180, 760)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel('GranjitaAutomate')
        title.setObjectName('title')
        layout.addWidget(title)
        layout.addWidget(QLabel('Tu granja conectada · OTG mediante Panda · Versión 1.0'))
        self.summary = QLabel('Listo para buscar tus placas')
        self.summary.setObjectName('summary')
        layout.addWidget(self.summary)
        toolbar = QHBoxLayout()
        self.scan_button = QPushButton('Buscar y validar / Reintentar')
        self.scan_button.clicked.connect(self.scan)
        toolbar.addWidget(self.scan_button)
        panda = QPushButton('Abrir Panda')
        panda.clicked.connect(self.open_panda)
        toolbar.addWidget(panda)
        self.auto = QCheckBox('Revisar cada 30 segundos')
        self.auto.setChecked(self.store.setting('auto', '0') == '1')
        self.auto.toggled.connect(lambda checked: self.store.set_setting('auto', int(checked)))
        toolbar.addWidget(self.auto)
        toolbar.addStretch()
        settings = QPushButton('Configuración')
        settings.clicked.connect(self.configure)
        toolbar.addWidget(settings)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Nombre', 'Dispositivo', 'Acceso ADB', 'Modelo', 'Android', 'Estado', 'Comprobación'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.table.doubleClicked.connect(self.rename)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for text, callback in [('Cambiar nombre', self.rename), ('Ver historial', self.history), ('Respaldar SQLite', self.backup), ('Ayuda de conexión', self.help)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.detail = QLabel('1. Abre Panda.  2. Completa la conexión OTG.  3. Pulsa Buscar y validar.')
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(65)
        layout.addWidget(self.detail)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.notice = QLabel('SQLite local · Los registros guardados se verifican al iniciar una búsqueda.')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.render()
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.scan() if self.auto.isChecked() else None)
        self.timer.start(30000)
        QTimer.singleShot(400, self.scan)

    def selected(self):
        row = self.table.currentRow()
        return self.rows[row] if row >= 0 and row < len(self.rows) else None

    def render(self):
        selected = self.selected()['serial'] if hasattr(self, 'rows') and self.selected() else None
        self.rows = self.store.devices()
        self.table.setRowCount(0)
        colors = {'Validado': '#15803d', 'Desconectado': '#64748b', 'Requiere autorización': '#b45309'}
        for i, row in enumerate(self.rows):
            self.table.insertRow(i)
            transport = 'TCP/IP' if ':' in row['serial'] else 'USB / otro'
            checked = row['last_check'][11:19] + ' · GT'
            values = [row['alias'] or 'Sin nombre', row['serial'], transport, row['model'], row['android'], row['status'] if self.fresh else 'Pendiente de verificar', checked]
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(row['last_check'] if j == 6 else value)
                if j == 5:
                    item.setForeground(QColor(colors.get(value, '#b45309')))
                self.table.setItem(i, j, item)
            if row['serial'] == selected:
                self.table.selectRow(i)
        if self.fresh:
            valid = sum(r['status'] == 'Validado' for r in self.rows)
            absent = sum(r['status'] == 'Desconectado' for r in self.rows)
            self.summary.setText(f'{valid} validados   ·   {len(self.rows)-valid-absent} requieren atención   ·   {absent} desconectados')
        else:
            self.summary.setText(f'{len(self.rows)} placas guardadas · Pendientes de verificar')

    def scan(self):
        if self.worker is not None:
            return
        self.scan_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.notice.setText('Buscando y validando mediante el servidor ADB existente…')
        self.worker = ScanWorker(int(self.store.setting('port', '5037')))
        self.worker.progress.connect(self.update_progress)
        self.worker.completed.connect(self.scanned)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def update_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def scanned(self, results):
        try:
            self.store.save_scan(results)
            self.fresh = True
            self.render()
            self.notice.setText(f'Búsqueda completada: {len(results)} dispositivos detectados. Historial guardado en SQLite.')
            if not results:
                self.detail.setText('No se detectan placas. Abre Panda, completa el proceso OTG y pulsa Reintentar. Si usa otro puerto ADB, ajústalo en Configuración.')
        except Exception as exc:
            self.scan_failed(f'No se pudo guardar la búsqueda: {exc}')

    def scan_failed(self, error):
        self.fresh = False
        self.render()
        self.summary.setText('No se pudo comprobar la conexión · Los datos guardados no son el estado actual')
        self.notice.setText('Abre Panda y completa su conexión OTG. Después pulsa Reintentar.')
        self.detail.setText(f'Diagnóstico: {error}')

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.scan_button.setEnabled(True)
        self.progress.hide()

    def show_detail(self):
        row = self.selected()
        if row:
            prefix = '' if self.fresh else 'Registro histórico; falta comprobar el estado actual.\n'
            self.detail.setText(prefix + row['detail'])

    def rename(self, *_):
        row = self.selected()
        if not row:
            QMessageBox.information(self, 'Selecciona una placa', 'Selecciona primero una fila de la lista.')
            return
        text, ok = QInputDialog.getText(self, 'Nombre de la placa', 'Nombre fácil de reconocer:', text=row['alias'])
        if ok:
            self.store.alias(row['serial'], text.strip()[:100])
            self.render()

    def history(self):
        row = self.selected()
        if not row:
            return
        records = self.store.history(row['serial'])
        box = QMessageBox(self)
        box.setWindowTitle('Historial de la placa')
        box.setText(row['alias'] or row['serial'])
        box.setInformativeText('Últimas 100 comprobaciones. Abre los detalles para consultarlas.')
        box.setDetailedText('\n\n'.join(f"{r['at']} · {r['status']}\n{r['detail']}" for r in records))
        box.exec()

    def backup(self):
        target, _ = QFileDialog.getSaveFileName(self, 'Guardar respaldo de SQLite', str(Path.home() / 'granjita-respaldo.sqlite3'), 'SQLite (*.sqlite3)')
        if target:
            try:
                self.store.backup(target)
                QMessageBox.information(self, 'Respaldo creado', f'Base de datos respaldada en:\n{target}')
            except Exception as exc:
                QMessageBox.warning(self, 'No se pudo respaldar', str(exc))

    def configure(self):
        if self.worker is not None:
            QMessageBox.information(self, 'Comprobación en curso', 'Espera a que termine la búsqueda para cambiar el puerto.')
            return
        port, ok = QInputDialog.getInt(self, 'Servidor de Panda', 'Puerto ADB local (normalmente 5037):', int(self.store.setting('port', '5037')), 1, 65535)
        if ok:
            self.store.set_setting('port', port)
            self.fresh = False
            self.render()
            self.scan()

    def open_panda(self):
        configured = self.store.setting('panda')
        path = Path(configured) if configured else Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'panda_android' / 'touping.exe'
        if not path.is_file():
            chosen, _ = QFileDialog.getOpenFileName(self, 'Selecciona el ejecutable de Panda', '', 'Programa (*.exe)')
            if not chosen:
                return
            path = Path(chosen)
        self.store.set_setting('panda', str(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def help(self):
        QMessageBox.information(self, 'Conectar mediante Panda',
            '1. Abre Panda y comprueba la alimentación de las placas.\n'
            '2. Completa en Panda el proceso OTG habitual.\n'
            '3. Si Android solicita autorización USB, acéptala en la placa desde Panda.\n'
            '4. Pulsa Buscar y validar / Reintentar.\n\n'
            'Validado significa que la placa respondió a una consulta real.\n'
            'Esta versión acompaña el proceso de Panda; no automatiza sus botones.\n'
            'No reinicia el servidor ADB ni modifica la configuración USB de las placas.')

    def closeEvent(self, event):
        if self.worker is not None:
            QMessageBox.information(self, 'Comprobación en curso', 'Espera a que termine la búsqueda antes de cerrar.')
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet('''
        QWidget { background: #f4f7fb; color: #172c43; font-family: 'Segoe UI'; font-size: 13px; }
        QLabel#title { font-size: 30px; font-weight: 700; }
        QLabel#summary { background: #e1edf8; padding: 18px; border-radius: 10px; font-size: 18px; font-weight: 600; }
        QPushButton { background: #ffffff; border: 1px solid #c7d5e3; border-radius: 7px; padding: 10px 14px; }
        QPushButton:hover { background: #e1edf8; }
        QPushButton:disabled { color: #94a3b8; }
        QTableWidget { background: white; alternate-background-color: #f0f5fa; border: 1px solid #d5e0eb; gridline-color: #e3eaf2; }
        QHeaderView::section { background: #e1edf8; padding: 10px; border: none; font-weight: 600; }
        QTableWidget::item:selected { background: #d2e7fc; color: #172c43; }
    ''')
    window = Window()
    window.show()
    sys.exit(app.exec())

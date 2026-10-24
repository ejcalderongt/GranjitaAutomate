import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QLockFile
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog, QFileDialog, QCheckBox, QProgressBar, QDialog, QTabWidget,
    QPlainTextEdit, QLineEdit)

from .core import Adb, Store, ROOT
from .inventory import FleetStore, scan_fleet, collect_inventory


class ScanWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, ports, known=None, panda_path=None):
        super().__init__()
        self.ports = ports
        self.known = known or []
        self.panda_path = panda_path

    def run(self):
        try:
            from .reconciliation import reconcile
            self.completed.emit(reconcile(self.ports, self.known, self.panda_path, self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class InventoryWorker(QThread):
    progress = Signal(int, int)
    result = Signal(str, int, str, list)
    completed = Signal()

    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def run(self):
        from concurrent.futures import ThreadPoolExecutor

        def collect(row):
            try:
                return collect_inventory(row['port'], row['serial'])
            except Exception as exc:
                from .core import now
                return [dict(field='Consulta general', value=str(exc), state='Error', source='ADB', at=now())]

        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, (row, observations) in enumerate(zip(self.rows, pool.map(collect, self.rows)), 1):
                self.result.emit(row['id'], row['port'], row['serial'], observations)
                self.progress.emit(i, len(self.rows))
        self.completed.emit()


class InventoryDialog(QDialog):
    def __init__(self, store, row, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Ficha de inventario · ' + row['display_name'])
        self.resize(1080, 680)
        layout = QVBoxLayout(self)
        observations, snapshot, count = store.inventory(row['id'])
        identity = QLabel(f"Nombre: {row['display_name']} · Serial físico: {row['hardware_serial'] or 'No disponible'} · {row['identity_state']}\nIdentidad interna: {row['id']}\nConexión seleccionada: localhost:{row['port']} → {row['serial']}")
        identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(identity)
        caption = f"Última captura: {snapshot['at']} · origen :{snapshot['port']} · Valores históricos hasta actualizar" if snapshot else 'Sin inventario todavía. Cierra y pulsa Inventariar seleccionada o Inventariar todas.'
        caption += '\nCambios destacados respecto de la captura anterior.' if count > 1 else '\nAún no hay una captura anterior para comparar.'
        layout.addWidget(QLabel(caption))
        tabs = QTabWidget()
        groups = {
            'Sistema y root': lambda f: f in ('Fabricante','Modelo','Serie hardware','Serie de arranque','Android','API','Compilación','Parche de seguridad','Arquitecturas','Idioma del sistema','Idioma seleccionado','Zona horaria','Identidad de sesión ADB','Ruta de su','Evaluación de root'),
            'Red y USB': lambda f: f in ('IP por interfaz','Rutas IPv4','Rutas IPv6','DNS privado (modo)','DNS privado (servidor)','Proxy global','Wi-Fi habilitado','Datos móviles habilitados','Wi-Fi actual','Redes activas y DNS','USB configurado','USB actual'),
            'Recursos y ajustes': lambda f: f in ('Batería','Almacenamiento','Depuración compilada','Depuración ADB habilitada','Accesibilidad habilitada','Servicios de accesibilidad','Consulta general'),
            'Aplicaciones': lambda f: f == 'Paquetes y versiones (código)',
        }
        for title, predicate in groups.items():
            page = QWidget()
            box = QVBoxLayout(page)
            table = QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(['Dato', 'Valor', 'Resultado', 'Cambio'])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            detail = QPlainTextEdit()
            detail.setReadOnly(True)
            detail.setMaximumHeight(230)
            subset = [o for o in observations if predicate(o['field'])]
            for i, observation in enumerate(subset):
                table.insertRow(i)
                for j, value in enumerate([observation['field'], observation['value'].replace('\n',' · '), observation['state'], 'Modificado' if observation['changed'] else '—']):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    if observation['changed']:
                        item.setBackground(QColor('#fff1c2'))
                    table.setItem(i, j, item)
            def show(table=table, subset=subset, detail=detail):
                i = table.currentRow()
                if 0 <= i < len(subset):
                    o = subset[i]
                    detail.setPlainText(f"{o['field']} · {o['state']}\nFecha: {o['at']}\nFuente: {o['source']}\n\n{o['value'] or '(sin valor disponible)'}")
            table.itemSelectionChanged.connect(show)
            box.addWidget(table, 1)
            box.addWidget(detail)
            if subset:
                table.selectRow(0)
            tabs.addTab(page, title)
        layout.addWidget(tabs)
        close = QPushButton('Cerrar ficha')
        close.clicked.connect(self.accept)
        layout.addWidget(close)


class Window(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or FleetStore()
        self.worker = None
        self.fresh = False
        self.reconciliation = {}
        self.setWindowTitle('GranjitaAutomate · v2.4')
        self.resize(1280, 900)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel('GranjitaAutomate')
        title.setObjectName('title')
        layout.addWidget(title)
        layout.addWidget(QLabel('Inventario de tu granja · API Panda y laboratorio · Versión 2.4'))
        self.summary = QLabel('Listo para buscar tus placas')
        self.summary.setObjectName('summary')
        layout.addWidget(self.summary)
        self.server_table = QTableWidget(0, 5)
        self.server_table.setHorizontalHeaderLabels(['Servidor / puerto', 'Proceso ADB (PID)', 'Estado', 'Conexiones', 'Comprobación'])
        self.server_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.server_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.server_table.setMaximumHeight(130)
        layout.addWidget(self.server_table)
        toolbar = QHBoxLayout()
        self.scan_button = QPushButton('Conciliar y conectar / Reintentar')
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
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('Filtrar por nombre, dispositivo, modelo o puerto…')
        self.filter.textChanged.connect(self.render)
        layout.addWidget(self.filter)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(['Nombre', 'Serial físico', 'Conexión ADB', 'Puerto / acceso', 'Modelo', 'Android', 'Estado', 'Inventario', 'Comprobación', 'Panda', 'Diagnóstico / siguiente paso'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.table.doubleClicked.connect(self.show_inventory)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for text, callback in [('Ver ficha', self.show_inventory), ('Inventariar seleccionada', self.inventory_selected), ('Inventariar todas', self.inventory_all), ('Cambiar nombre', self.rename), ('Ver historial', self.history), ('Respaldar SQLite', self.backup)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        identity_actions = QHBoxLayout()
        for text, callback in [('Laboratorio Appium / Automate', self.automation_lab), ('API Panda', self.panda_api), ('Asociar conexión a otra ficha', self.link_connection), ('Ayuda de conexión', self.help)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            identity_actions.addWidget(button)
        identity_actions.addStretch()
        layout.addLayout(identity_actions)
        self.detail = QLabel('Al iniciar se intenta abrir Panda y recuperar conexiones conocidas. Selecciona una fila para consultar el diagnóstico.')
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(45)
        layout.addWidget(self.detail)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.notice = QLabel('SQLite local · Los registros guardados se verifican al iniciar una búsqueda. Doble clic para abrir una ficha.')
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
        selected = (self.selected()['port'], self.selected()['serial']) if hasattr(self, 'rows') and self.selected() else None
        all_rows = self.store.fleet_devices()
        all_rows.sort(key=lambda r: (r['status'] != 'Validado', r['display_name'].lower(), r['port']))
        from .reconciliation import diagnosis
        query = self.filter.text().lower() if hasattr(self, 'filter') else ''
        self.rows = [r for r in all_rows if query in f"{r['display_name']} {r['hardware_serial']} {r['serial']} {r['model']} {r['port']}".lower()]
        self.server_table.setRowCount(0)
        for i, server in enumerate(sorted(self.store.servers(), key=lambda s: (s['status'] != 'ADB responde', s['port']))):
            self.server_table.insertRow(i)
            values = [f"127.0.0.1:{server['port']}", str(server['pid'] or 'No disponible'), server['status'] if self.fresh else 'Pendiente de verificar', str(server['count']) if self.fresh else '—', server['at'][11:19] + ' · GT']
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(server['detail'] or server['at'])
                self.server_table.setItem(i, j, item)
        self.table.setRowCount(0)
        colors = {'Validado': '#15803d', 'Desconectado': '#64748b', 'Requiere autorización': '#b45309'}
        for i, row in enumerate(self.rows):
            self.table.insertRow(i)
            transport = f"{row['port']} / " + ('TCP/IP' if ':' in row['serial'] else 'USB / otro')
            checked = row['last_check'][11:19] + ' · GT'
            _, snapshot, _ = self.store.inventory(row['id'])
            inventory_at = snapshot['at'][11:19] + ' · GT' if snapshot else 'Sin captura'
            values = [row['display_name'], row['hardware_serial'] or 'No disponible', row['serial'], transport, row['model'], row['android'], row['status'] if self.fresh else 'Pendiente de verificar', inventory_at, checked]
            recognition, advice = diagnosis(row, self.reconciliation.get('panda', []), bool(self.reconciliation) and not self.reconciliation.get('panda_error'))
            values.extend([recognition if self.fresh else 'Sin comprobar', advice if self.fresh else 'Estado histórico: esperando conciliación.'])
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                if self.fresh and row['status'] == 'Validado':
                    item.setBackground(QColor('#dcfce7'))
                item.setToolTip(row['last_check'] if j == 8 else snapshot['at'] if j == 7 and snapshot else f"{row['identity_state']} · Leído: {row['identity_at']}" if j == 1 else value)
                if j == 6:
                    item.setForeground(QColor(colors.get(value, '#b45309')))
                self.table.setItem(i, j, item)
            if (row['port'], row['serial']) == selected:
                self.table.selectRow(i)
        if self.fresh:
            valid = sum(r['status'] == 'Validado' for r in all_rows)
            absent = sum(r['status'] == 'Desconectado' for r in all_rows)
            identities = len({r['id'] for r in all_rows})
            physical = len({r['hardware_serial'] for r in all_rows if r['status'] == 'Validado' and r['hardware_serial']})
            self.summary.setText(f'{physical} seriales físicos activos · {valid} conexiones validadas   ·   {len(all_rows)-valid-absent} requieren atención   ·   {absent} desconectadas   ·   {identities} fichas')
        else:
            self.summary.setText(f'{len(self.rows)} placas guardadas · Pendientes de verificar')

    def scan(self):
        if self.worker is not None:
            return
        self.scan_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.notice.setText('Buscando servidores ADB activos y validando sus conexiones…')
        ports = self.ports()
        panda_path = self.store.setting('panda') or str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'panda_android' / 'touping.exe')
        self.worker = ScanWorker(ports, self.store.fleet_devices(), panda_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.completed.connect(self.scanned)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def automation_lab(self):
        if self.worker is not None:
            QMessageBox.information(self,'Proceso en curso','Espera a que termine la consulta antes de abrir el laboratorio.')
            return
        if not self.fresh:
            QMessageBox.information(self,'Conexiones pendientes','Primero busca y valida las conexiones.')
            return
        from .automation_ui import AutomationDialog
        self.timer.stop()
        try:
            AutomationDialog(self.store,self.selected(),self).exec()
        finally:
            self.timer.start(30000)

    def panda_api(self):
        from .panda_ui import PandaDialog
        PandaDialog(self.store,self).exec()

    def update_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def scanned(self, results):
        try:
            self.store.save_fleet(results)
            self.reconciliation = results.get('reconciliation', {})
            self.fresh = True
            self.render()
            count = len(results['devices'])
            rec = self.reconciliation
            self.notice.setText(f"Conciliación: {count} transportes detectados · {len(rec.get('attempts', []))} reconexiones intentadas · Panda: {len(rec.get('panda', [])) if not rec.get('panda_error') else 'sin verificar'}. {results['warning']} " + ' '.join(rec.get('notes', [])) + (' API: ' + rec['panda_error'] if rec.get('panda_error') else ''))
            if not count:
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
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self.scan_button.setEnabled(True)
        self.progress.hide()

    def show_detail(self):
        row = self.selected()
        if row:
            prefix = '' if self.fresh else 'Registro histórico; falta comprobar el estado actual.\n'
            from .reconciliation import diagnosis
            _, advice = diagnosis(row, self.reconciliation.get('panda', []), not self.reconciliation.get('panda_error'))
            self.detail.setText(prefix + row['identity_state'] + ' · ' + row['detail'] + '\n' + advice)

    def rename(self, *_):
        row = self.selected()
        if not row:
            QMessageBox.information(self, 'Selecciona una placa', 'Selecciona primero una fila de la lista.')
            return
        text, ok = QInputDialog.getText(self, 'Nombre de la placa', f"Nombre automático: {row['auto_name']}\nAlias opcional (déjalo vacío para usar el serial):", text=row['alias'])
        if ok:
            self.store.rename_device(row['id'], text.strip()[:100])
            self.render()

    def history(self):
        row = self.selected()
        if not row:
            return
        records = self.store.device_history(row['id'])
        box = QMessageBox(self)
        box.setWindowTitle('Historial de la placa')
        box.setText(row['display_name'])
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
        text, ok = QInputDialog.getText(self, 'Servidores ADB', 'Puertos locales separados por coma. También se detectan procesos ADB activos:', text=','.join(map(str,self.ports())))
        if ok:
            try:
                ports = sorted(set(int(p.strip()) for p in text.split(',')))
                if not ports or len(ports) > 32 or any(p < 1 or p > 65535 for p in ports):
                    raise ValueError()
            except ValueError:
                QMessageBox.warning(self, 'Puertos inválidos', 'Introduce hasta 32 puertos entre 1 y 65535, separados por coma.')
                return
            self.store.set_setting('ports', ','.join(map(str, ports)))
            self.fresh = False
            self.render()
            self.scan()

    def ports(self):
        return [int(p) for p in self.store.setting('ports', '5037,5038').split(',')]

    def show_inventory(self, *_):
        row = self.selected()
        if row:
            InventoryDialog(self.store, row, self).exec()
        else:
            QMessageBox.information(self, 'Selecciona una placa', 'Selecciona una conexión para abrir la ficha.')

    def inventory_selected(self):
        row = self.selected()
        self.start_inventory([row] if row else [])

    def inventory_all(self):
        self.start_inventory(self.store.fleet_devices())

    def start_inventory(self, rows):
        if self.worker is not None:
            QMessageBox.information(self, 'Proceso en curso', 'Espera a que termine el proceso actual.')
            return
        rows = [r for r in rows if self.fresh and r['status'] == 'Validado']
        if not rows:
            QMessageBox.information(self, 'Primero valida la conexión', 'Busca y valida las placas antes de inventariarlas.')
            return
        self.inventory_errors = []
        self.scan_button.setEnabled(False)
        self.progress.setRange(0, len(rows))
        self.progress.setValue(0)
        self.progress.show()
        self.notice.setText('Leyendo inventario: sistema, redes, recursos, paquetes y evidencias de root. No se ejecuta su.')
        self.worker = InventoryWorker(rows)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.inventory_result)
        self.worker.completed.connect(self.inventory_done)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def inventory_result(self, identifier, port, serial, observations):
        try:
            self.store.save_inventory(identifier, port, serial, observations)
        except Exception as exc:
            self.inventory_errors.append(str(exc))

    def inventory_done(self):
        self.render()
        self.notice.setText('Inventario guardado. Abre una ficha para ver valores, evidencia y cambios.' if not self.inventory_errors else 'Algunas capturas no se guardaron: ' + '; '.join(self.inventory_errors))

    def link_connection(self):
        if self.worker is not None:
            return
        row = self.selected()
        if not row:
            return
        candidates = {r['id']: r for r in self.store.fleet_devices() if r['id'] != row['id']}
        choices = {f"{r['display_name']} · {r['id'][:8]}": identifier for identifier, r in candidates.items()}
        if not choices:
            return
        choice, ok = QInputDialog.getItem(self, 'Asociación física', 'Elige la ficha del MISMO dispositivo físico. Revisa los números de serie en ambas fichas:', list(choices), 0, False)
        if ok:
            confirm = QMessageBox.question(self, 'Confirmar identidad', '¿Confirmas que ambas conexiones pertenecen a la misma placa física? Se conservará el historial en la ficha elegida.')
            if confirm == QMessageBox.StandardButton.Yes:
                self.store.link_connection(row['port'], row['serial'], choices[choice])
                self.render()

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
            'Al iniciar abre Panda si falta y reintenta transportes conocidos en su servidor de origen.\n'
            'No reinicia ADB ni activa físicamente el rack. Sin telemetría no se puede confirmar energía por socket.')

    def closeEvent(self, event):
        if self.worker is not None:
            QMessageBox.information(self, 'Comprobación en curso', 'Espera a que termine la búsqueda antes de cerrar.')
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    from .core import DATA
    DATA.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(DATA / 'application.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None, 'GranjitaAutomate', 'La aplicación ya está abierta en esta carpeta.')
        return
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
    try:
        window = Window()
    except Exception as exc:
        QMessageBox.critical(None, 'No se pudo abrir GranjitaAutomate', f'No se pudo preparar la base de datos.\n{exc}\n\nConserva la carpeta data y su respaldo antes de intentar reparar.')
        return
    window.show()
    sys.exit(app.exec())

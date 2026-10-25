import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QLockFile
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog, QFileDialog, QCheckBox, QProgressBar, QDialog, QTabWidget,
    QPlainTextEdit, QLineEdit, QGroupBox, QMenu)

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
        self.startup_pending = True
        self.setWindowTitle('GranjitaAutomate · v2.10')
        self.resize(1280, 930)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel('GranjitaAutomate')
        title.setObjectName('title')
        header.addWidget(title)
        header.addStretch()
        version = QLabel('Versión 2.10')
        version.setToolTip('Versión instalada del programa. Los cambios se documentan en el repositorio del proyecto.')
        header.addWidget(version)
        self.advanced_button = QPushButton('Avanzado')
        self.advanced_button.setToolTip('Opciones de inventario, nombres, ubicación física, diagnóstico y respaldo de la base de datos.')
        header.addWidget(self.advanced_button)
        layout.addLayout(header)
        indicator_row = QHBoxLayout()
        self.indicators = {}
        indicators = [
            ('online', 'En línea', 'Seriales físicos distintos que respondieron por ADB. No confirma acceso a Internet.'),
            ('ready', 'Aptos para tareas', 'Dispositivos en línea con serial físico único y sin conflicto de identidad.'),
            ('review', 'Requieren revisión', 'Fichas que no están listas para tareas: desconectadas, sin verificar o con identidad ambigua.'),
            ('saved', 'Fichas guardadas', 'Registros del inventario local. Puede haber fichas históricas pendientes de asociar; no equivale al número físico del rack.'),
        ]
        for key, label, tooltip in indicators:
            card = QWidget()
            card.setObjectName('indicatorCard')
            card.setStyleSheet('QWidget#indicatorCard { background:#e7f0f6; border-radius:9px; }')
            card.setToolTip(tooltip)
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 10, 16, 10)
            value = QLabel('—')
            value.setStyleSheet('font-size:34px;font-weight:700;color:#172c43;background:transparent;')
            value.setToolTip(tooltip)
            caption = QLabel(label)
            caption.setStyleSheet('font-size:14px;background:transparent;')
            caption.setToolTip(tooltip)
            box.addWidget(value)
            box.addWidget(caption)
            self.indicators[key] = value
            indicator_row.addWidget(card, 1)
        layout.addLayout(indicator_row)
        self.summary = QLabel('Conecta los dispositivos para comprobar su estado actual.')
        self.summary.setObjectName('summary')
        self.summary.setWordWrap(True)
        self.summary.setToolTip('Los números se actualizan al terminar la comprobación. Los datos guardados no se presentan como conexiones actuales.')
        layout.addWidget(self.summary)
        connect_group = QGroupBox('1. Conectar y comprobar')
        connect_group.setToolTip('Enciende primero las placas y el rack. Después comprueba sus conexiones desde el programa.')
        connect_layout = QVBoxLayout(connect_group)
        connect_layout.addWidget(QLabel('Enciende el rack y las placas. Después comprueba cuáles responden.'))
        toolbar = QHBoxLayout()
        self.scan_button = QPushButton('Conectar dispositivos')
        self.scan_button.setToolTip('Abre Panda si hace falta, intenta recuperar conexiones conocidas y comprueba los dispositivos. No enciende físicamente el rack.')
        self.scan_button.clicked.connect(self.scan)
        toolbar.addWidget(self.scan_button)
        panda = QPushButton('Abrir Panda')
        panda.setToolTip('Abre Panda para completar Habilitar / Escanear, el modo OTG o una autorización pendiente.')
        panda.clicked.connect(self.open_panda)
        toolbar.addWidget(panda)
        toolbar.addStretch()
        connect_layout.addLayout(toolbar)
        layout.addWidget(connect_group)
        self.server_table = QTableWidget(0, 5)
        self.server_table.setHorizontalHeaderLabels(['Servidor / puerto', 'Proceso ADB (PID)', 'Estado', 'Conexiones', 'Comprobación'])
        self.server_table.setToolTip('Diagnóstico técnico de los servidores ADB que gestiona Panda. Una placa puede tener más de un transporte.')
        self.server_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.server_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.server_table.setMaximumHeight(130)
        self.server_table.hide()
        layout.addWidget(self.server_table)
        # Mantener preferencias y comportamiento existentes; se controlan desde el menú.
        self.auto = QCheckBox(central)
        self.auto.setChecked(self.store.setting('auto', '0') == '1')
        self.auto.toggled.connect(lambda checked: self.store.set_setting('auto', int(checked)))
        self.auto.hide()
        self.active_first = QCheckBox(central)
        self.active_first.setChecked(self.store.setting('active_first', '0') == '1')
        self.active_first.toggled.connect(self.change_order)
        self.active_first.hide()
        device_group = QGroupBox('2. Revisar y elegir un dispositivo')
        device_group.setToolTip('Revisa el estado y selecciona una fila. El verde indica respuesta comprobada; abre la ficha para ver los detalles.')
        device_layout = QVBoxLayout(device_group)
        search = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText('Buscar por nombre, rack, posición o serial…')
        self.filter.setToolTip('Filtra la lista sin eliminar registros. Borra el texto para volver a ver todos los dispositivos.')
        self.filter.textChanged.connect(self.render)
        search.addWidget(self.filter, 1)
        ficha = QPushButton('Ver ficha')
        ficha.setToolTip('Muestra el inventario y las últimas observaciones del dispositivo seleccionado. También puedes hacer doble clic en una fila.')
        ficha.clicked.connect(self.show_inventory)
        search.addWidget(ficha)
        device_layout.addLayout(search)
        self.table = QTableWidget(0, 16)
        self.table.setHorizontalHeaderLabels(['Nombre', 'Serial físico', 'Conexión ADB', 'Puerto / acceso', 'Modelo', 'Android', 'Estado', 'Inventario', 'Comprobación', 'Panda', 'Diagnóstico / siguiente paso', 'Rack', 'Posición', 'Número fijo Panda', 'Último snapshot', 'Recuperación'])
        self.table.setToolTip('Selecciona un dispositivo para consultar su diagnóstico. Los desconectados conservan su posición física asignada.')
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(75)
        for column, width in {0:210, 1:150, 2:175, 6:145, 9:120, 10:260, 11:80, 12:80, 14:185}.items():
            self.table.setColumnWidth(column, width)
        for logical, visual in [(11, 0), (12, 1), (13, 2)]:
            self.table.horizontalHeader().moveSection(self.table.horizontalHeader().visualIndex(logical), visual)
        explanations = {
            0:'Nombre o alias guardado para reconocer el dispositivo.',
            1:'Serial declarado por Android; se valida para evitar confundir placas cuando cambia su IP.',
            2:'Identificador del transporte ADB; puede cambiar y no es la identidad física.',
            3:'Servidor ADB de origen y tipo de acceso observado.',
            4:'Modelo reportado por Android.', 5:'Versión de Android reportada.',
            6:'Validado: respondió. Los demás estados requieren revisar el diagnóstico.',
            7:'Fecha de la última captura de inventario; puede contener datos históricos.',
            8:'Hora de Guatemala de la última comprobación de esta conexión.',
            9:'Si la API de Panda reconoce el serial y qué modo de conexión reporta.',
            10:'Posibles causas y siguiente paso sugerido; no constituye una medida eléctrica del socket.',
            11:'Identificador del rack asignado, por ejemplo R01.',
            12:'Posición física asignada dentro del rack; no cambia al desconectarse.',
            13:'Número permanente reservado para Panda en el mapa físico.',
            14:'Último snapshot registrado, con fecha y estado completo o parcial.',
            15:'Resultado guardado de la verificación o recuperación del snapshot.',
        }
        for column, tooltip in explanations.items():
            self.table.horizontalHeaderItem(column).setToolTip(tooltip)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.table.doubleClicked.connect(self.show_inventory)
        device_layout.addWidget(self.table, 1)
        self.detail = QLabel('Selecciona una fila para ver su estado y el siguiente paso sugerido.')
        self.detail.setToolTip('Explicación de la identidad, el resultado de conexión y el diagnóstico del dispositivo seleccionado.')
        self.detail.setWordWrap(True)
        device_layout.addWidget(self.detail)
        layout.addWidget(device_group, 1)
        execute_group = QGroupBox('3. Preparar y ejecutar')
        execute_group.setToolTip('Puedes respaldar primero el estado y después crear la tarea. El snapshot es opcional, no un requisito para ejecutar.')
        execute_layout = QVBoxLayout(execute_group)
        execute_layout.addWidget(QLabel('Opcional: guarda un snapshot. Luego crea la tarea y selecciona sus dispositivos.'))
        actions = QHBoxLayout()
        for text, callback, tooltip in [
            ('Snapshots', self.snapshot_panel, 'Crea y consulta snapshots. Al recuperar, solo repone archivos administrados ausentes; no restaura sesiones de otras aplicaciones.'),
            ('Automatización', self.automation_lab, 'Crea una receta, selecciona uno o varios dispositivos y define likes, scroll y horario. Incluye resultados y auditoría del laboratorio local.'),
        ]:
            button = QPushButton(text)
            button.setToolTip(tooltip)
            if text == 'Automatización':
                button.setStyleSheet('QPushButton { background:#246b4d; color:white; font-weight:600; } QPushButton:hover { background:#1e5940; }')
            button.clicked.connect(callback)
            actions.addWidget(button, 1)
        execute_layout.addLayout(actions)
        layout.addWidget(execute_group)
        menu = QMenu(self.advanced_button)
        menu.setToolTipsVisible(True)
        def add(parent, text, callback, tooltip):
            action = parent.addAction(text)
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
            action.triggered.connect(callback)
            return action
        inventory_menu = menu.addMenu('Inventario')
        inventory_menu.setToolTipsVisible(True)
        inventory_menu.menuAction().setToolTip('Actualizar las observaciones guardadas o consultar el historial de una ficha.')
        for text, callback, tooltip in [
            ('Actualizar seleccionada', self.inventory_selected, 'Consulta y guarda un inventario nuevo de la fila seleccionada.'),
            ('Actualizar todas', self.inventory_all, 'Consulta y guarda el inventario de las conexiones validadas. Puede tardar varios minutos.'),
            ('Ver historial', self.history, 'Consulta las últimas comprobaciones guardadas de la ficha seleccionada.'),
        ]: add(inventory_menu, text, callback, tooltip)
        identity_menu = menu.addMenu('Identidad y ubicación')
        identity_menu.setToolTipsVisible(True)
        identity_menu.menuAction().setToolTip('Administrar alias, mapa físico y asociaciones entre conexiones e identidades.')
        for text, callback, tooltip in [
            ('Cambiar nombre', self.rename, 'Cambia el alias local de la ficha seleccionada; no cambia el serial ni renombra Android.'),
            ('Asignar rack / posición', self.physical_position, 'Verifica el serial y asigna una posición física. Desde ese diálogo puedes aplicar el nombre y número guardados a Panda.'),
            ('Asociar conexión a otra ficha', self.link_connection, 'Corrige manualmente la asociación histórica de un transporte. Revisa cuidadosamente ambas identidades antes de confirmar.'),
        ]: add(identity_menu, text, callback, tooltip)
        connection_menu = menu.addMenu('Conexión y diagnóstico')
        connection_menu.setToolTipsVisible(True)
        connection_menu.menuAction().setToolTip('Consultar Panda, configurar puertos y ver el diagnóstico técnico de ADB.')
        add(connection_menu, 'API Panda', self.panda_api, 'Consulta la API local y compara sus dispositivos con las fichas. No cambia nombres ni grupos.')
        add(connection_menu, 'Configurar puertos ADB', self.configure, 'Define qué puertos locales consultar además de los detectados. No reinicia los servidores.')
        def toggle(parent, text, tooltip, checked, callback):
            action = parent.addAction(text)
            action.setCheckable(True)
            action.setChecked(checked)
            action.setToolTip(tooltip)
            action.toggled.connect(callback)
            return action
        toggle(connection_menu, 'Ver servidores ADB', 'Muestra u oculta la tabla técnica de puertos, procesos y conexiones.', False, self.server_table.setVisible)
        toggle(connection_menu, 'Revisar cada 30 segundos', 'Repite la conciliación cuando no hay otra consulta en curso.', self.auto.isChecked(), self.auto.setChecked)
        view_menu = menu.addMenu('Vista')
        view_menu.setToolTipsVisible(True)
        view_menu.menuAction().setToolTip('Cambiar la prioridad de orden o mostrar más columnas sin alterar los datos.')
        toggle(view_menu, 'Activos primero', 'Prioriza los activos. Desactiva para conservar el orden físico fijo de rack y posición.', self.active_first.isChecked(), self.active_first.setChecked)
        toggle(view_menu, 'Ver columnas técnicas', 'Muestra serial, transporte, versión Android y otros campos técnicos en la tabla.', False, self.show_technical_columns)
        self.show_technical_columns(False)
        menu.addSeparator()
        add(menu, 'Respaldar SQLite', self.backup, 'Crea una copia coherente de la base principal: inventario, mapa físico y snapshots. La base de tareas es independiente.')
        add(menu, 'Ayuda de conexión', self.help, 'Muestra los pasos para conectar placas mediante Panda y los límites del diagnóstico.')
        self.advanced_button.setMenu(menu)
        self.progress = QProgressBar()
        self.progress.setToolTip('Progreso de la consulta actual. Mientras se ejecuta, espera antes de cambiar configuración o cerrar.')
        self.progress.hide()
        layout.addWidget(self.progress)
        self.notice = QLabel('El programa comprueba las conexiones al abrir. Los registros históricos se conservan para revisión.')
        self.notice.setToolTip('Resultado del último proceso. Los errores de consulta o recuperación se muestran aquí y se conservan en el historial correspondiente.')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.render()
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.scan() if self.auto.isChecked() else None)
        self.timer.start(30000)
        QTimer.singleShot(400, self.scan)

    def show_technical_columns(self, visible):
        for column in [1, 2, 3, 4, 5, 7, 8, 13, 15]:
            self.table.setColumnHidden(column, not visible)

    def snapshot_panel(self):
        if self.worker is not None:
            QMessageBox.information(self, 'Proceso en curso', 'Espera a que termine la consulta o recuperación.');return
        from .snapshots_ui import SnapshotDialog
        self.timer.stop()
        try:
            SnapshotDialog(self.store, self.selected(), self).exec()
        finally:
            self.timer.start(30000)

    def recover_startup(self):
        if self.worker is not None:
            return
        from .snapshots_ui import SnapshotWorker
        self.worker = SnapshotWorker(self.store)
        self.scan_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.notice.setText('Verificando snapshots y recuperando archivos administrados ausentes…')
        self.worker.progress.connect(lambda count, text: self.notice.setText(f'Snapshots: {count} · {text}'))
        self.worker.result.connect(lambda results: self.notice.setText(f"Snapshots: {len(results)} placas procesadas · {sum(r['detail'].startswith('Error') for r in results)} errores. Abre Snapshots para ver estados y diferencias."))
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def change_order(self, checked):
        self.store.set_setting('active_first', int(checked))
        self.render()

    def physical_position(self):
        if self.worker is not None:
            QMessageBox.information(self, 'Consulta en curso', 'Espera a que termine la conciliación.');return
        row = self.selected()
        if not row or not self.fresh:
            QMessageBox.information(self, 'Selecciona una placa', 'Primero concilia y selecciona una placa validada.');return
        from .physical_ui import PositionDialog
        self.timer.stop()
        try:
            PositionDialog(self.store, row, self).exec()
            self.render()
        finally:
            self.timer.start(30000)

    def selected(self):
        row = self.table.currentRow()
        return self.rows[row] if row >= 0 and row < len(self.rows) else None

    def render(self):
        selected = (self.selected()['port'], self.selected()['serial']) if hasattr(self, 'rows') and self.selected() else None
        all_rows = self.store.fleet_devices()
        from .physical import ordered_rows
        all_rows = ordered_rows(all_rows, self.store.positions(), self.active_first.isChecked())
        from .reconciliation import diagnosis
        query = self.filter.text().lower() if hasattr(self, 'filter') else ''
        self.rows = [r for r in all_rows if query in f"{r['display_name']} {r['hardware_serial']} {r['serial']} {r['model']} {r['port']} {r.get('rack', '')} {r.get('slot', '')}".lower()]
        self.server_table.setRowCount(0)
        for i, server in enumerate(sorted(self.store.servers(), key=lambda s: (s['status'] != 'ADB responde', s['port']))):
            self.server_table.insertRow(i)
            values = [f"127.0.0.1:{server['port']}", str(server['pid'] or 'No disponible'), server['status'] if self.fresh else 'Pendiente de verificar', str(server['count']) if self.fresh else '—', server['at'][11:19] + ' · GT']
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(server['detail'] or server['at'])
                self.server_table.setItem(i, j, item)
        with self.store.connect() as db:
            checkpoints = {r['hardware_serial']: dict(r) for r in db.execute('SELECT hardware_serial,at,status FROM device_checkpoints ORDER BY rowid')}
            recoveries = {r['hardware_serial']: dict(r) for r in db.execute('SELECT hardware_serial,status,detail FROM recovery_events ORDER BY id')}
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
            values.extend([recognition if self.fresh else 'Sin comprobar', advice if self.fresh else 'Estado histórico: esperando conciliación.', row.get('rack', 'Sin asignar'), str(row.get('slot', '—')), str(row.get('panda_number', '—'))])
            checkpoint = checkpoints.get(row['hardware_serial'])
            recovery = recoveries.get(row['hardware_serial'])
            values.extend([(checkpoint['at'] + ' · ' + checkpoint['status']) if checkpoint else 'Sin snapshot', (recovery['status'] + ' · ' + recovery['detail']) if recovery else 'Sin evaluación'])
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
            ready = sum(r['status'] == 'Validado' and r['identity_state'] == 'Serial leído' for r in all_rows)
            for key, value in dict(online=physical, ready=ready, review=identities-ready, saved=identities).items():
                self.indicators[key].setText(str(value))
            checked_at = max((r['last_check'] for r in all_rows), default='')
            self.summary.setText(('Última comprobación: ' + checked_at[11:19] + ' GT · ' if checked_at else '') + 'Verde: respuesta confirmada · Revisa el diagnóstico de los pendientes.')
        else:
            for key in ('online', 'ready', 'review'):
                self.indicators[key].setText('—')
            self.indicators['saved'].setText(str(len({r['id'] for r in all_rows})))
            self.summary.setText('Pendiente de comprobación · Los registros guardados todavía no representan el estado actual.')

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
        self.render()
        if self.startup_pending and self.fresh:
            self.startup_pending = False
            QTimer.singleShot(0, self.recover_startup)

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
            '4. Pulsa Conectar dispositivos.\n\n'
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
        QLabel#summary { font-size: 14px; color: #42566b; }
        QGroupBox { font-weight:600; border:1px solid #d5e0eb; border-radius:8px; margin-top:12px; padding:14px 10px 10px; }
        QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; }
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

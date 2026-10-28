"""Panel de inventario de aplicaciones, asignaciones y observaciones de cuenta."""
import json
from PySide6.QtCore import Qt,QThread,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QMessageBox,QFormLayout,QGroupBox
from .app_inventory import AppInventory,PRESENCE_LABELS,CATALOG,ACCOUNT_LABELS,SCREEN_LABELS,METHOD_LABELS,collect_technical,inspect_screen
from .inventory import scan_fleet
from .physical import ordered_rows
from . import __version__


class AppAuditWorker(QThread):
    progress=Signal(int,int,str)
    completed=Signal(dict)
    def __init__(self,store,rows,scope,app_id):
        super().__init__();self.store,self.rows,self.scope,self.app_id=store,rows,scope,app_id
    def run(self):
        inventory=AppInventory(self.store);saved=0;errors=0;unreadable=0
        try:
            ports=[int(p) for p in self.store.setting('ports','5037,5038').split(',')]
            self.store.save_fleet(scan_fleet(ports))
            current={r['id']:r for r in ordered_rows(self.store.fleet_devices(),self.store.positions())}
            for index,original in enumerate(self.rows,1):
                row=current.get(original['id'],original)
                apps=[self.app_id] if self.scope=='screen' else list(CATALOG)
                try:
                    if self.scope=='technical':
                        results=collect_technical(row)
                        for app_id,payload in results.items():inventory.observe(row,app_id,'technical',payload,'adb');saved+=1
                    else:
                        payload=inspect_screen(row,self.app_id)
                        inventory.observe(row,self.app_id,'screen',payload,'uiautomator2');saved+=1
                        if payload.get('status')!='ok':errors+=1
                        if payload.get('screen_state')=='unreadable':unreadable+=1
                except Exception as exc:
                    errors+=1
                    for app_id in apps:
                        payload=dict(status='error',error_class=type(exc).__name__)
                        if self.scope=='screen':payload.update(screen_state='unreadable',account_state='unknown',observed_account='',confidence='low',signals=['read_failed'])
                        try:inventory.observe(row,app_id,self.scope,payload,'adb' if self.scope=='technical' else 'uiautomator2');saved+=1
                        except Exception:pass
                self.progress.emit(index,len(self.rows),row['display_name'])
            self.completed.emit(dict(saved=saved,errors=errors,unreadable=unreadable,devices=len(self.rows)))
        except Exception as exc:self.completed.emit(dict(saved=saved,errors=errors+1,devices=0,error_class=type(exc).__name__))


class AppAccountsDialog(QDialog):
    def __init__(self,store,preferred=None,parent=None):
        super().__init__(parent);self.store=store;self.inventory=AppInventory(store);self.worker=None
        self.setWindowTitle('Apps y cuentas · GranjitaAutomate '+__version__);self.resize(1260,900)
        layout=QVBoxLayout(self)
        title=QLabel('Inventario de apps y cuentas');title.setStyleSheet('font-size:23px;font-weight:600;');layout.addWidget(title)
        intro=QLabel('Cuenta asignada y cuenta observada son datos distintos. Una app abierta o un feed visible no confirma sesión. Lecturas guardadas con fecha; sin contraseñas, cookies ni tokens.')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setStyleSheet('background:#e8f3ed;padding:12px;font-size:16px;');layout.addWidget(self.summary)
        bar=QHBoxLayout()
        self.app_filter=QComboBox()
        for app_id,profile in CATALOG.items():self.app_filter.addItem(profile['name'],app_id)
        self.app_filter.setToolTip('Elige la app de la ficha. Actualizar inventario consulta las cuatro apps; Leer pantalla analiza únicamente la seleccionada, sin abrirla ni navegar.')
        bar.addWidget(self.app_filter)
        self.status_filter=QComboBox()
        for text,value in [('Todos los estados','all'),('Con cuenta declarada','present'),('Sin cuenta declarada','absent'),('Pendiente de declarar','undeclared'),('Sin verificar','unverified'),('Configuración pendiente','needs_setup'),('Sesión observada','session_observed'),('Cuenta diferente','mismatch'),('Sin cuenta asignada','unassigned'),('No instalada','not_installed')]:self.status_filter.addItem(text,value)
        bar.addWidget(self.status_filter)
        self.search=QLineEdit();self.search.setPlaceholderText('Buscar dispositivo o cuenta…');bar.addWidget(self.search,1)
        self.selection_buttons=[]
        for text,callback in [('Todos',lambda:self.select_all(True)),('Ninguno',lambda:self.select_all(False))]:
            button=QPushButton(text);button.clicked.connect(callback);bar.addWidget(button);self.selection_buttons.append(button)
        layout.addLayout(bar)
        self.table=QTableWidget(0,9);self.table.setHorizontalHeaderLabels(['Usar','Dispositivo','App','Instalación / versión','Primer plano','Cuenta asignada','Cuenta observada','Estado / coincidencia','Últimas lecturas GT'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.selected);self.table.itemChanged.connect(self.check_changed);layout.addWidget(self.table,1)
        actions=QHBoxLayout();self.buttons=[]
        for text,callback,tip in [
            ('Actualizar inventario',lambda:self.audit('technical'),'Comprueba conexiones/seriales y consulta instalación, versión y primer plano en las cuatro apps de los dispositivos marcados. No abre apps.'),
            ('Leer pantalla',lambda:self.audit('screen'),'Analiza la pantalla que ya está visible mediante UiAutomator2/Appium. No abre la app ni navega, acepta diálogos o pulsa likes. TikTok dispone de reglas conservadoras; otras apps quedan sin verificar.'),
            ('Ver historial',self.history,'Muestra las observaciones y asignaciones anteriores de la ficha seleccionada, con fuente y fecha.')]:
            button=QPushButton(text);button.clicked.connect(callback);button.setToolTip(tip);self.buttons.append(button);actions.addWidget(button)
        layout.addLayout(actions)
        self.screen_hint=QLabel();self.screen_hint.setWordWrap(True);layout.addWidget(self.screen_hint)
        group=QGroupBox('Cuenta de la ficha seleccionada');form=QFormLayout(group)
        self.assignment=QLineEdit();self.assignment.setPlaceholderText('@cuenta_esperada');self.assignment.setMaxLength(65)
        self.assignment.setToolTip('Identificador público asignado por el operador. Guardarlo no confirma que haya una sesión abierta. Vacío permite retirar la asignación, preservando historial.')
        self.save_assignment=QPushButton('Guardar asignación');self.save_assignment.clicked.connect(self.assign)
        expected=QHBoxLayout();expected.addWidget(self.assignment);expected.addWidget(self.save_assignment);form.addRow('Cuenta esperada',expected)
        self.observed=QLineEdit();self.observed.setPlaceholderText('@cuenta_visible');self.observed.setMaxLength(65)
        self.manual_state=QComboBox()
        for key,label in ACCOUNT_LABELS.items():self.manual_state.addItem(label,key)
        self.manual_state.setToolTip('Declara lo comprobado por el operador. Sesión observada requiere una cuenta visible; no equivale a validar credenciales ni mantener una sesión activa permanentemente.')
        self.save_manual=QPushButton('Confirmar lo observado');self.save_manual.clicked.connect(self.confirm)
        observed=QHBoxLayout();observed.addWidget(self.observed);observed.addWidget(self.manual_state);observed.addWidget(self.save_manual);form.addRow('Validación manual',observed)
        layout.addWidget(group)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(150);layout.addWidget(self.detail)
        self.state=QLabel('Inventario guardado: pulsa Actualizar inventario para una comprobación actual.');self.state.setWordWrap(True);layout.addWidget(self.state)
        self.app_filter.currentIndexChanged.connect(self.render);self.status_filter.currentIndexChanged.connect(self.render);self.search.textChanged.connect(self.render)
        self.selected_ids={preferred['id']} if preferred else set();self._rendering=False
        self.render()
    def rows(self):return ordered_rows(self.store.fleet_devices(),self.store.positions())
    def render(self,*args):
        self._rendering=True
        app_id=self.app_filter.currentData();wanted=self.status_filter.currentData();query=self.search.text().casefold()
        self.entries=[];views=[(r,self.inventory.view(r,app_id)) for r in self.rows()]
        for row,view in views:
            text=json.dumps(dict(name=row['display_name'],serial=row.get('hardware_serial'),**view),ensure_ascii=False).casefold()
            if query and query not in text:continue
            keep=wanted=='all' or wanted in ('present','absent') and view['declared_presence']==wanted or wanted=='undeclared' and view['declared_presence']=='unknown' or wanted=='unverified' and (view['account_state']=='unknown' or not view['fresh'] or not view['assignment_checked']) or wanted=='not_installed' and view['installation']=='not_installed' or wanted in ('mismatch','unassigned') and view['match']==wanted or wanted in ('needs_setup','session_observed') and view['account_state']==wanted
            if keep:self.entries.append((row,view))
        self.table.blockSignals(True);self.table.setRowCount(len(self.entries))
        for i,(row,v) in enumerate(self.entries):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Checked if row['id'] in self.selected_ids else Qt.CheckState.Unchecked);self.table.setItem(i,0,check)
            installation={'installed':'Instalada','not_installed':'No instalada','unknown':'Sin comprobar'}[v['installation']]
            versions=', '.join(x.get('version_name') or str(x.get('version_code') or 'Versión sin comprobar') for x in v['variants'])
            if versions:installation+=' · '+versions
            if v['technical_status']=='error':installation='Lectura fallida · sin comprobar'
            account=ACCOUNT_LABELS[v['account_state']]
            if v['match']=='mismatch':account='Cuenta diferente · revisar'
            elif v['match']=='match':account+=' · coincide'
            elif v['observed_at'] and (not v['fresh'] or not v['assignment_checked']):account+=' · verificar nuevamente'
            elif v['screen_status']=='error':account='Sin verificar · lectura fallida'
            if v['installation']=='not_installed' and v['account_state']=='session_observed':account='Sesión histórica · app no instalada'
            account=PRESENCE_LABELS[v['declared_presence']]+' · '+account
            foreground='Sí' if v['foreground'] is True else 'No' if v['foreground'] is False else 'Sin comprobar'
            from datetime import datetime
            def short(at):return datetime.fromisoformat(at).strftime('%d/%m %H:%M') if at else '—'
            dates='App: '+short(v['technical_at'])+' · Cuenta: '+short(v['observed_at'])
            device_label=(f"Panda {v['declared_panda_number']:02d} · " if v['declared_panda_number'] else '')+row['display_name']
            for j,value in enumerate([device_label,CATALOG[app_id]['name'],installation,foreground,v['expected_account'] or 'Sin asignar',v['observed_account'] or 'Sin identificar',account,dates],1):
                item=QTableWidgetItem(value);item.setToolTip(value+'\n'+('Observación: '+str(v['observed_at'])+' · Fuente: '+METHOD_LABELS.get(v['method'],'Sin lectura') if j>=6 else 'Lectura técnica: '+str(v['technical_at']))+'\nDeclaración manual: '+str(v['declaration_at'])+' · '+str(v['declaration_source']));self.table.setItem(i,j,item)
        self.table.blockSignals(False)
        self.summary.setText(f"{sum(v['declared_presence']=='present' for r,v in views)} con cuenta declarada · {sum(v['declared_presence']=='absent' for r,v in views)} sin cuenta declarada · {sum(v['declared_presence']=='unknown' for r,v in views)} pendientes de declarar\n{len(views)} dispositivos · {sum(v['installation']=='installed' for r,v in views)} con {CATALOG[app_id]['name']} instalada · {sum(v['account_state']=='unknown' or not v['fresh'] for r,v in views)} identidades de cuenta sin verificar · {sum(v['match']=='mismatch' for r,v in views)} diferentes · {sum(v['account_state']=='needs_setup' for r,v in views)} con configuración pendiente")
        self._rendering=False
        self.buttons[1].setEnabled(self.worker is None and app_id=='tiktok')
        self.screen_hint.setText('TikTok: deja visible tu Perfil propio y pulsa Leer pantalla para intentar identificar la cuenta. El programa no navegará por ti ni aceptará diálogos.' if app_id=='tiktok' else 'Esta app admite inventario técnico y confirmación manual de cuenta; su adaptador automático todavía está pendiente.')
        if self.entries:self.table.selectRow(0)
    def check_changed(self,item):
        if self._rendering or item.column()!=0:return
        row=self.entries[item.row()][0]
        if item.checkState()==Qt.CheckState.Checked:self.selected_ids.add(row['id'])
        else:self.selected_ids.discard(row['id'])
    def select_all(self,checked):
        if self.worker:return
        if checked:self.selected_ids.update(r['id'] for r,v in self.entries)
        else:self.selected_ids.clear()
        self.render()
    def current(self):
        i=self.table.currentRow();return self.entries[i] if 0<=i<len(self.entries) else None
    def selected(self):
        current=self.current()
        if not current:return
        row,v=current
        self.assignment.setText(v['expected_account']);self.observed.setText(v['observed_account']);self.manual_state.setCurrentIndex(self.manual_state.findData(v['account_state']))
        comparison={'match':'Coincide con la asignación','mismatch':'Es diferente de la asignada','unassigned':'Sin cuenta asignada','unverified':'Pendiente de una observación posterior a la asignación'}
        self.detail.setPlainText(f"Declaración: {PRESENCE_LABELS[v['declared_presence']]} · {v['declaration_at'] or '—'} · fuente {v['declaration_source'] or '—'}\n{row['display_name']} · {CATALOG[v['app_id']]['name']}\nPantalla observada: {SCREEN_LABELS[v['screen_state']]}\nCuenta esperada: {v['expected_account'] or 'Sin asignar'} · Observada: {v['observed_account'] or 'Sin identificar'}\n{comparison[v['match']]}\nÚltima lectura de cuenta: {v['observed_at'] or 'Sin lectura'} · Fuente: {METHOD_LABELS.get(v['method'],'Sin lectura')}\nÚltima lectura técnica: {v['technical_at'] or 'Sin lectura'}. La información mostrada es la última evidencia guardada.")
    def assign(self):
        if self.worker or not self.current():return
        row,v=self.current()
        try:self.inventory.assign(row,v['app_id'],self.assignment.text());self.render();self.state.setText('Asignación guardada. Se requiere observación posterior para comprobar coincidencia.')
        except Exception as exc:QMessageBox.warning(self,'No se guardó la asignación',str(exc))
    def confirm(self):
        if self.worker or not self.current():return
        row,v=self.current()
        try:self.inventory.confirm(row,v['app_id'],self.observed.text(),self.manual_state.currentData());self.render();self.state.setText('Observación manual guardada con fecha y fuente; no se modificó el teléfono.')
        except Exception as exc:QMessageBox.warning(self,'No se guardó la observación',str(exc))
    def history(self):
        if not self.current():return
        row,v=self.current();history=self.inventory.history(row,v['app_id']);lines=['Observaciones (hasta 200, más recientes primero):']
        for entry in history['observations']:
            payload=entry['payload'];description=PRESENCE_LABELS[payload['presence']] if entry['scope']=='declaration' else SCREEN_LABELS.get(payload.get('screen_state'),'Inventario técnico: '+payload.get('installation',payload.get('status','Sin comprobar')))
            lines.append(entry['at']+' · '+METHOD_LABELS[entry['method']]+' · '+description+(' · '+payload['observed_account'] if payload.get('observed_account') else ''))
        lines.append('Asignaciones (hasta 100):')
        lines.extend(entry['at']+' · '+(entry['expected_account'] or 'Asignación retirada') for entry in history['assignments'])
        self.detail.setPlainText('\n'.join(lines))
    def audit(self,scope):
        if self.worker:return
        rows=[r for r in self.rows() if r['id'] in self.selected_ids]
        if not rows:QMessageBox.information(self,'Selecciona dispositivos','Marca al menos un dispositivo para auditar.');return
        # Evitar competir con una sesión de automatización del mismo rack.
        from .core import DATA
        import sqlite3
        from contextlib import closing
        path=DATA/'automation.sqlite3'
        if path.exists():
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('Ejecutando','En cola','Programado')").fetchone()[0]:
                    QMessageBox.information(self,'Tareas en curso','Espera a que termine el lote antes de auditar apps.');return
        self.worker=AppAuditWorker(self.store,rows,scope,self.app_filter.currentData());self.worker.progress.connect(lambda n,total,name:self.state.setText(f'Auditando {n}/{total} · {name}'));self.worker.completed.connect(self.audit_done);self.worker.finished.connect(self.finished)
        self.set_busy(True);self.state.setText('Comprobando conexiones e identidad antes de la auditoría…');self.worker.start()
    def audit_done(self,result):
        self.state.setText(f"Auditoría terminada · {result['devices']} dispositivos · {result['saved']} observaciones guardadas · {result['errors']} incidencias · {result.get('unreadable',0)} pantallas no comprobadas. Cuenta sin evidencia permanece sin verificar.")
    def set_busy(self,busy):
        for widget in [self.table,self.app_filter,self.status_filter,self.search,self.assignment,self.observed,self.manual_state,self.save_assignment,self.save_manual,*self.buttons,*self.selection_buttons]:widget.setEnabled(not busy)
    def finished(self):
        self.worker.wait();self.worker.deleteLater();self.worker=None;self.set_busy(False);self.render()
    def closeEvent(self,event):
        if self.worker:QMessageBox.information(self,'Auditoría en curso','Espera a que termine la lectura antes de cerrar.');event.ignore()
        else:event.accept()
    def reject(self):
        if self.worker:return
        super().reject()


def main():
    """Abrir el mismo panel como ventana independiente, sin iniciar auditorías."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from .inventory import FleetStore
    app=QApplication([]);app.setStyle('Fusion');app.setFont(QFont('Segoe UI',10))
    dialog=AppAccountsDialog(FleetStore());dialog.show();app.exec()


if __name__=='__main__':main()

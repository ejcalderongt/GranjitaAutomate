"""Inventario de solo lectura y seguimiento de múltiples servidores ADB."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
import os
import re
import subprocess
import time
import uuid

from .core import Adb, AdbError, Store, now


def usable_serial(value):
    value = (value or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{5,80}', value):
        return ''
    if value.lower() in {'unknown', 'null', 'none', 'android', '0123456789', '0123456789abcdef', '1234567890', 'serial', 'default'} or len(set(value)) == 1:
        return ''
    return value


def identity_from_properties(properties):
    hardware = usable_serial(properties.get('ro.serialno'))
    boot = usable_serial(properties.get('ro.boot.serialno'))
    # Dos fuentes que discrepan requieren revisión, no asociación automática.
    conflict = bool(hardware and boot and hardware != boot)
    return dict(hardware_serial=hardware or boot, manufacturer=properties.get('ro.product.manufacturer', ''),
                hardware_model=properties.get('ro.product.model', ''), identity_conflict=conflict)


def listeners():
    """Descubre puertos de procesos adb, sin iniciar ni reiniciar servidores."""
    if os.name != 'nt':
        return {}, 'Detección de procesos disponible en Windows.'
    command = "$a=@(Get-Process adb -ErrorAction SilentlyContinue); @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {$_.OwningProcess -in $a.Id} | Select-Object LocalPort,OwningProcess) | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], capture_output=True, text=True, timeout=12, creationflags=0x08000000)
        if result.returncode:
            return {}, 'No se pudieron consultar todos los procesos; se probarán los puertos configurados.'
        records = json.loads(result.stdout or '[]')
        if isinstance(records, dict):
            records = [records]
        return {int(r['LocalPort']): int(r['OwningProcess']) for r in records}, ''
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}, 'Detección de procesos no disponible; se probarán los puertos configurados.'


def shell(adb, serial, command):
    started = time.monotonic()
    with adb.connect() as sock:
        adb.request(sock, 'host:transport:' + serial)
        adb.request(sock, 'shell:' + command)
        data = b''
        while True:
            remaining = adb.timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise AdbError('Tiempo límite de consulta agotado.')
            sock.settimeout(remaining)
            chunk = sock.recv(16384)
            if not chunk:
                break
            data += chunk
            if len(data) > 2_000_000:
                raise AdbError('Respuesta demasiado grande.')
    return data.decode('utf-8', 'replace').strip()


def scan_fleet(ports, progress=None, discover=True):
    processes, warning = listeners() if discover else ({}, '')
    ports = sorted(set(ports) | set(processes))

    def inspect(port):
        report = dict(port=port, pid=processes.get(port), status='No disponible', count=0, detail='', at=now())
        try:
            devices = Adb(port, 3).devices()
            report.update(status='ADB responde', count=len(devices))
            return report, [dict(d, port=port) for d in devices]
        except Exception as exc:
            report['detail'] = str(exc)
            return report, []

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(inspect, ports))
    servers = [r[0] for r in responses]
    devices = [d for _, rows in responses for d in rows]

    def validate(device):
        result = dict(Adb(device['port']).validate(device), port=device['port'])
        if result['status'] == 'Validado':
            try:
                raw = shell(Adb(device['port']), device['serial'], 'getprop')
                properties = dict(re.findall(r'^\[([^]]+)\]: \[(.*)\]\r?$', raw, re.M))
                result.update(identity_from_properties(properties))
            except Exception:
                result['hardware_serial'] = ''
        return result

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(validate, devices):
            results.append(result)
            if progress:
                progress(len(results), len(devices))
    return dict(servers=servers, devices=results, warning=warning)


PROPERTIES = {
    'Fabricante': 'ro.product.manufacturer', 'Modelo': 'ro.product.model',
    'Serie hardware': 'ro.serialno', 'Serie de arranque': 'ro.boot.serialno',
    'Android': 'ro.build.version.release', 'API': 'ro.build.version.sdk',
    'Compilación': 'ro.build.display.id', 'Parche de seguridad': 'ro.build.version.security_patch',
    'Arquitecturas': 'ro.product.cpu.abilist', 'Idioma del sistema': 'persist.sys.locale',
    'Zona horaria': 'persist.sys.timezone', 'USB configurado': 'persist.sys.usb.config',
    'USB actual': 'sys.usb.state', 'Depuración compilada': 'ro.debuggable',
}
COMMANDS = {
    'IP por interfaz': 'ip -o addr show',
    'Rutas IPv4': 'ip route show', 'Rutas IPv6': 'ip -6 route show',
    'DNS privado (modo)': 'settings get global private_dns_mode',
    'DNS privado (servidor)': 'settings get global private_dns_specifier',
    'Proxy global': 'settings get global http_proxy',
    'Wi-Fi habilitado': 'settings get global wifi_on',
    'Datos móviles habilitados': 'settings get global mobile_data',
    'Wi-Fi actual': 'cmd wifi status',
    'Redes activas y DNS': 'dumpsys connectivity',
    'Batería': 'dumpsys battery', 'Almacenamiento': 'df -k /data',
    'Identidad de sesión ADB': 'id',
    'Ruta de su': 'command -v su',
    'Depuración ADB habilitada': 'settings get global adb_enabled',
    'Accesibilidad habilitada': 'settings get secure accessibility_enabled',
    'Servicios de accesibilidad': 'settings get secure enabled_accessibility_services',
    'Idioma seleccionado': 'settings get system system_locales',
    'Paquetes y versiones (código)': 'pm list packages --show-versioncode',
}


def collect_inventory(port, serial):
    adb = Adb(port, timeout=8)
    observations = []

    def query(label, command):
        # Un código de salida remoto permite distinguir un resultado vacío de un fallo.
        wrapped = command + '; __granjita_rc=$?; printf "\\n__GRANJITA_RC=%s\\n" "$__granjita_rc"'
        at = now()
        try:
            raw = shell(adb, serial, wrapped)
            body, marker, rc = raw.rpartition('__GRANJITA_RC=')
            if not marker:
                raise AdbError('La consulta no confirmó su código de salida.')
            value = body.strip()
            code = int(rc.strip())
            denied = bool(re.search(r'permission denied|securityexception|not allowed|requires .*permission', value, re.I))
            if label == 'Redes activas y DNS' and not denied:
                value = '\n'.join(line.strip() for line in value.splitlines() if re.search(r'Active default network|NetworkAgentInfo|LinkProperties|DnsAddresses|Transports:', line))
            state = 'Restringido' if denied else 'Error' if code else 'Disponible' if value and value != 'null' else 'Sin dato'
            if label == 'Ruta de su' and code == 1 and not value:
                state = 'Sin indicios'
            elif code and not value:
                value = f'La consulta terminó con código {code}.'
            # No almacenar usuario/contraseña que pudieran estar incluidos en un proxy.
            value = re.sub(r'(?i)(?:[^\s/@:]+:[^\s/@]+)@', '[credencial omitida]@', value)
            if label == 'Proxy global' and '@' in value:
                value = '[credencial omitida]@' + value.rsplit('@', 1)[1]
            observations.append(dict(field=label, value=value, state=state, source=command, at=at))
        except Exception as exc:
            observations.append(dict(field=label, value=str(exc), state='Error', source=command, at=at))

    # Una sola lectura de getprop, limitada a propiedades concretas en vez de conservar toda la salida.
    at = now()
    try:
        raw = shell(adb, serial, 'getprop')
        restricted = bool(re.search(r'permission denied|securityexception', raw, re.I))
        properties = dict(re.findall(r'^\[([^]]+)\]: \[(.*)\]$', raw, re.M))
        for label, name in PROPERTIES.items():
            value = properties.get(name, '')
            observations.append(dict(field=label, value=value, state='Restringido' if restricted else 'Disponible' if value else 'Sin dato', source='getprop ' + name, at=at))
    except Exception as exc:
        for label, name in PROPERTIES.items():
            observations.append(dict(field=label, value=str(exc), state='Error', source='getprop ' + name, at=at))
    for label, command in COMMANDS.items():
        query(label, command)
    by_field = {o['field']: o for o in observations}
    session = by_field['Identidad de sesión ADB']
    su = by_field['Ruta de su']
    if session['state'] == 'Disponible' and re.search(r'\buid=0\b', session['value']):
        root = 'Confirmado: sesión ADB ejecutándose con UID 0'
    elif su['state'] == 'Disponible':
        root = 'Indicios: existe su; privilegios no comprobados'
    elif session['state'] != 'Disponible' or su['state'] in ('Restringido', 'Error') and su['value']:
        root = 'No comprobable con las consultas disponibles'
    else:
        root = 'No observado; no demuestra ausencia de root'
    observations.append(dict(field='Evaluación de root', value=root, state='Evaluado', source='id + command -v su (sin ejecutar su)', at=now()))
    return observations


class FleetStore(Store):
    def __init__(self, path=None):
        super().__init__(path)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 5:
            raise ValueError('La base pertenece a una versión más nueva. Usa la versión compatible del programa.')
        if version < 2:
            self.backup(self.path.with_name(self.path.stem + '-antes-v2.sqlite3'))
            with self.connect() as db:
                db.executescript('''
                    CREATE TABLE inventory_devices(id TEXT PRIMARY KEY, alias TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
                    CREATE TABLE connections(port INTEGER NOT NULL, serial TEXT NOT NULL, device_id TEXT NOT NULL,
                        model TEXT NOT NULL DEFAULT '',android TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,
                        detail TEXT NOT NULL,last_seen TEXT NOT NULL,last_check TEXT NOT NULL,PRIMARY KEY(port,serial));
                    CREATE TABLE servers(port INTEGER PRIMARY KEY,pid INTEGER,status TEXT NOT NULL,count INTEGER NOT NULL,detail TEXT NOT NULL,at TEXT NOT NULL);
                    CREATE TABLE snapshots(id INTEGER PRIMARY KEY,device_id TEXT NOT NULL,port INTEGER NOT NULL,serial TEXT NOT NULL,at TEXT NOT NULL);
                    CREATE TABLE observations(snapshot_id INTEGER NOT NULL,field TEXT NOT NULL,value TEXT NOT NULL,state TEXT NOT NULL,source TEXT NOT NULL,at TEXT NOT NULL);
                    CREATE INDEX observations_snapshot ON observations(snapshot_id);
                    CREATE TABLE connection_events(id INTEGER PRIMARY KEY,device_id TEXT NOT NULL,at TEXT NOT NULL,status TEXT NOT NULL,detail TEXT NOT NULL);
                    PRAGMA user_version=2;
                ''')
                port = int(self.setting('port', '5037'))
                for row in db.execute('SELECT * FROM devices').fetchall():
                    identifier = str(uuid.uuid4())
                    db.execute('INSERT INTO inventory_devices VALUES (?,?,?)', (identifier, row['alias'], row['last_seen']))
                    db.execute('INSERT INTO connections VALUES (?,?,?,?,?,?,?,?,?)', (port, row['serial'], identifier, row['model'], row['android'], 'Pendiente de verificar', row['detail'], row['last_seen'], row['last_check']))
                    for event in db.execute('SELECT * FROM events WHERE serial=?', (row['serial'],)).fetchall():
                        db.execute('INSERT INTO connection_events(device_id,at,status,detail) VALUES (?,?,?,?)', (identifier, event['at'], event['status'], event['detail']))
        if version < 3:
            self.backup(self.path.with_name(self.path.stem + '-antes-v3.sqlite3'))
            with self.connect() as db:
                db.executescript('''
                    CREATE TABLE device_identity(device_id TEXT PRIMARY KEY,hardware_serial TEXT NOT NULL,
                        manufacturer TEXT NOT NULL,model TEXT NOT NULL,state TEXT NOT NULL,at TEXT NOT NULL);
                    PRAGMA user_version=3;
                ''')
                for device in db.execute('SELECT id FROM inventory_devices').fetchall():
                    snapshot = db.execute('SELECT id FROM snapshots WHERE device_id=? ORDER BY id DESC LIMIT 1', (device['id'],)).fetchone()
                    if snapshot:
                        observations = db.execute('SELECT field,value FROM observations WHERE snapshot_id=? AND state=?', (snapshot['id'], 'Disponible')).fetchall()
                        values = {o['field']:o['value'] for o in observations}
                        identity = identity_from_properties({'ro.serialno':values.get('Serie hardware',''), 'ro.boot.serialno':values.get('Serie de arranque',''), 'ro.product.manufacturer':values.get('Fabricante',''), 'ro.product.model':values.get('Modelo','')})
                        self._save_identity(db,device['id'],identity,now())

        if version < 4:
            self.backup(self.path.with_name(self.path.stem + '-antes-v4.sqlite3'))
            with self.connect() as db:
                db.executescript("""
                    CREATE TABLE physical_positions(hardware_serial TEXT PRIMARY KEY,rack TEXT NOT NULL,
                        slot INTEGER NOT NULL,panda_number INTEGER NOT NULL UNIQUE,at TEXT NOT NULL,
                        UNIQUE(rack,slot));
                    PRAGMA user_version=4;
                """)

        if version < 5:
            self.backup(self.path.with_name(self.path.stem + '-antes-v5.sqlite3'))
            with self.connect() as db:
                db.executescript("""
                    CREATE TABLE device_checkpoints(id TEXT PRIMARY KEY,hardware_serial TEXT NOT NULL,
                        device_id TEXT NOT NULL,at TEXT NOT NULL,status TEXT NOT NULL,manifest TEXT NOT NULL,sha256 TEXT NOT NULL);
                    CREATE INDEX checkpoint_serial ON device_checkpoints(hardware_serial,at);
                    CREATE TABLE checkpoint_files(snapshot_id TEXT NOT NULL,name TEXT NOT NULL,content BLOB NOT NULL,
                        sha256 TEXT NOT NULL,size INTEGER NOT NULL,PRIMARY KEY(snapshot_id,name));
                    CREATE TABLE recovery_events(id INTEGER PRIMARY KEY,snapshot_id TEXT,hardware_serial TEXT NOT NULL,
                        at TEXT NOT NULL,status TEXT NOT NULL,detail TEXT NOT NULL);
                    PRAGMA user_version=5;
                """)

    # La posición se vincula al serial físico, nunca a IP o puerto ADB.
    def positions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM physical_positions ORDER BY rack,slot')]

    def assign_position(self, hardware_serial, rack, slot, panda_number):
        rack = rack.strip().upper()
        if not re.fullmatch(r'R[0-9]{2,3}', rack) or not usable_serial(hardware_serial):
            raise ValueError('Usa un rack como R01 y un serial físico válido.')
        if type(slot) is not int or not 1 <= slot <= 999 or type(panda_number) is not int or not 1 <= panda_number <= 999999:
            raise ValueError('Posición o número Panda inválidos.')
        with self.connect() as db:
            identities = db.execute('SELECT state FROM device_identity WHERE hardware_serial=?', (hardware_serial,)).fetchall()
            if len(identities) != 1 or identities[0]['state'] == 'Fuentes en conflicto':
                raise ValueError('El serial debe corresponder a una única ficha sin conflicto.')
            occupied = db.execute('SELECT hardware_serial FROM physical_positions WHERE (rack=? AND slot=?) OR panda_number=?', (rack,slot,panda_number)).fetchall()
            if any(r['hardware_serial'] != hardware_serial for r in occupied):
                raise ValueError('La posición o número Panda ya pertenece a otra placa.')
            db.execute("INSERT INTO physical_positions VALUES (?,?,?,?,?) ON CONFLICT(hardware_serial) DO UPDATE SET rack=excluded.rack,slot=excluded.slot,panda_number=excluded.panda_number,at=excluded.at", (hardware_serial,rack,slot,panda_number,now()))

    @staticmethod
    def _save_identity(db, identifier, data, stamp):
        serial = usable_serial(data.get('hardware_serial'))
        if not serial:
            return
        state = 'Fuentes en conflicto' if data.get('identity_conflict') else 'Serial leído'
        db.execute('INSERT OR REPLACE INTO device_identity VALUES (?,?,?,?,?,?)', (identifier,serial,data.get('manufacturer',''),data.get('hardware_model',''),state,stamp))

    def save_fleet(self, report):
        stamp = now()
        successful = {s['port'] for s in report['servers'] if s['status'] == 'ADB responde'}
        seen = {(d['port'], d['serial']) for d in report['devices']}
        serial_counts = Counter(usable_serial(d.get('hardware_serial')) for d in report['devices'] if usable_serial(d.get('hardware_serial')))
        with self.connect() as db:
            queried = {s['port'] for s in report['servers']}
            for old in db.execute('SELECT port FROM servers').fetchall():
                if old['port'] not in queried:
                    db.execute("UPDATE servers SET status='No consultado',detail='Puerto fuera de la búsqueda actual.',count=0 WHERE port=?", (old['port'],))
            for server in report['servers']:
                db.execute('INSERT OR REPLACE INTO servers VALUES (?,?,?,?,?,?)', (server['port'], server['pid'], server['status'], server['count'], server['detail'], server['at']))
            for row in db.execute('SELECT * FROM connections').fetchall():
                if (row['port'], row['serial']) not in seen:
                    status = 'Desconectado' if row['port'] in successful else 'Servidor sin verificar'
                    detail = 'No aparece en el servidor consultado.' if status == 'Desconectado' else 'No se pudo consultar el servidor de origen; estado de la placa desconocido.'
                    db.execute('UPDATE connections SET status=?,detail=?,last_check=? WHERE port=? AND serial=?', (status, detail, stamp, row['port'], row['serial']))
                    if status != row['status']:
                        db.execute('INSERT INTO connection_events(device_id,at,status,detail) VALUES (?,?,?,?)', (row['device_id'], stamp, status, detail))
            for d in report['devices']:
                row = db.execute('SELECT device_id FROM connections WHERE port=? AND serial=?', (d['port'], d['serial'])).fetchone()
                hardware = usable_serial(d.get('hardware_serial'))
                # Una IP reutilizada no debe sobrescribir la identidad de la ficha.
                if row and hardware:
                    previous = db.execute('SELECT hardware_serial FROM device_identity WHERE device_id=?', (row['device_id'],)).fetchone()
                    if previous and previous['hardware_serial'] != hardware:
                        d = dict(d, status='Identidad en conflicto', detail='La conexión ahora declara otro serial físico. Revisa la placa antes de inventariarla.')
                        hardware = ''
                identifier = row['device_id'] if row else str(uuid.uuid4())
                matched = False
                if not row:
                    candidates = db.execute('SELECT * FROM device_identity WHERE hardware_serial=?', (hardware,)).fetchall() if hardware else []
                    if len(candidates) == 1 and serial_counts[hardware] == 1 and not d.get('identity_conflict'):
                        candidate = candidates[0]
                        same_metadata = (candidate['manufacturer'] and candidate['model'] and candidate['manufacturer'] == d.get('manufacturer') and candidate['model'] == d.get('hardware_model'))
                        active = db.execute("SELECT port,serial FROM connections WHERE device_id=?", (candidate['device_id'],)).fetchall()
                        absence_confirmed = all(c['port'] in successful and (c['port'], c['serial']) not in seen for c in active)
                        if same_metadata and candidate['state'] == 'Serial leído' and absence_confirmed:
                            identifier, matched = candidate['device_id'], True
                    if not matched:
                        db.execute('INSERT INTO inventory_devices VALUES (?,?,?)', (identifier, '', stamp))
                db.execute('''INSERT INTO connections VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(port,serial) DO UPDATE SET
                    device_id=excluded.device_id,model=excluded.model,android=CASE WHEN excluded.android='' THEN connections.android ELSE excluded.android END,
                    status=excluded.status,detail=excluded.detail,last_seen=excluded.last_seen,last_check=excluded.last_check''',
                    (d['port'], d['serial'], identifier, d['model'], d['android'], d['status'], d['detail'], stamp, stamp))
                if d['status'] != 'Identidad en conflicto':
                    self._save_identity(db,identifier,d,stamp)
                db.execute('INSERT INTO connection_events(device_id,at,status,detail) VALUES (?,?,?,?)', (identifier, stamp, d['status'], d['detail']))

    def fleet_devices(self):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('''SELECT c.*,d.alias,d.id,i.hardware_serial,i.state AS identity_state,i.at AS identity_at
                FROM connections c JOIN inventory_devices d ON d.id=c.device_id LEFT JOIN device_identity i ON i.device_id=d.id ORDER BY d.alias,c.port,c.serial''')]
            counts = {r['hardware_serial']:r['n'] for r in db.execute('SELECT hardware_serial,COUNT(*) AS n FROM device_identity GROUP BY hardware_serial')}
            for row in rows:
                serial = row['hardware_serial'] or ''
                duplicate = counts.get(serial,0) > 1
                state = 'Serial repetido: revisar' if duplicate else row['identity_state'] or 'Sin serial físico'
                auto = f'Placa {serial}' if serial else f"Equipo {row['id'][:8]}"
                if duplicate or state == 'Fuentes en conflicto':
                    auto += f" · {row['id'][:8]}"
                row.update(display_name=row['alias'] or auto, auto_name=auto, identity_state=state)
            return rows

    def servers(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM servers ORDER BY port')]

    def rename_device(self, identifier, name):
        with self.connect() as db:
            db.execute('UPDATE inventory_devices SET alias=? WHERE id=?', (name, identifier))

    def device_history(self, identifier):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM connection_events WHERE device_id=? ORDER BY id DESC LIMIT 100', (identifier,))]

    def save_inventory(self, identifier, port, serial, observations):
        with self.connect() as db:
            cursor = db.execute('INSERT INTO snapshots(device_id,port,serial,at) VALUES (?,?,?,?)', (identifier, port, serial, now()))
            db.executemany('INSERT INTO observations VALUES (?,?,?,?,?,?)', [(cursor.lastrowid, o['field'], o['value'], o['state'], o['source'], o['at']) for o in observations])
            values = {o['field']:o['value'] for o in observations if o['state'] == 'Disponible'}
            identity = identity_from_properties({'ro.serialno':values.get('Serie hardware',''), 'ro.boot.serialno':values.get('Serie de arranque',''), 'ro.product.manufacturer':values.get('Fabricante',''), 'ro.product.model':values.get('Modelo','')})
            self._save_identity(db,identifier,identity,now())

    def inventory(self, identifier):
        with self.connect() as db:
            snapshots = db.execute('SELECT * FROM snapshots WHERE device_id=? ORDER BY id DESC LIMIT 2', (identifier,)).fetchall()
            if not snapshots:
                return [], None, 0
            current = [dict(r) for r in db.execute('SELECT * FROM observations WHERE snapshot_id=?', (snapshots[0]['id'],))]
            previous = {r['field']: (r['value'], r['state']) for r in db.execute('SELECT * FROM observations WHERE snapshot_id=?', (snapshots[1]['id'],))} if len(snapshots) > 1 else {}
            for row in current:
                row['changed'] = row['field'] in previous and previous[row['field']] != (row['value'], row['state'])
            return current, dict(snapshots[0]), len(snapshots)

    def link_connection(self, port, serial, target_id):
        """Asociación física explícita por el usuario; nunca se deduce de IP/modelo."""
        with self.connect() as db:
            old = db.execute('SELECT device_id FROM connections WHERE port=? AND serial=?', (port, serial)).fetchone()
            if not old or not db.execute('SELECT id FROM inventory_devices WHERE id=?', (target_id,)).fetchone():
                raise ValueError('Dispositivo no encontrado.')
            old_id = old['device_id']
            db.execute('UPDATE connections SET device_id=? WHERE port=? AND serial=?', (target_id, port, serial))
            # Transferir observaciones solo si la identidad anterior ya no tiene transportes.
            if old_id != target_id and not db.execute('SELECT 1 FROM connections WHERE device_id=?', (old_id,)).fetchone():
                db.execute('UPDATE snapshots SET device_id=? WHERE device_id=?', (target_id, old_id))
                db.execute('UPDATE connection_events SET device_id=? WHERE device_id=?', (target_id, old_id))
                db.execute('DELETE FROM inventory_devices WHERE id=?', (old_id,))

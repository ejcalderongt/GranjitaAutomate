"""Inventario de solo lectura y seguimiento de múltiples servidores ADB."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
import time
import uuid

from .core import Adb, AdbError, Store, now


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
        return dict(Adb(device['port']).validate(device), port=device['port'])

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
        if version > 2:
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

    def save_fleet(self, report):
        stamp = now()
        successful = {s['port'] for s in report['servers'] if s['status'] == 'ADB responde'}
        seen = {(d['port'], d['serial']) for d in report['devices']}
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
                identifier = row['device_id'] if row else str(uuid.uuid4())
                if not row:
                    db.execute('INSERT INTO inventory_devices VALUES (?,?,?)', (identifier, '', stamp))
                db.execute('''INSERT INTO connections VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(port,serial) DO UPDATE SET
                    model=excluded.model,android=CASE WHEN excluded.android='' THEN connections.android ELSE excluded.android END,
                    status=excluded.status,detail=excluded.detail,last_seen=excluded.last_seen,last_check=excluded.last_check''',
                    (d['port'], d['serial'], identifier, d['model'], d['android'], d['status'], d['detail'], stamp, stamp))
                db.execute('INSERT INTO connection_events(device_id,at,status,detail) VALUES (?,?,?,?)', (identifier, stamp, d['status'], d['detail']))

    def fleet_devices(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT c.*,d.alias,d.id FROM connections c JOIN inventory_devices d ON d.id=c.device_id ORDER BY d.alias,c.port,c.serial''')]

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

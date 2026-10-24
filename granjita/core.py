"""Acceso no disruptivo al servidor ADB existente e inventario portable."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import socket
import sqlite3
import time

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'


def now():
    return datetime.now(timezone(timedelta(hours=-6))).isoformat(timespec='seconds')


class AdbError(Exception):
    pass


class Adb:
    def __init__(self, port=5037, timeout=5):
        self.port, self.timeout = int(port), timeout

    @staticmethod
    def read(sock, size):
        result = b''
        while len(result) < size:
            chunk = sock.recv(size - len(result))
            if not chunk:
                raise AdbError('El servidor cerró la conexión.')
            result += chunk
        return result

    def request(self, sock, service):
        data = service.encode('utf-8')
        sock.sendall(f'{len(data):04x}'.encode() + data)
        status = self.read(sock, 4)
        if status == b'FAIL':
            size = int(self.read(sock, 4), 16)
            raise AdbError(self.read(sock, size).decode('utf-8', 'replace'))
        if status != b'OKAY':
            raise AdbError('Respuesta ADB no reconocida.')

    def connect(self):
        return socket.create_connection(('127.0.0.1', self.port), self.timeout)

    def devices(self):
        with self.connect() as sock:
            self.request(sock, 'host:devices-l')
            size = int(self.read(sock, 4), 16)
            return parse_devices(self.read(sock, size).decode('utf-8', 'replace'))

    def validate(self, device):
        result = dict(device)
        result['android'] = ''
        if device['state'] != 'device':
            result['status'] = 'Requiere autorización' if device['state'] == 'unauthorized' else 'Sin respuesta'
            result['detail'] = guidance(device['state'])
            return result
        started = time.monotonic()
        try:
            with self.connect() as sock:
                self.request(sock, 'host:transport:' + device['serial'])
                self.request(sock, 'shell:echo GRANJITA_OK; getprop ro.build.version.release')
                data = b''
                while True:
                    sock.settimeout(max(0.1, self.timeout - (time.monotonic() - started)))
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 65536 or time.monotonic() - started > self.timeout:
                        raise AdbError('La validación excedió el límite.')
                lines = data.decode('utf-8', 'replace').strip().splitlines()
                if not lines or lines[0].strip() != 'GRANJITA_OK':
                    raise AdbError('La placa no confirmó la prueba de comunicación.')
                result['android'] = lines[1].strip() if len(lines) > 1 else ''
                result['status'] = 'Validado'
                result['detail'] = 'Comunicación confirmada mediante una consulta real.'
        except (OSError, ValueError, AdbError) as exc:
            result['status'] = 'Error de validación'
            result['detail'] = f'{exc}\nRevisa la conexión OTG en Panda y pulsa Reintentar.'
        return result

    def scan(self, progress=None):
        devices = self.devices()
        results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(self.validate, devices):
                results.append(result)
                if progress:
                    progress(len(results), len(devices))
        return results


def parse_devices(text):
    result = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        metadata = dict(p.split(':', 1) for p in parts[2:] if ':' in p)
        result.append(dict(serial=parts[0], state=parts[1], model=metadata.get('model', '').replace('_', ' ')))
    return result


def guidance(state):
    if state == 'unauthorized':
        return 'Abre la pantalla de la placa desde Panda y acepta la autorización de depuración USB. Después pulsa Reintentar.'
    return 'Revisa alimentación, cable OTG y estado de la placa en Panda. Completa allí el proceso de conexión y pulsa Reintentar.'


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else DATA / 'granjita.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS devices (
                    serial TEXT PRIMARY KEY, alias TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
                    android TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, detail TEXT NOT NULL,
                    last_seen TEXT NOT NULL, last_check TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, at TEXT NOT NULL, serial TEXT NOT NULL,
                    status TEXT NOT NULL, detail TEXT NOT NULL);
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key, default=''):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row['value'] if row else default

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, str(value)))

    def save_scan(self, results):
        stamp = now()
        with self.connect() as db:
            seen = {d['serial'] for d in results}
            for row in db.execute('SELECT serial,status FROM devices').fetchall():
                if row['serial'] not in seen:
                    detail = 'No aparece en la última búsqueda. Revisa la conexión OTG en Panda.'
                    db.execute("UPDATE devices SET status='Desconectado',detail=?,last_check=? WHERE serial=?", (detail, stamp, row['serial']))
                    if row['status'] != 'Desconectado':
                        db.execute('INSERT INTO events(at,serial,status,detail) VALUES (?,?,?,?)', (stamp, row['serial'], 'Desconectado', detail))
            for d in results:
                db.execute('''INSERT INTO devices(serial,model,android,status,detail,last_seen,last_check)
                    VALUES (?,?,?,?,?,?,?) ON CONFLICT(serial) DO UPDATE SET
                    model=excluded.model,android=CASE WHEN excluded.android='' THEN devices.android ELSE excluded.android END,
                    status=excluded.status,detail=excluded.detail,last_seen=excluded.last_seen,last_check=excluded.last_check''',
                    (d['serial'], d['model'], d['android'], d['status'], d['detail'], stamp, stamp))
                db.execute('INSERT INTO events(at,serial,status,detail) VALUES (?,?,?,?)', (stamp, d['serial'], d['status'], d['detail']))

    def devices(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM devices ORDER BY alias,serial')]

    def alias(self, serial, alias):
        with self.connect() as db:
            db.execute('UPDATE devices SET alias=? WHERE serial=?', (alias, serial))

    def history(self, serial):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE serial=? ORDER BY id DESC LIMIT 100', (serial,))]

    def backup(self, target):
        if Path(target).resolve() == self.path.resolve():
            raise ValueError('Elige un archivo distinto a la base activa.')
        with self.connect() as source, closing(sqlite3.connect(target)) as dest:
            with dest:
                source.backup(dest)

"""Recoverable device maps: public references and user-scoped DPAPI blobs."""
import ctypes
import atexit
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import tempfile

HASH_LENGTH_HEX = 16
DEFAULT_KEEP = 5
log = logging.getLogger('device_map')
_ACTIVE_PAIRS = set()
_ACTIVE_HANDLES = {}


def _derive_ref(serial_plain, salt):
    if (not isinstance(serial_plain, str) or not 4 <= len(serial_plain) <= 128
            or not serial_plain.isascii() or not serial_plain.isprintable()
            or any(char.isspace() for char in serial_plain)):
        raise ValueError('Serial invalido')
    if not isinstance(salt, str) or not salt or not salt.isascii():
        raise ValueError('Salt invalido')
    return hashlib.sha256((serial_plain + salt).encode('ascii')).hexdigest()[:HASH_LENGTH_HEX]


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', ctypes.c_uint32), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data, decrypt):
    if not isinstance(data, bytes) or not data:
        raise ValueError('Blob invalido')
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
    except (AttributeError, OSError):
        raise RuntimeError('DPAPI no disponible') from None
    raw = ctypes.create_string_buffer(data, len(data))
    source = _Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    result = _Blob()
    pointer = ctypes.POINTER(_Blob)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt32.CryptUnprotectData
        function.argtypes = [pointer, ctypes.c_void_p, pointer, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_uint32, pointer]
        arguments = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [pointer, ctypes.c_wchar_p, pointer, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_uint32, pointer]
        arguments = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    function.restype = ctypes.c_int
    try:
        if not function(*arguments):
            raise RuntimeError('DPAPI fallo')
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if result.pbData:
            kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def _dpapi_encrypt(plain_bytes):
    return _dpapi(plain_bytes, False)


def _dpapi_decrypt(blob_bytes):
    return _dpapi(blob_bytes, True)


def _server(host, port):
    if not isinstance(host, str) or type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Servidor invalido')
    if host != 'localhost':
        try:
            ipaddress.IPv4Address(host)
        except ipaddress.AddressValueError:
            raise ValueError('Servidor invalido') from None
    return host + ':' + str(port)


def _validate(plates, servers, salt):
    if not isinstance(plates, list) or not plates or not isinstance(servers, list) or not servers:
        raise ValueError('Mapa de dispositivos invalido')
    counts = {}
    normalized_servers = []
    for item in servers:
        if not isinstance(item, dict):
            raise ValueError('Servidor invalido')
        endpoint = _server(item.get('host'), item.get('port'))
        if endpoint in counts:
            raise ValueError('Servidor duplicado')
        counts[endpoint] = 0
        normalized_servers.append(dict(item))
    public, private, seen_plates, seen_serials, refs = [], [], set(), set(), set()
    for item in plates:
        if not isinstance(item, dict):
            raise ValueError('Mapa de dispositivos invalido')
        plate, endpoint, serial = item.get('plate'), item.get('server'), item.get('device_serial_plain')
        if not isinstance(plate, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', plate):
            raise ValueError('Placa invalida')
        if not isinstance(endpoint, str) or endpoint not in counts:
            raise ValueError('Servidor invalido')
        ref = _derive_ref(serial, salt)
        if plate in seen_plates or serial in seen_serials:
            raise ValueError('Identidad duplicada')
        if ref in refs:
            raise ValueError('Colision de referencias')
        seen_plates.add(plate)
        seen_serials.add(serial)
        refs.add(ref)
        counts[endpoint] += 1
        public.append({'plate': plate, 'server': endpoint, 'device_ref': ref})
        private.append({'plate': plate, 'server': endpoint, 'device_serial_plain': serial})
    for item in normalized_servers:
        count = counts[_server(item['host'], item['port'])]
        if 'devices_count' in item and (type(item['devices_count']) is not int or item['devices_count'] < count):
            raise ValueError('Conteo de dispositivos invalido')
        item.setdefault('devices_count', count)
    normalized_servers = [{'host': item['host'], 'port': item['port'], 'devices_count': item['devices_count']}
                          for item in normalized_servers]
    return public, private, normalized_servers


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp invalido')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('Timestamp invalido')
    return parsed


def _read_pair(public_path, root, salt, private_bytes=None):
    public = json.loads(public_path.read_text(encoding='ascii'))
    private_path = root / 'secrets' / (public_path.stem + '.bin')
    private = json.loads(_dpapi_decrypt(private_path.read_bytes() if private_bytes is None else private_bytes).decode('ascii'))
    _timestamp(public['timestamp'])
    if (private['timestamp'] != public['timestamp'] or private['salt_present'] is not True
            or public['hash_algorithm'] != 'sha256' or public['hash_length_hex'] != HASH_LENGTH_HEX):
        raise ValueError('Mapa de dispositivos inconsistente')
    expected, normalized_private, servers = _validate(private['plates'], public['adb_servers'], salt)
    if not isinstance(public['plates'], list) or len(public['plates']) != len(expected):
        raise ValueError('Mapa de dispositivos inconsistente')
    by_plate = {item['plate']: item for item in public['plates']}
    if len(by_plate) != len(expected) or any(by_plate.get(item['plate']) != item for item in expected):
        raise ValueError('Mapa de dispositivos inconsistente')
    if 'owner_pid' in public and (type(public['owner_pid']) is not int or public['owner_pid'] <= 0):
        raise ValueError('Mapa de dispositivos inconsistente')
    return {'timestamp': public['timestamp'], 'adb_servers': servers,
            'hash_algorithm': 'sha256', 'hash_length_hex': HASH_LENGTH_HEX,
            'plates': [dict(item, device_ref=by_plate[item['plate']]['device_ref']) for item in normalized_private]}


def _open_private(path):
    if os.name != 'nt':
        return path.open('rb')
    import msvcrt
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    # READ/WRITE sharing, deliberately excluding FILE_SHARE_DELETE.
    handle = kernel32.CreateFileW(str(path), 0x80000000, 3, None, 3, 128, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError('Mapa de dispositivos no disponible')
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel32.CloseHandle(handle)
        raise
    return os.fdopen(descriptor, 'rb')


def _release_active_maps():
    for stream in _ACTIVE_HANDLES.values():
        stream.close()
    _ACTIVE_HANDLES.clear()
    _ACTIVE_PAIRS.clear()


atexit.register(_release_active_maps)


def _pid_active(pid):
    if pid == os.getpid():
        return True
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            return True
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return kernel32.GetLastError() != 87
        try:
            code = ctypes.c_uint32()
            return not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):
        return True


def rotate(root, keep):
    if type(keep) is not int or keep < 1:
        raise ValueError('Retencion invalida')
    root = Path(root).resolve()
    candidates = []
    for path in (root / 'runs').glob('device_map_*.json'):
        try:
            data = json.loads(path.read_text(encoding='ascii'))
            stamp = _timestamp(data['timestamp'])
            _read_pair(path, root, os.getenv('PANDA_DEVICE_SALT'))
            candidates.append((stamp, path, data.get('owner_pid')))
        except Exception:
            continue
    for _, path, owner in sorted(candidates, key=lambda row: (row[0], row[1].name), reverse=True)[keep:]:
        if (str(root), path.stem) in _ACTIVE_PAIRS:
            continue
        if owner is None or (owner != os.getpid() and _pid_active(owner)):
            continue
        try:
            (root / 'secrets' / (path.stem + '.bin')).unlink()
            path.unlink()
        except OSError:
            log.warning('device_map_rotation_deferred')


def save_map(plates, adb_servers, salt, root):
    public_plates, private_plates, servers = _validate(plates, adb_servers, salt)
    try:
        keep = int(os.getenv('PANDA_DEVICE_MAP_KEEP', str(DEFAULT_KEEP)))
        if keep < 1:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Retencion invalida') from None
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    stem = 'device_map_' + now.strftime('%Y%m%dT%H%M%S%fZ')
    public = {'timestamp': stamp, 'adb_servers': servers, 'hash_algorithm': 'sha256',
              'hash_length_hex': HASH_LENGTH_HEX, 'plates': public_plates, 'owner_pid': os.getpid()}
    private = {'timestamp': stamp, 'salt_present': True, 'plates': private_plates}
    # Encryption precedes directory creation and every write, including staging.
    try:
        cipher = _dpapi_encrypt(json.dumps(private, ensure_ascii=True).encode('ascii'))
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc) == 'DPAPI no disponible':
            raise RuntimeError('DPAPI no disponible') from None
        raise RuntimeError('DPAPI fallo') from None
    if not isinstance(cipher, bytes) or not cipher:
        raise RuntimeError('DPAPI fallo')
    root = Path(root).resolve()
    public_path, private_path = root / 'runs' / (stem + '.json'), root / 'secrets' / (stem + '.bin')
    staged, installed = [], []
    try:
        public_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.parent.mkdir(parents=True, exist_ok=True)
        if public_path.exists() or private_path.exists():
            raise RuntimeError('Mapa de dispositivos existente')
        for target, payload in ((private_path, cipher),
                                (public_path, json.dumps(public, ensure_ascii=True, indent=2).encode('ascii'))):
            with tempfile.NamedTemporaryFile(prefix='.device-map-', dir=target.parent, delete=False) as stream:
                staged.append(Path(stream.name))
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        for source, target in zip(staged, (private_path, public_path)):
            os.replace(source, target)
            installed.append(target)
    except Exception:
        for path in staged + installed:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise RuntimeError('Mapa de dispositivos no guardado') from None
    rotate(root, keep)
    return {'public': str(public_path.relative_to(root)).replace('\\', '/'),
            'private': str(private_path.relative_to(root)).replace('\\', '/')}


def load_latest_map(root):
    root = Path(root).resolve()
    paths = sorted((root / 'runs').glob('device_map_*.json'), reverse=True)
    if not paths:
        return None
    stream = None
    key = None
    try:
        def order(path):
            try:
                return _timestamp(json.loads(path.read_text(encoding='ascii'))['timestamp'])
            except Exception:
                # Preserve corrupt candidates; their fixed-width filename is the fallback key.
                return datetime.strptime(path.stem[len('device_map_'):], '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc)
        path = max(paths, key=order)
        key = (str(root), path.stem)
        stream = _ACTIVE_HANDLES.get(key)
        if stream is None:
            stream = _open_private(root / 'secrets' / (path.stem + '.bin'))
        stream.seek(0)
        result = _read_pair(path, root, os.getenv('PANDA_DEVICE_SALT'), stream.read())
        _ACTIVE_HANDLES[key] = stream
        _ACTIVE_PAIRS.add(key)
        return result
    except Exception:
        if stream is not None and _ACTIVE_HANDLES.get(key) is not stream:
            stream.close()
        log.warning('device_map_corrupt')
        return None

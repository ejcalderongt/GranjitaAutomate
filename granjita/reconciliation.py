"""Recuperación acotada de transportes conocidos; no configura USB ni reinicia ADB."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import subprocess
import time
from pathlib import Path
from .core import Adb, DATA, now
from .inventory import scan_fleet
from .panda_api import list_devices


def endpoint(value):
    try:
        host, port = value.rsplit(':', 1)
        ip = ipaddress.IPv4Address(host)
        return ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_unspecified and 1 <= int(port) <= 65535
    except (ValueError, AttributeError):
        return False


def ensure_panda(path):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        "[bool](Get-Process touping -ErrorAction SilentlyContinue)"], capture_output=True, text=True, timeout=8, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError('No se pudo comprobar el proceso de Panda.')
    if result.stdout.strip().lower() == 'true':
        return 'Panda ya estaba ejecutándose.'
    if not Path(path).is_file():
        return 'Panda no localizado: configura su ruta con Abrir Panda.'
    subprocess.Popen([str(path)], cwd=str(Path(path).parent), creationflags=0x08000000)
    time.sleep(8)
    return 'Panda abierto; puede requerir completar el modo OTG o la autorización Android.'


def reconnect(port, serial):
    try:
        adb = Adb(port, 3)
        with adb.connect() as sock:
            adb.request(sock, 'host:connect:' + serial)
            size = int(adb.read(sock, 4), 16)
            message = adb.read(sock, size).decode('utf-8', 'replace')
        return dict(port=port, serial=serial, result=message[:500])
    except Exception as exc:
        return dict(port=port, serial=serial, result=str(exc)[:500])


def reconcile(ports, known, panda_path, progress=None):
    notes = []
    try:
        notes.append(ensure_panda(panda_path))
    except Exception as exc:
        notes.append('Inicio de Panda no comprobado: ' + str(exc))
    panda, panda_error = [], ''
    try:
        panda = list_devices()
    except Exception as exc:
        panda_error = str(exc)
    first = scan_fleet(ports, progress)
    # No crear copias de transportes presentes en otro servidor, incluso offline.
    present = {d['serial'] for d in first['devices']}
    available = {s['port'] for s in first['servers'] if s['status'] == 'ADB responde'}
    active_hardware = {d.get('hardware_serial') for d in first['devices'] if d['status'] == 'Validado' and d.get('hardware_serial')}
    candidates = {}
    for r in sorted(known, key=lambda r: r.get('last_check', ''), reverse=True):
        if r['port'] in available and endpoint(r['serial']) and r['serial'] not in present and r.get('hardware_serial') not in active_hardware:
            key = r.get('hardware_serial') or r['serial']
            candidates.setdefault(key, (r['port'], r['serial']))
    targets = list(candidates.values())[:64]
    with ThreadPoolExecutor(max_workers=4) as pool:
        attempts = list(pool.map(lambda target: reconnect(*target), targets))
    report = scan_fleet(ports, progress) if attempts else first
    # Panda puede publicar su inventario después de inicializar los servidores.
    if not panda:
        try:
            panda = list_devices()
            panda_error = ''
        except Exception as exc:
            panda_error = str(exc)
    report['reconciliation'] = dict(at=now(), panda=panda, panda_error=panda_error, attempts=attempts, notes=notes)
    DATA.mkdir(exist_ok=True)
    (DATA / 'reconciliation-latest.json').write_text(json.dumps(report['reconciliation'], ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def diagnosis(row, panda, available=True):
    matches = [p for p in panda if p.get('onlySerial') == row.get('hardware_serial') and row.get('hardware_serial')]
    recognition = ('Sí · OTG' if any(p.get('mode') == 2 for p in matches) else 'Sí') if matches else ('No en lista actual' if available else 'Sin comprobar')
    state = row['status']
    if state == 'Validado':
        return recognition, 'Activa: ADB respondió. Energía del socket no medida.'
    if state == 'Identidad en conflicto':
        return recognition, 'Revisar serial físico y asociación histórica; no ejecutar tareas hasta resolver.'
    if state == 'Requiere autorización':
        return recognition, 'Aceptar autorización de depuración en Android desde Panda.'
    if state == 'Servidor sin verificar':
        return recognition, 'Abrir Panda y revisar servidor/puerto de origen; estado físico desconocido.'
    return recognition, 'Sin respuesta: revisar modo OTG, arranque, cable, red y alimentación. Probar cable/puerto conocidos; energía no comprobada.'

"""Vista física estable y sincronización administrativa tipada con Panda."""
from .inventory import Adb, shell, identity_from_properties
import re


def ordered_rows(rows, positions, active_first=False):
    mapping = {p['hardware_serial']: p for p in positions}
    grouped = {}
    for original in rows:
        row = dict(original)
        row.update(mapping.get(row.get('hardware_serial'), {}))
        # Una ficha puede tener varios transportes. Preferir uno validado sin borrar historial.
        key = row['id']
        rank = (row['status'] != 'Validado', row['status'] == 'Desconectado', row['port'], row['serial'])
        if key not in grouped or rank < grouped[key][0]:
            grouped[key] = (rank, row)
    def key(row):
        physical = (row.get('rack', 'ZZZZ'), row.get('slot', 999999), row['display_name'].lower(), row['id'])
        return (row['status'] != 'Validado', *physical) if active_first else physical
    return sorted([r for _,r in grouped.values()], key=key)


def verify_identity(row):
    if row['status'] != 'Validado' or row.get('identity_state') in ('Serial repetido: revisar', 'Fuentes en conflicto'):
        raise ValueError('Primero valida una identidad sin conflictos.')
    raw = shell(Adb(row['port']), row['serial'], 'getprop')
    props = dict(re.findall(r'^\[([^]]+)\]: \[(.*)\]\r?$', raw, re.M))
    identity = identity_from_properties(props)
    if identity['identity_conflict'] or not identity['hardware_serial'] or identity['hardware_serial'] != row.get('hardware_serial'):
        raise ValueError('La conexión cambió de identidad; vuelve a conciliar.')


def sync_position(row):
    from .panda_api import list_devices, update_device
    verify_identity(row)
    devices = list_devices()
    matches = [d for d in devices if d.get('onlySerial') == row['hardware_serial']]
    if len(matches) != 1 or matches[0].get('serial') != row['serial']:
        raise ValueError('Panda no confirma un único transporte coincidente; vuelve a conciliar.')
    number = row['panda_number']
    if any(str(d.get('sort')) == str(number) and d.get('onlySerial') != row['hardware_serial'] for d in devices):
        raise ValueError('El número ya está ocupado en Panda. Elige un número libre antes de sincronizar.')
    name = f"{row['rack']}-P{row['slot']:02d}"
    # Guardar evidencia anterior antes de modificar Panda; si falla la consulta posterior no reintentar a ciegas.
    from .core import DATA, now
    import json
    DATA.mkdir(exist_ok=True)
    audit = DATA / 'panda-position-changes.jsonl'
    entry = dict(at=now(), hardware_serial=row['hardware_serial'], before=matches[0], requested=dict(name=name, sort=number), state='Intento')
    with audit.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
    update_device(row['serial'], name, number)
    after = [d for d in list_devices() if d.get('onlySerial') == row['hardware_serial']]
    if len(after) != 1 or after[0].get('name') != name or str(after[0].get('sort')) != str(number):
        raise RuntimeError('Panda no confirmó el nombre/número; estado incierto, consultar antes de reintentar.')
    with audit.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(at=now(), hardware_serial=row['hardware_serial'], state='Confirmado', after=after[0]), ensure_ascii=False) + '\n')
    return f'Panda confirmó {name} · número {number}. Persistencia tras reinicio aún por validar.'

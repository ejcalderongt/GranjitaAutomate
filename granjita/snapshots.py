"""Subfase 4.2: snapshots lógicos SQLite y recuperación conservadora de archivos propios."""
import base64
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid
from .core import Adb, DATA, now
from .inventory import shell, collect_inventory
from .physical import verify_identity, ordered_rows

DIRECTORY='/sdcard/Download/Granjita'
MAX_FILE=16384
MAX_FILES=32


def digest(data):
    return hashlib.sha256(data).hexdigest()


def filename(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.(json|txt)',name):
        raise ValueError('Solo nombres simples .json/.txt del directorio administrado.')
    return name


def query(row, command):
    raw=shell(Adb(row['port'],8),row['serial'],command+'; __snap_rc=$?; printf "\\n__SNAP_RC=%s\\n" "$__snap_rc"')
    body,marker,rc=raw.rpartition('__SNAP_RC=')
    if not marker or rc.strip()!='0':
        raise RuntimeError('Consulta sin confirmación: '+body[-250:])
    return body.strip()


def safe_directory(row,create=False):
    query(row, f'[ ! -L /sdcard/Download ] && [ ! -L {DIRECTORY} ] && [ -d /sdcard/Download ] && [ -r /sdcard/Download ] && [ -x /sdcard/Download ] && ( [ ! -e {DIRECTORY} ] || ( [ -d {DIRECTORY} ] && [ -r {DIRECTORY} ] && [ -x {DIRECTORY} ] ) )' + (f' && mkdir -p {DIRECTORY}' if create else ''))


def list_files(row):
    safe_directory(row)
    output=query(row,f'if [ -d {DIRECTORY} ]; then ls -1 {DIRECTORY}; fi')
    names=[]
    for name in output.splitlines():
        filename(name)
        names.append(name)
    if len(names)>MAX_FILES:
        raise ValueError('Directorio excede 32 archivos; snapshot parcial, revisar contenido.')
    return names


def read_file(row,name):
    path=DIRECTORY+'/'+filename(name)
    # Códigos diferenciados: ausencia, enlace/objeto inesperado y fallo de lectura.
    output=query(row,f'if [ -L {path} ]; then echo UNSAFE; elif [ ! -e {path} ]; then echo MISSING; elif [ -f {path} ]; then echo FILE; wc -c < {path}; sha256sum {path}; else echo UNSAFE; fi')
    if output=='MISSING':return None
    lines=output.splitlines()
    if len(lines)!=3 or lines[0]!='FILE' or not lines[1].strip().isdigit() or int(lines[1])>MAX_FILE:
        raise ValueError('Archivo no regular, demasiado grande o ilegible: '+name)
    encoded=query(row,'base64 '+path)
    data=base64.b64decode(''.join(encoded.split()),validate=True)
    if len(data)!=int(lines[1]) or len(data)>MAX_FILE or digest(data)!=lines[2].split()[0] or digest(data)!=query(row,'sha256sum '+path).split()[0]:
        raise ValueError('El archivo cambió durante la lectura: '+name)
    return data


def write_missing(row,name,data):
    if len(data)>MAX_FILE:raise ValueError('Archivo demasiado grande.')
    safe_directory(row,True)
    path=DIRECTORY+'/'+filename(name)
    encoded=base64.b64encode(data).decode('ascii')
    # noclobber evita truncar un archivo que aparezca entre la comparación y la escritura.
    query(row,f"(set -C; printf '%s' '{encoded}' | base64 -d > {path})")
    if read_file(row,name)!=data:
        raise RuntimeError('Restauración sin verificación de contenido: '+name)


def latest(store,serial):
    with store.connect() as db:
        row=db.execute("SELECT * FROM device_checkpoints WHERE hardware_serial=? AND status='Completo' ORDER BY rowid DESC LIMIT 1",(serial,)).fetchone()
        return dict(row) if row else None


def event(store,row,snapshot_id,status,detail):
    with store.connect() as db:
        db.execute('INSERT INTO recovery_events(snapshot_id,hardware_serial,at,status,detail) VALUES (?,?,?,?,?)',(snapshot_id,row.get('hardware_serial') or '',now(),status,detail))


def eligible(store):
    rows=ordered_rows(store.fleet_devices(),store.positions())
    counts={}
    for r in rows:
        if r.get('hardware_serial'):counts[r['hardware_serial']]=counts.get(r['hardware_serial'],0)+1
    return [r for r in rows if r['status']=='Validado' and counts.get(r.get('hardware_serial'))==1 and r['identity_state'] not in ('Serial repetido: revisar','Fuentes en conflicto')]


def capture(store,row):
    verify_identity(row)
    if query(row,'getprop sys.boot_completed')!='1':
        raise RuntimeError('Esperando arranque Android; vuelve a verificar cuando termine.')
    identifier=str(uuid.uuid4())
    files={};errors=[]
    try:
        for name in list_files(row):
            content=read_file(row,name)
            if content is None:raise RuntimeError('Archivo desapareció durante captura: '+name)
            files[name]=content
    except Exception as exc:errors.append(str(exc))
    observations=collect_inventory(row['port'],row['serial'])
    errors.extend(o['field']+': '+o['state'] for o in observations if o['state']=='Error')
    def observe(command):
        try:return query(row,command)
        except Exception as exc:
            errors.append(str(exc));return ''
    boot=observe('cat /proc/sys/kernel/random/boot_id')
    foreground=observe('dumpsys activity activities | grep mResumedActivity || true')
    tasks=[]
    jobs=DATA/'automation.sqlite3'
    if jobs.exists():
        connection=sqlite3.connect(jobs.as_uri()+'?mode=ro',uri=True)
        try:
            connection.row_factory=sqlite3.Row
            tasks=[dict(t) for t in connection.execute('SELECT id,action,status,updated FROM tasks WHERE device_id=? ORDER BY updated DESC LIMIT 20',(row['id'],))]
        finally:connection.close()
    verify_identity(row)
    manifest=dict(schema_version=1,subphase='4.2',id=identifier,at=now(),hardware_serial=row['hardware_serial'],device_id=row['id'],
        origin=dict(port=row['port'],serial=row['serial']),position={k:row.get(k) for k in ('rack','slot','panda_number')},
        boot_id=boot,foreground=foreground,observations=observations,tasks=tasks,errors=errors,
        policy='missing_managed_files_only',files=[dict(name=n,size=len(b),sha256=digest(b)) for n,b in files.items() if b is not None])
    spec=json.dumps(manifest,ensure_ascii=False,sort_keys=True)
    state='Parcial' if errors else 'Completo'
    with store.connect() as db:
        db.execute('INSERT INTO device_checkpoints VALUES (?,?,?,?,?,?,?)',(identifier,row['hardware_serial'],row['id'],now(),state,spec,digest(spec.encode())))
        db.executemany('INSERT INTO checkpoint_files VALUES (?,?,?,?,?)',[(identifier,n,b,digest(b),len(b)) for n,b in files.items() if b is not None])
    event(store,row,identifier,state,f'Snapshot {state}: {len(files)} archivos; {len(errors)} incidencias.')
    return identifier,state


def restore(store,row):
    snapshot=latest(store,row['hardware_serial'])
    if not snapshot:return 'Sin snapshot completo'
    verify_identity(row)
    if digest(snapshot['manifest'].encode())!=snapshot['sha256']:
        raise ValueError('Manifiesto corrupto; restauración bloqueada.')
    manifest=json.loads(snapshot['manifest'])
    if manifest.get('hardware_serial')!=row['hardware_serial'] or manifest.get('policy')!='missing_managed_files_only':
        raise ValueError('Identidad o política del snapshot inválida.')
    if query(row,'getprop sys.boot_completed')!='1':
        event(store,row,snapshot['id'],'Pendiente','Esperando arranque Android')
        return 'Esperando arranque Android'
    safe_directory(row)
    with store.connect() as db:
        files=[dict(f) for f in db.execute('SELECT * FROM checkpoint_files WHERE snapshot_id=?',(snapshot['id'],))]
    expected={f['name']:f for f in manifest['files']}
    if len(expected)!=len(files):raise ValueError('Inventario de archivos incompleto.')
    # Validar todo antes de escribir el primer archivo.
    for f in files:
        filename(f['name'])
        if f['name'] not in expected or digest(f['content'])!=f['sha256'] or f['sha256']!=expected[f['name']]['sha256'] or len(f['content'])!=expected[f['name']]['size']:
            raise ValueError('Archivo de snapshot corrupto; restauración bloqueada.')
    restored=0;conflicts=[]
    for f in files:
        current=read_file(row,f['name'])
        if current is None:
            verify_identity(row)
            event(store,row,snapshot['id'],'Recuperando','Intento de recuperar archivo ausente: '+f['name'])
            write_missing(row,f['name'],f['content']);restored+=1
        elif digest(current)!=f['sha256']:
            conflicts.append(f['name'])
    current_observations=collect_inventory(row['port'],row['serial'])
    inventory_errors=[o['field'] for o in current_observations if o['state']=='Error']
    baseline={o['field']:o for o in manifest['observations']}
    drift=[o['field'] for o in current_observations if o['field'] in baseline and o['state']=='Disponible' and baseline[o['field']]['state']=='Disponible' and o['value']!=baseline[o['field']]['value']]
    detail=f'{restored} archivos recuperados; {len(conflicts)} diferentes conservados. {len(drift)} campos de inventario cambiaron.'
    if drift:detail+=' Diferencias (sin restaurar ajustes): '+', '.join(drift)
    if conflicts:detail+=' Revisar: '+', '.join(conflicts)
    if inventory_errors:detail+=' Consultas fallidas: '+', '.join(inventory_errors)
    verify_identity(row)
    event(store,row,snapshot['id'],'Revisar' if conflicts or inventory_errors else 'Verificado',detail)
    return detail


def reconcile_snapshots(store,rows=None,progress=None,capture_only=False):
    result=[]
    for row in rows if rows is not None else eligible(store):
        try:
            if capture_only or not latest(store,row['hardware_serial']):
                identifier,state=capture(store,row)
                detail=f'{state}: {identifier}'
            else:detail=restore(store,row)
        except Exception as exc:
            detail='Error: '+str(exc)
            event(store,row,None,'Error',detail)
        result.append(dict(hardware_serial=row.get('hardware_serial'),detail=detail))
        if progress:progress(len(result),row['display_name']+' · '+detail)
    return result

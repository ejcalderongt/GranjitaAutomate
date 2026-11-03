"""Conciliación de inventario Panda/ADB/AGX, sin gestos ni cambios en las placas."""
import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timezone

from core.adb_pool import PoolSnapshot,descubrir_pool
from core.panda_api import PandaClient
from core.panda_identity import leer_identidad_fisica


def verificar_rutas(snapshot,db):
    verified={};errors={};blocked=set()
    def inspect(route):
        if route.status!='device':
            return route,None,'adb_no_autorizado'
        try:
            physical=leer_identidad_fisica(route)
            db.identidad_agx(physical)
            return replace(route,hardware_serial=physical),physical,None
        except Exception as exc:
            return route,None,type(exc).__name__
    with ThreadPoolExecutor(max_workers=6) as pool:
        for route,physical,error in pool.map(inspect,snapshot.devices.values()):
            if error:
                errors[route.serial]=error
            elif physical in blocked:
                errors[route.serial]='serial_duplicado'
            elif physical in verified:
                errors[route.serial]='serial_duplicado'
                errors[verified[physical].serial]='serial_duplicado'
                verified.pop(physical);blocked.add(physical)
            else:
                verified[physical]=route
    return PoolSnapshot(verified,snapshot.errors,snapshot.successful,identity_errors=errors)


def conciliar(rows,snapshot,db):
    number_count=Counter(str(row.get('sort')) for row in rows)
    serial_count=Counter(row.get('onlySerial') for row in rows)
    routes={route.serial:route for route in snapshot.devices.values()}
    result=[]
    for row in rows:
        number=str(row.get('sort',''))
        physical=row.get('onlySerial')
        record={'numero_panda':number.zfill(2),'serial_panda':physical,
                'transporte':row.get('serial'),'nombre_panda':row.get('name'),
                'serial_fisico':None,'alias_agx':None,'canonical_id':None,'estado':'no_verificado'}
        route=routes.get(row.get('serial'))
        if not number.isdigit() or int(number)<1 or number_count[number]!=1 or serial_count[physical]!=1:
            record['estado']='ambiguo'
        elif 'status' in row and row['status']!='online':
            record['estado']='offline_panda'
        elif route is None:
            record['estado']='sin_adb_verificado'
        elif route.hardware_serial!=physical:
            record['estado']='conflicto_identidad'
        else:
            identity=db.identidad_agx(physical)
            record.update(serial_fisico=physical,alias_agx=identity.get('alias'),
                          canonical_id=identity.get('canonical_id'),estado='vinculado',
                          adb_host=route.server.host,adb_port=route.server.port)
        result.append(record)
    return result


def guardar_inventario(db,snapshot,rows,run_id):
    # Reutiliza la conciliación existente: preserva alias, cuenta, proxy e historia.
    db.sincronizar_pool(snapshot)
    now=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    with db.conexion() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS panda_inventario_observaciones (
            run_id TEXT NOT NULL,numero_panda TEXT NOT NULL,observado_utc TEXT NOT NULL,
            serial_panda TEXT,serial_fisico TEXT,transporte TEXT,nombre_panda TEXT,
            alias_agx TEXT,canonical_id TEXT,estado TEXT NOT NULL,
            PRIMARY KEY(run_id,numero_panda,transporte))''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_panda_hardware ON panda_inventario_observaciones(serial_fisico,observado_utc)')
        columns={row['name'] for row in con.execute('PRAGMA table_info(dispositivos)')}
        for name in ('panda_numero','panda_nombre','panda_verificado_en','panda_estado'):
            if name not in columns:
                con.execute(f'ALTER TABLE dispositivos ADD COLUMN {name} TEXT')
        con.execute("UPDATE dispositivos SET panda_estado='no_observado' WHERE panda_numero IS NOT NULL")
        for row in rows:
            con.execute('INSERT INTO panda_inventario_observaciones VALUES (?,?,?,?,?,?,?,?,?,?)',
                (run_id,row['numero_panda'],now,row.get('serial_panda'),row.get('serial_fisico'),
                 row.get('transporte'),row.get('nombre_panda'),row.get('alias_agx'),row.get('canonical_id'),row['estado']))
            if row['estado']=='vinculado':
                con.execute('''UPDATE dispositivos SET panda_numero=?,panda_nombre=?,panda_verificado_en=?,
                    panda_estado='vinculado' WHERE id_adb=?''',
                    (row['numero_panda'],row.get('nombre_panda'),now,row['serial_fisico']))
        con.execute('''INSERT INTO configuracion VALUES ('panda_inventory_run',?)
            ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor''',(run_id,))


async def obtener_inventario(db,client=None):
    panda=client or PandaClient()
    rows=await panda.inventario()
    raw=await asyncio.to_thread(descubrir_pool,db.servidores_configurados())
    if not raw.successful:
        raise RuntimeError('No se pudo consultar ningún servidor ADB')
    verified=await asyncio.to_thread(verificar_rutas,raw,db)
    result=await asyncio.to_thread(conciliar,rows,verified,db)
    return verified,result,{'panda_observados':len(rows),'rutas_adb':len(raw.devices),
        'identidades_adb_verificadas':len(verified.devices),'errores_identidad':len(verified.identity_errors),
        'errores_servidor':len(raw.errors),'vinculados':sum(r['estado']=='vinculado' for r in result),
        'con_historia_agx':sum(r['estado']=='vinculado' and bool(r['canonical_id']) for r in result)}

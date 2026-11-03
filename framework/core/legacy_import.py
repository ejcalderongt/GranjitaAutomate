"""Rescate reproducible AGX: snapshots SQLite consistentes e historia separada del vivo.

Uso: python -m core.legacy_import --source RUTA_AGX [--apply]
"""
import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from core.database import Database, ROOT, ahora


def lectura(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=15)


def snapshot(source,target):
    with closing(lectura(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError(f'Snapshot SQLite inválido: {target.name}')


def quote(name):
    return '"'+name.replace('"','""')+'"'


def encoded(row):
    return json.dumps(dict(row),ensure_ascii=False,sort_keys=True,
        default=lambda value:{'base64':base64.b64encode(value).decode('ascii')})


def inspeccionar(source):
    result={}
    for name in ('granjita.sqlite3','automation.sqlite3','traces.sqlite3'):
        path=Path(source)/'data'/name
        if not path.is_file():
            continue
        with closing(lectura(path)) as con:
            tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            result[name]={table:con.execute('SELECT COUNT(*) FROM '+quote(table)).fetchone()[0] for table in tables}
    if 'granjita.sqlite3' not in result:
        raise ValueError('Falta data/granjita.sqlite3 en AGX')
    return result


def importar(source,target=None):
    source=Path(source).resolve()
    counts=inspeccionar(source)
    target=Path(target or ROOT/'data/granja_tiktok.db').resolve()
    if target==source/'data/granjita.sqlite3' or source in target.parents:
        raise ValueError('El destino debe estar fuera del proyecto fuente AGX')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    archive=target.parent/'imports'/'agx'/stamp
    archive.mkdir(parents=True)
    if target.exists():
        snapshot(target,archive/'framework-before.sqlite3')
    for name in counts:
        snapshot(source/'data'/name,archive/name)
    panda_path=source/'data/panda-inventory.json'
    panda=None
    if panda_path.is_file():
        content=panda_path.read_bytes()
        panda=json.loads(content.decode('utf-8-sig'))
        (archive/'panda-inventory.json').write_bytes(content)
    # Trabajar únicamente sobre snapshots; nunca importar ejecutando módulos antiguos.
    db=Database(target)
    added=0
    historical=0
    with db.conexion() as dest:
        dest.execute('''CREATE TABLE IF NOT EXISTS legacy_agx_records (
            source_db TEXT NOT NULL, source_table TEXT NOT NULL, record_hash TEXT NOT NULL,
            payload TEXT NOT NULL, imported_at TEXT NOT NULL,
            PRIMARY KEY(source_db,source_table,record_hash))''')
        dest.execute('''CREATE TABLE IF NOT EXISTS legacy_agx_identities (
            legacy_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, hardware_serial TEXT NOT NULL,
            alias TEXT NOT NULL, observed_at TEXT NOT NULL, source TEXT NOT NULL)''')
        # Archivar filas por hash: reimportar no duplica evidencia ni borra versiones anteriores.
        for name in ('granjita.sqlite3','automation.sqlite3'):
            if name not in counts:
                continue
            with closing(lectura(archive/name)) as src:
                src.row_factory=sqlite3.Row
                for table in counts[name]:
                    for row in src.execute('SELECT * FROM '+quote(table)):
                        payload=encoded(row)
                        cursor=dest.execute('INSERT OR IGNORE INTO legacy_agx_records VALUES (?,?,?,?,?)',
                            (name,table,hashlib.sha256(payload.encode()).hexdigest(),payload,ahora()))
                        historical+=cursor.rowcount
        with closing(lectura(archive/'granjita.sqlite3')) as src:
            src.row_factory=sqlite3.Row
            aliases=dict(src.execute('SELECT alias_id,canonical_id FROM device_identity_aliases'))
            labels=dict(src.execute('SELECT id,alias FROM inventory_devices'))
            identities={r['device_id']:dict(r) for r in src.execute('SELECT * FROM device_identity')}
            for identity,row in identities.items():
                canonical=identity
                seen=set()
                while canonical in aliases:
                    if canonical in seen:
                        raise ValueError('Ciclo en alias de identidad AGX; importación revertida')
                    seen.add(canonical)
                    canonical=aliases[canonical]
                if canonical not in identities:
                    raise ValueError('Alias AGX sin identidad canónica')
                physical=identities[canonical]['hardware_serial'].strip()
                label=labels.get(canonical,'')
                dest.execute('''INSERT INTO legacy_agx_identities VALUES (?,?,?,?,?,?)
                    ON CONFLICT(legacy_id) DO UPDATE SET canonical_id=excluded.canonical_id,
                    hardware_serial=excluded.hardware_serial,
                    alias=CASE WHEN legacy_agx_identities.alias='' THEN excluded.alias ELSE legacy_agx_identities.alias END,
                    observed_at=excluded.observed_at,source=excluded.source''',
                    (identity,canonical,physical,label,row['at'],str(source)))
                if identity!=canonical or not physical or ':' in physical or physical.startswith('emulator-'):
                    continue
                # Solo rellenar inventario; conservar estado/cuenta/proxy y alias actuales.
                cursor=dest.execute('''INSERT OR IGNORE INTO dispositivos
                    (id_adb,alias,estado,conectado,inventario_estado) VALUES (?,?,'Desconectado',0,'historico_agx')''',
                    (physical,label))
                added+=cursor.rowcount
                dest.execute("UPDATE dispositivos SET alias=? WHERE id_adb=? AND COALESCE(alias,'')=''",(label,physical))
    aliases_added=0
    if panda is not None:
        with db.conexion() as dest:
            for row in panda['devices']:
                physical=row.get('onlySerial')
                label=str(row.get('name') or '').strip()
                if not physical or not label:
                    continue
                payload=encoded({'at':panda['at'],'device':row})
                historical+=dest.execute('INSERT OR IGNORE INTO legacy_agx_records VALUES (?,?,?,?,?)',
                    ('panda-inventory.json','devices',hashlib.sha256(payload.encode()).hexdigest(),payload,ahora())).rowcount
                # Solo serial físico confirmado; no inferir correspondencia por número Panda o IP.
                aliases_added+=dest.execute("UPDATE legacy_agx_identities SET alias=? WHERE hardware_serial=? AND alias=''",
                    (label,physical)).rowcount
                dest.execute("UPDATE dispositivos SET alias=? WHERE id_adb=? AND COALESCE(alias,'')=''",(label,physical))
    report={'source':str(source),'destination':str(target),'archive':str(archive),
            'tables':counts,'devices_added':added,'historical_rows_added':historical,
            'historical_aliases_added':aliases_added,
            'panda_inventory_sha256':hashlib.sha256((archive/'panda-inventory.json').read_bytes()).hexdigest() if panda else None,
            'live_auth_imported':False,'live_connections_imported':False,
            'snapshots_sha256':{name:hashlib.sha256((archive/name).read_bytes()).hexdigest() for name in counts}}
    (archive/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--database',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(importar(args.source,args.database) if args.apply else inspeccionar(args.source),
                     ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

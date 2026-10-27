"""Reasociar conflictos de IP a fichas existentes verificadas; vista previa por defecto.

Uso: python -m scripts.reasignar_conflictos [--apply]
No borra fichas, snapshots, alias ni tareas. Evidencia privada en data/.
"""
import argparse
from collections import Counter
import json
import sqlite3
from granjita.core import DATA, now, Adb
from granjita.inventory import FleetStore, scan_fleet, shell, identity_from_properties
from granjita.panda_api import list_devices
import re


def plan_changes(db, report, panda):
    changes=[]
    for d in report['devices']:
        old=db.execute('SELECT c.device_id,c.status,i.hardware_serial FROM connections c LEFT JOIN device_identity i ON i.device_id=c.device_id WHERE c.port=? AND c.serial=?',(d['port'],d['serial'])).fetchone()
        if not old or old['status']!='Identidad en conflicto':
            continue
        hardware=d.get('hardware_serial')
        if d['status']!='Validado' or not hardware or d.get('identity_conflict'):
            raise ValueError('Una conexión en conflicto no tiene identidad actual verificable.')
        matches=[p for p in panda if p.get('serial')==d['serial'] and p.get('onlySerial')==hardware]
        has_aliases=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='device_identity_aliases'").fetchone()
        active_filter=' AND device_id NOT IN (SELECT alias_id FROM device_identity_aliases)' if has_aliases else ''
        targets=db.execute('SELECT * FROM device_identity WHERE hardware_serial=?'+active_filter,(hardware,)).fetchall()
        if len(matches)!=1 or len(targets)!=1:
            raise ValueError('Panda o la ficha destino no confirman una correspondencia única.')
        target=targets[0]
        if target['state']!='Serial leído' or not target['manufacturer'] or not target['model'] or target['manufacturer']!=d.get('manufacturer') or target['model']!=d.get('hardware_model'):
            raise ValueError('Fabricante/modelo o estado de identidad no coinciden.')
        if target['device_id']==old['device_id']:
            raise ValueError('La ficha destino ya es la anterior; requiere otro diagnóstico.')
        changes.append(dict(port=d['port'],transport=d['serial'],old_id=old['device_id'],old_hardware=old['hardware_serial'],target_id=target['device_id'],hardware_serial=hardware,manufacturer=target['manufacturer'],model=target['model'],panda_number=matches[0].get('sort')))
    return changes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    report=scan_fleet([5037,5038])
    panda=list_devices()
    path=DATA/'granjita.sqlite3'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        changes=plan_changes(db,report,panda)
    print(json.dumps(dict(mode='apply' if args.apply else 'preview',connections=len(changes),physical_devices=len({c['hardware_serial'] for c in changes}),panda_numbers=sorted({c['panda_number'] for c in changes})),ensure_ascii=False))
    if not args.apply or not changes:
        return
    # Releer Android justo antes de aplicar, sin confiar solo en IP ni datos guardados.
    for c in changes:
        raw=shell(Adb(c['port']),c['transport'],'getprop')
        identity=identity_from_properties(dict(re.findall(r'^\[([^]]+)\]: \[(.*)\]\r?$',raw,re.M)))
        if identity.get('identity_conflict') or identity['hardware_serial']!=c['hardware_serial'] or identity['manufacturer']!=c['manufacturer'] or identity['hardware_model']!=c['model']:
            raise ValueError('La identidad cambió durante la revisión; no se aplicó el lote.')
    stamp=now()
    backup=DATA/'backups'/('antes-reasignacion-'+stamp.replace(':','').replace('-','')+'.sqlite3')
    backup.parent.mkdir(parents=True,exist_ok=True)
    # Backup coherente de SQLite, incluyendo WAL, antes de la transacción.
    with sqlite3.connect(path) as source,sqlite3.connect(backup) as destination:
        source.backup(destination)
    audit=DATA/('reasignacion-'+stamp.replace(':','').replace('-','')+'.json')
    evidence=dict(at=stamp,state='prepared',backup=str(backup),changes=changes)
    audit.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    with sqlite3.connect(path,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        for c in changes:
            old=db.execute('SELECT device_id,status FROM connections WHERE port=? AND serial=?',(c['port'],c['transport'])).fetchone()
            target=db.execute('SELECT * FROM device_identity WHERE device_id=?',(c['target_id'],)).fetchone()
            if not old or old['device_id']!=c['old_id'] or old['status']!='Identidad en conflicto' or not target or target['hardware_serial']!=c['hardware_serial'] or target['state']!='Serial leído':
                raise ValueError('La base cambió durante la revisión; transacción cancelada.')
            detail=json.dumps(dict(action='identity_reassigned',old_device_id=c['old_id'],new_device_id=c['target_id'],verified_hardware=c['hardware_serial'],panda_number=c['panda_number']),ensure_ascii=False)
            db.execute("UPDATE connections SET device_id=?,status='Validado',detail=?,last_seen=?,last_check=? WHERE port=? AND serial=?",(c['target_id'],detail,stamp,stamp,c['port'],c['transport']))
            for identifier in (c['old_id'],c['target_id']):
                db.execute('INSERT INTO connection_events(device_id,at,status,detail) VALUES (?,?,?,?)',(identifier,stamp,'Reasociación verificada',detail))
    evidence['state']='committed'
    audit.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    # Confirmación independiente y actualización normal del inventario.
    fresh=scan_fleet([5037,5038])
    store=object.__new__(FleetStore)
    store.path=path
    store.save_fleet(fresh)
    rows=store.fleet_devices()
    active={r['hardware_serial'] for r in rows if r['status']=='Validado' and r.get('hardware_serial')}
    conflicts=[r for r in rows if r['status']=='Identidad en conflicto']
    from granjita.physical import ordered_rows
    candidates=ordered_rows(rows,store.positions())
    ready=[r for r in candidates if r['status']=='Validado' and r['identity_state']=='Serial leído']
    current_panda=list_devices()
    pserials={p.get('onlySerial') for p in current_panda if p.get('onlySerial')}
    with store.connect() as db:
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
    evidence.update(verification=dict(at=now(),online=len(active),ready=len(ready),conflict_connections=len(conflicts),panda=len(pserials),same_physical_set=active==pserials,integrity=integrity))
    audit.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence['verification'],ensure_ascii=False))
    if conflicts or active!=pserials or integrity!='ok':
        raise RuntimeError('Reasociación aplicada; verificación requiere revisión. Consultar auditoría antes de repetir.')


if __name__=='__main__':
    main()

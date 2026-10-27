"""Consolidación explícita de fichas duplicadas, sin eliminar historia."""
import json
from collections import Counter
from .core import now


def plan_consolidations(db,report,panda,numbers):
    plans=[]
    good_ports={s['port'] for s in report['servers'] if s['status']=='ADB responde'}
    current={(d['port'],d['serial']):d for d in report['devices']}
    for number in numbers:
        candidates=[p for p in panda if p.get('sort')==number]
        if len(candidates)!=1:raise ValueError('Panda no confirma una pantalla única.')
        device=candidates[0];hardware=device.get('onlySerial')
        live=[d for d in report['devices'] if d.get('hardware_serial')==hardware]
        if not live or any(d['status']!='Validado' or d.get('identity_conflict') for d in live):raise ValueError('La identidad actual no está validada.')
        if {d['serial'] for d in live}!={device.get('serial')}:raise ValueError('Serial simultáneo en distintos transportes; no consolidar.')
        identities=[dict(r) for r in db.execute('SELECT i.*,d.created,d.alias FROM device_identity i JOIN inventory_devices d ON d.id=i.device_id WHERE i.hardware_serial=? AND i.device_id NOT IN (SELECT alias_id FROM device_identity_aliases) ORDER BY d.created,d.id',(hardware,))]
        if len(identities)==1:continue
        if len(identities)<2:raise ValueError('No se encontraron fichas candidatas.')
        metadata={(i['manufacturer'],i['model'],i['state']) for i in identities}
        if len(metadata)!=1 or any(not i['manufacturer'] or not i['model'] or i['state']!='Serial leído' for i in identities):raise ValueError('Las fichas discrepan en fabricante, modelo o estado.')
        manufacturer,model,_=next(iter(metadata))
        if any(d.get('manufacturer')!=manufacturer or d.get('hardware_model')!=model for d in live):raise ValueError('Android actual no coincide con metadatos históricos.')
        aliases={i['alias'] for i in identities if i['alias']}
        if len(aliases)>1:raise ValueError('Hay alias manuales incompatibles; revisar antes de consolidar.')
        ids=[i['device_id'] for i in identities];marks=','.join('?' for _ in ids)
        if db.execute('SELECT 1 FROM device_identity_aliases WHERE canonical_id IN ('+marks+')',ids).fetchone():raise ValueError('Existe consolidación previa; no crear cadenas de referencias.')
        connections=[dict(r) for r in db.execute('SELECT * FROM connections WHERE device_id IN ('+marks+')',ids)]
        for c in connections:
            if c['port'] not in good_ports:raise ValueError('Falta verificar un servidor de origen.')
            observed=current.get((c['port'],c['serial']))
            if observed and (observed.get('hardware_serial')!=hardware or observed['status']!='Validado'):raise ValueError('Una conexión histórica ahora corresponde a otro dispositivo.')
        plans.append(dict(panda_number=number,hardware_serial=hardware,canonical_id=ids[0],identities=identities,connections=connections,live=live,alias=next(iter(aliases),'')))
    return plans


def apply_consolidations(store,plans):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # Revalidar todas las fichas antes del primer cambio: el lote es atómico.
        for plan in plans:
            for before in plan['identities']:
                row=db.execute('SELECT * FROM device_identity WHERE device_id=?',(before['device_id'],)).fetchone()
                if not row or any(row[k]!=before[k] for k in ('hardware_serial','manufacturer','model','state')):raise ValueError('La identidad cambió durante la revisión.')
                if db.execute('SELECT 1 FROM device_identity_aliases WHERE alias_id=? OR canonical_id=?',(before['device_id'],before['device_id'])).fetchone():raise ValueError('La referencia cambió durante la revisión.')
            for c in plan['connections']:
                row=db.execute('SELECT device_id FROM connections WHERE port=? AND serial=?',(c['port'],c['serial'])).fetchone()
                if not row or row['device_id']!=c['device_id']:raise ValueError('La conexión cambió durante la revisión.')
        for plan in plans:
            evidence=json.dumps(plan,ensure_ascii=False,sort_keys=True)
            canonical=plan['canonical_id']
            if plan['alias']:db.execute('UPDATE inventory_devices SET alias=? WHERE id=?',(plan['alias'],canonical))
            for identity in plan['identities']:
                identifier=identity['device_id']
                if identifier!=canonical:
                    db.execute('INSERT INTO device_identity_aliases VALUES(?,?,?,?)',(identifier,canonical,now(),evidence))
                    db.execute('UPDATE connections SET device_id=? WHERE device_id=?',(canonical,identifier))
                db.execute('INSERT INTO connection_events(device_id,at,status,detail) VALUES(?,?,?,?)',(identifier,now(),'Identidad consolidada',evidence))
    return len(plans)

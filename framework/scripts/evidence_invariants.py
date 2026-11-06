"""Read-only SQLite state comparisons; raw row values are never exported."""
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing

OWN_SEQUENCES=frozenset(('farm_preflight_verdicts','farm_stage_metrics'))
DECLARED_TABLES={'telemetria_panda.db':'auditorias_panda','telemetry_qa.db':'eventos_ia_qa'}


def file_hash(path):
    path=Path(path)
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def _value(value):
    if isinstance(value,bytes):
        return ['bytes',value.hex()]
    if isinstance(value,float):
        return ['float',value.hex()]
    return [type(value).__name__,value]


def _digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=True,separators=(',',':'),sort_keys=True).encode('ascii')).hexdigest()


def _quote(name):
    return '"'+name.replace('"','""')+'"'


def snapshot(path):
    path=Path(path)
    tables={}
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        schema=db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name,tbl_name").fetchall()
        names=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        sequence=dict(db.execute('SELECT name,seq FROM sqlite_sequence')) if 'sqlite_sequence' in names else None
        for name in names:
            if name=='sqlite_sequence':
                continue
            info=db.execute('PRAGMA table_info('+_quote(name)+')').fetchall()
            columns=[row[1] for row in info]
            data=db.execute('SELECT * FROM '+_quote(name)).fetchall()
            encoded=[[_value(v) for v in row] for row in data]
            item={'count':len(data),'hash':_digest(sorted(encoded,key=lambda row:json.dumps(row,ensure_ascii=True,sort_keys=True)))}
            if name.startswith('farm_') or name in DECLARED_TABLES.values():
                pk=[index for _,index in sorted((row[5],index) for index,row in enumerate(info) if row[5])]
                if not pk:
                    raise ValueError('Farm table requires a stable primary key')
                item['key_columns']=[columns[index] for index in pk]
                row_map={}
                for row,values in zip(data,encoded):
                    key=_digest([values[index] for index in pk])
                    owner=_digest(_value(row[columns.index('run_id')])) if 'run_id' in columns else None
                    stable=[value for column,value in zip(columns,values) if column not in ('finished_at','decision')]
                    row_map[key]={'hash':_digest(values),'owner':owner,'stable_hash':_digest(stable)}
                item['rows']=row_map
            tables[name]=item
    sequence_tables=[row[1] for row in schema if row[0]=='table' and 'AUTOINCREMENT' in row[3].upper()]
    return {'file_hash':file_hash(path),'schema_hash':_digest(schema),'tables':tables,
            'sqlite_sequence':sequence,'sequence_tables':sequence_tables}


def declare_run_writes(before,database,run_id,devices,cycles=1):
    """Plan exact row keys before execution; never infer authorization from new rows."""
    if (database not in DECLARED_TABLES or not isinstance(devices,list) or not devices
            or any(not isinstance(device,str) for device in devices)
            or len(set(devices))!=len(devices) or type(cycles) is not int or cycles<1):
        raise ValueError('Escrituras declaradas invalidas')
    table=DECLARED_TABLES[database]
    item=before['tables'].get(table,{})
    columns=item.get('key_columns',[])
    count=len(devices)*cycles
    if database=='telemetria_panda.db':
        if set(columns)!={'run_id','ciclo','id_placa'}:
            raise ValueError('Esquema de auditoria invalido')
        records=[{'run_id':run_id,'ciclo':cycle,'id_placa':device}
                 for cycle in range(1,cycles+1) for device in devices]
    else:
        if columns!=['id'] or table not in before.get('sequence_tables',[]):
            raise ValueError('Esquema de auditoria invalido')
        start=(before['sqlite_sequence'] or {}).get(table,0)
        records=[{'id':start+offset} for offset in range(1,count+1)]
    keys=sorted(_digest([_value(row[column]) for column in columns]) for row in records)
    return {table:{'INSERT':count,'UPDATE':0,'DELETE':0,'keys':keys}}


def compare(before,after,current_run_id,*,mode='outside_run',database='telemetria_panda.db',expected_writes=None):
    """Compare final row states; physical exceptions require an explicit declaration."""
    if mode not in ('outside_run','physical_run') or database not in DECLARED_TABLES:
        raise ValueError('Modo de evidencia invalido')
    declarations={} if expected_writes is None else expected_writes
    if not isinstance(declarations,dict) or (declarations and mode!='physical_run'):
        raise ValueError('Escrituras declaradas invalidas')
    permitted=DECLARED_TABLES[database]
    for name,rule in declarations.items():
        if (name!=permitted or not isinstance(rule,dict)
                or any(type(rule.get(op)) is not int or rule[op]<0 for op in ('INSERT','UPDATE','DELETE'))
                or rule['INSERT']<1 or rule['UPDATE'] or rule['DELETE']
                or set(rule)!={'INSERT','UPDATE','DELETE','keys'}):
            raise ValueError('Escrituras declaradas invalidas')
        keys=rule.get('keys')
        if keys is not None and (not isinstance(keys,list) or len(keys)!=rule['INSERT']
                or any(not isinstance(key,str) or len(key)!=64
                or any(c not in '0123456789abcdef' for c in key) for key in keys)
                or len(set(keys))!=len(keys)):
            raise ValueError('Escrituras declaradas invalidas')
    owner=_digest(_value(current_run_id))
    violations=[]
    nonfarm={}
    farm_counts={}
    expected_rows={}
    observed={}
    write_violations=[]
    for name in sorted(set(before['tables'])|set(after['tables'])):
        left=before['tables'].get(name)
        right=after['tables'].get(name)
        if not name.startswith('farm_'):
            if name in declarations:
                rule=declarations[name]
                expected_rows[name]={**rule,'run_id_hash':owner}
                actual={'INSERT':0,'UPDATE':0,'DELETE':0,'keys':[],'run_id_hash':owner}
                if left is None or right is None or 'rows' not in left or 'rows' not in right:
                    write_violations.append({'table':name,'kind':'declared_table_missing'})
                else:
                    for key,row in left['rows'].items():
                        target=right['rows'].get(key)
                        if target is None:
                            actual['DELETE']+=1
                            write_violations.append({'table':name,'kind':'previous_row_deleted','key':key})
                        elif target['hash']!=row['hash']:
                            actual['UPDATE']+=1
                            write_violations.append({'table':name,'kind':'previous_row_updated','key':key})
                    for key,row in right['rows'].items():
                        if key not in left['rows']:
                            actual['INSERT']+=1
                            actual['keys'].append(key)
                            if row['owner']!=owner:
                                write_violations.append({'table':name,'kind':'foreign_run_insert','key':key})
                    actual['keys'].sort()
                observed[name]=actual
                if (any(actual[op]!=rule[op] for op in ('INSERT','UPDATE','DELETE'))
                        or 'keys' in rule and sorted(rule['keys'])!=actual['keys']):
                    write_violations.append({'table':name,'kind':'declared_writes_mismatch'})
                continue
            nonfarm[name]={'before':left['hash'] if left else None,'after':right['hash'] if right else None}
            continue
        if database!='telemetria_panda.db':
            nonfarm[name]={'before':left['hash'] if left else None,'after':right['hash'] if right else None}
            continue
        farm_counts[name]={'before':left['count'] if left else 0,'after':right['count'] if right else 0}
        if left is None or right is None:
            violations.append({'table':name,'kind':'table_set_changed'})
            continue
        for key,row in left['rows'].items():
            farm_row=right['rows'].get(key)
            if farm_row is None:
                violations.append({'table':name,'kind':'row_deleted'})
            elif farm_row['hash']!=row['hash']:
                allowed=(name=='farm_preflight_runs' and row['owner']==owner
                         and farm_row['owner']==owner and farm_row['stable_hash']==row['stable_hash'])
                if not allowed:
                    violations.append({'table':name,'kind':'row_updated'})
        for key,row in right['rows'].items():
            if key not in left['rows'] and row['owner']!=owner:
                violations.append({'table':name,'kind':'foreign_run_insert'})
    old=before['sqlite_sequence']
    new=after['sqlite_sequence']
    expected=[]
    unexpected=[]
    for name in sorted(set(old or {})|set(new or {})):
        a=(old or {}).get(name)
        b=(new or {}).get(name)
        if a==b:
            continue
        change={'name':name,'before':a,'after':b}
        farm_allowed=database=='telemetria_panda.db' and name in OWN_SEQUENCES
        app_allowed=(mode=='physical_run' and name in declarations and b is not None
                     and b-(a or 0)==declarations[name]['INSERT'])
        if (farm_allowed or app_allowed) and b is not None and b>=(a or 0):
            expected.append(change)
        else:
            unexpected.append(change)
    for name,rule in declarations.items():
        if name in after.get('sequence_tables',[]) and (new or {}).get(name,0)-(old or {}).get(name,0)!=rule['INSERT']:
            if not any(row['name']==name for row in unexpected):
                unexpected.append({'name':name,'before':(old or {}).get(name),'after':(new or {}).get(name)})
    sequence={'expected_farm_advances':expected,'unexpected_changes':unexpected,'absent':old is None and new is None}
    schema_unchanged=before['schema_hash']==after['schema_hash']
    nonfarm_unchanged=all(row['before']==row['after'] for row in nonfarm.values())
    for name in declarations.keys()-expected_rows.keys():
        write_violations.append({'table':name,'kind':'declared_table_missing'})
    if mode=='physical_run' and database=='telemetry_qa.db' and permitted not in declarations:
        write_violations.append({'table':permitted,'kind':'run_declaration_missing'})
    immutable_file=database=='telemetry_qa.db' and mode=='outside_run'
    file_unchanged=before['file_hash']==after['file_hash']
    passed=(schema_unchanged and nonfarm_unchanged and not violations and not unexpected
            and not write_violations and (not immutable_file or file_unchanged))
    return {'status':'PASS' if passed else 'FAIL','schema_unchanged':schema_unchanged,
            'non_farm_tables_unchanged':nonfarm_unchanged,'non_farm_table_hashes':nonfarm,
            'farm_counts':farm_counts,'farm_violations':violations,
            'sqlite_sequence_advance':sequence,'sqlite_sequence_absent':sequence['absent'],
            'full_hash_before':before['file_hash'],'full_hash_after':after['file_hash'],
            'full_hash_changed':not file_unchanged,'file_hash_before':before['file_hash'],
            'file_hash_after':after['file_hash'],'mode':mode,'database':database,
            'expected_writes':expected_rows,'observed_writes':observed,'write_violations':write_violations,
            'tables_unchanged_hashes':nonfarm}


def compare_protected(before,after):
    changed=sorted(name for name in set(before)|set(after) if before.get(name)!=after.get(name))
    return {'status':'FAIL' if changed else 'PASS','changed_count':len(changed)}

"""Read-only SQLite state comparisons; raw row values are never exported."""
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing

OWN_SEQUENCES=frozenset(('farm_preflight_verdicts','farm_stage_metrics'))


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
            if name.startswith('farm_'):
                pk=[index for _,index in sorted((row[5],index) for index,row in enumerate(info) if row[5])]
                if not pk:
                    raise ValueError('Farm table requires a stable primary key')
                row_map={}
                for row,values in zip(data,encoded):
                    key=_digest([values[index] for index in pk])
                    owner=_digest(_value(row[columns.index('run_id')])) if 'run_id' in columns else None
                    stable=[value for column,value in zip(columns,values) if column not in ('finished_at','decision')]
                    row_map[key]={'hash':_digest(values),'owner':owner,'stable_hash':_digest(stable)}
                item['rows']=row_map
            tables[name]=item
    return {'file_hash':file_hash(path),'schema_hash':_digest(schema),'tables':tables,'sqlite_sequence':sequence}


def compare(before,after,current_run_id):
    owner=_digest(_value(current_run_id))
    violations=[]
    nonfarm={}
    farm_counts={}
    for name in sorted(set(before['tables'])|set(after['tables'])):
        left=before['tables'].get(name)
        right=after['tables'].get(name)
        if not name.startswith('farm_'):
            nonfarm[name]={'before':left['hash'] if left else None,'after':right['hash'] if right else None}
            continue
        farm_counts[name]={'before':left['count'] if left else 0,'after':right['count'] if right else 0}
        if left is None or right is None:
            violations.append({'table':name,'kind':'table_set_changed'})
            continue
        for key,row in left['rows'].items():
            observed=right['rows'].get(key)
            if observed is None:
                violations.append({'table':name,'kind':'row_deleted'})
            elif observed['hash']!=row['hash']:
                allowed=(name=='farm_preflight_runs' and row['owner']==owner
                         and observed['owner']==owner and observed['stable_hash']==row['stable_hash'])
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
        if name in OWN_SEQUENCES and b is not None and b>=(a or 0):
            expected.append(change)
        else:
            unexpected.append(change)
    sequence={'expected_farm_advances':expected,'unexpected_changes':unexpected,'absent':old is None and new is None}
    schema_unchanged=before['schema_hash']==after['schema_hash']
    nonfarm_unchanged=all(row['before']==row['after'] for row in nonfarm.values())
    passed=schema_unchanged and nonfarm_unchanged and not violations and not unexpected
    return {'status':'PASS' if passed else 'FAIL','schema_unchanged':schema_unchanged,
            'non_farm_tables_unchanged':nonfarm_unchanged,'non_farm_table_hashes':nonfarm,
            'farm_counts':farm_counts,'farm_violations':violations,
            'sqlite_sequence_advance':sequence,'sqlite_sequence_absent':sequence['absent'],
            'full_hash_before':before['file_hash'],'full_hash_after':after['file_hash'],
            'full_hash_changed':before['file_hash']!=after['file_hash']}


def compare_protected(before,after):
    changed=sorted(name for name in set(before)|set(after) if before.get(name)!=after.get(name))
    return {'status':'FAIL' if changed else 'PASS','changed_count':len(changed)}

"""Trazas estructuradas locales sin cuerpos, comandos ni secretos."""
from contextlib import contextmanager,closing
from contextvars import ContextVar,copy_context
from datetime import datetime,timedelta,timezone
from functools import wraps
import hashlib
import inspect
import json
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
import traceback
import uuid
from . import __version__

DB_PATH=Path(__file__).resolve().parent.parent/'data'/'traces.sqlite3'
_CONTEXT=ContextVar('granjita_trace',default=None)
_LOCK=threading.RLock()
_READY=set()
_FAILURE=None
_WRITES=0
_DROPPED=0
SAFE={'app_source','package','device_id','hardware_serial','transport','port','task_id','snapshot_id','target','index','status','outcome','count','error_class','category','fingerprint','frames','response_bytes','response_type','method','route','command_kind','field','state','moved','can_scroll_more','size','source','saved','failed','available','version','remote_exit_code','http_status','error_code','api_code'}


def stamp():return datetime.now(timezone(timedelta(hours=-6))).isoformat(timespec='milliseconds')


def database():
    path=Path(DB_PATH);path.parent.mkdir(parents=True,exist_ok=True)
    initialize=str(path) not in _READY or not path.exists()
    db=sqlite3.connect(path,timeout=1)
    db.row_factory=sqlite3.Row
    key=str(path)
    if initialize:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''CREATE TABLE IF NOT EXISTS trace_events(id INTEGER PRIMARY KEY,at TEXT NOT NULL,
            run_id TEXT NOT NULL,span_id TEXT NOT NULL,parent_id TEXT,task_id TEXT,process TEXT NOT NULL,
            phase TEXT NOT NULL,status TEXT NOT NULL,duration_ms REAL,source TEXT NOT NULL,metadata TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS traces_run ON trace_events(run_id,id);
            CREATE INDEX IF NOT EXISTS traces_task ON trace_events(task_id,id);
            CREATE TABLE IF NOT EXISTS trace_feedback(id INTEGER PRIMARY KEY,at TEXT NOT NULL,run_id TEXT NOT NULL,
                note TEXT NOT NULL,expected TEXT NOT NULL);''')
        _READY.add(key)
    return db


def clean(data):
    output={}
    for key,value in data.items():
        if key not in SAFE or value is None:continue
        if isinstance(value,(bool,int,float)):output[key]=value
        elif isinstance(value,str):
            # Los únicos textos aceptados son etiquetas o identificadores, nunca salidas libres.
            if re.fullmatch(r'[A-Za-z0-9_ .:/<>@,\-áéíóúÁÉÍÓÚñÑ]{0,400}',value):output[key]=value
    return output


def emit(process,phase,status='info',duration_ms=None,**metadata):
    global _FAILURE,_WRITES,_DROPPED
    context=_CONTEXT.get() or dict(run_id=str(uuid.uuid4()),span_id=str(uuid.uuid4()),parent_id=None,task_id=metadata.get('task_id'))
    source='test' if 'unittest.__main__' in sys.modules or '-m unittest' in str(sys.argv[0]).lower() or '/unittest/' in str(sys.argv[0]).replace('\\','/').lower() else 'app'
    try:
        with _LOCK:
            db=database()
            try:
                with db:
                    db.execute('INSERT INTO trace_events(at,run_id,span_id,parent_id,task_id,process,phase,status,duration_ms,source,metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (stamp(),context['run_id'],context['span_id'],context['parent_id'],context.get('task_id'),process,phase,status,duration_ms,source,json.dumps(clean(dict(context.get('labels',{}),**dict(metadata,version=__version__))),ensure_ascii=False,sort_keys=True)))
                    _WRITES+=1
                    if _WRITES%1000==0:
                        cutoff=(datetime.now(timezone(timedelta(hours=-6)))-timedelta(days=30)).isoformat(timespec='milliseconds')
                        db.execute('DELETE FROM trace_events WHERE at<?',(cutoff,))
                        db.execute('DELETE FROM trace_events WHERE id < (SELECT id FROM trace_events ORDER BY id DESC LIMIT 1 OFFSET 99999)')
            finally:db.close()
        _FAILURE=None
        return context['run_id']
    except Exception as exc:
        # El diagnóstico nunca cambia el resultado de una operación ni intenta repetirla.
        _FAILURE=type(exc).__name__
        _DROPPED+=1
        return None


def failure_info(exc):
    message=str(exc).lower()
    category='timeout' if 'time' in message or 'tiempo' in message else 'identity' if 'serial' in message or 'identidad' in message else 'authorization' if any(w in message for w in ('permission','autoriz','denied')) else 'connection' if any(w in message for w in ('connection','connect','not found','conexi')) else 'other'
    frames=' / '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(exc.__traceback__)[-6:])
    fingerprint=hashlib.sha256((type(exc).__name__+'|'+category+'|'+frames).encode()).hexdigest()[:16]
    return dict(error_class=type(exc).__name__,category=category,frames=frames,fingerprint=fingerprint)


@contextmanager
def span(process,**metadata):
    parent=_CONTEXT.get()
    context=dict(run_id=parent['run_id'] if parent else str(uuid.uuid4()),span_id=str(uuid.uuid4()),parent_id=parent['span_id'] if parent else None,task_id=metadata.get('task_id') or (parent.get('task_id') if parent else None))
    context['labels']=dict(parent.get('labels',{}) if parent else {})
    context['labels'].update({k:v for k,v in metadata.items() if v is not None})
    token=_CONTEXT.set(context);started=time.perf_counter()
    emit(process,'start',**metadata)
    try:
        yield context['run_id']
    except Exception as exc:
        emit(process,'end','error',(time.perf_counter()-started)*1000,**dict(metadata,**failure_info(exc)))
        raise
    else:emit(process,'end','ok',(time.perf_counter()-started)*1000,**metadata)
    finally:_CONTEXT.reset(token)


def traced(process):
    def decorate(function):
        signature=inspect.signature(function)
        @wraps(function)
        def run(*args,**kwargs):
            arguments=signature.bind_partial(*args,**kwargs).arguments
            metadata={k:arguments[k] for k in ('task_id','port','target') if k in arguments}
            row=arguments.get('row') or arguments.get('device')
            instance=arguments.get('self')
            if row is None and instance is not None:row=getattr(instance,'row',None)
            if instance is not None and hasattr(instance,'port'):metadata['port']=instance.port
            if isinstance(row,dict):metadata.update({k:row.get(k) for k in ('device_id','hardware_serial','port')});metadata['device_id']=row.get('id');metadata['transport']=row.get('serial')
            if 'serial' in arguments:metadata['transport']=arguments['serial']
            if 'command' in arguments:
                first=arguments['command'].split()[0] if arguments['command'].split() else ''
                metadata['command_kind']=first if first in ('getprop','settings','dumpsys','pm','id','base64','sha256sum','cat','monkey') else 'managed-script'
            if 'adb' in arguments:metadata['port']=getattr(arguments['adb'],'port',None)
            with span(process,**metadata):
                result=function(*args,**kwargs)
                if isinstance(result,list):emit(process,'result',count=len(result))
                if isinstance(result,dict) and 'status' in result:emit(process,'result',state=result['status'],hardware_serial=result.get('hardware_serial'))
                if isinstance(result,dict) and 'devices' in result:emit(process,'result',count=len(result['devices']),available=sum(s.get('status')=='ADB responde' for s in result.get('servers',[])))
                if isinstance(result,tuple) and len(result)==2 and isinstance(result[0],str):emit(process,'result',status='warning' if result[1]=='Parcial' else 'info',snapshot_id=result[0],state=result[1])
                if isinstance(result,str):emit(process,'response',response_bytes=len(result.encode('utf-8')))
                return result
        return run
    return decorate


def context_map(pool,function,values):
    context=copy_context()
    return pool.map(lambda value:context.copy().run(function,value),values)


def health():return dict(last_error=_FAILURE,dropped=_DROPPED)


def read_events(run_id=None,limit=500,include_tests=False,task_id=None):
    with _LOCK:
        db=database()
        try:
            where=[];args=[]
            if run_id:where.append('run_id=?');args.append(run_id)
            if task_id:where.append('task_id=?');args.append(task_id)
            if not include_tests:where.append("source='app'")
            sql='SELECT * FROM trace_events'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY id DESC LIMIT ?'
            rows=[dict(r) for r in db.execute(sql,(*args,min(max(limit,1),10000)))]
        finally:db.close()
    for row in rows:row['metadata']=json.loads(row['metadata'])
    return rows


def add_feedback(run_id,note,expected):
    if not note.strip() or len(note)>2000 or len(expected)>2000:raise ValueError('Nota obligatoria de hasta 2000 caracteres.')
    with _LOCK:
        db=database()
        try:
            if not db.execute('SELECT 1 FROM trace_events WHERE run_id=?',(run_id,)).fetchone():raise ValueError('Traza no encontrada.')
            with db:db.execute('INSERT INTO trace_feedback(at,run_id,note,expected) VALUES (?,?,?,?)',(stamp(),run_id,note.strip(),expected.strip()))
        finally:db.close()


def feedback(run_id):
    with _LOCK:
        db=database()
        try:return [dict(r) for r in db.execute('SELECT * FROM trace_feedback WHERE run_id=? ORDER BY id',(run_id,))]
        finally:db.close()


def clear_traces():
    """Archiva SQLite y limpia solo eventos anteriores al corte, preservando auditoría."""
    global _DROPPED,_FAILURE
    import uuid
    # No alterar tareas mediante JobStore: su constructor recupera estados.
    jobs_path=Path(DB_PATH).parent/'automation.sqlite3'
    if jobs_path.exists():
        with closing(sqlite3.connect(jobs_path.resolve().as_uri()+'?mode=ro',uri=True)) as jobs:
            if jobs.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('Ejecutando','En cola','Programado')").fetchone()[0]:
                raise ValueError('Espera a que termine o cancela el lote antes de limpiar logs.')
    with _LOCK:
        db=database()
        try:
            cutoff=db.execute('SELECT COALESCE(MAX(id),0) FROM trace_events').fetchone()[0]
            folder=Path(DB_PATH).parent/'backups'
            folder.mkdir(parents=True,exist_ok=True)
            backup=folder/('traces-antes-limpiar-'+uuid.uuid4().hex+'.sqlite3')
            with closing(sqlite3.connect(backup)) as target:
                db.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise RuntimeError('El respaldo de trazas no pasó la verificación; no se limpiaron logs.')
            with db:
                removed=db.execute('DELETE FROM trace_events WHERE id<=?',(cutoff,)).rowcount
            result=dict(at=stamp(),removed=removed,cutoff_id=cutoff,backup=str(backup))
            # Metadatos de limpieza separados: el visor puede quedar en cero eventos.
            with (Path(DB_PATH).parent/'log-cleanups.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(result,ensure_ascii=False)+'\n')
            _DROPPED=0;_FAILURE=None
            return result
        finally:db.close()

"""Métricas QA sin contenido del feed ni credenciales; conexiones cortas y WAL."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import logging
import math
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

DEFAULT_DB = Path(__file__).resolve().parents[1]/'sessions/telemetry_qa.db'
logger = logging.getLogger('qa.telemetry')


@contextmanager
def _conexion(path):
    con = sqlite3.connect(Path(path), timeout=1)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA busy_timeout=1000')
        with con:
            yield con
    finally:
        con.close()


def inicializar_db_telemetria(db_path=DEFAULT_DB):
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _conexion(path) as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript('''CREATE TABLE IF NOT EXISTS metricas_rendimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_utc TEXT NOT NULL,
            actualizada_utc TEXT NOT NULL, run_id TEXT NOT NULL, cycle_id TEXT NOT NULL,
            account_id TEXT NOT NULL, ciclo_numero INTEGER NOT NULL CHECK(ciclo_numero>0),
            proxy_ip TEXT NOT NULL DEFAULT 'REDACTED', proxy_ref TEXT, geo_provider TEXT NOT NULL,
            latencia_dom_ms REAL, espera_dom_visible_ms REAL, latencia_openai_ms REAL,
            latencia_admision_ms REAL, latencia_ia_total_ms REAL,
            tiempo_retencion_programado_seg REAL, tiempo_retencion_ejecutado_seg REAL,
            estado_retencion TEXT, estado_ciclo TEXT NOT NULL, fase TEXT NOT NULL,
            duracion_total_ms REAL, error_log TEXT, swipe_estado TEXT,
            UNIQUE(run_id,account_id,cycle_id));
        ''')
        columns = {row['name'] for row in con.execute('PRAGMA table_info(metricas_rendimiento)')}
        for name, kind in (('actualizada_utc',"TEXT NOT NULL DEFAULT ''"),('run_id',"TEXT NOT NULL DEFAULT 'legacy'"),
                ('cycle_id',"TEXT NOT NULL DEFAULT ''"),('proxy_ref','TEXT'),('fase',"TEXT NOT NULL DEFAULT 'legacy'"),
                ('espera_dom_visible_ms','REAL'),('tiempo_retencion_programado_seg','REAL'),
                ('duracion_total_ms','REAL'),('swipe_estado','TEXT')):
            if name not in columns:
                con.execute(f'ALTER TABLE metricas_rendimiento ADD COLUMN {name} {kind}')
        for name in ('latencia_admision_ms','latencia_ia_total_ms'):
            if name not in columns:
                # La tabla recién creada ya tiene las columnas.
                current={row['name'] for row in con.execute('PRAGMA table_info(metricas_rendimiento)')}
                if name not in current:
                    con.execute(f'ALTER TABLE metricas_rendimiento ADD COLUMN {name} REAL')
        con.execute("UPDATE metricas_rendimiento SET cycle_id='legacy-'||id WHERE cycle_id=''")
        con.execute("UPDATE metricas_rendimiento SET actualizada_utc=timestamp_utc WHERE actualizada_utc=''")
        con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_qa_metrics_cycle ON metricas_rendimiento(run_id,account_id,cycle_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_qa_metrics_run ON metricas_rendimiento(run_id,account_id,ciclo_numero)')
        con.execute('''CREATE TABLE IF NOT EXISTS eventos_poc (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_utc TEXT NOT NULL,
            run_id TEXT NOT NULL, account_id TEXT NOT NULL, evento TEXT NOT NULL,
            estado TEXT NOT NULL, error_tipo TEXT)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_poc_events_run ON eventos_poc(run_id,id)')
        con.execute('''CREATE TABLE IF NOT EXISTS eventos_red_qa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp_utc TEXT NOT NULL,
            run_id TEXT NOT NULL,account_id TEXT NOT NULL,operation_id TEXT NOT NULL,
            accion TEXT NOT NULL,fase TEXT NOT NULL,estado TEXT NOT NULL,
            evento TEXT NOT NULL,
            modo TEXT NOT NULL DEFAULT 'mobile_api',
            latencia_ms REAL,latencia_total_ms REAL,http_status INTEGER,cambio_ip INTEGER,
            proxy_ref TEXT,ip_anterior_ref TEXT,ip_nueva_ref TEXT,error_codigo TEXT)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_qa_network_run ON eventos_red_qa(run_id,operation_id,id)')
        if 'evento' not in {row['name'] for row in con.execute('PRAGMA table_info(eventos_red_qa)')}:
            con.execute("ALTER TABLE eventos_red_qa ADD COLUMN evento TEXT NOT NULL DEFAULT ''")
        if 'modo' not in {row['name'] for row in con.execute('PRAGMA table_info(eventos_red_qa)')}:
            con.execute("ALTER TABLE eventos_red_qa ADD COLUMN modo TEXT NOT NULL DEFAULT 'mobile_api'")
        con.execute('''CREATE TABLE IF NOT EXISTS eventos_ia_qa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp_utc TEXT NOT NULL,
            run_id TEXT NOT NULL,account_id TEXT NOT NULL,cycle_id TEXT,
            request_id TEXT NOT NULL UNIQUE,modelo TEXT NOT NULL,estado TEXT NOT NULL,
            latencia_ms REAL,latencia_total_ms REAL,api_llamada INTEGER NOT NULL,error_codigo TEXT)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_qa_ai_run ON eventos_ia_qa(run_id,account_id,id)')
    return path


async def inicializar_db_telemetria_async(db_path=DEFAULT_DB):
    return await asyncio.to_thread(inicializar_db_telemetria, db_path)


def _metric(value):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError('Métrica debe ser finita y no negativa')
    return number


def registrar_metrica_ciclo(account_id, ciclo_numero, proxy_ip=None, geo_provider='UNKNOWN',
        latencia_dom=None, latencia_openai=None, tiempo_retencion=None, estado_retencion=None,
        estado_ciclo='running', error_log=None, db_path=DEFAULT_DB, *, run_id=None, cycle_id=None,
        fase='inicio', espera_dom_visible_ms=None, tiempo_retencion_programado_seg=None,
        duracion_total_ms=None, swipe_estado=None, latencia_admision_ms=None, latencia_ia_total_ms=None):
    from core.browser import validar_account_id
    validar_account_id(account_id)
    if isinstance(ciclo_numero,bool) or not isinstance(ciclo_numero,int) or ciclo_numero < 1:
        raise ValueError('Número de ciclo inválido')
    if estado_ciclo not in ('running','passed','failed','cancelled'):
        raise ValueError('Estado de ciclo inválido')
    if geo_provider not in ('UNKNOWN','FAILED_ALL','ipapi.co','ip-api.com','ipinfo.io'):
        geo_provider = 'UNKNOWN'
    # Solo códigos de error, nunca mensajes de excepción potencialmente sensibles.
    error_type = type(error_log).__name__ if isinstance(error_log,BaseException) else (
        error_log if error_log in ('TimeoutError','Error','ValueError','TypeError','OperationalError',
            'OSError','CancelledError','InterruptedError','APIError','APIConnectionError','APITimeoutError',
            'RateLimitError','AuthenticationError','ValidationError') else 'Error' if error_log else None)
    proxy_ref = hashlib.sha256(str(proxy_ip).encode()).hexdigest() if proxy_ip else None
    now = datetime.now(timezone.utc).isoformat()
    keys = (run_id or uuid4().hex, account_id, cycle_id or str(ciclo_numero))
    values = (now,now,keys[0],keys[2],account_id,ciclo_numero,'REDACTED',proxy_ref,geo_provider,
        _metric(latencia_dom),_metric(espera_dom_visible_ms),_metric(latencia_openai),
        _metric(tiempo_retencion_programado_seg),_metric(tiempo_retencion),estado_retencion,
        estado_ciclo,fase,_metric(duracion_total_ms),error_type,swipe_estado,
        _metric(latencia_admision_ms),_metric(latencia_ia_total_ms))
    with _conexion(db_path) as con:
        con.execute('''INSERT INTO metricas_rendimiento (
            timestamp_utc,actualizada_utc,run_id,cycle_id,account_id,ciclo_numero,proxy_ip,proxy_ref,geo_provider,
            latencia_dom_ms,espera_dom_visible_ms,latencia_openai_ms,tiempo_retencion_programado_seg,
            tiempo_retencion_ejecutado_seg,estado_retencion,estado_ciclo,fase,duracion_total_ms,error_log,swipe_estado,
            latencia_admision_ms,latencia_ia_total_ms)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id,account_id,cycle_id) DO UPDATE SET
            actualizada_utc=excluded.actualizada_utc,latencia_dom_ms=excluded.latencia_dom_ms,
            espera_dom_visible_ms=excluded.espera_dom_visible_ms,latencia_openai_ms=excluded.latencia_openai_ms,
            tiempo_retencion_programado_seg=excluded.tiempo_retencion_programado_seg,
            tiempo_retencion_ejecutado_seg=excluded.tiempo_retencion_ejecutado_seg,
            estado_retencion=excluded.estado_retencion,estado_ciclo=excluded.estado_ciclo,fase=excluded.fase,
            duracion_total_ms=excluded.duracion_total_ms,error_log=excluded.error_log,swipe_estado=excluded.swipe_estado,
            latencia_admision_ms=excluded.latencia_admision_ms,latencia_ia_total_ms=excluded.latencia_ia_total_ms''', values)
    logger.info('Métrica QA persistida: ciclo=%s estado=%s fase=%s',ciclo_numero,estado_ciclo,fase)


async def registrar_metrica_ciclo_async(*args, **kwargs):
    await asyncio.to_thread(registrar_metrica_ciclo, *args, **kwargs)


def listar_metricas(db_path=DEFAULT_DB, *, run_id=None, limit=100):
    if not isinstance(limit,int) or not 1 <= limit <= 1000:
        raise ValueError('Límite de lectura inválido')
    with _conexion(db_path) as con:
        rows = con.execute('SELECT * FROM metricas_rendimiento '+('WHERE run_id=? ' if run_id else '')+
            'ORDER BY id DESC LIMIT ?', (run_id,limit) if run_id else (limit,)).fetchall()
    return [dict(row) for row in rows]


def registrar_evento_poc(run_id, account_id, evento, estado, *, error=None, db_path=DEFAULT_DB):
    from core.browser import validar_account_id
    validar_account_id(account_id)
    if evento not in ('admision','navegador_listo','esperando_login','continuacion_solicitada',
                      'login_verificado','parada_solicitada','prueba_fallida','cierre_exitoso','cierre_fallido'):
        raise ValueError('Evento POC inválido')
    if estado not in ('iniciado','en_espera','completado','cancelado','fallido'):
        raise ValueError('Estado POC inválido')
    error_type = type(error).__name__ if isinstance(error,BaseException) else None
    with _conexion(db_path) as con:
        con.execute('INSERT INTO eventos_poc(timestamp_utc,run_id,account_id,evento,estado,error_tipo) VALUES (?,?,?,?,?,?)',
                    (datetime.now(timezone.utc).isoformat(),run_id,account_id,evento,estado,error_type))
    logger.info('Evento POC persistido: evento=%s estado=%s',evento,estado)


async def registrar_evento_poc_async(*args, **kwargs):
    await asyncio.to_thread(registrar_evento_poc, *args, **kwargs)


def registrar_evento_red(run_id,account_id,operation_id,accion,fase,estado,*,db_path=DEFAULT_DB,
        latencia_ms=None,latencia_total_ms=None,http_status=None,cambio_ip=None,
        proxy_endpoint=None,ip_anterior=None,ip_nueva=None,error_codigo=None,modo='mobile_api'):
    from core.browser import validar_account_id
    validar_account_id(account_id)
    if accion not in ('rotacion','validacion') or estado not in ('iniciado','solicitado','verificado','fallido','cancelado'):
        raise ValueError('Evento de red inválido')
    if modo not in ('mobile_api','rotating_residential'):
        raise ValueError('Modalidad de proxy inválida')
    if error_codigo is not None and not re.fullmatch('[a-z0-9_]{1,64}',error_codigo):
        raise ValueError('Código de error de red inválido')
    reference=lambda value:hashlib.sha256(str(value).encode()).hexdigest() if value else None
    label = ('Conexión Segura Establecida' if accion=='validacion' and estado=='verificado' else
             'Fallo de Validación de Red' if accion=='validacion' and estado=='fallido' else
             'Rotación Verificada' if accion=='rotacion' and estado=='verificado' else
             'Fallo de Rotación' if estado=='fallido' else
             'Operación de Red Cancelada' if estado=='cancelado' else 'Operación de Red en Curso')
    with _conexion(db_path) as con:
        con.execute('''INSERT INTO eventos_red_qa(timestamp_utc,run_id,account_id,operation_id,accion,fase,estado,evento,
            latencia_ms,latencia_total_ms,http_status,cambio_ip,proxy_ref,ip_anterior_ref,ip_nueva_ref,error_codigo,modo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (datetime.now(timezone.utc).isoformat(timespec='microseconds'),run_id,account_id,operation_id,accion,fase,estado,label,
             _metric(latencia_ms),_metric(latencia_total_ms),http_status,None if cambio_ip is None else int(cambio_ip),
             reference(proxy_endpoint),reference(ip_anterior),reference(ip_nueva),error_codigo,modo))
    logger.info('%s: fase=%s estado=%s código=%s',label,fase,estado,error_codigo or 'none')


async def registrar_evento_red_async(*args, **kwargs):
    await asyncio.to_thread(registrar_evento_red,*args,**kwargs)


def ultima_ip_validada_ref(account_id,proxy_endpoint,*,db_path=DEFAULT_DB):
    reference=hashlib.sha256(proxy_endpoint.encode()).hexdigest()
    with _conexion(db_path) as con:
        row=con.execute('''SELECT ip_nueva_ref FROM eventos_red_qa WHERE account_id=? AND proxy_ref=?
            AND modo='mobile_api' AND accion='validacion' AND estado='verificado' AND fase IN ('preflight','post_rotacion','navegador')
            ORDER BY id DESC LIMIT 1''',(account_id,reference)).fetchone()
    return row['ip_nueva_ref'] if row else None


def registrar_evento_ia(run_id,account_id,request_id,estado,*,db_path=DEFAULT_DB,cycle_id=None,
        latencia_ms=None,latencia_total_ms=None,api_llamada=False,error_codigo=None,modelo='gpt-4o-mini'):
    from core.browser import validar_account_id
    validar_account_id(account_id)
    if modelo not in ('gpt-4o-mini','gpt-4o'):
        raise ValueError('Modelo de telemetría inválido')
    if estado not in ('éxito','fallo_api','omitido','cancelado'):
        raise ValueError('Estado IA inválido')
    if error_codigo is not None and not re.fullmatch('[a-z0-9_]{1,64}',error_codigo):
        raise ValueError('Código IA inválido')
    with _conexion(db_path) as con:
        con.execute('''INSERT INTO eventos_ia_qa(timestamp_utc,run_id,account_id,cycle_id,request_id,
            modelo,estado,latencia_ms,latencia_total_ms,api_llamada,error_codigo) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (datetime.now(timezone.utc).isoformat(timespec='microseconds'),run_id,account_id,cycle_id,request_id,
             modelo,estado,_metric(latencia_ms),_metric(latencia_total_ms),int(bool(api_llamada)),error_codigo))
    logger.info('IA QA persistida: estado=%s latencia_ms=%s llamada=%s',estado,latencia_ms,bool(api_llamada))


async def registrar_evento_ia_async(*args,**kwargs):
    await asyncio.to_thread(registrar_evento_ia,*args,**kwargs)

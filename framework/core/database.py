"""SQLite local: conexiones cortas por operación, WAL y claves foráneas."""
import json
import os
import sqlite3
import ipaddress
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TZ = timezone(timedelta(hours=-6),name='America/Guatemala')


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


class Database:
    """No comparte conexiones entre hilos/procesos; comparte únicamente la ruta."""
    def __init__(self,path=None):
        self.path = Path(path or os.getenv('TIKTOK_DB_PATH') or ROOT/'data/granja_tiktok.db').resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.conexion() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS dispositivos (
                    id_adb TEXT PRIMARY KEY, alias TEXT, proxy TEXT,
                    estado TEXT NOT NULL DEFAULT 'Espera', ultima_conexion TIMESTAMP,
                    conectado BOOLEAN NOT NULL DEFAULT 0 CHECK(conectado IN (0,1)),
                    ultimo_heartbeat TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS interacciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_adb TEXT NOT NULL REFERENCES dispositivos(id_adb),
                    timestamp TIMESTAMP NOT NULL, descripcion_video TEXT NOT NULL,
                    decision_ia TEXT NOT NULL CHECK(json_valid(decision_ia)),
                    dio_like BOOLEAN NOT NULL DEFAULT 0 CHECK(dio_like IN (0,1)),
                    comento BOOLEAN NOT NULL DEFAULT 0 CHECK(comento IN (0,1)),
                    comentario_texto TEXT NOT NULL DEFAULT '', latencia_ms INTEGER NOT NULL,
                    run_id TEXT NOT NULL, ciclo INTEGER NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    ia_valida BOOLEAN NOT NULL DEFAULT 1 CHECK(ia_valida IN (0,1)),
                    error TEXT, UNIQUE(run_id,id_adb,ciclo)
                );
                CREATE INDEX IF NOT EXISTS idx_interacciones_fecha ON interacciones(timestamp DESC,id DESC);
                CREATE INDEX IF NOT EXISTS idx_interacciones_device ON interacciones(id_adb,timestamp DESC);
            ''')
            con.execute('BEGIN IMMEDIATE')
            columns={row['name'] for row in con.execute('PRAGMA table_info(dispositivos)')}
            for name,kind in (('adb_host','TEXT'),('adb_port','INTEGER'),('adb_origins','TEXT'),('adb_transport','TEXT'),
                              ('inventario_estado','TEXT'),('cuenta_estado',"TEXT NOT NULL DEFAULT 'sin_verificar'"),
                              ('cuenta_motivo','TEXT'),('cuenta_verificada_en','TIMESTAMP')):
                if name not in columns:
                    con.execute(f'ALTER TABLE dispositivos ADD COLUMN {name} {kind}')
            interaction_columns={row['name'] for row in con.execute('PRAGMA table_info(interacciones)')}
            if 'legacy_device_id' not in interaction_columns:
                con.execute('ALTER TABLE interacciones ADD COLUMN legacy_device_id TEXT')
            con.execute('''CREATE TABLE IF NOT EXISTS servidores_adb (
                host TEXT NOT NULL, puerto INTEGER NOT NULL, ultima_consulta TIMESTAMP,
                estado TEXT NOT NULL, error TEXT, PRIMARY KEY(host,puerto))''')
            con.execute('CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY,valor TEXT NOT NULL)')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS proxy_pool (
                    endpoint TEXT PRIMARY KEY,host TEXT NOT NULL,puerto INTEGER NOT NULL,
                    exit_ip TEXT,habilitado INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS proxy_perfiles (
                    account_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL UNIQUE REFERENCES proxy_pool(endpoint));
                CREATE TABLE IF NOT EXISTS auditoria_proxy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT NOT NULL,
                    run_id TEXT NOT NULL,device_id TEXT NOT NULL,endpoint TEXT,
                    etapa TEXT NOT NULL,resultado TEXT NOT NULL,ip_esperada TEXT,ip_observada TEXT,
                    latencia_ms REAL,error_tipo TEXT,alcance TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_auditoria_proxy_run ON auditoria_proxy(run_id,id);
                CREATE TABLE IF NOT EXISTS auditoria_acciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,interaction_id INTEGER NOT NULL REFERENCES interacciones(id),
                    timestamp TEXT NOT NULL,evento TEXT NOT NULL,resultado TEXT NOT NULL,detalle TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS resumenes_carga (
                    run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, detalle TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS api_slots (
                    token TEXT PRIMARY KEY,run_id TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS api_rate (
                    run_id TEXT PRIMARY KEY,next_start REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS proxy_reservas (
                    endpoint TEXT PRIMARY KEY REFERENCES proxy_pool(endpoint),
                    identidad TEXT NOT NULL UNIQUE, id_adb TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL, reservado TIMESTAMP NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'activo');
                CREATE TABLE IF NOT EXISTS alertas (
                    clave TEXT PRIMARY KEY,mensaje TEXT NOT NULL,activa INTEGER NOT NULL,
                    actualizada TIMESTAMP NOT NULL);
                CREATE TABLE IF NOT EXISTS eventos_dispositivo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,id_adb TEXT NOT NULL REFERENCES dispositivos(id_adb),
                    timestamp TIMESTAMP NOT NULL,estado TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ejecuciones_granja (
                    run_id TEXT PRIMARY KEY,tipo TEXT NOT NULL,estado TEXT NOT NULL,
                    subset_json TEXT NOT NULL,inicio TIMESTAMP NOT NULL,fin TIMESTAMP);
                CREATE TABLE IF NOT EXISTS logs_granja (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,
                    id_adb TEXT,timestamp TIMESTAMP NOT NULL,nivel TEXT NOT NULL,mensaje TEXT NOT NULL,
                    detalle TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_logs_run ON logs_granja(run_id,id DESC);
                CREATE TABLE IF NOT EXISTS verificaciones_red (
                    run_id TEXT NOT NULL,id_adb TEXT NOT NULL,ip_externa TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,confirmada INTEGER NOT NULL DEFAULT 0,
                    modo TEXT NOT NULL,error TEXT,PRIMARY KEY(run_id,id_adb));
                CREATE UNIQUE INDEX IF NOT EXISTS idx_smoke_ip_unica
                    ON verificaciones_red(run_id,ip_externa) WHERE confirmada=1 AND modo='smoke';
            ''')
            proxy_columns={row['name'] for row in con.execute('PRAGMA table_info(proxy_pool)')}
            if 'lab_shared_exit' not in proxy_columns:
                con.execute('ALTER TABLE proxy_pool ADD COLUMN lab_shared_exit INTEGER NOT NULL DEFAULT 0')

    @contextmanager
    def conexion(self):
        # Cada llamada usa su propia conexión; check_same_thread=False no es necesario.
        con = sqlite3.connect(self.path,timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA busy_timeout=15000')
            with con:
                yield con
        finally:
            con.close()

    def actualizar_dispositivo(self,id_adb,*,alias=None,proxy=None,estado='Espera',conectado=None):
        if estado not in ('Calentando','Espera','Error','Desconectado',
                          'Espera - Sin Proxy','Carga Lenta - Reintentando','Pendiente Cuenta',
                          'Navegando','Analizando con IA','Reconectando','Recuperando','Cuarentena'):
            raise ValueError('Estado de dispositivo no válido')
        now = ahora()
        with self.conexion() as con:
            con.execute('''INSERT INTO dispositivos
                (id_adb,alias,proxy,estado,conectado,ultima_conexion,ultimo_heartbeat)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(id_adb) DO UPDATE SET
                alias=COALESCE(excluded.alias,dispositivos.alias),
                proxy=COALESCE(excluded.proxy,dispositivos.proxy),
                estado=CASE WHEN dispositivos.cuenta_estado='pendiente' THEN 'Pendiente Cuenta' ELSE excluded.estado END,
                conectado=COALESCE(?,dispositivos.conectado),
                ultima_conexion=COALESCE(excluded.ultima_conexion,dispositivos.ultima_conexion),
                ultimo_heartbeat=excluded.ultimo_heartbeat''',
                (id_adb,alias,proxy,estado,int(bool(conectado)),now if conectado else None,
                 now,None if conectado is None else int(conectado)))
            if estado=='Pendiente Cuenta':
                con.execute("UPDATE dispositivos SET cuenta_estado='pendiente',estado='Pendiente Cuenta' WHERE id_adb=?",(id_adb,))
            if estado=='Carga Lenta - Reintentando':
                con.execute('INSERT INTO eventos_dispositivo(id_adb,timestamp,estado) VALUES (?,?,?)',
                            (id_adb,now,estado))

    def sincronizar_inventario(self,devices):
        """devices: mapping UDID -> estado ADB; llamar solo tras lectura ADB válida."""
        now=ahora()
        with self.conexion() as con:
            con.execute('UPDATE dispositivos SET conectado=0')
            for udid,status in devices.items():
                connected=status=='device'
                con.execute('''INSERT INTO dispositivos(id_adb,estado,conectado,ultima_conexion)
                    VALUES (?,?,?,?) ON CONFLICT(id_adb) DO UPDATE SET
                    conectado=excluded.conectado,
                    ultima_conexion=COALESCE(excluded.ultima_conexion,dispositivos.ultima_conexion),
                    estado=CASE WHEN dispositivos.cuenta_estado='pendiente' THEN 'Pendiente Cuenta'
                        WHEN excluded.conectado=0 THEN 'Error'
                        WHEN dispositivos.estado='Desconectado' THEN 'Espera'
                        ELSE dispositivos.estado END''',
                    (udid,'Espera' if connected else 'Error',int(connected),now if connected else None))
            # Dispositivos ausentes del inventario completo, sin inventar placas.
            for row in con.execute('SELECT id_adb FROM dispositivos').fetchall():
                if row['id_adb'] not in devices:
                    con.execute("UPDATE dispositivos SET estado=CASE WHEN cuenta_estado='pendiente' THEN 'Pendiente Cuenta' ELSE 'Desconectado' END WHERE id_adb=?",(row['id_adb'],))

    def dispositivos(self):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM dispositivos ORDER BY id_adb')]

    def marcar_latido(self,id_adb):
        with self.conexion() as con:
            con.execute('UPDATE dispositivos SET ultimo_heartbeat=? WHERE id_adb=?',(ahora(),id_adb))

    def sincronizar_pool(self,snapshot):
        now=ahora()
        successful={(s.host,s.port) for s in snapshot.successful}
        identities={serial:self.identidad_agx(serial)
                    for serial,route in snapshot.devices.items() if route.hardware_serial}
        aliases={serial:identity.get('alias') or
                 (f'AGX · {serial}' if identity.get('canonical_id') else f'Nueva · {serial}')
                 for serial,identity in identities.items()}
        with self.conexion() as con:
            for server in snapshot.successful:
                con.execute('''INSERT INTO servidores_adb VALUES (?,?,?,'disponible',NULL)
                    ON CONFLICT(host,puerto) DO UPDATE SET ultima_consulta=excluded.ultima_consulta,
                    estado=excluded.estado,error=NULL''',(server.host,server.port,now))
            for key,error in snapshot.errors.items():
                # Las claves se construyen con ADBServer.key; soportan hosts IPv6.
                host,port=key.rsplit(':',1)
                con.execute('''INSERT INTO servidores_adb VALUES (?,?,?,'error',?)
                    ON CONFLICT(host,puerto) DO UPDATE SET ultima_consulta=excluded.ultima_consulta,
                    estado='error',error=excluded.error''',(host.strip('[]'),int(port),now,error))
            for serial,route in snapshot.devices.items():
                connected=route.status=='device'
                origins=json.dumps([{'host':s.host,'port':s.port} for s in route.origins])
                con.execute('''INSERT INTO dispositivos
                    (id_adb,estado,conectado,ultima_conexion,adb_host,adb_port,adb_origins,inventario_estado,alias,adb_transport)
                    VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id_adb) DO UPDATE SET
                    alias=CASE WHEN COALESCE(dispositivos.alias,'')='' THEN excluded.alias ELSE dispositivos.alias END,
                    conectado=excluded.conectado,
                    ultima_conexion=COALESCE(excluded.ultima_conexion,dispositivos.ultima_conexion),
                    adb_host=excluded.adb_host,adb_port=excluded.adb_port,
                    adb_transport=excluded.adb_transport,
                    adb_origins=excluded.adb_origins,inventario_estado=excluded.inventario_estado,
                    estado=CASE WHEN dispositivos.cuenta_estado='pendiente' THEN 'Pendiente Cuenta'
                        WHEN excluded.conectado=0 THEN 'Error'
                        WHEN dispositivos.estado='Desconectado' OR dispositivos.inventario_estado='servidor_no_disponible'
                        THEN 'Espera' ELSE dispositivos.estado END''',
                    (serial,'Espera' if connected else 'Error',int(connected),now if connected else None,
                     route.server.host,route.server.port,origins,route.status,aliases.get(serial),route.serial))
            for row in con.execute('SELECT id_adb,adb_host,adb_port FROM dispositivos').fetchall():
                if row['id_adb'] in snapshot.devices:
                    continue
                observed=(row['adb_host'],row['adb_port']) in successful
                # No confundir fallo de servidor con desconexión física confirmada.
                con.execute("UPDATE dispositivos SET conectado=0,estado=CASE WHEN cuenta_estado='pendiente' THEN 'Pendiente Cuenta' ELSE ? END,inventario_estado=? WHERE id_adb=?",
                    ('Desconectado' if observed else 'Error',
                     'ausente' if observed else 'servidor_no_disponible',row['id_adb']))

    def servidores_adb(self):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM servidores_adb ORDER BY host,puerto')]

    def guardar_servidores(self,servers):
        value=json.dumps([{'host':s.host,'port':s.port} for s in servers])
        with self.conexion() as con:
            con.execute('''INSERT INTO configuracion VALUES ('adb_servers',?)
                ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor''',(value,))

    def servidores_configurados(self):
        from core.adb_pool import ADBServer
        with self.conexion() as con:
            row=con.execute("SELECT valor FROM configuracion WHERE clave='adb_servers'").fetchone()
        return [ADBServer(x['host'],x['port']) for x in json.loads(row['valor'])] if row else None

    def alerta(self,clave,mensaje,activa=True):
        with self.conexion() as con:
            con.execute('''INSERT INTO alertas VALUES (?,?,?,?) ON CONFLICT(clave) DO UPDATE SET
                mensaje=excluded.mensaje,activa=excluded.activa,actualizada=excluded.actualizada''',
                (clave,mensaje,int(activa),ahora()))

    def alertas(self):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM alertas WHERE activa=1')]

    def eventos_recientes(self):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM eventos_dispositivo ORDER BY id DESC LIMIT 100')]

    def registrar_auth(self,id_adb,authenticated,reason):
        with self.conexion() as con:
            con.execute("INSERT INTO dispositivos(id_adb) VALUES (?) ON CONFLICT DO NOTHING",(id_adb,))
            con.execute('''UPDATE dispositivos SET cuenta_estado=?,cuenta_motivo=?,cuenta_verificada_en=?,estado=?
                WHERE id_adb=?''',('compatible' if authenticated else 'pendiente',reason,ahora(),
                                  'Calentando' if authenticated else 'Pendiente Cuenta',id_adb))
            if not authenticated:
                con.execute('INSERT INTO eventos_dispositivo(id_adb,timestamp,estado) VALUES (?,?,?)',
                            (id_adb,ahora(),'Pendiente Cuenta'))

    def excluir_ip_sin_cuenta(self,run_id,id_adb):
        with self.conexion() as con:
            con.execute('''UPDATE verificaciones_red SET confirmada=0,
                error='Pendiente Cuenta: placa excluida tras limpieza'
                WHERE run_id=? AND id_adb=? AND EXISTS(SELECT 1 FROM dispositivos d
                    WHERE d.id_adb=verificaciones_red.id_adb AND d.cuenta_estado='pendiente')''',
                (run_id,id_adb))

    def reservas_proxy(self):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM proxy_reservas ORDER BY reservado DESC')]

    def iniciar_ejecucion(self,run_id,subset,smoke=False):
        with self.conexion() as con:
            con.execute('INSERT INTO ejecuciones_granja VALUES (?,?,?,?,?,NULL)',
                (run_id,'smoke' if smoke else 'farm','activo',json.dumps(sorted(subset)),ahora()))

    def finalizar_ejecucion(self,run_id,estado):
        with self.conexion() as con:
            con.execute('UPDATE ejecuciones_granja SET estado=?,fin=? WHERE run_id=?',(estado,ahora(),run_id))

    def guardar_resumen_carga(self,run_id,subset,simulated=False):
        """Duración observada hasta UI lista; no mide reproducción del video."""
        with self.conexion() as con:
            samples=con.execute("SELECT id_adb,detalle FROM logs_granja WHERE run_id=? AND mensaje='Latencia de carga UI' ORDER BY id",(run_id,)).fetchall()
            result=[]
            for serial in sorted(subset):
                values=[json.loads(r['detalle'])['latencia_ms'] for r in samples if r['id_adb']==serial]
                result.append({'id_adb':serial,'muestras':len(values),'media_ms':sum(values)/len(values) if values else None,
                               'max_ms':max(values) if values else None,'simulated':simulated})
            con.execute('INSERT OR REPLACE INTO resumenes_carga VALUES (?,?,?)',
                        (run_id,ahora(),json.dumps(result,allow_nan=False)))

    def resumen_carga(self,run_id):
        with self.conexion() as con:
            row=con.execute('SELECT detalle FROM resumenes_carga WHERE run_id=?',(run_id,)).fetchone()
            return json.loads(row['detalle']) if row else []

    def legado_agx(self):
        """Historial privado; nunca modifica el estado de autenticación en vivo."""
        with self.conexion() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_agx_records'").fetchone():
                return []
            rows=con.execute("SELECT payload FROM legacy_agx_records WHERE source_db='granjita.sqlite3' AND source_table='device_app_observations'").fetchall()
            latest={}
            for row in rows:
                record=json.loads(row['payload'])
                if record['app_id']!='tiktok' or record['scope'] not in ('declaration','technical','screen'):
                    continue
                key=(record['hardware_serial'],record['scope'])
                if key not in latest or record['at']>latest[key]['at']:
                    latest[key]=record
            result=[]
            for (serial,scope),record in sorted(latest.items()):
                payload=json.loads(record['payload'])
                result.append({'serial_historico':serial,'tipo':scope,'fecha_evidencia':record['at'],
                    'cuenta_declarada':payload.get('presence'),
                    'pantalla_observada':payload.get('screen_state'),
                    'paquetes_observados':', '.join(v['package'] for v in payload.get('variants',[]) if 'package' in v),
                    'fuente':'AGX · histórico, requiere revalidación'})
            return result

    def identidad_agx(self,serial):
        """Enlace por serial físico exacto, nunca por IP histórica o por alias."""
        with self.conexion() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_agx_identities'").fetchone():
                return {}
            rows=con.execute('''SELECT canonical_id,alias FROM legacy_agx_identities
                WHERE hardware_serial=? ORDER BY (legacy_id=canonical_id) DESC''',(serial,)).fetchall()
            if len({row['canonical_id'] for row in rows})>1:
                raise ValueError('Serial físico ambiguo en histórico AGX; conciliar antes de ejecutar')
            return dict(rows[0]) if rows else {}

    def log_granja(self,run_id,id_adb,mensaje,*,nivel='INFO',detalle=None):
        with self.conexion() as con:
            con.execute('INSERT INTO logs_granja(run_id,id_adb,timestamp,nivel,mensaje,detalle) VALUES (?,?,?,?,?,?)',
                (run_id,id_adb,ahora(),nivel,mensaje,json.dumps(detalle or {},ensure_ascii=False)))

    def auditar_proxy(self,run_id,device_id,endpoint,etapa,resultado,*,ip_esperada=None,
                      ip_observada=None,latencia_ms=None,error_tipo=None,alcance='Android: configuración + HTTPS explícito; no acredita tráfico de TikTok'):
        if resultado not in ('confirmado','fallido','sin_recurso','incierto'):
            raise ValueError('Resultado de auditoría inválido')
        with self.conexion() as con:
            con.execute('''INSERT INTO auditoria_proxy(timestamp,run_id,device_id,endpoint,etapa,resultado,
                ip_esperada,ip_observada,latencia_ms,error_tipo,alcance) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (ahora(),run_id,device_id,endpoint,etapa,resultado,ip_esperada,ip_observada,
                 latencia_ms,error_tipo,alcance))

    def auditoria_proxies(self,run_id=None,limit=200):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('''SELECT * FROM auditoria_proxy
                WHERE (? IS NULL OR run_id=?) ORDER BY id DESC LIMIT ?''',(run_id,run_id,limit))]

    def ultimo_smoke(self):
        with self.conexion() as con:
            row=con.execute("SELECT * FROM ejecuciones_granja WHERE tipo='smoke' ORDER BY inicio DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def logs_vivos(self,run_id):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM logs_granja WHERE run_id=? ORDER BY id DESC LIMIT 200',(run_id,))][::-1]

    def registrar_ip(self,run_id,id_adb,ip,*,confirmada=False,smoke=False,error=None,laboratory=False):
        ip=str(ipaddress.ip_address(ip))
        with self.conexion() as con:
            con.execute('''INSERT INTO verificaciones_red VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(run_id,id_adb) DO UPDATE SET ip_externa=excluded.ip_externa,
                timestamp=excluded.timestamp,confirmada=excluded.confirmada,modo=excluded.modo,error=excluded.error''',
                (run_id,id_adb,ip,ahora(),int(confirmada),'laboratory' if laboratory else 'smoke' if smoke else 'farm',error))

    def ips_ejecucion(self,run_id):
        with self.conexion() as con:
            return [dict(row) for row in con.execute('SELECT * FROM verificaciones_red WHERE run_id=? ORDER BY id_adb',(run_id,))]

    def registrar_interaccion(self,id_adb,*,run_id,ciclo,descripcion_video,decision_ia,latencia_ms,ia_valida=True):
        encoded=json.dumps(decision_ia,ensure_ascii=False,allow_nan=False)
        if not isinstance(decision_ia,dict) or type(decision_ia.get('interactuar')) is not bool:
            raise ValueError('Decisión requiere interactuar booleano')
        legacy_id=self.identidad_agx(id_adb).get('canonical_id')
        with self.conexion() as con:
            con.execute("INSERT INTO dispositivos(id_adb,estado) VALUES (?,'Espera') ON CONFLICT DO NOTHING",(id_adb,))
            con.execute('''INSERT INTO interacciones
                (id_adb,timestamp,descripcion_video,decision_ia,latencia_ms,run_id,ciclo,ia_valida,legacy_device_id)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id,id_adb,ciclo) DO NOTHING''',
                (id_adb,ahora(),descripcion_video,encoded,max(0,round(latencia_ms)),run_id,ciclo,int(ia_valida),legacy_id))
            return con.execute('SELECT id FROM interacciones WHERE run_id=? AND id_adb=? AND ciclo=?',
                               (run_id,id_adb,ciclo)).fetchone()['id']

    def registrar_accion(self,interaction_id,event,comentario='',**details):
        with self.conexion() as con:
            result=('intentada' if event in ('like_attempt','comment_send_attempt') else
                    'comando_enviado' if event in ('like_click','comment_send_click','swipe') else
                    'omitida' if event.endswith('_skipped') else 'registrada')
            con.execute('INSERT INTO auditoria_acciones(interaction_id,timestamp,evento,resultado,detalle) VALUES (?,?,?,?,?)',
                (interaction_id,ahora(),event,result,json.dumps(details,ensure_ascii=False)))
            if event=='like_click':
                con.execute('UPDATE interacciones SET dio_like=1 WHERE id=?',(interaction_id,))
            elif event=='comment_send_click':
                con.execute('UPDATE interacciones SET comento=1,comentario_texto=? WHERE id=?',(comentario,interaction_id))

    def auditoria_de_acciones(self,device=None,limit=200):
        with self.conexion() as con:
            return [dict(r) for r in con.execute('''SELECT a.*,i.id_adb,i.run_id,i.ciclo FROM auditoria_acciones a
                JOIN interacciones i ON i.id=a.interaction_id WHERE (? IS NULL OR i.id_adb=?)
                ORDER BY a.id DESC LIMIT ?''',(device,device,limit))]

    def finalizar_interaccion(self,interaction_id,*,error=None):
        with self.conexion() as con:
            con.execute('UPDATE interacciones SET estado=?,error=? WHERE id=?',
                        ('error' if error else 'completada',error,interaction_id))

    def interacciones(self,*,device=None,skip_only=False,limit=25,offset=0):
        if not 1<=limit<=100 or offset<0:
            raise ValueError('Paginación no válida')
        conditions,params=[],[]
        if device:
            conditions.append('id_adb=?'); params.append(device)
        if skip_only:
            conditions.append("ia_valida=1 AND json_extract(decision_ia,'$.interactuar')=0")
        where=' WHERE '+' AND '.join(conditions) if conditions else ''
        with self.conexion() as con:
            total=con.execute('SELECT COUNT(*) FROM interacciones'+where,params).fetchone()[0]
            rows=con.execute('SELECT * FROM interacciones'+where+' ORDER BY timestamp DESC,id DESC LIMIT ? OFFSET ?',
                             (*params,limit,offset)).fetchall()
            return [dict(row) for row in rows],total

    def kpis(self):
        local=datetime.now(LOCAL_TZ).replace(hour=0,minute=0,second=0,microsecond=0)
        start=local.astimezone(timezone.utc).isoformat(timespec='microseconds')
        end=(local+timedelta(days=1)).astimezone(timezone.utc).isoformat(timespec='microseconds')
        with self.conexion() as con:
            row=con.execute('''SELECT COUNT(*) AS exitosas, COALESCE(SUM(dio_like),0) AS likes,
                COALESCE(SUM(comento),0) AS comentarios FROM interacciones
                WHERE timestamp>=? AND timestamp<? AND estado='completada' AND ia_valida=1''',(start,end)).fetchone()
            result=dict(row)
            result['conectados']=con.execute('SELECT COUNT(*) FROM dispositivos WHERE conectado=1').fetchone()[0]
            result['sin_cuenta']=con.execute("SELECT COUNT(*) FROM dispositivos WHERE cuenta_estado='pendiente'").fetchone()[0]
            result['cuenta_sin_verificar']=con.execute("SELECT COUNT(*) FROM dispositivos WHERE cuenta_estado='sin_verificar'").fetchone()[0]
        count=result['exitosas']
        result['tasa_likes']=100*result['likes']/count if count else 0
        result['tasa_comentarios']=100*result['comentarios']/count if count else 0
        return result

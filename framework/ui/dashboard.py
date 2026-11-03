"""Ejecutar con python main.py --ui o streamlit run ui/dashboard.py."""
import math
import json
import sys
import os
import importlib
import hashlib
from pathlib import Path

# Streamlit puede iniciar desde cualquier cwd.
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from core.project_env import load_project_environment
load_project_environment()

import streamlit as st
from core.database import Database
from ui.poc_dashboard import DashboardPOC
from config.proxies import ADBError
from core.adb_pool import descubrir_pool
from ui.jobs import DiagnosticJobs
from config.android_app import TIKTOK_PACKAGE
from core.panda_identity import resolver_pool_panda
from ui import farm_control as farm_control_module
if not hasattr(farm_control_module,'WebJobs'):
    farm_control_module=importlib.reload(farm_control_module)
FarmJobs,WebJobs,guardar_pool=(farm_control_module.FarmJobs,farm_control_module.WebJobs,farm_control_module.guardar_pool)
from config.proxies import leer_proxy_pool

st.set_page_config(page_title='Panda Box · QA',page_icon='🧪',layout='wide')


@st.cache_resource
def database(schema_version=10,code_revision=None):
    # Streamlit puede conservar tanto el módulo importado como una instancia anterior.
    from core import database as storage
    required=('auditoria_proxies','auditoria_de_acciones','auditar_proxy')
    if any(not hasattr(storage.Database,name) for name in required):
        storage=importlib.reload(storage)
    return storage.Database()


@st.cache_resource
def diagnostic_jobs():
    return DiagnosticJobs()


@st.cache_resource
def farm_jobs():
    return FarmJobs()


@st.cache_resource
def web_jobs():
    return WebJobs()


db=database(code_revision=(ROOT/'core/database.py').stat().st_mtime_ns)
jobs=diagnostic_jobs()
farm=farm_jobs()
web=web_jobs()
st.title('Panda Box · Control QA')
st.caption('Inventario físico, decisiones de IA y pruebas de una placa. Datos locales · America/Guatemala (UTC−6).')
control,audit,tests=st.tabs(['Panel de Control','Auditoría de IA','Configuración y Pruebas'])


@st.fragment(run_every='2s')
def controles_granja():
    st.subheader('Lanzar automatización')
    current=farm.snapshot()
    running=current is not None and current['returncode'] is None
    diagnostic=jobs.snapshot()
    diagnostic_running=diagnostic is not None and diagnostic['returncode'] is None
    web_state=web.snapshot()
    web_running=web_state is not None and web_state['returncode'] is None
    try:
        pool=leer_proxy_pool(ROOT/'config/proxy_pool.json')
        enabled=sum(p['enabled'] for p in pool)
        if any(p.get('lab_shared_exit') for p in pool):
            st.info('Laboratorio local: puertos separados con una misma IP pública de salida.')
    except (ValueError,OSError,KeyError):
        enabled=0
    st.caption(f"Proxies habilitados: {enabled} · API OpenAI: {'configurada' if os.getenv('OPENAI_API_KEY') else 'pendiente de configurar'}")
    if not enabled:
        st.info('Primero abre «Configuración y Pruebas» → «Configurar proxies», completa las IPs reales y guarda el pool.')
    left,middle,right=st.columns(3)
    mode=left.radio('Modo',['Smoke test','Granja'],key='farm_mode',horizontal=True,disabled=running)
    count=middle.number_input('Número de placas',min_value=1,max_value=40,value=3,key='farm_count',disabled=running)
    cycles=right.number_input('Ciclos por placa (0 = continuo)',min_value=0,max_value=100000,value=1,key='farm_cycles',disabled=running)
    network_mode=st.selectbox('Control de red Android',['root','proxy-laboratory','vpn-lockdown'],
        format_func=lambda value:{'root':'Estricto · firewall con root','proxy-laboratory':'Laboratorio sin root · proxy y datos móviles',
                                  'vpn-lockdown':'VPN Always-on + Lockdown · requiere helper y USB'}[value],
        key='farm_network_mode',disabled=running)
    if network_mode=='proxy-laboratory':
        st.info('Este modo no bloquea conexiones directas por WiFi. Guarda y restaura proxy y datos móviles; verifica HTTPS por el proxy.')
    elif network_mode=='vpn-lockdown':
        st.info('Requiere un APK VPN funcional, consentimiento y primer ensayo por USB. Un ajuste lockdown=1 no acredita por sí solo ausencia de fugas.')
        build_info=ROOT/'tools/agx_vpn_helper.build.json'
        if build_info.is_file():
            try:
                metadata=json.loads(build_info.read_text(encoding='utf-8'))
                artifact=ROOT/'tools/agx_vpn_helper.apk'
                if artifact.is_file():
                    digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
                    st.caption(f'APK local: {artifact.stat().st_size} bytes · SHA-256: {digest}')
                    if digest!=metadata.get('helper_apk_hash'):
                        st.error('El APK cambió respecto al reporte de compilación; vuelve a validarlo.')
                if metadata.get('tcp_engine_included') is False:
                    st.warning('El APK local es de control: motor TCP no incluido. No está habilitado como túnel de navegación.')
            except (OSError,ValueError):
                st.warning('No se pudo leer el reporte de compilación del helper.')
    if mode=='Smoke test':
        st.caption('Prueba el subset fijo inicial. Requiere que los primeros proxies del pool estén habilitados y ciclos mayores que cero.')
    else:
        st.caption('El número de placas limita la concurrencia. Con ciclos 0 la granja continúa hasta que pulses Detener.')
    start,stop=st.columns(2)
    if start.button('Iniciar smoke test' if mode=='Smoke test' else 'Iniciar granja',type='primary',
                    disabled=running or web_running or diagnostic_running or os.getenv('PANDA_SIMULATION')=='1',key='farm_start'):
        try:
            farm.start(smoke=mode=='Smoke test',count=int(count),cycles=int(cycles),db_path=db.path,network_mode=network_mode)
            st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:
            st.error(str(exc))
    if stop.button('Detener automatización',disabled=not running or bool(current and current.get('stopping')),key='farm_stop'):
        farm.cancel()
        st.rerun()
    if current:
        if running:
            st.info('Cierre cooperativo solicitado; esperando limpieza de firewall y proxies.' if current.get('stopping') else 'Automatización en ejecución. Puedes seguir sus estados y logs en este panel.')
        else:
            st.caption(f"Última automatización finalizada · código {current['returncode']}")
        with st.expander('Salida de la automatización',expanded=bool(not running and current['returncode'])):
            st.code(current.get('log') or 'Esperando salida…',language=None)


@st.fragment(run_every='2s')
def controles_web():
    with st.expander('Automatización web · Patchright'):
        st.caption('Navegador móvil del servidor. El control de placas Android utiliza el modo anterior.')
        current=web.snapshot()
        running=current is not None and current['returncode'] is None
        native=farm.snapshot()
        diagnostic=jobs.snapshot()
        busy=running or (native is not None and native['returncode'] is None) or (diagnostic is not None and diagnostic['returncode'] is None)
        try:
            endpoints=[p['endpoint'] for p in leer_proxy_pool(ROOT/'config/proxy_pool.json') if p['enabled']]
        except (ValueError,OSError):
            endpoints=[]
        endpoint=st.selectbox('Proxy del perfil web',endpoints,key='web_proxy',disabled=busy)
        profile=st.text_input('Perfil persistente web',value='cuenta_tiktok_01',key='web_profile',disabled=busy)
        username=st.text_input('Usuario del proxy (opcional)',key='web_proxy_user',disabled=busy)
        password=st.text_input('Contraseña del proxy (opcional)',type='password',key='web_proxy_password',disabled=busy)
        cycles=st.number_input('Ciclos web',min_value=1,max_value=100000,value=1,key='web_cycles',disabled=busy)
        selectors=st.text_input('Archivo de selectores web',value=str(ROOT/'config/web_selectors.mobile.json'),key='web_selectors',disabled=busy)
        st.caption('Los selectores móviles son candidatos: valídalos en tu sesión. Un control ambiguo detiene esa cuenta.')
        confirmed=st.checkbox('Verifiqué manualmente la sesión de este perfil',key='web_authenticated',disabled=busy)
        execute=st.checkbox('Aplicar likes y comentarios decididos por IA',key='web_execute',disabled=busy)
        import importlib.util
        if importlib.util.find_spec('playwright_ghost_cursor') is None:
            st.info('Cursor opcional no instalado: se utilizará el método estándar; no se declara integración GhostCursor.')
        login=st.button('Abrir sesión web',key='web_login',disabled=busy or not endpoints)
        start=st.button('Iniciar navegación web',key='web_start',disabled=busy or not endpoints or not confirmed)
        if login or start:
            try:
                web.start_web(endpoint=endpoint,profile=profile,cycles=int(cycles),login_only=login,
                    execute=execute,db_path=db.path,username=username,password=password,selectors=selectors)
                st.rerun()
            except (ValueError,OSError,RuntimeError):
                st.error('No se pudo iniciar: revisa dependencias, selectores, perfil y configuración del proxy.')
        if st.button('Detener navegación web',key='web_stop',disabled=not running):
            web.cancel()
            st.rerun()
        if current:
            st.caption('Web en ejecución' if running else f"Web finalizada · código {current['returncode']}")
            st.code(current.get('log') or 'Esperando salida…',language=None)


def configurar_proxies():
    import pandas as pd
    path=ROOT/'config/proxy_pool.json'
    st.subheader('Configurar proxies')
    try:
        raw=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'proxies':[]}
        rows=raw['proxies']
        if raw.get('mode')=='laboratory':
            st.info(f"Proxy local de laboratorio en {raw.get('lab_host')}. La IP de salida compartida es real y se verifica; no representa IPs residenciales distintas.")
            st.caption('Las tres filas locales ya están preconfiguradas. El smoke utiliza las primeras filas, en ese orden.')
        else:
            st.caption('Completa IPv4 del proveedor, puerto e IP pública de salida. Sustituye los ejemplos antes de habilitar las filas.')
            st.caption('Los endpoints de proveedor usan autorización por IP, sin usuario/contraseña.')
        if not isinstance(rows,list):
            raise ValueError('El pool debe contener una lista proxies.')
    except (ValueError,OSError,KeyError) as exc:
        st.error(f'No se pudo abrir el pool: {exc}')
        return
    with st.form('proxy_configuration'):
        edited=st.data_editor(pd.DataFrame(rows,columns=['enabled','host','port','exit_ip']),
            num_rows='dynamic',hide_index=True,width='stretch',key='proxy_editor',
            column_config={
                'enabled':st.column_config.CheckboxColumn('Habilitado',default=False),
                'host':st.column_config.TextColumn('IPv4 del proxy',required=True),
                'port':st.column_config.NumberColumn('Puerto',min_value=1,max_value=65535,step=1,required=True),
                'exit_ip':st.column_config.TextColumn('IP pública de salida',required=True)})
        save=st.form_submit_button('Guardar proxies',type='primary')
    if save:
        try:
            saved=guardar_pool(path,edited.to_dict('records'))
            required=int(st.session_state.get('farm_count',3)) if st.session_state.get('farm_mode','Smoke test')=='Smoke test' else 1
            valid=(len(saved)>=required and all(p['enabled'] for p in saved[:required]))
            if valid:
                for alert in db.alertas():
                    if alert['clave']=='deployment' and alert['mensaje'].startswith(('Configura al menos','Plantilla creada','Los primeros')):
                        db.alerta('deployment','Pool actualizado desde el dashboard',activa=False)
            st.success(f"Pool guardado: {len(saved)} entradas, {sum(p['enabled'] for p in saved)} habilitadas.")
            st.caption('Vuelve al Panel de Control para iniciar el smoke test.')
        except (ValueError,OSError) as exc:
            st.error(str(exc))


@st.fragment(run_every='5s')
def panel_control():
    for alert in db.alertas():
        st.error(alert['mensaje'])
    try:
        if os.getenv('PANDA_SIMULATION')=='1':
            st.warning('SIMULACIÓN: base aislada, sin hardware ni autenticación real')
            raise ADBError('Inventario físico desactivado en simulación')
        snapshot=resolver_pool_panda(descubrir_pool(db.servidores_configurados()),db)
        for error in snapshot.identity_errors.values():
            st.warning(error)
        db.sincronizar_pool(snapshot)
        for server,error in snapshot.errors.items():
            st.warning(f'{server}: {error}')
        if not snapshot.successful:
            raise ADBError('Ningún servidor ADB respondió; presencia actual no verificada')
        st.caption(f'Inventario ADB actualizado. {len(snapshot.successful)} servidores consultados. '
                   'Refresco cada 5 segundos con la página activa.')
    except ADBError as exc:
        st.warning(str(exc))
        st.caption('No se pudo confirmar presencia actual. Revisar la disponibilidad de los servidores ADB.')
    metrics=db.kpis()
    all_rows=db.dispositivos()
    def placeholder(row):
        return (':' in row['id_adb'] and not row.get('adb_transport') and not row['conectado']
                and row.get('cuenta_estado')=='sin_verificar' and not row.get('proxy'))
    historical=[row for row in all_rows if placeholder(row)]
    rows=[row for row in all_rows if not placeholder(row)]
    metrics['cuenta_sin_verificar']=sum(row['cuenta_estado']=='sin_verificar' for row in rows)
    columns=st.columns(5)
    columns[0].metric('Conectados · última lectura',metrics['conectados'])
    columns[1].metric('Ciclos IA válidos hoy',metrics['exitosas'])
    columns[2].metric('Likes / ciclos hoy',f"{metrics['tasa_likes']:.1f}%")
    columns[3].metric('Comentarios / ciclos hoy',f"{metrics['tasa_comentarios']:.1f}%")
    columns[4].metric('Placas sin Cuenta Activa',metrics['sin_cuenta'])
    st.caption(f"Cuentas sin comprobar: {metrics['cuenta_sin_verificar']}. El contador de placas sin cuenta "
               'solo incluye las detectadas por el Auth Check.')
    if metrics['sin_cuenta']:
        st.warning(f"{metrics['sin_cuenta']} placas en Pendiente Cuenta. Configurar o revisar sus perfiles manualmente.")
    st.caption('Tasas = clics realizados / ciclos completados con IA válida hoy. Incluyen SKIP en el denominador; '
               'los clics no certifican aceptación por TikTok.')
    colors={'Calentando':'🟢','Espera':'🟡','Error':'🔴','Desconectado':'⚪',
            'Espera - Sin Proxy':'🟡','Carga Lenta - Reintentando':'🟠','Pendiente Cuenta':'🟡',
            'Navegando':'🟢','Analizando con IA':'🔵'}
    colors.update({'Reconectando':'🟠','Recuperando':'🟠','Cuarentena':'🔴'})
    if historical and st.toggle(f'Mostrar {len(historical)} conexiones antiguas por IP',key='show_transport_history'):
        rows=all_rows
    rows=sorted(rows,key=lambda row:(not row['conectado'],row.get('alias') or row['id_adb']))
    display=[{**row,'estado':f"{colors.get(row['estado'],'⚪')} {row['estado']}"} for row in rows]
    smoke=db.ultimo_smoke()
    if smoke and smoke['estado']=='activo':
        selected=set(json.loads(smoke['subset_json']))
        for row in display:
            row['smoke_test']='Seleccionada' if row['id_adb'] in selected else 'Pasiva — fuera del subset'
    if any(row['cuenta_estado']=='pendiente' for row in display):
        import pandas as pd
        table=pd.DataFrame(display)
        st.dataframe(table.style.apply(lambda row: ['background-color: #fff3cd; color: #664d03'
            if row['cuenta_estado']=='pendiente' else '' for _ in row],axis=1),
            width='stretch',hide_index=True)
    else:
        st.dataframe(display,width='stretch',hide_index=True)
    st.caption(f'{len(rows)} dispositivos conocidos · capacidad prevista 40. No se generan placas ficticias. '
               'Calentando indica ejecución del backend; ultima_conexion acredita observación ADB.')
    with st.expander('Servidores ADB y disponibilidad'):
        st.dataframe(db.servidores_adb(),width='stretch',hide_index=True)
    with st.expander('Resultado de asignación y verificación de proxies'):
        st.dataframe(db.auditoria_proxies(limit=30),width='stretch',hide_index=True)
        st.caption('Consulta Auditoría de IA para descargar el reporte. Sin registros = sin comprobación ejecutada.')
    with st.expander('Bootstrap · última medición'):
        boot=db.logs_vivos('bootstrap')
        if boot:
            details=json.loads(boot[-1]['detalle'])
            st.caption(f"Red ADB: {details.get('network_ms')} ms · con identidad: {details.get('total_ms')} ms · "
                       f"rutas: {details.get('connected')} · medición, no garantía de arranque tras corte")
        else:
            st.caption('Sin mediciones de bootstrap todavía.')
    with st.expander('Datos rescatados de AGX · históricos'):
        legacy=db.legado_agx()
        if legacy:
            st.caption('Declaraciones y observaciones fechadas. No acreditan conexión ni sesión actual. '
                       'Las IP:puerto históricas no se usan como identidad permanente.')
            st.dataframe(legacy,width='stretch',hide_index=True)
        else:
            st.caption('Sin importación histórica de AGX en esta base.')


@st.fragment(run_every='1s')
def logs_smoke():
    run=db.ultimo_smoke()
    if run is None:
        return
    st.subheader('Smoke Test · Logs Vivos')
    subset=json.loads(run['subset_json'])
    st.info(f"{len(subset)} placas seleccionadas · {run['estado']} · "+
            ('el resto permanece pasivo' if run['estado']=='activo' else 'última prueba finalizada'))
    st.caption('Run: '+run['run_id']+' · '+', '.join(subset))
    st.dataframe(db.ips_ejecucion(run['run_id']),width='stretch',hide_index=True)
    summary=db.resumen_carga(run['run_id'])
    if summary:
        st.caption('Resumen de carga de UI: milisegundos hasta feed y autenticación compatibles; vacío = sin medición.')
        st.dataframe(summary,width='stretch',hide_index=True)
    st.caption('IP observada por curl bajo firewall. No certifica tráfico de TikTok ni fugas DNS.')
    logs=db.logs_vivos(run['run_id'])
    critical=[x for x in logs if x['nivel']=='CRITICAL']
    if critical:
        st.error(critical[-1]['mensaje'])
    text='\n'.join(f"{x['timestamp']} [{x['nivel']}] {x['id_adb'] or 'supervisor'} · "
                   f"{x['mensaje']} {x['detalle']}" for x in logs)
    st.code(text or 'Esperando eventos de los workers…',language=None)


@st.fragment(run_every='5s')
def auditoria():
    st.subheader('Verificación de proxies · últimas 200 comprobaciones')
    network=db.auditoria_proxies()
    st.dataframe(network,width='stretch',hide_index=True)
    st.caption('Reserva confirmada = endpoint asignado. salida_https confirmada = IP observada igual a la esperada. '
               'No acredita reproducción ni aceptación de likes/comentarios por TikTok.')
    st.download_button('Descargar auditoría de proxies (JSON)',
        json.dumps(network,ensure_ascii=False,indent=2),file_name='auditoria-proxies.json',mime='application/json',
        key='export_proxy_audit')
    devices=[row['id_adb'] for row in db.dispositivos()]
    left,right=st.columns(2)
    selected=left.selectbox('Dispositivo',['Todos',*devices],key='audit_device')
    actions=db.auditoria_de_acciones(None if selected=='Todos' else selected)
    with st.expander('Trazas de acciones · intentos, comandos enviados y omisiones'):
        st.dataframe(actions,width='stretch',hide_index=True)
        st.caption('comando_enviado acredita que ADB devolvió el control; no confirma aceptación por TikTok. '
                   'Un intento sin comando posterior tiene resultado incierto y no se repite automáticamente.')
        st.download_button('Descargar trazas de acciones (JSON)',json.dumps(actions,ensure_ascii=False,indent=2),
            file_name='trazas-acciones.json',mime='application/json',key='export_action_traces')
    skip=right.checkbox('Solo SKIP válidos de OpenAI',key='audit_skip')
    filters=(selected,skip)
    if st.session_state.get('audit_filters')!=filters:
        st.session_state.audit_page=1
        st.session_state.audit_filters=filters
    size=25
    _,count=db.interacciones(device=None if selected=='Todos' else selected,skip_only=skip,limit=1)
    pages=max(1,math.ceil(count/size))
    st.session_state.audit_page=min(st.session_state.get('audit_page',1),pages)
    page=st.number_input('Página',min_value=1,max_value=pages,step=1,key='audit_page')
    rows,_=db.interacciones(device=None if selected=='Todos' else selected,skip_only=skip,
                            limit=size,offset=(page-1)*size)
    st.dataframe(rows,width='stretch',hide_index=True)
    st.download_button('Descargar acciones de esta página (JSON)',
        json.dumps(rows,ensure_ascii=False,indent=2),file_name='auditoria-acciones.json',mime='application/json',
        key='export_action_audit')
    st.caption(f'{count} registros · página {page}/{pages} · fechas almacenadas en UTC · latencia_ms mide consulta IA.')


@st.fragment(run_every='1s')
def configuracion():
    st.code(str(db.path),language=None)
    st.caption('SQLite WAL, claves foráneas y conexiones independientes por operación. '
               'Los diagnósticos no consultan OpenAI ni modifican la red.')
    with st.expander('Reservas de proxies y cuarentenas'):
        st.dataframe(db.reservas_proxy(),width='stretch',hide_index=True)
    with st.expander('Eventos de carga lenta'):
        st.dataframe(db.eventos_recientes(),width='stretch',hide_index=True)
    current=jobs.snapshot()
    running=current is not None and current['returncode'] is None
    package=st.text_input('Paquete para diagnóstico',value=TIKTOK_PACKAGE)
    farm_state=farm.snapshot()
    farm_running=farm_state is not None and farm_state['returncode'] is None
    if st.button('Lanzar diagnóstico físico',disabled=running or farm_running,type='primary'):
        try:
            jobs.start(package.strip())
            st.rerun()
        except (OSError,RuntimeError) as exc:
            st.error(str(exc))
    if current is None:
        st.info('Conecta una placa por USB. El diagnóstico selecciona el primer dispositivo autorizado.')
        return
    st.caption(f"Sesión: {current['directory']}")
    if running:
        st.info('Diagnóstico activo: realiza en el teléfono los pasos solicitados abajo.')
        if st.button('Cancelar diagnóstico'):
            jobs.cancel()
            st.info('Cancelación solicitada. Se espera la salida cooperativa y restauración del teclado.')
        prompt=current.get('prompt',{})
        if prompt.get('pending'):
            st.write(prompt['text'])
            answer=st.selectbox('Respuesta',['Continuar','Sí, coordenadas correctas','No, revisar coordenadas'],
                                key=f"answer_{prompt['id']}")
            if st.button('Enviar respuesta',key=f"submit_{prompt['id']}"):
                try:
                    jobs.answer(prompt['id'],{'Continuar':'','Sí, coordenadas correctas':'s',
                                             'No, revisar coordenadas':'n'}[answer])
                except RuntimeError as exc:
                    st.error(str(exc))
    else:
        st.write(f"Proceso finalizado · código {current['returncode']}")
    image=Path(current['directory'])/'debug_layout.png'
    if image.exists():
        st.image(str(image),caption='Overlay capturado en la placa',width=420)
    if 'diagnostics' in current:
        st.json(current['diagnostics'])
    with st.expander('Salida del diagnóstico'):
        st.code(current.get('log','Esperando salida…'),language=None)


with control:
    controles_granja()
    controles_web()
    panel_control()
    logs_smoke()
with audit:
    auditoria()
with tests:
    configurar_proxies()
    configuracion()
    with st.expander('POC de escritorio · pruebas QA'):
        st.caption('Panel nativo separado; conserva este dashboard de Streamlit.')
        st.code(r'.\.venv\Scripts\python.exe main.py --poc-ui',language='powershell')

"""Extracción ADB y candidatos semánticos; nunca adivina IDs ofuscados."""
import json
import re
import xml.etree.ElementTree as ET
import threading
import time
import unicodedata
from pathlib import Path

from config.proxies import ADBError, adb


def analizar_autenticacion(xml,package,*,strict_profile=True):
    """Heurística conservadora de UI: no acredita una sesión válida en el servidor."""
    if len(xml)>2_000_000 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        raise ValueError('XML de autenticación no válido')
    root=ET.fromstring(xml)
    parents={child:parent for parent in root.iter() for child in parent}
    nodes=[n for n in root.iter('node') if n.get('package')==package and n.get('displayed','true')!='false']
    if not nodes:
        raise ADBError('La pantalla no pertenece al paquete esperado; autenticación indeterminada')
    def normalized(text):
        return ' '.join(''.join(c for c in unicodedata.normalize('NFD',text.casefold())
                                if unicodedata.category(c)!='Mn').split()).strip(' .!…')
    profile=False
    for node in nodes:
        bounds=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',node.get('bounds',''))
        if not bounds:
            continue
        x1,y1,x2,y2=map(int,bounds.groups())
        if x2<=x1 or y2<=y1:
            continue
        labels=[normalized(node.get(k,'')) for k in ('text','content-desc')]
        resource=node.get('resource-id','').lower()
        action=node.get('clickable')=='true' or node.get('class','').endswith('Button') or bool(
            re.search(r'login|sign.?in|sign.?up|register',resource))
        parent=parents.get(node)
        if parent is not None and parent.get('package')==package:
            action=action or parent.get('clickable')=='true' or parent.get('class','').endswith('Button')
        login=any(re.fullmatch(r'(?:iniciar sesion(?: o registrarse)?|inicia sesion|registrarse|registrate|crear cuenta|'
                              r'log in(?: or sign up)?|login|sign in|sign up|register)(?: en tiktok| to tiktok)?',x) for x in labels)
        if action and login:
            return {'authenticated':False,'reason':'control_de_login_o_registro_visible','heuristic':True}
        if any(x.split(',',1)[0].strip() in ('perfil','profile','me','yo') for x in labels) or re.search(
            r'(?:profile_tab|tab_profile|bottom_profile|profile_bottom_tab)',resource):
            profile=True
    if strict_profile and not profile:
        return {'authenticated':False,'reason':'pestana_perfil_no_visible','heuristic':True}
    return {'authenticated':True if profile else None,'reason':'ui_compatible_con_cuenta' if profile
            else 'carga_o_auth_indeterminada','heuristic':True}


def comprobar_cuenta(device_id,package,*,sessions='sessions',strict_profile=True):
    directory=Path(sessions)
    directory.mkdir(parents=True,exist_ok=True)
    result=adb('-s',device_id,'shell','uiautomator','dump','--compressed',
               '/sdcard/panda_auth.xml',timeout=5)
    if 'dumped to' not in result.lower():
        raise ADBError('No se pudo confirmar el dump de autenticación')
    xml=adb('-s',device_id,'exec-out','cat','/sdcard/panda_auth.xml',timeout=3)
    try:
        report=analizar_autenticacion(xml,package,strict_profile=strict_profile)
    except ET.ParseError as exc:
        raise ADBError('Dump de autenticación incompleto') from exc
    (directory/'auth_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def contiene_feed(xml,package,markers=None):
    if len(xml)>2_000_000 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        raise ValueError('Micro-dump no válido')
    if markers is not None and (not isinstance(markers,list) or not markers or
                               any(not isinstance(x,str) or not x.strip() for x in markers)):
        raise ValueError('markers requiere una lista no vacía de etiquetas/IDs')
    markers=markers or ['video_player','player_container','video_view','feed_viewpager',
                        'feed_container','recommend_feed']
    for node in ET.fromstring(xml).iter('node'):
        if node.get('package')!=package or node.get('displayed','true')=='false':
            continue
        label=(node.get('resource-id','')+' '+node.get('content-desc','')).lower()
        bounds=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',node.get('bounds',''))
        if bounds and any(marker.lower() in label for marker in markers):
            x1,y1,x2,y2=map(int,bounds.groups())
            if x2>x1 and y2>y1:
                return True
    return False


def esperar_feed(device_id,package,*,stop=None,on_slow=lambda:None,markers=None,timeout=15,max_attempts=5,on_progress=lambda data:None):
    """Hasta cinco micro-dumps en una ventana total de 15 s, sin screenshots/pull."""
    stop=stop or threading.Event()
    if not 0<timeout<=15 or not 1<=max_attempts<=5:
        raise ValueError('Espera UI requiere <=15 segundos y <=5 intentos')
    started=time.monotonic()
    deadline=started+timeout
    last_error=None
    attempts=0
    for index in range(max_attempts):
        if stop.is_set():
            raise InterruptedError('Espera UI cancelada')
        remaining=deadline-time.monotonic()
        if remaining<=0:
            break
        attempts+=1
        on_progress({'attempt':attempts,'state':'dump_start'})
        try:
            output=adb('-s',device_id,'shell','uiautomator','dump','--compressed',
                       '/sdcard/panda_wait.xml',timeout=min(3,remaining))
            remaining=deadline-time.monotonic()
            if 'dumped to' in output.lower() and remaining>0:
                xml=adb('-s',device_id,'exec-out','cat','/sdcard/panda_wait.xml',timeout=min(1,remaining))
                auth=analizar_autenticacion(xml,package,strict_profile=False)
                if auth['authenticated'] is False:
                    on_progress({'attempt':attempts,'state':'login_required','reason':auth['reason']})
                    return {'ready':False,'attempts':attempts,'elapsed':time.monotonic()-started}
                if contiene_feed(xml,package,markers):
                    on_progress({'attempt':attempts,'state':'feed_ready'})
                    return {'ready':True,'attempts':attempts,'elapsed':time.monotonic()-started}
        except (ADBError,ValueError,ET.ParseError) as exc:
            last_error=type(exc).__name__
            on_progress({'attempt':attempts,'state':'dump_error','error':last_error})
        remaining=deadline-time.monotonic()
        # Polling acotado e interrumpible; nunca asumir carga completa por el paso del tiempo.
        delay=max(0,remaining/(max_attempts-index))
        if stop.wait(delay):
            raise InterruptedError('Espera UI cancelada')
    remaining=deadline-time.monotonic()
    if remaining>0 and stop.wait(remaining):
        raise InterruptedError('Espera UI cancelada')
    on_slow()
    return {'ready':False,'attempts':attempts,'elapsed':time.monotonic()-started,'last_error':last_error}


def analizar_xml(path, *, screen_size=None):
    data = Path(path).read_bytes()
    if len(data) > 4_000_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML excesivo o con entidades no admitidas')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError('Dump UI inválido o incompleto') from exc
    nodes = list(root.iter('node'))
    parsed = []
    for node in nodes:
        bounds = node.get('bounds', '')
        match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
        center = None
        if match:
            x1,y1,x2,y2 = map(int,match.groups())
            if x2>x1 and y2>y1:
                center = [(x1+x2)/2,(y1+y2)/2]
        parsed.append({'resource_id':node.get('resource-id',''),
            'text':node.get('text',''),'content_desc':node.get('content-desc',''),
            'class':node.get('class',''),'package':node.get('package',''),
            'clickable':node.get('clickable')=='true','bounds':bounds,
            'enabled':node.get('enabled','true')=='true',
            'selected':node.get('selected')=='true',
            'checked':node.get('checked')=='true',
            'center_px':center, 'center_relative':(
                [round(center[0]/screen_size[0],6),round(center[1]/screen_size[1],6)]
                if center and screen_size else None)})
    terms = {
        'description':r'description|desc_text|caption|video_desc|post_text',
        'like':r'(?<!\w)(like|likes|me gusta|dislike|unlike)(?!\w)|digg',
        'comments':r'comment|comentario',
        'comment_input':r'comment_input|comment_edit|edit_comment|añade un comentario|add comment|add a comment|escribe un comentario',
        'comment_send':r'comment_send|send_comment|(?<!\w)(send|enviar|publicar|post)(?!\w)',
    }
    candidates = {key:[] for key in terms}
    for item in parsed:
        labels = ' '.join((item['resource_id'],item['content_desc'],item['text'])).lower()
        for key,pattern in terms.items():
            if re.search(pattern,labels):
                candidates[key].append(item)
        if item['class'].endswith('EditText') and item not in candidates['comment_input']:
            candidates['comment_input'].append(item)
    return {'schema_version':1,'screen_size':screen_size,
            'candidates':candidates,'clickable_components':[n for n in parsed if n['clickable']],
            'text_components':[n for n in parsed if n['text'] or n['content_desc']],
            'warnings':['Candidatos heurísticos: verificar en pantalla; no identifican el post con certeza.',
                        'Coordenadas válidas solo para el dump y orientación capturados.']}


def capturar_pantalla_y_xml(device_id, sessions='sessions'):
    directory = Path(sessions)
    directory.mkdir(parents=True, exist_ok=True)
    remote = '/sdcard/window_dump.xml'
    local = directory/'window_dump.xml'
    temporary = directory/'window_dump.pending.xml'
    # Evita reutilizar un dump viejo si uiautomator falla sin código de error.
    adb('-s',device_id,'shell','rm','-f',remote)
    result = adb('-s',device_id,'shell','uiautomator','dump',remote,timeout=40)
    if 'dumped to' not in result.lower():
        raise ADBError(f'No se confirmó el dump UI: {result[:300]}')
    try:
        adb('-s',device_id,'pull',remote,str(temporary.resolve()),timeout=30)
        size_output = adb('-s',device_id,'shell','wm','size')
        sizes = re.findall(r'(\d+)x(\d+)',size_output)
        size = tuple(map(int,sizes[-1])) if sizes else None
        report = analizar_xml(temporary,screen_size=size)
        # Ajustar rotación: wm size suele informar tamaño natural.
        if size:
            rotation = ET.parse(temporary).getroot().get('rotation','0')
            if rotation in ('1','3'):
                size = size[::-1]
                report = analizar_xml(temporary,screen_size=size)
        temporary.replace(local)
    finally:
        temporary.unlink(missing_ok=True)
    report['udid'] = device_id
    report['xml_path'] = str(local.resolve())
    # Screenshot opcional: un fallo no invalida el XML capturado.
    try:
        adb('-s',device_id,'shell','screencap','-p','/sdcard/window_dump.png')
        adb('-s',device_id,'pull','/sdcard/window_dump.png',str((directory/'window_dump.png').resolve()))
        report['screenshot_path'] = str((directory/'window_dump.png').resolve())
    except ADBError as exc:
        report['warnings'].append(f'Captura PNG no disponible: {exc}')
    output = directory/'components.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for item in report['clickable_components']:
        print(f"clickable id={item['resource_id']!r} text={item['text']!r} "
              f"desc={item['content_desc']!r} bounds={item['bounds']} "
              f"rel={item['center_relative']}",flush=True)
    print(f'Reporte UI guardado: {output.resolve()}',flush=True)
    return report

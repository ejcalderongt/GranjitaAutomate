"""Diagnóstico físico interactivo, sin consultas a OpenAI ni publicaciones."""
import json
import os
import random
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from config.device_test import primer_dispositivo_usb, shell
from config.proxies import ADBError, adb, verificar_adb
from core.ai_orchestrator import ADB_IME, inyectar_unicode, teclado_unicode
from core.selectors import capturar_pantalla_y_xml
from config.android_app import TIKTOK_PACKAGE

TEST_TEXT = '¡hola, probando automatización de granja 2026! 🔥'


def capturar_png(device_id, target):
    target = Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary = target.with_suffix('.pending.png')
    remote = '/sdcard/panda_diagnostic_screen.png'
    try:
        adb('-s',device_id,'shell','rm','-f',remote)
        adb('-s',device_id,'shell','screencap','-p',remote)
        adb('-s',device_id,'pull',remote,str(temporary.resolve()),timeout=30)
        with Image.open(temporary) as image:
            image.verify()
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def generar_overlay(screen, components, output):
    report = json.loads(Path(components).read_text(encoding='utf-8'))
    counts, warnings = {}, []
    with Image.open(screen) as source:
        image = source.convert('RGBA')
    if list(image.size)!=report.get('screen_size'):
        raise ValueError('El tamaño del screenshot y del mapa XML no coincide; recaptura sin rotar')
    overlay = Image.new('RGBA',image.size,(0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    for kind in ('description','like','comments'):
        count = 0
        for node in report.get('candidates',{}).get(kind,[]):
            match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',node.get('bounds',''))
            if not match:
                warnings.append(f'{kind}: bounds inválido')
                continue
            x1,y1,x2,y2 = map(int,match.groups())
            if not (0<=x1<x2<=image.width and 0<=y1<y2<=image.height):
                warnings.append(f'{kind}: bounds fuera de pantalla')
                continue
            draw.rectangle((x1,y1,x2-1,y2-1),fill=(255,0,0,65),outline=(255,0,0,230),width=3)
            x,y = (x1+x2)//2,(y1+y2)//2
            draw.line((x-8,y,x+8,y),fill=(255,255,0,255),width=2)
            draw.line((x,y-8,x,y+8),fill=(255,255,0,255),width=2)
            draw.text((x1+3,max(0,y1-13)),f'{kind}: {x},{y}',fill=(255,0,0,255))
            count += 1
        counts[kind] = count
        if not count:
            warnings.append(f'{kind}: ningún candidato dibujable')
    Image.alpha_composite(image,overlay).convert('RGB').save(output)
    return {'counts':counts,'warnings':warnings,'image_size':list(image.size),
            'layout_path':str(Path(output).resolve())}


def probar_teclado(device_id, directory, *, preguntar=input):
    directory = Path(directory)/'keyboard'
    directory.mkdir(parents=True,exist_ok=True)
    initial_ime = shell(device_id,'settings','get','secure','default_input_method').strip()
    if initial_ime!=ADB_IME:
        print('AVISO: ADBKeyBoard no está configurado como método de entrada predeterminado '
              'en los ajustes de Android. Se activará temporalmente para la prueba.',flush=True)
    # Settings es una actividad neutra; cada OEM expone su búsqueda de forma distinta.
    result = shell(device_id,'am','start','-W','-a','android.settings.SETTINGS')
    if 'Error' in result or 'Exception' in result or 'Status: ok' not in result:
        raise ADBError(f'No se pudo abrir Ajustes: {result[:300]}')
    typed = False
    with teclado_unicode(device_id,directory):
        try:
            preguntar('En el teléfono abre la búsqueda de Ajustes, vacía el campo y déjalo '
                      'enfocado. Pulsa Enter aquí cuando esté listo: ')
            capturar_pantalla_y_xml(device_id,sessions=directory)
            root = ET.parse(directory/'window_dump.xml').getroot()
            focused = [n for n in root.iter('node') if n.get('focused')=='true'
                       and n.get('class','').endswith('EditText')]
            if len(focused)!=1:
                raise ValueError('No hay un único EditText enfocado; no se inyectó texto')
            typed = True  # El broadcast puede haberse recibido aunque se pierda USB.
            start = time.perf_counter()
            inyectar_unicode(device_id,TEST_TEXT)
            # Dump inmediato: no se asume que un broadcast exitoso equivalga a escribir.
            capturar_pantalla_y_xml(device_id,sessions=directory)
            elapsed = (time.perf_counter()-start)*1000
            root = ET.parse(directory/'window_dump.xml').getroot()
            exact = any(n.get('class','').endswith('EditText') and
                        unicodedata.normalize('NFC',n.get('text',''))==TEST_TEXT
                        for n in root.iter('node'))
            if not exact:
                print('ALERTA: no se encontró el texto completo en el XML. Comprueba si '
                      'ADBKeyBoard está configurado como método de entrada predeterminado '
                      'en los ajustes de Android; también revisa foco y accesibilidad.',flush=True)
            else:
                print('Unicode verificado en XML: tildes, signos y emoji coinciden.',flush=True)
            return {'status':'passed' if exact else 'failed','exact_text_match':exact,
                    'initial_ime':initial_ime,'test_ime':ADB_IME,
                    'broadcast_and_dump_ms':round(elapsed,2),
                    'xml_path':str((directory/'window_dump.xml').resolve())}
        finally:
            if typed:
                # Borrar la búsqueda mientras el IME de prueba sigue activo.
                shell(device_id,'am','broadcast','-a','ADB_CLEAR_TEXT','-p','com.android.adbkeyboard')


def analizar_gfxinfo(text):
    totals = [int(n) for n in re.findall(r'^\s*Total frames rendered:\s*(\d+)',text,re.M)]
    janky = [int(n) for n in re.findall(r'^\s*Janky frames:\s*(\d+)',text,re.M)]
    if not totals or len(totals)!=len(janky):
        return {'available':False}
    total,bad = sum(totals),sum(janky)
    return {'available':True,'total_frames':total,'janky_frames':bad,
            'cumulative_jank_percent':round(100*bad/total,2) if total else None}


def medir_rendimiento(device_id, package, directory, *, seconds=None, check=lambda:None):
    seconds = random.SystemRandom().randint(12,28) if seconds is None else seconds
    if not 12<=seconds<=28:
        raise ValueError('La ventana de rendimiento debe ser de 12–28 segundos')
    directory = Path(directory)/'performance'
    directory.mkdir(parents=True,exist_ok=True)
    samples, intervals, previous = [], [], None
    start = time.monotonic()
    while True:
        check()
        tick = time.perf_counter()
        # stdout capturado y persistido, nunca impreso en cada muestra.
        text = shell(device_id,'dumpsys','gfxinfo',package,'framestats',timeout=8)
        latency = (time.perf_counter()-tick)*1000
        number = len(samples)
        (directory/f'gfxinfo-{number:02d}.txt').write_text(text,encoding='utf-8')
        parsed = analizar_gfxinfo(text)
        sample = {'elapsed_seconds':round(time.monotonic()-start,3),
                  'adb_latency_ms':round(latency,2),**parsed}
        samples.append(sample)
        if parsed['available'] and previous:
            frames = parsed['total_frames']-previous['total_frames']
            bad = parsed['janky_frames']-previous['janky_frames']
            if frames>0 and 0<=bad<=frames:
                intervals.append({'frames':frames,'janky_frames':bad,
                                  'jank_percent':round(100*bad/frames,2)})
            elif frames<0 or bad<0:
                sample['counter_reset_or_process_changed'] = True
        previous = parsed if parsed['available'] else None
        remaining = seconds-(time.monotonic()-start)
        if remaining<=0:
            break
        time.sleep(min(3,remaining))
    meaningful = [x for x in intervals if x['frames']>=10]
    sustained = sum(x['jank_percent']>=10 for x in meaningful)>=3
    result = {'requested_seconds':seconds,'actual_seconds':round(time.monotonic()-start,3),
              'samples':samples,'intervals':intervals,
              'status':('warning' if sustained else 'measured') if meaningful else 'inconclusive',
              'sustained_jank_warning':sustained,
              'criterion':'Heurística QA: al menos 3 intervalos con >=10 frames y >=10% jank.',
              'limitation':'gfxinfo mide UI HWUI; no acredita frames de video/SurfaceView ni causa de red.'}
    (directory/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def abrir_imagen(path):
    if os.name=='nt':
        os.startfile(str(Path(path).resolve()))


def diagnosticar_dispositivo(*, package=TIKTOK_PACKAGE, directory='sessions', preguntar=input,
                            check=lambda:None, open_viewer=True):
    verificar_adb()
    device_id = primer_dispositivo_usb()
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    output = directory/'diagnostics.json'
    report = {'started_at':datetime.now(timezone.utc).isoformat(),'udid':device_id,
              'package':package,'status':'incomplete','openai_requests':0,
              'network_modified':False,'visual':{},'keyboard':{},'performance':{}}
    try:
        check()
        print(f'Diagnóstico físico USB: {device_id}. No se publicarán comentarios ni likes.',flush=True)
        report['android_http_proxy'] = shell(device_id,'settings','get','global','http_proxy')
        preguntar('Deja visible la pantalla Para Ti de TikTok y pulsa Enter: ')
        begin = time.perf_counter()
        components = capturar_pantalla_y_xml(device_id,sessions=directory)
        if package not in {n.get('package') for n in components.get('text_components',[])}:
            raise ValueError('El mapa no contiene el paquete esperado; usa --package para tu variante')
        capturar_png(device_id,directory/'current_screen.png')
        report['visual'] = generar_overlay(directory/'current_screen.png',directory/'components.json',
                                          directory/'debug_layout.png')
        report['visual']['capture_and_overlay_ms'] = round((time.perf_counter()-begin)*1000,2)
        try:
            if open_viewer:
                abrir_imagen(directory/'debug_layout.png')
        except OSError as exc:
            report['visual']['viewer_error'] = str(exc)
        answer = preguntar(f'Abre {directory / "debug_layout.png"}. ¿Los rectángulos y cruces '
                           'coinciden con descripción, like y comentarios? [s/n]: ')
        report['visual']['operator_confirmed'] = answer.strip().lower() in ('s','si','sí')
        try:
            report['keyboard'] = probar_teclado(device_id,directory,preguntar=preguntar)
        except ValueError as exc:
            report['keyboard'] = {'status':'failed','error':str(exc)}
            print(f'ALERTA teclado: {exc}. Revisa ADBKeyBoard en los ajustes de Android.',flush=True)
        preguntar('Regresa manualmente a Para Ti de TikTok. Pulsa Enter para observar 12–28 segundos: ')
        current = capturar_pantalla_y_xml(device_id,sessions=directory/'performance'/'ui')
        if package not in {n.get('package') for n in current.get('text_components',[])}:
            raise ValueError('TikTok no está visible para la medición')
        report['performance'] = medir_rendimiento(device_id,package,directory,check=check)
        visual_ok = (report['visual']['operator_confirmed'] and
                     all(report['visual']['counts'].values()) and not report['visual']['warnings'])
        report['status'] = ('passed' if visual_ok and report['keyboard'].get('exact_text_match')
                            and report['performance']['status']=='measured' else 'needs_review')
        report['scope'] = 'Revisión visual humana, Unicode XML y rendimiento HWUI en una ventana; no certificación de red.'
        print(f"Diagnóstico: {report['status']}. Informe: {output.resolve()}",flush=True)
        return report
    except BaseException as exc:
        report['status'] = 'aborted'
        report['error_type'] = type(exc).__name__
        report['error'] = str(exc)
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

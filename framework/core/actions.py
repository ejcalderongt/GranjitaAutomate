"""Acciones Android y web, evidencia visual y adaptador de cursor opcional."""
import math
import random
import logging
import sys
import inspect
import os
import re
import subprocess
import tempfile
import importlib
import threading
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import suppress
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.actions import interaction as Interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# No sustituir carpetas existentes ni instalar dependencias mediante pip al arrancar.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def preparar_ghost_cursor(root=None, repository=None):
    """Clonación opcional y acotada; un único instalador entre procesos.

    GHOST_CURSOR_REPOSITORY debe identificar un repositorio HTTPS de GitHub.
    La página principal de GitHub no identifica un repositorio clonable.
    GHOST_CURSOR_AUTOCLONE=0 permite desactivar la descarga en pruebas/offline.
    """
    root = Path(root or _PROJECT_ROOT).resolve()
    target = root/'ghost_cursor'
    if target.exists():
        return target.is_dir()
    if os.getenv('GHOST_CURSOR_AUTOCLONE', '1') == '0':
        return False
    repository = repository or os.getenv('GHOST_CURSOR_REPOSITORY', '')
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository):
        return False
    lock = root/'.ghost-cursor-install.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        return False  # Otro proceso prepara el adaptador; este usa el fallback.
    except OSError:
        return False
    try:
        handle.close()
        if target.exists():
            return target.is_dir()
        with tempfile.TemporaryDirectory(prefix='.ghost-cursor-', dir=root) as staging:
            checkout = Path(staging)/'checkout'
            environment = os.environ.copy()
            environment['GIT_TERMINAL_PROMPT'] = '0'
            environment['GCM_INTERACTIVE'] = 'Never'
            subprocess.run(['git', 'clone', '--depth', '1', '--', repository, str(checkout)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15, env=environment, cwd=root,
                **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            if not (checkout/'ghost_cursor.py').is_file():
                logging.getLogger(__name__).warning('Adaptador descargado sin ghost_cursor.py; se mantiene el método estándar')
                return False
            checkout.rename(target)
        importlib.invalidate_caches()
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning('Preparación de cursor no disponible (%s); método estándar activo',
            type(exc).__name__)
        return False
    finally:
        with suppress(OSError):
            lock.unlink()


from core.project_env import load_project_environment
load_project_environment()
try:
    from ghost_cursor.ghost_cursor import create_cursor
except Exception as exc:
    create_cursor = None
    logging.getLogger(__name__).warning(
        'ghost_cursor no está disponible (%s); arrastre estándar activo. '
        'La descarga requiere GHOST_CURSOR_REPOSITORY con una URL completa.', type(exc).__name__)


def iniciar_preparacion_cursor():
    """Descargar y cargar en segundo plano; las cuentas pueden usar el fallback."""
    if create_cursor is not None or os.getenv('GHOST_CURSOR_AUTOCLONE', '1') == '0':
        return None
    repository = os.getenv('GHOST_CURSOR_REPOSITORY', '')
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository):
        return None

    def prepare():
        global create_cursor
        try:
            if preparar_ghost_cursor(repository=repository):
                importlib.invalidate_caches()
                from ghost_cursor.ghost_cursor import create_cursor as factory
                if not callable(factory):
                    raise TypeError('El adaptador requiere una función create_cursor')
                create_cursor = factory
        except Exception as exc:
            logging.getLogger(__name__).warning('Cursor opcional no cargado (%s); método estándar activo',
                type(exc).__name__)

    thread = threading.Thread(target=prepare, name='cursor-setup', daemon=True)
    thread.start()
    return thread


_cursor_setup_thread = iniciar_preparacion_cursor()


def cursor_global(page):
    """Adaptador opcional del paquete Python instalado, sin descargar sustitutos."""
    try:
        from playwright_ghost_cursor import create_cursor as factory
    except ImportError:
        return None
    cursor=factory(page)
    if inspect.isawaitable(cursor):
        if inspect.iscoroutine(cursor):
            cursor.close()
        raise TypeError('Se requiere adaptador de cursor síncrono')
    return cursor


def simular_movimiento_tactil_humano(page, selector_destino, *, scope=None):
    """Posicionar y pulsar el primer control visible del contenedor activo."""
    target=(scope or page).locator(selector_destino).first
    target.wait_for(state='visible',timeout=5000)
    try:
        cursor=cursor_global(page)
        if cursor is not None:
            box=target.bounding_box()
            if not box:
                raise ValueError('Control sin geometría visible')
            move=cursor.move_to(box['x']+box['width']/2,box['y']+box['height']/2)
            if inspect.isawaitable(move):
                if inspect.iscoroutine(move):
                    move.close()
                raise TypeError('Se requiere move_to síncrono')
    except Exception as exc:
        logging.getLogger(__name__).warning('Posicionamiento opcional no disponible (%s); control estándar activo',type(exc).__name__)
    # Una sola operación con efecto externo; no repetir si el resultado es incierto.
    target.click(timeout=5000)


def hacer_swipe_feed_tiktok(page, account_id='cuenta'):
    return hacer_swipe_down_movil(page,account_id)


def simular_entrada_tactil(page, selector=None):
    """API compatible del panel; no reintentar un click con resultado incierto."""
    if selector:
        if not page.locator(selector).first.is_visible():
            return False
        simular_movimiento_tactil_humano(page,selector)
        return True
    size=page.viewport_size or {'width':390,'height':844}
    x=random.uniform(.26,.82)*size['width']
    y=random.uniform(.24,.66)*size['height']
    page.mouse.move(x,y,steps=random.randint(18,30))
    return True


def ejecutar_swipe_feed(page, account_id='cuenta'):
    """Compatibilidad con el fragmento del panel, conservando captura y limpieza."""
    result=hacer_swipe_feed_tiktok(page,account_id)
    page.wait_for_timeout(random.uniform(1000,2500))
    return result


def ejecutar_swipe_vertical(driver, *, rng=None):
    rng = rng or random.Random()
    size = driver.get_window_size()
    w, h = int(size['width']), int(size['height'])
    if w < 40 or h < 80:
        raise ValueError('Pantalla demasiado pequeña')
    x, y = w*rng.uniform(.42,.58), h*rng.uniform(.76,.84)
    end_y, drift = h*rng.uniform(.20,.28), w*rng.uniform(-.04,.04)
    bend, steps, duration = w*rng.uniform(-.025,.025), 20, rng.randint(420,680)
    finger = PointerInput(Interaction.POINTER_TOUCH, 'finger')
    actions = ActionBuilder(driver, mouse=finger)
    points = []
    finger.create_pointer_move(duration=0, x=round(x), y=round(y), origin='viewport')
    finger.create_pointer_down(button=0)
    for i in range(1, steps+1):
        t = i/steps
        eased = (1-math.cos(math.pi*t))/2
        px = max(1, min(w-2, round(x+drift*eased+bend*math.sin(math.pi*t))))
        py = max(1, min(h-2, round(y+(end_y-y)*eased)))
        points.append([px,py])
        finger.create_pointer_move(duration=duration//steps,x=px,y=py,origin='viewport')
    finger.create_pointer_up(button=0)
    try:
        actions.perform()
    finally:
        with suppress(Exception):
            actions.clear_actions()
    return {'screen':size,'points':points,'duration_ms':duration//steps*steps}


def interactuar_elemento_nativo(driver, selector_xpath, timeout=8):
    element = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((AppiumBy.XPATH, selector_xpath)))
    element.click()
    return element


def guardar_evidencia_visual(page, account_id, accion_tipo):
    """Captura PNG acotada; un fallo de captura no termina otras cuentas."""
    from core.browser import ROOT, directorio_cuenta, validar_account_id
    validar_account_id(account_id)
    validar_account_id(accion_tipo)
    temporary = None
    try:
        folder = directorio_cuenta(ROOT/'logs', account_id)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        target = folder/f'{timestamp}_{accion_tipo}.png'
        temporary = folder/f'.{uuid4().hex}.tmp'
        page.screenshot(path=str(temporary), type='png', full_page=False, timeout=5000)
        temporary.replace(target)
        return target
    except Exception as exc:
        logging.getLogger(__name__).warning('Captura fallida para %s: %s', account_id, type(exc).__name__)
        return None
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def hacer_swipe_down_movil(page, account_id: str = 'cuenta', *, rng=None):
    """Arrastre de ratón en viewport móvil, con posicionamiento opcional por cursor.

    El adaptador debe implementar create_cursor(page).move_to(x, y) síncrono.
    Una variante asíncrona se descarta sin mezclar bucles de eventos.
    """
    from core.browser import validar_account_id
    validar_account_id(account_id)
    rng = rng or random.Random()
    size = page.viewport_size or {'width':390, 'height':844}
    width, height = size['width'], size['height']
    if width < 40 or height < 80:
        raise ValueError('Viewport demasiado pequeño')
    x = rng.uniform(180,220)*width/390
    y = rng.uniform(620,720)*height/844
    end_x = max(1, min(width-2, x+rng.uniform(-15,15)*width/390))
    end_y = rng.uniform(180,280)*height/844
    positioned = False
    try:
        cursor=create_cursor(page) if create_cursor is not None else cursor_global(page)
    except Exception as exc:
        cursor=None
        logging.getLogger(__name__).warning('%s: cursor no disponible (%s); arrastre estándar',account_id,type(exc).__name__)
    if cursor is not None:
        try:
            if inspect.isawaitable(cursor):
                if inspect.iscoroutine(cursor):
                    cursor.close()
                raise TypeError('El adaptador requiere API síncrona')
            result = cursor.move_to(x, y)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError('move_to requiere API síncrona')
            positioned = True
        except Exception as exc:
            logging.getLogger(__name__).warning('%s: cursor no disponible (%s); arrastre estándar',
                account_id, type(exc).__name__)
    if not positioned:
        page.mouse.move(x, y, steps=rng.randint(18,30))
    try:
        page.mouse.down()
        steps = rng.randint(18,30)
        duration = rng.uniform(420,680)
        # Distribuir eventos en el tiempo; steps por sí solo no añade latencia.
        for step in range(1,steps+1):
            fraction = (1-math.cos(math.pi*step/steps))/2
            page.mouse.move(x+(end_x-x)*fraction, y+(end_y-y)*fraction, steps=1)
            page.wait_for_timeout(duration/steps)
    finally:
        # Intentar soltar incluso cuando el envío anterior tuvo resultado incierto.
        try:
            page.mouse.up()
        finally:
            guardar_evidencia_visual(page, account_id, 'post_swipe')
    return {'start':[x,y], 'end':[end_x,end_y], 'cursor':positioned}


def escribir_comentario_movil(page, field, text, *, rng=None):
    """Entrada secuencial; Playwright expresa delay en milisegundos."""
    rng = rng or random.Random()
    field.click(timeout=5000)
    field.fill('', timeout=5000)
    for character in text:
        page.keyboard.type(character, delay=rng.uniform(60,190))

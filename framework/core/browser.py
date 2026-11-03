"""Perfiles móviles persistentes de Playwright, independientes de Android."""
import re
import os
from pathlib import Path
from urllib.parse import urlsplit,unquote
from tiktok_warmer.core.socks_bridge import proxy_para_chromium, BrowserRuntime

ROOT = Path(__file__).resolve().parents[1]


def validar_account_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError('account_id requiere 1–64 letras, números, guiones o guion bajo')
    reserved = {'con', 'prn', 'aux', 'nul', 'farm', 'local_proxy', 'diagnostics'}
    reserved.update(f'{prefix}{n}' for prefix in ('com', 'lpt') for n in range(1, 10))
    if value.lower() in reserved:
        raise ValueError('account_id reservado')
    return value


def directorio_cuenta(root, account_id):
    validar_account_id(account_id)
    root = Path(root).resolve()
    target = root / account_id
    if target.resolve().parent != root:
        raise ValueError('El perfil debe permanecer dentro del directorio de cuentas')
    target.mkdir(parents=True, exist_ok=True)
    return target


def opciones_proxy(proxy):
    """Normaliza autenticación sin incluir credenciales en el endpoint registrado."""
    if proxy.get('server'):
        parsed=urlsplit(proxy['server'])
        if parsed.scheme not in ('http','https','socks5') or not parsed.hostname or not parsed.port:
            raise ValueError('Proxy HTTP/SOCKS5 inválido')
        options={'server':f'{parsed.scheme}://{parsed.hostname}:{parsed.port}'}
        if parsed.username is not None:
            options.update(username=unquote(parsed.username),password=unquote(parsed.password or ''))
    else:
        options={'server':f"http://{proxy['host']}:{proxy['port']}"}
    for key in ('username','password'):
        if proxy.get(key) is not None:
            options[key]=proxy[key]
    if bool(options.get('username')) != bool(options.get('password')):
        raise ValueError('El proxy requiere usuario y contraseña completos')
    return options


def proxy_desde_entorno():
    """Configuración privada para una apertura explícita fuera del pool de cuentas."""
    from dotenv import dotenv_values
    settings = {**dotenv_values(ROOT/'.env'),
                **dotenv_values(ROOT/'tiktok_warmer/.env'), **os.environ}
    server = settings.get('PROXY_URL', '')
    if settings.get('PROXY_HOST') or settings.get('PROXY_PORT'):
        host, port = settings.get('PROXY_HOST'), settings.get('PROXY_PORT')
        if not host or not port or any(c in host for c in '/@?#:'):
            raise ValueError('PROXY_HOST y PROXY_PORT incompletos o inválidos')
        server = f'{urlsplit(server).scheme}://{host}:{port}'
    result = {'server': server}
    for key, alias in (('username', 'USER'), ('password', 'PASS')):
        value = settings.get('PROXY_'+key.upper()) or settings.get('PROXY_'+alias)
        if value:
            result[key] = value
    if result.get('password') == 'MI_CONTRASENA_REAL':
        raise ValueError('Contraseña del proxy pendiente')
    return result


def iniciar_contexto_seguro(account_id, puerto_puente_local=None, *, proxy=None,
                            headless=False, sessions_root=None, engine='patchright'):
    """Abrir con puente propio dinámico o un listener externo de loopback explícito."""
    if puerto_puente_local is not None:
        if proxy is not None or isinstance(puerto_puente_local, bool) or not isinstance(puerto_puente_local, int) or not 1 <= puerto_puente_local <= 65535:
            raise ValueError('Puerto de puente inválido o configuración ambigua')
        selected = {'server': f'http://127.0.0.1:{puerto_puente_local}'}
    else:
        selected = proxy if proxy is not None else proxy_desde_entorno()
    return iniciar_navegador_tiktok(account_id, selected, headless=headless,
        sessions_root=sessions_root, engine=engine)


def cerrar_contexto_seguro(context, playwright):
    """Intentar ambos cierres; cualquier fallo impide acreditar una limpieza completa."""
    clean = True
    for resource, method in ((context, 'close'), (playwright, 'stop')):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception:
                clean = False
    return clean


def iniciar_navegador_tiktok(account_id, proxy, *, headless=False, sessions_root=None, engine='playwright'):
    if engine=='patchright':
        from patchright.sync_api import sync_playwright
    elif engine=='playwright':
        from playwright.sync_api import sync_playwright
    else:
        raise ValueError('Motor web desconocido')
    folder = directorio_cuenta(sessions_root or ROOT/'sessions', account_id)
    proxy_options, bridge = proxy_para_chromium(opciones_proxy(proxy))
    playwright = None
    try:
        playwright = BrowserRuntime(sync_playwright().start(), bridge)
        device = {key:value for key,value in playwright.devices['Pixel 5'].items()
                  if key != 'default_browser_type'}
        device['viewport'] = {'width':390, 'height':844}
        context = playwright.chromium.launch_persistent_context(
            str(folder), headless=headless,
            proxy=proxy_options,
            **device)
        context.set_default_timeout(10000)
        context.set_default_navigation_timeout(30000)
        return playwright, context, context.pages[0] if context.pages else context.new_page()
    except BaseException:
        if playwright:
            playwright.stop()
        elif bridge:
            bridge.close()
        raise


async def iniciar_contexto_async(account_id, proxy, *, headless=False, sessions_root=None, engine='patchright'):
    """Page asíncrona; el puente continúa en su loop independiente."""
    import asyncio
    if engine == 'patchright':
        from patchright.async_api import async_playwright
    elif engine == 'playwright':
        from playwright.async_api import async_playwright
    else:
        raise ValueError('Motor web desconocido')
    folder = directorio_cuenta(sessions_root or ROOT/'sessions', account_id)
    start_bridge = asyncio.create_task(asyncio.to_thread(proxy_para_chromium, opciones_proxy(proxy)))
    try:
        options, bridge = await asyncio.shield(start_bridge)
    except asyncio.CancelledError:
        _, bridge = await start_bridge
        if bridge is not None:
            await asyncio.to_thread(bridge.close)
        raise
    runtime = context = None
    try:
        runtime = await async_playwright().start()
        device = {k:v for k,v in runtime.devices['Pixel 5'].items() if k != 'default_browser_type'}
        device['viewport'] = {'width':390, 'height':844}
        context = await runtime.chromium.launch_persistent_context(str(folder), headless=headless, proxy=options, **device)
        context.set_default_timeout(5000)
        context.set_default_navigation_timeout(30000)
        return runtime, context, context.pages[0] if context.pages else await context.new_page(), bridge
    except BaseException:
        await cerrar_contexto_async(context, runtime, bridge)
        raise


async def cerrar_contexto_async(context, runtime, bridge, *, close_timeout=10):
    import asyncio
    clean = True
    for resource, method in ((context, 'close'), (runtime, 'stop')):
        if resource is not None:
            try:
                await asyncio.wait_for(getattr(resource, method)(),timeout=close_timeout)
            except Exception:
                clean = False
    if bridge is not None:
        try:
            await asyncio.to_thread(bridge.close)
        except Exception:
            clean = False
    return clean

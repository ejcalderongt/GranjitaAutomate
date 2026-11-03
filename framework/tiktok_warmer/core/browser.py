"""Contexto móvil Chromium para pruebas autorizadas de conectividad."""
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote
from .socks_bridge import proxy_para_chromium, BrowserRuntime

ROOT = Path(__file__).resolve().parents[1]


def configurar_proxy(url, username=None, password=None):
    parsed = urlsplit(url or '')
    if parsed.scheme not in ('http', 'https', 'socks5') or not parsed.hostname or not parsed.port:
        raise ValueError('PROXY_URL requiere HTTP(S) o SOCKS5 con host y puerto explícito')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('PROXY_URL no admite rutas, consultas ni fragmentos')
    host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
    config = {'server': f'{parsed.scheme}://{host}:{parsed.port}'}
    user = username if username else unquote(parsed.username or '')
    secret = password if password else unquote(parsed.password or '')
    if bool(user) != bool(secret):
        raise ValueError('La autenticación requiere usuario y contraseña completos')
    if user:
        config.update(username=user, password=secret)
    return config


def iniciar_navegador_tiktok(account_id, proxy_url=None, *, username=None, password=None, headless=False):
    from patchright.sync_api import sync_playwright
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', account_id):
        raise ValueError('Identificador de cuenta inválido')
    proxy = configurar_proxy(proxy_url, username, password)
    proxy, bridge = proxy_para_chromium(proxy)
    playwright = None
    try:
        playwright = BrowserRuntime(sync_playwright().start(), bridge)
        # Emulación de Chromium móvil; no afirma representar Safari de iPhone.
        profile = {k: v for k, v in playwright.devices['Pixel 5'].items() if k != 'default_browser_type'}
        profile['viewport'] = {'width': 390, 'height': 844}
        context = playwright.chromium.launch_persistent_context(
            str(ROOT / 'sessions' / account_id), proxy=proxy, headless=headless, **profile)
        context.set_default_navigation_timeout(30000)
        return playwright, context, context.pages[0] if context.pages else context.new_page()
    except BaseException:
        if playwright:
            playwright.stop()
        elif bridge:
            bridge.close()
        raise

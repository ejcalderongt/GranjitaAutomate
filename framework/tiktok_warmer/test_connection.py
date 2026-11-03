"""Preflight auditable: proxy, IP, geolocalización y Chromium móvil."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
import ipaddress
import json
import os
import re
from pathlib import Path
import sys
import uuid
from urllib.parse import urlsplit
import httpx

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from tiktok_warmer.core.browser import configurar_proxy, iniciar_navegador_tiktok
from core.geo_resolver import obtener_geolocalizacion_con_bypass


async def resolver_geo_por_proxy(ip, runtime, options):
    """Usar el mismo puente; nunca abrir una ruta directa si falla el proxy."""
    bridge = getattr(runtime, 'bridge', None)
    if bridge is not None:
        endpoint = bridge.endpoint
        if not isinstance(endpoint, str) or not endpoint.startswith('http://127.0.0.1:'):
            raise ValueError('Listener local inválido para GeoIP')
        proxy = httpx.Proxy(endpoint)
    else:
        if options['server'].startswith('socks5://') and options.get('username'):
            raise ValueError('SOCKS5 autenticado requiere un puente activo')
        auth = (options['username'], options['password']) if options.get('username') else None
        proxy = httpx.Proxy(options['server'], auth=auth)
    async with httpx.AsyncClient(proxy=proxy, timeout=10, trust_env=False, follow_redirects=False) as client:
        return await obtener_geolocalizacion_con_bypass(ip, cliente_http=client)


def resolver_geo_en_worker(ip, runtime, options):
    """Playwright síncrono ya ejecuta un loop; no anidar asyncio.run en su hilo."""
    bridge = getattr(runtime, 'bridge', None)
    loop = getattr(bridge, 'loop', None)
    if isinstance(loop, asyncio.AbstractEventLoop) and loop.is_running():
        pending = asyncio.run_coroutine_threadsafe(resolver_geo_por_proxy(ip, runtime, options), loop)
        try:
            return pending.result(timeout=35)
        except FutureTimeout:
            pending.cancel()
            raise TimeoutError('GeoIP excedió el presupuesto de ejecución') from None
    # HTTP directo o listener externo: loop propio de worker, nunca en el hilo
    # del navegador. El cliente se crea y se cierra dentro del mismo loop.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='geoip-worker') as executor:
        return executor.submit(lambda: asyncio.run(resolver_geo_por_proxy(ip, runtime, options))).result()


def clasificar_error(exc):
    # Nunca persistir el texto original de Playwright: puede contener secretos.
    text = str(exc).upper()
    if '407' in text or 'INVALID_AUTH_CREDENTIALS' in text:
        return 'proxy_authentication_failed'
    if 'PROXY_CONNECTION_FAILED' in text or 'TUNNEL_CONNECTION_FAILED' in text:
        return 'proxy_connection_or_connect_failed'
    if 'EXECUTABLE DOESN' in text:
        return 'browser_not_installed'
    if 'TIMEOUT' in text or type(exc).__name__ == 'TimeoutError':
        return 'network_timeout'
    return 'configuration_invalid' if isinstance(exc, ValueError) else 'network_or_browser_error'


def probar_infraestructura(*, headless=False, check_tiktok=False):
    settings = {**dotenv_values(PROJECT / '.env'), **dotenv_values(ROOT / '.env'), **os.environ}
    report = {'run_id': uuid.uuid4().hex, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'failed', 'stage': 'configuration', 'browser_initialized': False,
              'proxy_connectivity': False, 'authentication': 'not_verified',
              'proxy_verified': False, 'cleanup_confirmed': False,
              'region_verified': False, 'expected_continent': 'EU', 'observed_ip': None,
              'scope': 'browser HTTPS requests only; no Android VPN or leak certification'}
    playwright = context = None
    try:
        url = settings.get('PROXY_URL')
        username = settings.get('PROXY_USERNAME') or settings.get('PROXY_USER')
        password = settings.get('PROXY_PASSWORD') or settings.get('PROXY_PASS')
        if settings.get('PROXY_HOST') or settings.get('PROXY_PORT'):
            host, port = settings.get('PROXY_HOST'), settings.get('PROXY_PORT')
            if not host or not port or any(c in host for c in '/@?#:'):
                raise ValueError('PROXY_HOST y PROXY_PORT incompletos o inválidos')
            scheme = urlsplit(url or '').scheme
            url = f'{scheme}://{host}:{port}'
        if password == 'MI_CONTRASENA_REAL':
            report['error_code'] = 'proxy_password_pending'
            print('[Diagnóstico] Falta sustituir MI_CONTRASENA_REAL en tiktok_warmer/.env')
            return 2, report
        proxy = configurar_proxy(url, username, password)
        report['proxy_endpoint'] = proxy['server']
        report['transport'] = 'loopback_http_to_authenticated_socks5' if proxy['server'].startswith('socks5://') and proxy.get('username') else 'direct_proxy'
        print('[Diagnóstico] Proxy: ' + proxy['server'])
        report['stage'] = 'browser_start'
        playwright, context, page = iniciar_navegador_tiktok('proxy_diagnostic', url,
            username=username, password=password, headless=headless)
        report['browser_initialized'] = True
        report['stage'] = 'proxy_https'
        response = page.goto('https://api.ipify.org?format=json', wait_until='domcontentloaded')
        report['http_status'] = response.status if response else None
        if response is None or response.status != 200:
            raise RuntimeError('IP probe HTTP status invalid')
        observed = str(ipaddress.ip_address(json.loads(page.locator('body').inner_text())['ip']))
        report.update(observed_ip=observed, proxy_connectivity=True, proxy_verified=True,
            authentication='accepted' if proxy.get('username') else 'no_credentials_supplied_connection_accepted')
        print('[Diagnóstico] IP observada: ' + observed)
        report['stage'] = 'geolocation'
        geo = resolver_geo_en_worker(observed, playwright, proxy)
        report.update(continent_code=geo['continente'], detected_continent=geo['continente'],
                      country_code=geo['pais'], geo_source=geo['provider_used'],
                      geo_provider_used=geo['provider_used'], geo_fallback_used=geo['fallback_used'],
                      geo_attempts=geo['attempts'], geo_status=geo['geo_status'],
                      geo_transport=geo.get('transport'),
                      region_verified=geo['geo_status'] == 'resolved' and geo['continente'] == 'EU')
        if geo['geo_status'] != 'resolved':
            report.update(status='partial', error_code='geo_unavailable')
            print('[Diagnóstico] Proxy verificado; región desconocida: proveedores GeoIP no disponibles')
            return 2, report
        print('[Diagnóstico] Región Europa: ' + ('confirmada por geolocalización' if report['region_verified'] else 'no coincide'))
        if not report['region_verified']:
            report.update(status='region_mismatch', error_code='region_mismatch')
            return 2, report
        if check_tiktok:
            report['stage'] = 'tiktok_navigation'
            response = page.goto('https://www.tiktok.com/foryou', wait_until='domcontentloaded')
            report['tiktok_http_status'] = response.status if response else None
            # Un HTTP 200 no acredita login, ausencia de desafíos ni interacción.
        report.update(status='passed', stage='completed')
        return 0, report
    except Exception as exc:
        report['error_code'] = clasificar_error(exc)
        report['error_type'] = type(exc).__name__
        report['network_codes'] = re.findall(r'(?:ERR_|SSL_)[A-Z_]+', str(exc))
        print('[Diagnóstico] Fallo: ' + report['error_code'])
        if report['network_codes']:
            print('[Diagnóstico] Código de red: ' + ', '.join(report['network_codes']))
        return 2, report
    finally:
        for resource, method in ((context, 'close'), (playwright, 'stop')):
            if resource:
                try:
                    getattr(resource, method)()
                except Exception:
                    report.setdefault('cleanup_errors', []).append(method)
                    report['status'] = 'failed'
        report['cleanup_confirmed'] = not report.get('cleanup_errors')
        report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
        folder = PROJECT / 'runs' / ('proxy-preflight-' + report['run_id'])
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / 'resultado.json'
        destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print('[Diagnóstico] Reporte: ' + str(destination))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--check-tiktok', action='store_true')
    args = parser.parse_args()
    code, report = probar_infraestructura(headless=args.headless, check_tiktok=args.check_tiktok)
    return code if report['status'] == 'passed' else 2


if __name__ == '__main__':
    sys.exit(main())

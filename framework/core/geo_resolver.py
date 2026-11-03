"""GeoIP asíncrono con fallback acotado y trazabilidad por proveedor."""
import asyncio
import ipaddress
import logging
import re
import time

import httpx

logger = logging.getLogger('warmer.geo')
CONTINENTS = frozenset(('AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA'))
# Europa geográfica, no pertenencia a la Unión Europea. Los países
# transcontinentales requieren el continente específico del proveedor.
EUROPE = frozenset('AD AL AT AX BA BE BG BY CH CZ DE DK EE ES FI FO FR GB GG GI GR HR HU IE IM IS IT JE LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS SE SI SJ SK SM UA VA XK'.split())
AMBIGUOUS = frozenset(('RU', 'TR', 'KZ', 'GE', 'AZ', 'CY', 'AM'))


def _normalizar(name, data, target):
    if not isinstance(data, dict) or data.get('status') == 'fail' or data.get('error'):
        raise ValueError('provider_payload_error')
    ip_field, country_field, continent_field = (
        ('query', 'countryCode', 'continentCode') if name == 'ip-api.com' else
        ('ip', 'country', 'continent_code') if name == 'ipinfo.io' else
        ('ip', 'country_code', 'continent_code'))
    if str(ipaddress.ip_address(data.get(ip_field, ''))) != target:
        raise ValueError('ip_mismatch')
    country = data.get(country_field)
    if not isinstance(country, str) or not re.fullmatch('[A-Z]{2}', country) or country in ('ZZ', 'XX'):
        raise ValueError('invalid_country')
    continent = data.get(continent_field)
    source = 'provider'
    if continent not in CONTINENTS:
        if name != 'ipinfo.io' or country in AMBIGUOUS:
            raise ValueError('continent_unknown')
        continent = 'EU' if country in EUROPE else 'OTHER'
        source = 'country_fallback_europe_vs_other'
    org = data.get('org') or data.get('isp') or 'UNKNOWN'
    return {'pais': country, 'continente': continent,
            'org': org[:300] if isinstance(org, str) else 'UNKNOWN',
            'provider_used': name, 'ip': target, 'continent_source': source}


async def obtener_geolocalizacion_con_bypass(ip_objetivo, cliente_http=None):
    """Un intento por proveedor; no reintenta cuotas ni cierra clientes prestados."""
    target = str(ipaddress.ip_address(ip_objetivo))
    if not ipaddress.ip_address(target).is_global:
        raise ValueError('GeoIP requiere una IP pública')
    providers = (
        ('ipapi.co', f'https://ipapi.co/{target}/json/'),
        ('ip-api.com', f'http://ip-api.com/json/{target}?fields=status,message,query,countryCode,continentCode,org,isp'),
        ('ipinfo.io', f'https://ipinfo.io/{target}/json'),
    )
    own_client = cliente_http is None
    client = cliente_http if cliente_http is not None else httpx.AsyncClient(timeout=10, trust_env=False)
    attempts = []
    try:
        for name, url in providers:
            started = time.perf_counter()
            attempt = {'provider': name, 'transport': url.split(':', 1)[0]}
            try:
                async with asyncio.timeout(10):
                    response = await client.get(url, timeout=10, follow_redirects=False)
                attempt['http_status'] = response.status_code
                if response.status_code == 429:
                    attempt['outcome'] = 'rate_limited'
                    logger.info('GeoIP: cuota agotada en %s; consultar siguiente proveedor', name)
                elif response.status_code != 200:
                    attempt['outcome'] = 'http_error'
                else:
                    result = _normalizar(name, response.json(), target)
                    attempt['outcome'] = 'success'
                    attempt['latency_ms'] = round((time.perf_counter()-started)*1000, 2)
                    attempts.append(attempt)
                    result.update(attempts=attempts, fallback_used=len(attempts) > 1,
                                  geo_status='resolved', transport=attempt['transport'])
                    return result
            except (httpx.RequestError, TimeoutError) as exc:
                attempt.update(outcome='network_error', error_type=type(exc).__name__)
            except (ValueError, TypeError) as exc:
                attempt.update(outcome='invalid_payload', error_type=type(exc).__name__)
            attempt['latency_ms'] = round((time.perf_counter()-started)*1000, 2)
            attempts.append(attempt)
        return {'pais': 'UNKNOWN', 'continente': 'UNKNOWN', 'org': 'UNKNOWN',
                'provider_used': 'FAILED_ALL', 'ip': target, 'attempts': attempts,
                'fallback_used': len(attempts) > 1, 'geo_status': 'unavailable'}
    finally:
        if own_client:
            await client.aclose()

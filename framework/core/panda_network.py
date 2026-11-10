"""Bounded connectivity checks from the enrolled Android hardware."""
import asyncio
import ipaddress
import re

from config.farm_preflight import timezone_country
from config.proxies import adb, ADBError
from core.adb_pool import ADBServer, DeviceRoute
from core.panda_identity import leer_identidad_fisica

HOST = 'ipv4.icanhazip.com'
PACKAGE = 'com.zhiliaoapp.musically'
ADB_FAILURES = (ADBError, OSError, ValueError)


def plate_route(plate):
    host, _, port = plate['server'].rpartition(':')
    return DeviceRoute(plate['transporte'], ADBServer(host.strip('[]'), int(port)), 'device')


def shell_route(route, *command, timeout):
    return adb('-H', route.server.host, '-P', str(route.server.port), '-s',
               route.serial, 'shell', *command, timeout=timeout)


def probe_plate(plate):
    route = plate_route(plate)
    try:
        if leer_identidad_fisica(route) != plate['serial']:
            return 'identity_unverified'
    except ADB_FAILURES:
        return 'identity_unverified'
    try:
        tool = shell_route(route, 'command -v curl || true', timeout=3)
        if tool:
            result = shell_route(route, 'curl', '-fsS', '--max-time', '5', f'https://{HOST}', timeout=7)
            if ipaddress.ip_address(result).version == 4:
                return 'https_ok'
            return 'network_failed'
        shell_route(route, 'ping', '-c', '1', '-W', '3', HOST, timeout=5)
        return 'ping_ok'
    except ADB_FAILURES:
        return 'network_failed'


def foreground(route):
    result = shell_route(route, 'dumpsys window | grep -E "mCurrentFocus=" || true', timeout=5)
    return any(re.search(r'\b' + re.escape(PACKAGE) + '/', line) for line in result.splitlines())


def open_tiktok(route):
    launcher = ('-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER')
    resolved = shell_route(route, 'cmd', 'package', 'resolve-activity', '--brief',
                           *launcher, PACKAGE, timeout=5)
    components = [line.strip() for line in resolved.splitlines()
                  if re.fullmatch(re.escape(PACKAGE) + r'/[A-Za-z0-9_.$]+', line.strip())]
    if len(components) != 1:
        return
    shell_route(route, 'input', 'keyevent', 'KEYCODE_WAKEUP', timeout=4)
    shell_route(route, 'am', 'start', '-W', *launcher, '-n', components[0], timeout=12)


def prepare_plate(plate, country, target_zone):
    route = plate_route(plate)
    state = {'app':'unchecked','locale':'unchecked','timezone':'unchecked'}
    try:
        if leer_identidad_fisica(route) != plate['serial']:
            return state
    except ADB_FAILURES:
        return state
    try:
        if not foreground(route):
            open_tiktok(route)
        state['app'] = 'ok' if foreground(route) else 'manual'
    except ADB_FAILURES:
        state['app'] = 'manual'
    try:
        locale = shell_route(route, 'getprop persist.sys.locale; getprop ro.product.locale', timeout=5)
        first = locale.splitlines()[0].strip() if locale else ''
        region = re.search(r'[_-]([A-Za-z]{2})$', first)
        state['locale'] = 'ok' if region and region[1].upper() == country else 'manual'
    except ADB_FAILURES:
        state['locale'] = 'manual'
    try:
        zone = shell_route(route, 'getprop', 'persist.sys.timezone', timeout=5)
        if target_zone and zone != target_zone:
            help_text = shell_route(route, 'cmd time_zone_detector help 2>/dev/null || true', timeout=5)
            if 'suggest_manual_time_zone' in help_text and '--zone_id' in help_text:
                automatic = shell_route(route, 'cmd', 'time_zone_detector',
                                        'is_auto_detection_enabled', timeout=5)
                if automatic == 'false':
                    shell_route(route, 'cmd', 'time_zone_detector', 'suggest_manual_time_zone',
                                '--zone_id', target_zone, timeout=5)
                    zone = shell_route(route, 'getprop', 'persist.sys.timezone', timeout=5)
        zone_ok = zone == target_zone if target_zone else timezone_country(zone) == country
        state['timezone'] = 'ok' if zone_ok else 'manual'
    except ADB_FAILURES:
        state['timezone'] = 'manual'
    return state


async def check_devices(plates, *, prepare=None):
    limit = asyncio.Semaphore(4)

    async def check(plate):
        async with limit:
            status = await asyncio.to_thread(probe_plate, plate)
            profile = (await asyncio.to_thread(prepare_plate, plate, *prepare)
                       if prepare and status != 'identity_unverified' else {})
        return {'plate': plate['map_plate'], 'alias': plate['alias'],
                'device_ref': plate['device_ref'], 'network': status, **profile}

    return await asyncio.gather(*(check(plate) for plate in plates))

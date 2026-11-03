"""Identidades TCP Panda verificadas por Android, nunca por IP histórica."""
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from config.device_test import shell
from config.proxies import ADBError, usar_servidor_adb
from core.adb_pool import PoolSnapshot


def serial_util(value):
    value=value.strip()
    if (not re.fullmatch(r'[A-Za-z0-9._-]{5,80}',value)
            or value.lower() in {'unknown','null','none','android','0123456789',
                                 '0123456789abcdef','1234567890','serial','default'}
            or len(set(value))==1):
        return None
    return value


def leer_identidad_fisica(route):
    with usar_servidor_adb(route.server.host,route.server.port):
        if shell(route.serial,'getprop','ro.kernel.qemu',timeout=5).strip()=='1':
            raise ADBError('Panda: transporte apunta a emulador')
        serial=serial_util(shell(route.serial,'getprop','ro.serialno',timeout=5))
        boot=serial_util(shell(route.serial,'getprop','ro.boot.serialno',timeout=5))
    if not serial and not boot:
        raise ADBError('Panda: sin serial físico fiable')
    if serial and boot and serial!=boot:
        raise ADBError('Panda: ro.serialno y ro.boot.serialno discrepan')
    return serial or boot


def confirmar_identidad(route):
    if route.hardware_serial and leer_identidad_fisica(route)!=route.hardware_serial:
        raise ADBError('La identidad física del transporte Panda cambió; operación cancelada')


def resolver_pool_panda(snapshot,database):
    routes=list(snapshot.devices.items())
    def resolve(pair):
        key,route=pair
        if route.status!='device' or ':' not in route.serial:
            return key,route,None
        try:
            physical=leer_identidad_fisica(route)
            database.identidad_agx(physical)  # Validar que el vínculo no sea ambiguo; un serial nuevo es válido.
            return physical,replace(route,hardware_serial=physical),None
        except (ADBError,OSError,ValueError) as exc:
            return key,replace(route,status='identity_unverified'),str(exc)
    devices,errors={},dict(snapshot.identity_errors)
    blocked=set()
    with ThreadPoolExecutor(max_workers=min(8,max(1,len(routes)))) as pool:
        for key,route,error in pool.map(resolve,routes):
            if error:
                errors[route.serial]=error
            if key in blocked:
                continue
            if key in devices and devices[key].serial!=route.serial:
                errors[key]='Varias rutas distintas declaran el mismo serial físico; selección bloqueada'
                del devices[key]
                blocked.add(key)
                continue
            devices[key]=route
    return PoolSnapshot(devices,dict(snapshot.errors),list(snapshot.successful),errors,
                        dict(snapshot.reconnect_errors))

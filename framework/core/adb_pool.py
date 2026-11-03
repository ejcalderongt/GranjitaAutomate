"""Inventario consolidado de servidores ADB explícitos, sin arrancar ni matar Panda."""
import json
import os
import re
import socket
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass,field
from pathlib import Path

from config import proxies

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/'config/adb_servers.json'


@dataclass(frozen=True)
class ADBServer:
    host: str
    port: int=5037

    def __post_init__(self):
        if not re.fullmatch(r'[a-zA-Z0-9_.:-]+',self.host) or not 1<=self.port<=65535:
            raise ValueError('Host/puerto ADB inválido')

    @property
    def key(self):
        return f'[{self.host}]:{self.port}' if ':' in self.host else f'{self.host}:{self.port}'


@dataclass
class DeviceRoute:
    serial: str
    server: ADBServer
    status: str
    origins: list=field(default_factory=list)
    hardware_serial: str | None=None


@dataclass
class PoolSnapshot:
    devices: dict
    errors: dict
    successful: list
    identity_errors: dict=field(default_factory=dict)
    reconnect_errors: dict=field(default_factory=dict)


def cargar_objetivos(servers,path=None):
    config=Path(path or os.getenv('ADB_SERVERS_CONFIG') or DEFAULT_CONFIG)
    raw=json.loads(config.read_text(encoding='utf-8'))
    targets={server:[] for server in servers}
    entries=[item for item in raw['servers'] if isinstance(item,dict)]
    if raw.get('devices_file'):
        local=config.parent/raw['devices_file']
        if local.is_file():
            entries+=json.loads(local.read_text(encoding='utf-8'))['targets']
    for item in entries:
        server=ADBServer(item['host'],int(item.get('port',5037)))
        if server not in targets:
            raise ValueError('Objetivo TCP asignado a un servidor ADB no configurado')
        for address in item.get('devices',[]):
            host,port=address.rsplit(':',1)
            ipaddress.ip_address(host.strip('[]'))
            if not 1<=int(port)<=65535:
                raise ValueError('Puerto de placa TCP fuera de rango')
            if address not in targets[server]:
                targets[server].append(address)
    return targets


def cargar_servidores(path=None):
    if path is None and os.getenv('ADB_SERVERS_CONFIG'):
        path=os.environ['ADB_SERVERS_CONFIG']
    raw=json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding='utf-8'))
    servers=[]
    for item in raw['servers']:
        if isinstance(item,str):
            host,port=item.rsplit(':',1)
            server=ADBServer(host.strip('[]'),int(port))
        else:
            server=ADBServer(item['host'],int(item.get('port',5037)))
        if server not in servers:
            servers.append(server)
    if not servers or len(servers)>32:
        raise ValueError('Configura entre 1 y 32 servidores ADB explícitos')
    return servers


def consultar_servidor(server,timeout=3):
    # El cliente adb puede arrancar un daemon local si no existe. Evitarlo en Panda.
    try:
        with socket.create_connection((server.host,server.port),timeout=min(timeout,1)):
            pass
    except OSError as exc:
        raise proxies.ADBError(f'Servidor {server.key} no accesible: {exc}') from exc
    output=proxies.adb('-H',server.host,'-P',str(server.port),'devices','-l',timeout=timeout)
    if 'List of devices attached' not in output:
        raise proxies.ADBError(f'Inventario incompleto de {server.key}')
    devices={}
    for line in output.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[1] in ('device','offline','unauthorized'):
            devices[parts[0]]=parts[1]
    return devices


def descubrir_pool(servers=None,timeout=3,*,reconnect=False,targets=None,connect_workers=40,initialize_servers=False):
    servers=servers or cargar_servidores()
    targets=(targets if targets is not None else cargar_objetivos(servers)) if reconnect else {}
    devices,errors,successful={},{},[]
    reconnect_errors={}
    def query(server):
        try:
            found=consultar_servidor(server,timeout)
        except proxies.ADBError:
            if not initialize_servers or server.host not in ('127.0.0.1','localhost','::1'):
                raise
            proxies.adb('-H',server.host,'-P',str(server.port),'start-server',timeout=timeout)
            found=consultar_servidor(server,timeout)
        missing=[address for address in targets.get(server,[]) if found.get(address) not in ('device','unauthorized')]
        def connect(address):
            try:
                if found.get(address)=='offline':
                    proxies.adb('-H',server.host,'-P',str(server.port),'disconnect',address,timeout=timeout)
                proxies.adb('-H',server.host,'-P',str(server.port),'connect',address,timeout=timeout)
                return address,None
            except (proxies.ADBError,OSError) as exc:
                return address,str(exc)
        attempts={}
        if missing:
            with ThreadPoolExecutor(max_workers=min(connect_workers,len(missing))) as pool:
                attempts=dict(pool.map(connect,missing))
            found=consultar_servidor(server,timeout)
        # Una respuesta "connected" no basta: volver a confirmar estado device.
        failures={f'{server.key}/{address}':error or 'Conexión TCP no autorizada o no disponible'
                  for address,error in attempts.items() if error or found.get(address)!='device'}
        return found,failures
    with ThreadPoolExecutor(max_workers=min(8,len(servers))) as executor:
        jobs=[(server,executor.submit(query,server)) for server in servers]
        # Orden de configuración estable, sin depender del orden de respuesta.
        for server,future in jobs:
            try:
                found,failures=future.result()
                reconnect_errors.update(failures)
            except (proxies.ADBError,OSError) as exc:
                errors[server.key]=str(exc)
                continue
            successful.append(server)
            for serial,status in found.items():
                if serial not in devices:
                    devices[serial]=DeviceRoute(serial,server,status,[server])
                else:
                    route=devices[serial]
                    route.origins.append(server)
                    if route.status!='device' and status=='device':
                        route.server,route.status=server,status
    return PoolSnapshot(devices,errors,successful,reconnect_errors=reconnect_errors)

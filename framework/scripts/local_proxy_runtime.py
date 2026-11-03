"""Proxy HTTP/CONNECT local, sin interceptar TLS ni ejecutar automatizaciones."""
import json
import ipaddress
import socket
from pathlib import Path
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def detect_host(settings):
    peer=next((ip for ip in settings['allowed_clients'] if ip!=settings['host'] and not ipaddress.ip_address(ip).is_loopback),None)
    if not peer:
        return settings['host']
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as connection:
        connection.connect((peer,9))  # Determinar ruta local sin enviar paquetes.
        return connection.getsockname()[0]


def observe_exit():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('https://api.ipify.org',timeout=4) as response:
        return str(ipaddress.IPv4Address(response.read(80).decode().strip()))


def prepare_settings(root,detect=detect_host,observe=observe_exit):
    config_path=root/'config/local_proxy.local.json'
    settings=json.loads(config_path.read_text(encoding='utf-8'))
    old_host=settings['host']
    try:
        host=str(ipaddress.IPv4Address(detect(settings)))
        if any(ipaddress.ip_address(host) in ipaddress.ip_network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
            settings['host']=host
            settings['allowed_clients']=sorted(set(settings['allowed_clients']+[host]))
    except (ValueError,OSError):
        pass
    pool_path=root/'config/proxy_pool.json'
    pool=json.loads(pool_path.read_text(encoding='utf-8'))
    if pool.get('mode')=='laboratory' and pool.get('lab_host')==old_host:
        pool['lab_host']=settings['host']
        try:
            observed=observe()
            if not ipaddress.ip_address(observed).is_global:
                raise ValueError('Salida no pública')
        except (ValueError,OSError):
            observed=None
        for entry in pool['proxies']:
            if entry['host']==old_host:
                entry['host']=settings['host']
                if observed:
                    entry['exit_ip']=observed
        temporary=pool_path.with_name(pool_path.name+'.runtime.tmp')
        temporary.write_text(json.dumps(pool,indent=2)+'\n',encoding='utf-8')
        temporary.replace(pool_path)
    config_path.write_text(json.dumps(settings,indent=2)+'\n',encoding='utf-8')
    return settings


def main():
    import proxy
    config=prepare_settings(ROOT)
    directory=ROOT/'sessions/local_proxy'
    directory.mkdir(parents=True,exist_ok=True)
    # Los puertos se comparten en un único servicio, con ACL explícita de clientes.
    args=['--hostname',config['host'],'--port',str(config['ports'][0]),
          '--ports',*[str(p) for p in config['ports'][1:]],
          '--num-acceptors','1','--num-workers','1','--log-level','WARNING',
          '--log-file',str(directory/'proxy.log'),'--pid-file',str(directory/'proxy.pid'),
          '--plugins','proxy.plugin.FilterByClientIpPlugin',
          '--filtered-client-ips-mode','whitelist',
          '--filtered-client-ips',','.join(config['allowed_clients'])]
    with proxy.Proxy(args):
        while True:
            time.sleep(1)


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        main()
    except KeyboardInterrupt:
        pass

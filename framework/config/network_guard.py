"""Aislamiento temporal de salida del dispositivo de prueba mediante root."""
import ipaddress
import json
import shlex
import uuid
import re
from contextlib import contextmanager
from pathlib import Path

from config.proxies import ADBError
from config.device_test import shell
from config.proxies import servidor_adb_actual
from core.diagnostic_bridge import escribir_json


def root_executor(device_id):
    if shell(device_id,'id','-u').strip()=='0':
        return lambda *args:shell(device_id,*args)
    if shell(device_id,'su','-c','id -u').strip()!='0':
        raise ADBError('No se obtuvo root')
    return lambda *args:shell(device_id,'su','-c',shlex.join(args))


def canales_gestion(device_id,root):
    """Conservar solo respuestas adbd a peers observados; nunca ACCEPT global established."""
    try:
        address,port=device_id.rsplit(':',1)
        ipaddress.ip_address(address.strip('[]'))
        port=int(port)
    except (ValueError,TypeError):
        return []  # Transporte USB: el firewall IP no corta ese transporte.
    try:
        output=root('ss','-tn')
    except ADBError:
        output=root('netstat','-tn')
    peers=set()
    for line in output.splitlines():
        if not ('ESTAB' in line.upper()):
            continue
        endpoints=[]
        for value in line.split():
            try:
                host,p=value.rsplit(':',1)
                ip=ipaddress.ip_address(host.strip('[]'))
                if getattr(ip,'ipv4_mapped',None):
                    ip=ip.ipv4_mapped
                endpoints.append((str(ip),int(p)))
            except ValueError:
                continue
        if len(endpoints)>=2 and endpoints[-2][1]==port:
            peers.add((endpoints[-1][0],port))
    if not peers:
        raise ADBError('No se pudo identificar el canal ADB TCP; firewall cancelado para no perder gestión')
    return sorted(peers)


@contextmanager
def trafico_restringido(device_id, proxy_host, proxy_port, sessions='sessions',preserve_management=False):
    """Solo TCP hacia el proxy IPv4. Todo otro OUTPUT IPv4/IPv6 se rechaza.

    No intercepta tráfico ni convierte protocolos: una app que ignore el proxy
    perderá conectividad. Requiere root, iptables e ip6tables funcionales.
    """
    directory = Path(sessions)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        policy = shell(device_id, 'dumpsys', 'netpolicy')
    except ADBError as exc:
        policy = f'No disponible: {exc}'
    (directory/'netpolicy.txt').write_text(policy, encoding='utf-8')
    # netpolicy no acredita bloqueo de QUIC, IPv6 ni salida directa.
    try:
        host = str(ipaddress.IPv4Address(proxy_host))
    except ipaddress.AddressValueError as exc:
        raise ADBError('El aislamiento requiere la IPv4 literal del proxy para bloquear '
                       'también DNS directo. No se abrirá la aplicación.') from exc
    try:
        root=root_executor(device_id)
    except ADBError as exc:
        raise ADBError('Sin root no se puede instalar el aislamiento. Se guardó '
                       'sessions/netpolicy.txt como diagnóstico; no prueba restricciones. '
                       'Configura una VPN lockdown o un gateway de laboratorio. App bloqueada.') from exc
    chain = 'PANDA_'+uuid.uuid4().hex[:12]
    management=canales_gestion(device_id,root) if preserve_management else []
    created, hooks = [], []
    lease_path=directory/'firewall_lease.json'
    def guardar_lease():
        escribir_json(lease_path,{'chain':chain,'created':list(created),'hooks':list(hooks),
                               'adb_server':servidor_adb_actual(),'device_id':device_id})
    recovery_path = directory/'firewall_cleanup_required.txt'
    recovery = '\n'.join(
        f'{b} -D OUTPUT -j {chain}; {b} -F {chain}; {b} -X {chain}'
        for b in ('iptables','ip6tables'))
    recovery_path.write_text(f'Dispositivo: {device_id}\nSi se interrumpe el proceso, '
                             f'ejecutar como root:\n{recovery}\n',encoding='utf-8')

    def verificar_reglas():
        for binary in ('iptables', 'ip6tables'):
            root(binary, '-w', '5', '-C', 'OUTPUT', '-j', chain)
            root(binary, '-w', '5', '-C', chain, '-j', 'REJECT')
        root('iptables', '-w', '5', '-C', chain, '-p', 'tcp', '-d', host,
             '--dport', str(proxy_port), '-j', 'ACCEPT')
        for peer,port in management:
            binary='iptables' if ipaddress.ip_address(peer).version==4 else 'ip6tables'
            root(binary,'-w','5','-C',chain,'-p','tcp','--sport',str(port),'-d',peer,
                 '-m','conntrack','--ctstate','ESTABLISHED','-j','ACCEPT')

    try:
        # Comprobar ambas familias antes de modificar ninguna.
        for binary in ('iptables', 'ip6tables'):
            root(binary, '-w', '5', '-S', 'OUTPUT')
        for binary in ('iptables', 'ip6tables'):
            created.append(binary)
            guardar_lease()
            root(binary, '-w', '5', '-N', chain)
            for peer,port in management:
                if (ipaddress.ip_address(peer).version==4)==(binary=='iptables'):
                    root(binary,'-w','5','-A',chain,'-p','tcp','--sport',str(port),'-d',peer,
                         '-m','conntrack','--ctstate','ESTABLISHED','-j','ACCEPT')
            if binary == 'iptables':
                root(binary, '-w', '5', '-A', chain, '-p', 'tcp', '-d', host,
                     '--dport', str(proxy_port), '-j', 'ACCEPT')
            root(binary, '-w', '5', '-A', chain, '-j', 'REJECT')
            # Registrar antes de insertar para cubrir resultado ambiguo por USB.
            hooks.append(binary)
            guardar_lease()
            root(binary, '-w', '5', '-I', 'OUTPUT', '1', '-j', chain)
        verificar_reglas()
        print('Firewall activo: solo TCP hacia el proxy; IPv6 y resto de salida bloqueados.', flush=True)
        (directory/'network_guard.json').write_text(json.dumps({
            'mode':'root_output_allowlist','chain':chain,'proxy_ipv4':host,
            'proxy_port':proxy_port,'dns_direct_blocked':True,
            'management_peers':management,
            'scope':'Android kernel OUTPUT IPv4/IPv6; no garantía sobre offload/OEM'
        },indent=2),encoding='utf-8')
        yield verificar_reglas
    finally:
        errors = []
        for binary in reversed(created):
            try:
                if binary in hooks:
                    root(binary, '-w', '5', '-D', 'OUTPUT', '-j', chain)
                root(binary, '-w', '5', '-F', chain)
                root(binary, '-w', '5', '-X', chain)
            except ADBError as exc:
                errors.append(f'{binary}: {exc}')
        if errors:
            recovery_path.write_text(
                f'Dispositivo: {device_id}\nEjecutar como root al reconectar:\n{recovery}\n'
                +'\n'.join(errors), encoding='utf-8')
            raise ADBError('Limpieza de firewall incompleta. Consulta '
                           'sessions/firewall_cleanup_required.txt; no se eliminaron reglas ajenas.')
        recovery_path.unlink(missing_ok=True)
        lease_path.unlink(missing_ok=True)


def recuperar_firewall(device_id,sessions):
    """Recuperación del supervisor: solo cadenas registradas de este worker."""
    lease=Path(sessions)/'firewall_lease.json'
    if not lease.exists():
        return
    data=json.loads(lease.read_text(encoding='utf-8'))
    chain=data['chain']
    if data['device_id']!=device_id or not re.fullmatch(r'PANDA_[a-f0-9]{12}',chain):
        raise ValueError('Lease de firewall no válido para este dispositivo')
    if data.get('adb_server') and tuple(data['adb_server'])!=servidor_adb_actual():
        raise ValueError('La recuperación debe usar el servidor ADB original del lease')
    root=root_executor(device_id)
    for binary in reversed(data['created']):
        if binary not in ('iptables','ip6tables'):
            raise ValueError('Tabla de firewall inesperada')
        root(binary,'-w','5','-S','OUTPUT')
        script=(f'if {binary} -w 5 -S {chain} >/dev/null 2>&1; then '
                f'while {binary} -w 5 -C OUTPUT -j {chain} >/dev/null 2>&1; do '
                f'{binary} -w 5 -D OUTPUT -j {chain} || exit 1; done; '
                f'{binary} -w 5 -F {chain} && {binary} -w 5 -X {chain}; fi')
        root('sh','-c',script)
    lease.unlink()
    (Path(sessions)/'firewall_cleanup_required.txt').unlink(missing_ok=True)

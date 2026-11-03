"""Sonda Android de laboratorio: HTTPS con confianza del sistema, sin MITM."""
import hashlib
import ipaddress
from pathlib import Path

from config.proxies import ADBError,adb


def consultar_salida_nativa(device_id,proxy,*,artifact=None):
    from config.device_test import shell
    artifact=Path(artifact) if artifact else Path(__file__).resolve().parents[1]/'tools/local_proxy/egress-probe.jar'
    if not artifact.is_file():
        raise ADBError('Falta tools/local_proxy/egress-probe.jar; compilar la sonda de laboratorio')
    host,port=proxy.rsplit(':',1)
    host=str(ipaddress.IPv4Address(host))
    port=int(port)
    if not 1<=port<=65535:
        raise ValueError('Puerto inválido')
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
    remote=f'/data/local/tmp/panda-egress-{digest[:16]}.jar'
    try:
        present=shell(device_id,'toybox','sha256sum',remote,timeout=3).split()[0]==digest
    except (ADBError,IndexError):
        present=False
    if not present:
        adb('-s',device_id,'push',str(artifact),remote,timeout=10)
        if shell(device_id,'toybox','sha256sum',remote,timeout=3).split()[0]!=digest:
            raise ADBError('No se confirmó la integridad de la sonda Android')
    output=shell(device_id,'env',f'CLASSPATH={remote}','app_process','/system/bin',
                 'org.panda.qa.EgressProbe',host,str(port),timeout=25)
    values=[line.partition('=')[2] for line in output.splitlines() if line.startswith('PANDA_EGRESS_IP=')]
    if len(values)!=1:
        raise ADBError('La sonda Android no confirmó una única salida HTTPS')
    return str(ipaddress.ip_address(values[0].strip()))

"""Verificación de red únicamente: no abre apps ni cambia la red de Android."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from core.adb_pool import descubrir_pool
    from core.panda_identity import resolver_pool_panda
    from core.mass_orchestrator import seleccionar_subset,bloquear_granja
    from core.database import Database
    from core.diagnostic_bridge import escribir_json
    from config.proxies import usar_servidor_adb,ProxyAllocator,leer_proxy_pool
    from config.device_test import shell,consultar_ip
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable',action='store_true',help='Habilitar el pool únicamente si pasan todas las pruebas HTTPS')
    args=parser.parse_args()
    path=ROOT/'config/proxy_pool.json'
    pool=json.loads(path.read_text(encoding='utf-8'))
    if pool.get('mode')!='laboratory':
        raise ValueError('Este verificador solo opera sobre el perfil laboratory')
    entries=pool['proxies'][:3]
    snapshot=resolver_pool_panda(descubrir_pool(),Database())
    selected=sorted(seleccionar_subset(snapshot,len(entries)))
    def verify(pair):
        index,entry=pair
        endpoint=f"http://{entry['host']}:{entry['port']}"
        result={'port':entry['port'],'windows_https':False,'android_https':False}
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':endpoint,'https':endpoint}))
            with opener.open('https://api.ipify.org',timeout=10) as response:
                observed=str(ipaddress.IPv4Address(response.read(80).decode().strip()))
            result['windows_https']=observed==entry['exit_ip']
        except Exception as exc:
            result['windows_error']=str(exc)
        route=snapshot.devices[selected[index]]
        try:
            with usar_servidor_adb(route.server.host,route.server.port):
                output=shell(route.serial,'sh','-c',f"printf 'CONNECT api.ipify.org:443 HTTP/1.1\\r\\nHost: api.ipify.org:443\\r\\n\\r\\n' | nc -w 3 -W 3 -q 1 {entry['host']} {entry['port']}",timeout=8)
                result['android_proxy_reachable']='200' in output.partition('\n')[0]
                observed=consultar_ip(route.serial,f"{entry['host']}:{entry['port']}",allow_native=True)
                result['android_https']=observed==entry['exit_ip']
                if result['android_https']:
                    result['android_proxy_reachable']=True
        except Exception as exc:
            result['android_error']=str(exc)
        return result
    with ThreadPoolExecutor(max_workers=3) as executor:
        results=list(executor.map(verify,enumerate(entries)))
    success=all(r['windows_https'] and r['android_https'] for r in results) and len(results)==3
    report={'results':results,'success':success,'apps_launched':False}
    escribir_json(ROOT/'sessions/local_proxy/verification.json',report)
    if success and args.enable:
        with bloquear_granja(ROOT/'sessions/farm.lock'):
            for entry in pool['proxies'][:3]:entry['enabled']=True
            escribir_json(path,pool)
            db=Database()
            ProxyAllocator(db).sincronizar(leer_proxy_pool(path))
            for alert in db.alertas():
                if alert['clave']=='deployment' and alert['mensaje'].startswith(('Configura al menos','Plantilla creada','Los primeros')):
                    db.alerta('deployment','Proxy local comprobado desde Android',activa=False)
    for result in results:
        print(f"Puerto {result['port']}: HTTPS Windows={result['windows_https']}; Android={result['android_https']}; acceso={result.get('android_proxy_reachable',False)}")
        if result.get('android_error'):print(result['android_error'])
    print('Pool habilitado.' if success and args.enable else 'No se ha habilitado el pool: revisar permisos y curl de Android.' if not success else 'Verificación completada.')
    return 0 if success else 2


if __name__=='__main__':
    raise SystemExit(main())

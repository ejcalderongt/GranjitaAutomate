"""Prueba HTTPS por cada proxy y reporte SQLite/JSON; no modifica Android."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
from pathlib import Path
import sys
import time
import urllib.request
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def main():
    from config.proxies import leer_proxy_pool
    from core.database import Database
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool',type=Path,default=ROOT/'config/proxy_pool.json')
    args=parser.parse_args()
    entries=[e for e in leer_proxy_pool(args.pool) if e['enabled']]
    if not entries:
        raise ValueError('No hay proxies habilitados')
    db=Database()
    run_id='diagnostico-windows-'+uuid4().hex
    def verify(entry):
        started=time.perf_counter()
        observed=None
        error=None
        try:
            endpoint='http://'+entry['endpoint']
            # proxy.py recibe CONNECT por HTTP; el destino se verifica con TLS.
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':endpoint,'https':endpoint}))
            with opener.open('https://api.ipify.org',timeout=10) as response:
                observed=str(ipaddress.ip_address(response.read(80).decode().strip()))
            if not entry.get('exit_ip') or observed!=entry['exit_ip']:
                raise ValueError('IP inesperada o no configurada')
            result='confirmado'
        except Exception as exc:
            result='fallido'
            error=type(exc).__name__
        db.auditar_proxy(run_id,'host_windows',entry['endpoint'],'diagnostico_windows',result,
            ip_esperada=entry.get('exit_ip'),ip_observada=observed,error_tipo=error,
            latencia_ms=round((time.perf_counter()-started)*1000,2),
            alcance='Windows: HTTPS explícito por proxy; no comprueba asignación ni tráfico Android')
        return result
    with ThreadPoolExecutor(max_workers=min(8,len(entries))) as executor:
        results=list(executor.map(verify,entries))
    rows=db.auditoria_proxies(run_id,limit=len(entries))
    output=ROOT/'runs'/run_id/'proxy-audit.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    for row in rows:
        print(f"[Red] {row['endpoint']}: {row['resultado']} · {row['latencia_ms']} ms")
    print('[Auditoría] '+str(output))
    return 0 if all(result=='confirmado' for result in results) else 2


if __name__=='__main__':
    raise SystemExit(main())

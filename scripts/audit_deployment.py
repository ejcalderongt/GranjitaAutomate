"""Auditoría de solo lectura de los cinco paquetes en conexiones actuales."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
from granjita.inventory import FleetStore,scan_fleet,shell
from granjita.core import DATA,Adb,now

PACKAGES=['gt.granjita.lab','io.appium.uiautomator2.server','io.appium.uiautomator2.server.test','io.appium.settings','com.llamalab.automate']


def main():
    store=FleetStore()
    report=scan_fleet([int(p) for p in store.setting('ports','5037,5038').split(',')])
    def inspect(row):
        record=dict(port=row['port'],serial=row['serial'],hardware_serial=row.get('hardware_serial',''),status=row['status'],packages={})
        for package in PACKAGES:
            try:
                record['packages'][package]=shell(Adb(row['port']),row['serial'],'pm path '+package).startswith('package:')
            except Exception:
                record['packages'][package]=None
        return record
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(inspect,report['devices']))
    (DATA/'deployment-audit.json').write_text(json.dumps(dict(at=now(),devices=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Conexiones actuales:',len(rows))
    print('Con todos los paquetes:',sum(all(v is True for v in r['packages'].values()) for r in rows))
    print('Por paquete:',{p:sum(r['packages'][p] is True for r in rows) for p in PACKAGES})


if __name__=='__main__':
    main()

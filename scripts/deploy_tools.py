"""Propagar APK de laboratorio y Automate sin copiar datos ni conceder permisos."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import shutil
import uuid

from granjita.core import ROOT,DATA,Adb,now
from granjita.inventory import FleetStore,scan_fleet,shell
from granjita.automation import runtime,validate_target
from granjita.panda_api import list_devices
from granjita.inventory import usable_serial
from collections import Counter


def supplement_from_panda(report,local_rows,rows,panda_rows):
    """Verificar transportes reutilizados sin fusionar ni sobrescribir fichas."""
    counts=Counter(r.get('onlySerial') for r in panda_rows)
    by_connection={r.get('serial'):r for r in panda_rows}
    known={r.get('hardware_serial') for r in rows}
    additional=[]
    for observed in report['devices']:
        hardware=usable_serial(observed.get('hardware_serial'))
        panda=by_connection.get(observed['serial'])
        if observed['status']!='Validado' or not hardware or hardware in known or observed.get('identity_conflict'):
            continue
        if not panda or panda.get('onlySerial')!=hardware or counts[hardware]!=1:
            continue
        candidates={r['id']:r for r in local_rows if r.get('hardware_serial')==hardware}
        identifier=next(iter(candidates)) if len(candidates)==1 else str(uuid.uuid5(uuid.NAMESPACE_OID,'panda-device:'+hardware))
        candidate=candidates.get(identifier,{})
        additional.append(dict(observed,id=identifier,display_name=candidate.get('display_name','Placa '+hardware),identity_state='Serial leído',verification='Panda onlySerial + getprop; sin modificar asociaciones locales'))
        known.add(hardware)
    return additional


def adb(row,*args,timeout=120):
    executable=Path(runtime()['sdk'])/'platform-tools/adb.exe'
    result=subprocess.run([str(executable),'-P',str(row['port']),'-s',row['serial'],*map(str,args)],capture_output=True,text=True,timeout=timeout,creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError((result.stdout+result.stderr)[-1500:])
    return result.stdout


def verify_apk(path,package):
    config=runtime()
    tools=Path(config['sdk'])/'build-tools/35.0.0'
    result=subprocess.run([str(tools/'aapt2.exe'),'dump','badging',str(path)],capture_output=True,text=True,check=True,creationflags=0x08000000)
    if not re.search(r"package: name='"+re.escape(package)+"'",result.stdout):
        raise ValueError('El APK no corresponde al paquete esperado: '+package)
    subprocess.run([str(Path(config['java_home'])/'bin/java.exe'),'-jar',str(tools/'lib/apksigner.jar'),'verify',str(path)],capture_output=True,check=True,creationflags=0x08000000)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(rows):
    folder=DATA/'deployment-apks'
    folder.mkdir(exist_ok=True)
    source=None
    paths=[]
    for row in rows:
        try:
            raw=shell(Adb(row['port']),row['serial'],'pm path com.llamalab.automate')
            paths=[line.removeprefix('package:') for line in raw.splitlines() if line.startswith('package:/data/app/')]
            if paths:
                source=row
                break
        except Exception:
            continue
    if not source:
        raise RuntimeError('No se encontró una placa accesible con Automate instalado desde Google Play.')
    automate=[]
    for index,path in enumerate(paths):
        local=folder/f'automate-{index}.apk'
        adb(source,'pull',path,local)
        verify_apk(local,'com.llamalab.automate')
        automate.append(local)
    driver=ROOT/'.tools/appium-home/node_modules/appium-uiautomator2-driver/node_modules'
    apks=driver/'appium-uiautomator2-server/apks'
    packages={
        'gt.granjita.lab':[DATA/'granjita-lab.apk'],
        'io.appium.uiautomator2.server':[next(apks.glob('appium-uiautomator2-server-v*.apk'))],
        'io.appium.uiautomator2.server.test':[apks/'appium-uiautomator2-server-debug-androidTest.apk'],
        'io.appium.settings':[driver/'io.appium.settings/apks/settings_apk-debug.apk'],
        'com.llamalab.automate':automate,
    }
    hashes={}
    for package,files in packages.items():
        hashes[package]=[dict(file=p.name,sha256=verify_apk(p,package)) for p in files]
    return packages,hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true',help='Instalar en todas las fichas accesibles con identidad sin conflicto')
    parser.add_argument('--workers',type=int,choices=[1,2],default=2)
    parser.add_argument('--verify-with-panda',action='store_true',help='Usar onlySerial de Panda y getprop coincidentes para verificar conexiones con IP reutilizada, sin cambiar fichas')
    args=parser.parse_args()
    store=FleetStore()
    report=scan_fleet([int(p) for p in store.setting('ports','5037,5038').split(',')])
    store.save_fleet(report)
    unique={}
    excluded=[]
    local_rows=store.fleet_devices()
    for row in local_rows:
        if row['status']=='Validado' and row['identity_state']=='Serial leído':
            unique.setdefault(row['id'],row)
        else:
            excluded.append(dict(id=row['id'],port=row['port'],status=row['status'],identity=row['identity_state']))
    rows=list(unique.values())
    if args.verify_with_panda:
        additional=supplement_from_panda(report,local_rows,rows,list_devices())
        rows+=additional
        print('Identidades adicionales verificadas con API Panda:',len(additional),flush=True)
    print('Fichas elegibles:',len(rows),'· conexiones excluidas/históricas:',len(excluded),flush=True)
    if not args.all:
        print('Vista previa. Usa --all para propagar los paquetes sin modificar permisos.')
        return
    packages,hashes=prepare(rows)
    result=dict(at=now(),packages=hashes,excluded=excluded,devices=[])
    result_path=DATA/'deployment-latest.json'
    previous={}
    if result_path.exists():
        previous=json.loads(result_path.read_text(encoding='utf-8'))
        history=DATA/'deployment-history'
        history.mkdir(exist_ok=True)
        shutil.copy2(result_path,history/(str(uuid.uuid4())+'.json'))
    already={d['id']:d for d in previous.get('devices',[])}
    lock=threading.Lock()

    def deploy(row):
        outcome=dict(id=row['id'],name=row['display_name'],port=row['port'],serial=row['serial'],packages={},at=now())
        try:
            validate_target(row)
        except Exception as exc:
            outcome['error']=str(exc)
            return outcome
        for package,files in packages.items():
            try:
                validate_target(row)
                old=already.get(row['id'],{})
                if old.get('packages',{}).get(package)=='Instalado y verificado' and previous.get('packages',{}).get(package)==hashes[package]:
                    if shell(Adb(row['port']),row['serial'],'pm path '+package).startswith('package:'):
                        outcome['packages'][package]='Instalado y verificado'
                        outcome.setdefault('previously_verified',[]).append(package)
                        continue
                command='install-multiple' if len(files)>1 else 'install'
                output=adb(row,command,'-r','-t',*files)
                if 'Success' not in output:
                    raise RuntimeError(output[-1200:])
                present=shell(Adb(row['port']),row['serial'],'pm path '+package)
                if not present.startswith('package:'):
                    raise RuntimeError('No se confirmó el paquete instalado.')
                outcome['packages'][package]='Instalado y verificado'
            except Exception as exc:
                outcome['packages'][package]='Error: '+str(exc)
        return outcome

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(deploy,row) for row in rows]
        for future in as_completed(futures):
            outcome=future.result()
            with lock:
                result['devices'].append(outcome)
                result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                okay=sum(v=='Instalado y verificado' for v in outcome['packages'].values())
                print(f"Progreso {len(result['devices'])}/{len(rows)} · puerto {outcome['port']} · {okay}/{len(packages)} paquetes",flush=True)
    complete=sum(len(d['packages'])==len(packages) and all(v=='Instalado y verificado' for v in d['packages'].values()) for d in result['devices'])
    print('Finalizado. Completos:',complete,'de',len(rows),'· informe local:',result_path,flush=True)


if __name__=='__main__':
    main()

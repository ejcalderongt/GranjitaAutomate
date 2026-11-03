"""Recuperación de leases propios y preparación de pantalla sin eludir credenciales."""
import json
import os
from pathlib import Path
import time

from config.device_test import shell
from config.proxies import ADBError,adb,usar_servidor_adb,ProxyAllocator
from core.adb_pool import ADBServer,DeviceRoute
from core.panda_identity import confirmar_identidad
from core.runtime_health import liberar_api

TEMP_XML=('window_dump.xml','window_dump.pending.xml','panda_wait.xml','panda_auth.xml')


def proceso_vivo(pid):
    if not isinstance(pid,int) or pid<=0:
        return False
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            return ctypes.get_last_error()!=87  # Acceso denegado: conservar por prudencia.
        try:
            code=wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value==259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def preparar_pantalla(route,command=None):
    command=command or shell
    with usar_servidor_adb(route.server.host,route.server.port):
        confirmar_identidad(route)
        command(route.serial,'input','keyevent','KEYCODE_WAKEUP')
        # Solo desbloqueo sin credenciales; PIN/patrón quedan a cargo del operador.
        command(route.serial,'input','keyevent','KEYCODE_MENU')


def reconectar_placa(item):
    route=item['route']
    with usar_servidor_adb(route.server.host,route.server.port):
        try:
            available=adb('-s',route.serial,'get-state',timeout=3)=='device'
        except ADBError:
            available=False
    if not available and ':' in route.serial:
        adb('-H',route.server.host,'-P',str(route.server.port),'disconnect',route.serial,timeout=3)
        adb('-H',route.server.host,'-P',str(route.server.port),'connect',route.serial,timeout=3)
    with usar_servidor_adb(route.server.host,route.server.port):
        if adb('-s',route.serial,'get-state',timeout=3)!='device':
            raise ADBError('La placa sigue desconectada tras reconexión')
        confirmar_identidad(route)


def recuperar_placa(item,args,db,cleanup):
    device_id=item.get('device_id',item['route'].serial)
    owner=item['reservation_owner']
    db.actualizar_dispositivo(device_id,estado='Reconectando')
    liberar_api(db,item.get('worker_token',''))
    try:
        for name in TEMP_XML:
            (Path(item['directory'])/name).unlink(missing_ok=True)
        reconectar_placa(item)
        db.actualizar_dispositivo(device_id,estado='Recuperando')
        error=cleanup(item,args.package)
        if error:
            raise ADBError(error)
        ProxyAllocator(db).finalizar(device_id,owner,cleanup_ok=True)
        db.actualizar_dispositivo(device_id,estado='Espera',conectado=True)
        db.log_granja(owner,device_id,'Auto-heal completado')
        return None
    except Exception as exc:
        ProxyAllocator(db).finalizar(device_id,owner,cleanup_ok=False)
        db.actualizar_dispositivo(device_id,estado='Cuarentena')
        db.log_granja(owner,device_id,'Auto-heal pendiente',nivel='ERROR',detalle={'error':str(exc)})
        return str(exc)


def recuperar_sesiones(root,args,db,cleanup,parallelism=40):
    """Solo workers anteriores verificablemente terminados y con propiedad persistida."""
    from concurrent.futures import ThreadPoolExecutor
    from core.diagnostic_bridge import escribir_json
    root=Path(root).resolve()
    jobs=[]
    skipped=[]
    xml_removed=0
    candidates=list(root.glob('farm/*/device-*/supervisor_lease.json'))
    # Compatibilidad con ejecuciones anteriores a la incorporación del lease del supervisor.
    for manifest in root.glob('farm/*/manifest.json'):
        try:
            data=json.loads(manifest.read_text(encoding='utf-8'))
            for worker in data['workers']:
                directory=Path(worker['directory']).resolve()
                if root not in directory.parents or (directory/'supervisor_lease.json').exists():
                    continue
                if not any((directory/name).exists() for name in ('proxy_lease.json','firewall_lease.json')):
                    if not proceso_vivo(worker.get('pid')):
                        for name in TEMP_XML:
                            temporary=directory/name
                            if temporary.exists():
                                temporary.unlink()
                                xml_removed+=1
                    continue
                lease=directory/'supervisor_lease.json'
                expected=worker.get('hardware_serial')
                if not expected and worker.get('device_id')!=worker['serial']:
                    expected=worker.get('device_id')
                escribir_json(lease,dict(worker,hardware_serial=expected,
                    device_id=worker.get('device_id',worker['serial']),owner=manifest.parent.name))
                candidates.append(lease)
        except (OSError,ValueError,KeyError) as exc:
            skipped.append(f'{manifest}: {exc}')
    for lease in candidates:
        try:
            data=json.loads(lease.read_text(encoding='utf-8'))
            if proceso_vivo(data.get('pid')) or proceso_vivo(data.get('supervisor_pid')):
                skipped.append(str(lease))
                continue
            directory=lease.parent.resolve()
            if root not in directory.parents:
                raise ValueError('Lease fuera de sessions')
            route=DeviceRoute(data['serial'],ADBServer(data['host'],data['port']),'device',
                              hardware_serial=data.get('hardware_serial'))
            if ':' in route.serial and not route.hardware_serial:
                raise ValueError('Lease TCP sin identidad: requiere revisión')
            jobs.append({'route':route,'device_id':data['device_id'],'directory':str(directory),
                         'reservation_owner':data['owner'],'worker_token':data.get('worker_token','')})
        except (OSError,ValueError,KeyError) as exc:
            skipped.append(f'{lease}: {exc}')
    def recover(item):
        error=recuperar_placa(item,args,db,cleanup)
        if error is None:
            (Path(item['directory'])/'supervisor_lease.json').unlink(missing_ok=True)
        return {'device_id':item['device_id'],'error':error}
    started=time.perf_counter()
    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        results=list(pool.map(recover,jobs))
    report={'duration_ms':round((time.perf_counter()-started)*1000,2),'workers':results,'skipped':skipped,'xml_removed':xml_removed}
    escribir_json(root/'bootstrap-recovery.json',report)
    db.alerta('bootstrap_recovery',f"Recuperación previa pendiente: {sum(bool(r['error']) for r in results)+len(skipped)} workers",
              activa=bool(skipped) or any(r['error'] for r in results))
    return report

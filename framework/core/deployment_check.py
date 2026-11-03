"""Preflight de campo sin modificar Android ni arrancar servidores Panda."""
import ipaddress
import json
import os
from pathlib import Path

from config.proxies import ADBError, leer_proxy_pool, verificar_adb


def preparar_pool(path, count, required=None):
    path = Path(path)
    empty = not path.exists() or not path.read_text(encoding='utf-8-sig').strip()
    if not empty:
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except ValueError as exc:
            raise ValueError(f'JSON inválido en {path}; corregir sin sobrescribir datos') from exc
        empty = isinstance(data, dict) and data.get('proxies') == []
        if not empty and isinstance(data, dict) and isinstance(data.get('proxies'), list):
            for item in data['proxies']:
                if (not isinstance(item, dict) or type(item.get('port')) is not int
                        or type(item.get('enabled', True)) is not bool):
                    raise ValueError('Cada proxy requiere port entero y enabled booleano')
    if empty:
        path.parent.mkdir(parents=True, exist_ok=True)
        template = {
            'instructions': 'Sustituir por endpoints residenciales fijos reales y su IP pública de salida; habilitar cada entrada. Las IPs de ejemplo son de documentación.',
            'proxies': [{'host': f'192.0.2.{20+i}', 'port': 8000,
                         'exit_ip': f'203.0.113.{20+i}', 'enabled': False}
                        for i in range(max(3, count))]}
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        raise ValueError(f'Plantilla creada en {path}. Completar proxies reales antes de ejecutar.')
    entries = leer_proxy_pool(path)
    enabled = [p for p in entries if p['enabled']]
    for p in enabled:
        if (not p.get('lab_shared_exit') and not ipaddress.ip_address(p['host']).is_global) or not p['exit_ip'] or not ipaddress.ip_address(p['exit_ip']).is_global:
            raise ValueError('Cada proxy habilitado requiere IPv4 pública real e IP pública de salida esperada')
    needed=count if required is None else required
    if len({p['endpoint'] if p.get('lab_shared_exit') else p['exit_ip'] for p in enabled}) < needed:
        if any(p.get('lab_shared_exit') for p in entries):
            raise ValueError(f'Configura al menos {needed} puertos de laboratorio habilitados; completar antes la conectividad desde Android')
        raise ValueError(f'Configura al menos {needed} proxies habilitados con IPs de salida distintas')
    return entries


def fijar_adb_local():
    local_config=Path(__file__).resolve().parents[1]/'config/native_dependencies.local.json'
    configured=None
    if not os.environ.get('ADB_PATH') and local_config.is_file():
        configured=json.loads(local_config.read_text(encoding='utf-8'))['adb_path']
    path = Path(os.environ.get('ADB_PATH') or configured or r'C:\Android\platform-tools\adb.exe').expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ADBError(f'ADB_PATH requiere un binario físico accesible: {path}')
    with path.open('rb') as binary:
        binary.read(1)
    os.environ['ADB_PATH'] = str(path.resolve())
    return verificar_adb()


def verificar_despliegue(args):
    entries=preparar_pool(args.proxy_pool, args.smoke_test or args.devices,required=args.smoke_test or 1)
    if args.smoke_test:
        args.smoke_proxies=seleccionar_proxies_smoke(entries,args.smoke_test)
    binary = fijar_adb_local()
    print(f'Preflight correcto. ADB explícito: {binary}', flush=True)


def seleccionar_proxies_smoke(entries,count):
    selected=entries[:count]
    if len(selected)!=count or any(not p['enabled'] for p in selected):
        raise ValueError(f'Los primeros {count} proxies deben estar habilitados; no se sustituyen por entradas posteriores')
    return selected


class PandaSimulado:
    """Doble explícito: nunca ejecuta shell ni acredita hardware real."""
    def inventario(self):
        from core.adb_pool import ADBServer, DeviceRoute, PoolSnapshot
        servers=[ADBServer('127.0.0.1',5037),ADBServer('127.0.0.1',5038)]
        return PoolSnapshot({f'SIMULADO-{i:02d}':DeviceRoute(f'SIMULADO-{i:02d}',
            servers[i%2],'device',[servers[i%2]]) for i in range(34)}, {}, servers)


def simular_entorno(args):
    from core.database import Database, ROOT
    import uuid
    if not args.smoke_test:
        raise ValueError('--simulate-env requiere --smoke-test o --ui')
    db=Database(ROOT/'data/simulation.db')
    snapshot=PandaSimulado().inventario()
    db.sincronizar_pool(snapshot)
    selected=sorted(snapshot.devices)[:args.smoke_test]
    run='SIMULADO-'+uuid.uuid4().hex
    db.iniciar_ejecucion(run,selected,smoke=True)
    try:
        for serial in snapshot.devices:
            db.actualizar_dispositivo(serial,alias='SIMULACIÓN SIN HARDWARE',conectado=False)
        for serial in selected:
            db.log_granja(run,serial,'SIMULACIÓN: autenticación y carga no medidas',detalle={'simulated':True})
    finally:
        db.guardar_resumen_carga(run,selected,simulated=True)
        db.finalizar_ejecucion(run,'simulado')
    print(f'SIMULACIÓN: 34 respuestas sintéticas; sin ADB, firewall ni OpenAI. SQLite: {db.path}',flush=True)
    return 0

"""Metadatos de artefactos y hardware; nunca sustituyen pruebas de red."""
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
from core.database import ROOT
from core.diagnostic_bridge import escribir_json


@contextmanager
def reporte_bloqueado(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix(path.suffix+'.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            if not isinstance(data,dict):
                raise ValueError('El reporte requiere un objeto JSON')
            yield data
            escribir_json(path,data)
        finally:
            lock.seek(0)
            if os.name=='nt':
                msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(lock,fcntl.LOCK_UN)


def inyectar_perfil_en_auditoria(run_id: str,perfil: dict,*,root=ROOT):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',run_id):
        raise ValueError('run_id inválido')
    if not isinstance(perfil.get('device_id'),str) or not perfil['device_id']:
        raise ValueError('Falta device_id')
    for key in ('sdk_level','width','height','density'):
        if type(perfil.get(key)) is not int or perfil[key]<=0:
            raise ValueError('Telemetría inválida: '+key)
    runs=(Path(root)/'runs').resolve()
    path=runs/f'diagnostico-real-{run_id}'/'resultado.json'
    if not path.resolve().is_relative_to(runs):
        raise ValueError('Reporte fuera de runs')
    if not path.is_file():
        return False
    with reporte_bloqueado(path) as data:
        profiles=data.setdefault('hardware_profiles',{})
        if not isinstance(profiles,dict):
            raise ValueError('hardware_profiles requiere un objeto')
        profiles[perfil['device_id']]={key:perfil[key] for key in ('device_id','sdk_level','width','height','density')}
        profiles[perfil['device_id']].update(observed_at=datetime.now(timezone.utc).isoformat(),
            source='provided_metadata',network_isolation_verified=False)
    return True

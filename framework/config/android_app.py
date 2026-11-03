"""Componente Android: el namespace de una clase puede diferir del paquete APK."""
import json
from pathlib import Path
import re

PROFILE=json.loads((Path(__file__).with_name('tiktok_app.json')).read_text(encoding='utf-8'))
TIKTOK_PACKAGE=PROFILE['package']
TIKTOK_ACTIVITY=PROFILE['activity']


def normalizar_activity(package,activity):
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+',package):
        raise ValueError('Paquete Android inválido')
    if '/' in activity:
        component_package,activity=activity.split('/',1)
        if component_package!=package:
            raise ValueError(f'El componente pertenece a {component_package}; se esperaba {package}')
    if activity.startswith('.'):
        activity=package+activity
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_$][\w$]*)+',activity):
        raise ValueError('Activity Android inválida')
    if package==TIKTOK_PACKAGE and activity!=TIKTOK_ACTIVITY and not activity.startswith(package+'.'):
        raise ValueError(f'Activity ajena al perfil global {TIKTOK_PACKAGE}: {activity}')
    return activity


def validar_componente_instalado(device_id,package,activity):
    from config.device_test import shell
    from config.proxies import ADBError
    activity=normalizar_activity(package,activity)
    component=f'{package}/{activity}'
    if not shell(device_id,'pm','path',package).strip().startswith('package:'):
        raise ADBError(f'App no instalada: {package}')
    resolved=shell(device_id,'cmd','package','resolve-activity','--brief','-n',component)
    for line in resolved.splitlines():
        if '/' in line:
            try:
                if normalizar_activity(package,line.strip())==activity:
                    return component
            except ValueError:
                pass
    raise ADBError(f'Activity no resuelta en {device_id}: {component}; comprobar versión instalada')

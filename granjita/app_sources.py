"""Perfiles de aplicación origen y apertura verificada sin interacciones."""
import re
import time
from .diagnostics import traced,emit

SOURCES={
    'laboratorio':dict(id='laboratorio',name='Granjita Lab',packages=['gt.granjita.lab'],like_adapter='lab_like_v1',mapping_status='verified'),
    'tiktok':dict(id='tiktok',name='TikTok',packages=['com.zhiliaoapp.musically','com.ss.android.ugc.trill'],like_adapter=None,mapping_status='pending'),
}


def source_profile(identifier='laboratorio'):
    import copy
    if not isinstance(identifier,str) or identifier not in SOURCES:raise ValueError('Perfil de aplicación origen no admitido.')
    return copy.deepcopy(SOURCES[identifier])


def require_like_mapping(identifier):
    profile=source_profile(identifier)
    if profile['mapping_status']!='verified' or not profile['like_adapter']:
        raise ValueError('El perfil '+profile['name']+' permite abrir y comprobar la app; el botón y el estado de like aún necesitan un mapeo verificado. No se ejecutó ningún like.')
    return profile


def foreground_package(raw):
    # Android/ROM usa distintas etiquetas para la actividad actual.
    # No usar historiales ni elegir arbitrariamente entre varios displays activos.
    packages=set()
    for line in raw.splitlines():
        line=line.strip()
        if re.match(r'^(?:mResumedActivity:|ResumedActivity:|topResumedActivity=|mCurrentFocus=)',line):
            found=re.search(r'\b([A-Za-z][A-Za-z0-9_.]*)/[A-Za-z0-9_.$]+',line)
            if found:packages.add(found.group(1))
    return next(iter(packages)) if len(packages)==1 else None


@traced('app.source.prepare')
def prepare_app(row,identifier,cancelled=lambda:False,task_id=None):
    from .automation import validate_target,AutomationError
    from .core import Adb
    from .inventory import shell
    profile=source_profile(identifier)
    def check():
        if cancelled():raise AutomationError('Preparación cancelada antes de la siguiente acción.')
    check();validate_target(row)
    adb=Adb(row['port'])
    installed=[]
    for package in profile['packages']:
        check()
        if any(line.startswith('package:') for line in shell(adb,row['serial'],'pm path '+package).splitlines()):installed.append(package)
    if not installed:raise AutomationError(profile['name']+' no está instalada. No se instala ni se inicia sesión automáticamente.')
    if len(installed)!=1:raise AutomationError('Hay varias variantes instaladas de '+profile['name']+'; se requiere un perfil específico antes de elegir.')
    package=installed[0]
    def current():return foreground_package(shell(adb,row['serial'],'dumpsys activity activities'))
    before=current();check()
    if before!=package:
        activity=shell(adb,row['serial'],'cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER '+package)
        components=[line.strip() for line in activity.splitlines() if re.fullmatch(re.escape(package)+r'/[A-Za-z0-9_.$]+',line.strip())]
        if len(components)!=1:raise AutomationError('No se pudo resolver una actividad de inicio única para '+profile['name']+'.')
        check()
        result=shell(adb,row['serial'],'am start -W -n '+components[0])
        if 'Error:' in result or 'Exception' in result:raise AutomationError('Android no pudo abrir '+profile['name']+'.')
    deadline=time.monotonic()+10
    while True:
        check()
        if current()==package:break
        if time.monotonic()>=deadline:raise AutomationError('No se confirmó '+profile['name']+' en primer plano. Revisar desbloqueo o diálogos del dispositivo.')
        time.sleep(.25)
    validate_target(row)
    emit('app.source','foreground_verified',state='already_open' if before==package else 'launched',app_source=identifier,package=package)
    return dict(app_source=identifier,package=package,foreground_verified=True,launched=before!=package,like_mapping=profile['mapping_status'],interaction_ready=False,readiness_reason='mapping_pending' if profile['mapping_status']!='verified' else 'requires_task_validation')


@traced('app.source.verify')
def verify_app_open(row,identifier,task_id=None):
    """Segunda lectura independiente: no lanza, instala ni pulsa controles."""
    from .automation import validate_target
    from .core import Adb,now
    from .inventory import shell
    profile=source_profile(identifier)
    validate_target(row)
    current=foreground_package(shell(Adb(row['port']),row['serial'],'dumpsys activity activities'))
    state='open' if current in profile['packages'] else 'not_foreground' if current else 'unconfirmed'
    emit('app.source','postcheck',state=state,app_source=identifier)
    return dict(at=now(),app_source=identifier,state=state,observed_package=current,foreground_verified=state=='open',interaction_ready=False)

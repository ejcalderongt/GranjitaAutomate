"""Parámetros tipados y ejecución del flujo local de likes con horario Guatemala."""
from datetime import datetime,timezone,timedelta
import base64
import hashlib
import xml.etree.ElementTree as ET
from .core import DATA
from .automation import Session,AutomationError,PACKAGE

GT=timezone(timedelta(hours=-6))


def clock_now():return datetime.now(GT)


def validate_parameters(parameters):
    if not isinstance(parameters,dict) or set(parameters)!={'count','scroll_after_like','start_at','end_at'}:
        raise ValueError('Parámetros del flujo inválidos.')
    if type(parameters['count']) is not int or not 1<=parameters['count']<=12 or type(parameters['scroll_after_like']) is not bool:
        raise ValueError('Usa entre 1 y 12 tarjetas por dispositivo y scroll verdadero/falso.')
    start,end=parameters['start_at'],parameters['end_at']
    if (start is None)!=(end is None):raise ValueError('Indica inicio y fin juntos.')
    if start is not None:
        if not isinstance(start,str) or not isinstance(end,str):raise ValueError('Horario inválido.')
        a,b=datetime.fromisoformat(start),datetime.fromisoformat(end)
        if a.utcoffset()!=timedelta(hours=-6) or b.utcoffset()!=timedelta(hours=-6) or not timedelta(0)<b-a<=timedelta(hours=24):
            raise ValueError('Horario de Guatemala, fin posterior e intervalo máximo de 24 horas.')
    return dict(parameters)


def window_state(parameters,current=None):
    validate_parameters(parameters)
    if parameters['start_at'] is None:return 'ready'
    current=current or clock_now()
    if current>=datetime.fromisoformat(parameters['end_at']):return 'expired'
    return 'waiting' if current<datetime.fromisoformat(parameters['start_at']) else 'ready'


def run_flow(row,task_id,parameters,cancelled=lambda:False,audit=lambda kind,data:None):
    validate_parameters(parameters)
    def check():
        if cancelled():raise AutomationError('Detenido antes de la siguiente acción; revisar los pasos guardados.')
        if window_state(parameters)!='ready':raise AutomationError('Fuera del horario permitido; no se inicia otra acción.')
    check()
    audit('started',{'target':'lab_like_01','index':1})
    totals={'applied':0,'already_marked':0}
    with Session(row) as session:
        if session.call('GET','/appium/device/current_package')!=PACKAGE:raise AutomationError('Destino de laboratorio no confirmado.')
        for index in range(1,parameters['count']+1):
            check()
            target=f'lab_like_{index:02d}'
            audit('started',dict(target=target,index=index))
            # Localizar la tarjeta exacta. Puede desplazar solo lo necesario para navegar al destino.
            session.call('POST','/element',{'using':'-android uiautomator','value':f'new UiScrollable(new UiSelector().description("lab_feed")).scrollIntoView(new UiSelector().description("{target}"))'})
            before=session.text(target).upper()
            audit('observed',dict(target=target,state=before))
            if before not in ('ME GUSTA: NO','ME GUSTA: SI'):raise AutomationError('Estado desconocido; no se pulsa.')
            check()
            if before=='ME GUSTA: NO':
                audit('click_requested',dict(target=target));session.click(target)
            if session.text(target).upper()!='ME GUSTA: SI':raise AutomationError('Like sin confirmar; no repetir automáticamente.')
            outcome='applied' if before=='ME GUSTA: NO' else 'already_marked'
            audit('verified',dict(target=target,outcome=outcome,before=before,after='ME GUSTA: SI'))
            totals[outcome]+=1
            path=DATA/'lab-evidence'/f'{task_id}-{index:02d}.png';path.parent.mkdir(exist_ok=True)
            path.write_bytes(base64.b64decode(session.call('GET','/screenshot')))
            audit('evidence',dict(target=target,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            if parameters['scroll_after_like']:
                check()
                before_xml=session.call('GET','/source')
                can_scroll=session.call('POST','/execute/sync',{'script':'mobile: scrollGesture','args':[{'elementId':session.element('lab_feed'),'direction':'down','percent':0.35}]})
                after_xml=session.call('GET','/source')
                def positions(source):return [(n.get('content-desc'),n.get('bounds')) for n in ET.fromstring(source).iter() if (n.get('content-desc') or '').startswith('lab_like_')]
                moved=positions(before_xml)!=positions(after_xml)
                audit('scroll',dict(target=target,moved=moved,can_scroll_more=can_scroll))
                if not moved and can_scroll:raise AutomationError('Scroll sin movimiento verificable; revisar.')
    return f"{sum(totals.values())} tarjetas verificadas · {totals['applied']} likes nuevos · {totals['already_marked']} ya marcados."

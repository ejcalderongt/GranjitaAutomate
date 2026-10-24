"""Adaptador de lectura de la API Android documentada de Panda."""
import json
import time
from urllib.parse import urlparse
import websocket


def list_devices(url='ws://127.0.0.1:22222/'):
    parsed=urlparse(url)
    if parsed.scheme!='ws' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password:
        raise ValueError('La integración inicial solo acepta una API local sin credenciales en URL.')
    connection=websocket.create_connection(url,timeout=5,suppress_origin=True)
    try:
        connection.send(json.dumps({'action':'list','devices':'all'}))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            message=json.loads(connection.recv())
            if not isinstance(message,dict) or 'code' not in message:
                continue
            if message['code']!=10000:
                raise RuntimeError(f"Panda rechazó la consulta de lectura (código {message['code']}). Verifica la licencia/API en Panda.")
            data=message.get('data')
            if isinstance(data,str):
                data=json.loads(data)
            if not isinstance(data,list):
                raise RuntimeError('La respuesta no contiene una lista de dispositivos compatible.')
            return data
        raise TimeoutError('Panda no confirmó la consulta a tiempo.')
    finally:
        connection.close()


def update_device(serial, name, number):
    """Cambio individual explícito de nombre/número; no admite all ni lotes ambiguos."""
    import re
    if not isinstance(serial,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,100}',serial) or serial.lower()=='all':
        raise ValueError('Se requiere un transporte individual.')
    if not re.fullmatch(r'R[0-9]{2,3}-P[0-9]{2,3}',name) or type(number) is not int or not 1 <= number <= 999999:
        raise ValueError('Nombre físico o número inválidos.')
    connection=websocket.create_connection('ws://127.0.0.1:22222/',timeout=5,suppress_origin=True)
    try:
        connection.send(json.dumps({'action':'updateDevices','devices':serial,'data':{'name':name,'sort':number}}))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            message=json.loads(connection.recv())
            if isinstance(message,dict) and 'code' in message:
                if message['code'] != 10000:
                    raise RuntimeError('Panda rechazó el cambio de nombre/número.')
                return
        raise TimeoutError('Cambio sin confirmación de Panda; consultar antes de reintentar.')
    finally:
        connection.close()

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

"""Contrato Android Panda documentado: WebSocket local, sin endpoints inventados."""
import asyncio
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

from PIL import Image
import websocket


class PandaError(RuntimeError):
    pass


class PandaClient:
    def __init__(self, url='ws://127.0.0.1:22222/', *, screenshots='./screenshots', request=None):
        parsed=urlsplit(url)
        if parsed.scheme!='ws' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password:
            raise ValueError('Panda requiere WebSocket local sin credenciales en URL')
        self.url=url
        self.screenshots=Path(screenshots).resolve()
        self.bindings={}
        self._injected=request
        self._limit=asyncio.Semaphore(4)

    async def _request(self,payload):
        if self._injected is not None:
            return await self._injected(payload)
        def call():
            connection=None
            try:
                connection=websocket.create_connection(self.url,timeout=5,suppress_origin=True,
                    http_no_proxy=['127.0.0.1','localhost','::1'])
                connection.send(json.dumps(payload))
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    connection.settimeout(max(.1,deadline-time.monotonic()))
                    raw=connection.recv()
                    if len(raw)>4*1024*1024:
                        raise PandaError('respuesta_grande')
                    result=json.loads(raw)
                    if isinstance(result,dict) and 'code' in result:
                        if result['code']!=10000:
                            raise PandaError('panda_rechazo')
                        return result.get('data')
                raise PandaError('confirmacion_ausente')
            except PandaError:
                raise
            except Exception:
                raise PandaError('conexion_o_respuesta_invalida') from None
            finally:
                if connection is not None:
                    connection.close()
        task=asyncio.create_task(asyncio.to_thread(call))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # No dejar una orden de resultado incierto ejecutándose tras liberar el lock.
            try:
                await task
            except Exception:
                pass
            raise

    async def inventario(self):
        data=await self._request({'action':'list','devices':'all'})
        if isinstance(data,str):
            data=json.loads(data)
        if not isinstance(data,list) or any(not isinstance(row,dict) for row in data):
            raise PandaError('inventario_invalido')
        return data

    @staticmethod
    def _resolve(rows,device_id):
        if not re.fullmatch(r'\d{1,6}',device_id) or int(device_id)<1:
            raise ValueError('Número visual Panda inválido')
        matches=[row for row in rows if str(row.get('sort','')).isdigit() and int(row['sort'])==int(device_id)]
        if len(matches)!=1:
            raise PandaError('numero_ausente_o_ambiguo')
        row=matches[0]
        identity=row.get('onlySerial')
        serial=row.get('serial')
        # Esta versión real de Panda omite status; list enumera conexiones actuales.
        # Un estado explícito offline siempre bloquea, y la captura debe confirmarse.
        if 'status' in row and row['status']!='online':
            raise PandaError('placa_offline')
        if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{3,100}',identity):
            raise PandaError('identidad_ausente')
        if not isinstance(serial,str) or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{3,100}',serial) or serial.lower()=='all':
            raise PandaError('transporte_invalido')
        if sum(r.get('onlySerial')==identity for r in rows)!=1 or sum(r.get('serial')==serial for r in rows)!=1:
            raise PandaError('identidad_ambigua')
        return row

    async def preparar(self,device_ids):
        if not device_ids or len({int(d) for d in device_ids})!=len(device_ids):
            raise ValueError('Selecciona números Panda únicos')
        rows=await self.inventario()
        failures={}
        for device_id in device_ids:
            try:
                row=self._resolve(rows,device_id)
                self.bindings[device_id]=row['onlySerial']
            except (PandaError,ValueError) as exc:
                failures[device_id]=type(exc).__name__
        return failures

    def _bound(self,rows,device_id):
        row=self._resolve(rows,device_id)
        if self.bindings.get(device_id)!=row['onlySerial']:
            raise PandaError('identidad_cambio')
        return row

    async def capturar_pantalla_dispositivo_async(self,device_id):
        async with self._limit:
            row=self._bound(await self.inventario(),device_id)
            # Directorio nuevo por orden: no aceptar una captura residual de otro ciclo.
            pending=self.screenshots/('.capture-'+uuid4().hex)
            await asyncio.to_thread(pending.mkdir,parents=True,exist_ok=False)
            await self._request({'action':'Screen','devices':row['serial'],'data':{'savePath':str(pending)}})
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                files=await asyncio.to_thread(lambda:list(pending.iterdir()))
                images=[p for p in files if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg') and not p.is_symlink()]
                if len(images)>1:
                    raise PandaError('captura_ambigua')
                if images:
                    def save():
                        if images[0].stat().st_size>8*1024*1024:
                            raise PandaError('captura_grande')
                        with Image.open(images[0]) as source:
                            if source.width*source.height>20_000_000:
                                raise PandaError('captura_grande')
                            image=source.convert('RGB')
                        target=self.screenshots/f'snapshot_{device_id}.png'
                        temporary=target.with_suffix('.pending.png')
                        image.save(temporary,format='PNG')
                        temporary.replace(target)
                        return target
                    try:
                        target=await asyncio.to_thread(save)
                        self._bound(await self.inventario(),device_id)
                        return target
                    except (OSError,ValueError):
                        pass  # Panda puede estar terminando de escribir el archivo.
                await asyncio.sleep(.1)
            raise PandaError('captura_no_confirmada')

    async def ejecutar_swipe_masivo_async(self,device_ids_list):
        rows=await self.inventario()
        eligible=[];excluded=[];serials=[]
        for device_id in device_ids_list:
            try:
                row=self._bound(rows,device_id)
                serials.append(row['serial']);eligible.append(device_id)
            except PandaError:
                excluded.append(device_id)
        if serials:
            # Un solo mensaje centralizado. SUCCESS acredita aceptación, no gesto físico.
            await self._request({'action':'pointerEvent','devices':','.join(serials),'data':{'type':'6'}})
        return {'accepted':eligible,'excluded':excluded}


async def capturar_pantalla_dispositivo_async(device_id, *, client):
    return await client.capturar_pantalla_dispositivo_async(device_id)


async def ejecutar_swipe_masivo_async(device_ids_list, *, client):
    return await client.ejecutar_swipe_masivo_async(device_ids_list)

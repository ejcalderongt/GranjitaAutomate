"""Control QA explícito de una ruta Panda; sin reconexiones ni acciones sociales."""
import asyncio
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess

from PIL import Image
from config.android_app import TIKTOK_PACKAGE
from config.proxies import ADBError, verificar_adb
from core.adb_pool import descubrir_pool


class AndroidDevice:
    def __init__(self, route):
        if route.status != 'device' or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]+',route.serial):
            raise ValueError('Ruta ADB explícita y autorizada requerida')
        self.route = route

    @classmethod
    async def seleccionar(cls, device_id):
        snapshot = await asyncio.to_thread(descubrir_pool)
        if device_id not in snapshot.devices:
            raise ADBError('Dispositivo no encontrado en los servidores configurados')
        return cls(snapshot.devices[device_id])

    async def ejecutar_comando(self, args, *, binary=False):
        """Espera el proceso acotado también al cancelar, antes de liberar el lease."""
        def run():
            route=self.route
            env=os.environ.copy()
            for name in ('ADB_SERVER_SOCKET','ANDROID_ADB_SERVER_ADDRESS','ANDROID_ADB_SERVER_PORT'):
                env.pop(name,None)
            try:
                result=subprocess.run([verificar_adb(),'-H',route.server.host,'-P',str(route.server.port),
                    '-s',route.serial,*args],capture_output=True,check=True,timeout=10,env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except (subprocess.SubprocessError,OSError):
                raise ADBError('Comando ADB no confirmado') from None
            if len(result.stdout)>16*1024*1024:
                raise ADBError('Respuesta ADB demasiado grande')
            return result.stdout if binary else result.stdout.decode('utf-8',errors='replace').strip()
        task=asyncio.create_task(asyncio.to_thread(run))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                pass
            raise

    async def verificar_identidad(self):
        serial=await self.ejecutar_comando(['shell','getprop','ro.serialno'])
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,100}',serial):
            raise ADBError('No se pudo verificar serial físico')
        return serial

    async def verificar_app_visible(self):
        text=await self.ejecutar_comando(['shell','dumpsys','activity','activities'])
        lines=[line for line in text.splitlines() if re.search(r'(?:mResumedActivity|topResumedActivity|ResumedActivity)\s*[:=]',line)]
        if not lines or any(TIKTOK_PACKAGE+'/' not in line for line in lines):
            raise ADBError('TikTok no está confirmado en primer plano; detener y revisar la placa')

    async def abrir_tiktok(self):
        installed=await self.ejecutar_comando(['shell','pm','path',TIKTOK_PACKAGE])
        if not installed.startswith('package:'):
            raise ADBError('TikTok global no está instalado')
        resolved=await self.ejecutar_comando(['shell','cmd','package','resolve-activity','--brief',
            '-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER','-p',TIKTOK_PACKAGE])
        components=[line.strip() for line in resolved.splitlines() if re.fullmatch(
            re.escape(TIKTOK_PACKAGE)+r'/[A-Za-z0-9_.$]+',line.strip())]
        if len(components)!=1:
            raise ADBError('Actividad principal no resuelta')
        result=await self.ejecutar_comando(['shell','am','start','-W','-n',components[0]])
        if 'Status: ok' not in result:
            raise ADBError('Lanzamiento no confirmado')

    async def capturar_pantalla(self, ruta_local):
        await self.verificar_app_visible()
        data=await self.ejecutar_comando(['exec-out','screencap','-p'],binary=True)
        await self.verificar_app_visible()
        def save():
            with Image.open(BytesIO(data)) as image:
                if image.format!='PNG' or image.width*image.height>20_000_000:
                    raise ValueError('Captura PNG inválida')
                image.verify()
            path=Path(ruta_local)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
            return path
        return await asyncio.to_thread(save)

    async def hacer_swipe_down(self):
        await self.verificar_app_visible()
        size=await self.ejecutar_comando(['shell','wm','size'])
        matches=re.findall(r'(?:Physical|Override) size:\s*(\d+)x(\d+)',size)
        rotation=await self.ejecutar_comando(['shell','dumpsys','input'])
        orientation=re.findall(r'SurfaceOrientation:\s*(\d)',rotation)
        if not matches or not orientation or orientation[-1]!='0':
            raise ADBError('Requiere orientación vertical verificada')
        width,height=map(int,matches[-1])
        if not 200<=width<=5000 or not 400<=height<=10000:
            raise ADBError('Dimensiones de pantalla inválidas')
        x=str(width//2)
        await self.ejecutar_comando(['shell','input','swipe',x,str(int(height*.8)),x,str(int(height*.25)),'500'])

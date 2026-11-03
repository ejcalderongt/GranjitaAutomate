"""Preguntas/respuestas por archivos para diagnóstico interactivo desde la UI."""
import json
import time
import uuid
from pathlib import Path


def escribir_json(path,data):
    path=Path(path)
    temporary=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


class DiagnosticBridge:
    def __init__(self,directory,timeout=600):
        self.directory=Path(directory).resolve()
        self.directory.mkdir(parents=True,exist_ok=True)
        self.timeout=timeout

    def comprobar_cancelacion(self):
        if (self.directory/'cancel').exists():
            raise KeyboardInterrupt('Diagnóstico cancelado desde la UI')

    def preguntar(self,text):
        request_id=uuid.uuid4().hex
        path=self.directory/'prompt.json'
        escribir_json(path,{'id':request_id,'text':text,'pending':True})
        deadline=time.monotonic()+self.timeout
        try:
            while time.monotonic()<deadline:
                self.comprobar_cancelacion()
                response=self.directory/'response.json'
                if response.exists():
                    data=json.loads(response.read_text(encoding='utf-8'))
                    if data.get('id')==request_id:
                        return str(data.get('answer',''))
                time.sleep(.25)
            raise TimeoutError('La pregunta de diagnóstico expiró tras 10 minutos')
        finally:
            escribir_json(path,{'id':request_id,'text':text,'pending':False})

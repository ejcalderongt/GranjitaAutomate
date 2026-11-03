"""Un diagnóstico por servidor; procesos sin ventana, logs y cancelación cooperativa."""
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from core.database import ROOT
from core.diagnostic_bridge import escribir_json


class DiagnosticJobs:
    def __init__(self,root=ROOT):
        self.root=Path(root).resolve()
        self.lock=threading.Lock()
        self.process=None
        self.directory=None

    def start(self,package):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError('Ya existe un diagnóstico activo en este servidor')
            directory=self.root/'sessions'/'diagnostics_ui'/uuid.uuid4().hex
            directory.mkdir(parents=True)
            with (directory/'process.log').open('wb') as log:
                process=subprocess.Popen([sys.executable,'-u',str(self.root/'main.py'),
                    '--test-device','--diagnose-device','--package',package,
                    '--diagnostic-session',str(directory)],cwd=self.root,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.process,self.directory=process,directory
            return directory

    def answer(self,prompt_id,answer):
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                raise RuntimeError('El diagnóstico ya terminó')
            prompt=json.loads((self.directory/'prompt.json').read_text(encoding='utf-8'))
            if not prompt.get('pending') or prompt['id']!=prompt_id:
                raise RuntimeError('La pregunta cambió; actualiza la vista')
            escribir_json(self.directory/'response.json',{'id':prompt_id,'answer':answer})

    def cancel(self):
        with self.lock:
            if self.directory and self.process and self.process.poll() is None:
                (self.directory/'cancel').touch()

    def snapshot(self):
        with self.lock:
            if self.directory is None:
                return None
            directory=self.directory
            result={'directory':str(directory),'returncode':self.process.poll()}
            for name in ('prompt','diagnostics'):
                path=directory/f'{name}.json'
                if path.exists():
                    result[name]=json.loads(path.read_text(encoding='utf-8'))
            log=directory/'process.log'
            if log.exists():
                with log.open('rb') as file:
                    file.seek(max(0,log.stat().st_size-12000))
                    result['log']=file.read().decode('utf-8',errors='replace')
            if result['returncode'] is not None and 'diagnostics' not in result:
                result['diagnostics']={'status':'initialization_error',
                    'returncode':result['returncode'],
                    'detail':'El proceso terminó antes de generar diagnostics.json; consultar salida.'}
            return result

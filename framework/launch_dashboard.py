"""Lanzador de escritorio: reutiliza Streamlit o inicia un servidor sin consola."""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8501'


def disponible():
    try:
        with urllib.request.urlopen(URL+'/_stcore/health',timeout=1) as response:
            return response.status==200 and response.read(100).strip()==b'ok'
    except (OSError,urllib.error.URLError):
        return False


def iniciar_dashboard(root=ROOT):
    root=Path(root).resolve()
    from core.project_env import load_project_environment
    load_project_environment(root/'.env')
    sessions=root/'sessions'
    sessions.mkdir(parents=True,exist_ok=True)
    # El bloqueo del SO se libera incluso si se interrumpe el lanzador.
    with (sessions/'dashboard-launch.lock').open('a+b') as lock:
        if os.name=='nt':
            import msvcrt
            lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
            deadline=time.monotonic()+35
            while True:
                try:
                    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                    break
                except OSError:
                    if time.monotonic()>=deadline:
                        raise RuntimeError('Otro lanzador sigue iniciando el dashboard')
                    time.sleep(.2)
        if disponible():
            return URL
        python=root/'.venv'/'Scripts'/'python.exe'
        interpreter=str(python) if python.exists() else sys.executable
        with (sessions/'dashboard-server.log').open('ab') as log:
            process=subprocess.Popen([interpreter,'-m','streamlit','run',str(root/'ui/dashboard.py'),
                '--server.address','127.0.0.1','--server.port','8501','--server.headless','true',
                '--browser.gatherUsageStats','false'],cwd=root,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if disponible():
                return URL
            if process.poll() is not None:
                raise RuntimeError('Streamlit no pudo iniciar. Consulta sessions/dashboard-server.log')
            time.sleep(.3)
        raise RuntimeError('Streamlit no respondió en 30 segundos. Consulta sessions/dashboard-server.log')


if __name__=='__main__':
    try:
        url=iniciar_dashboard()
        if '--no-browser' not in sys.argv:
            webbrowser.open(url,new=2)
    except Exception as exc:
        if os.name=='nt' and '--no-browser' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,str(exc),'Panda Box QA',16)
        else:
            print(str(exc),file=sys.stderr)
        raise SystemExit(1)

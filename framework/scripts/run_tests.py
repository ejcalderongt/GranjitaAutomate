"""Ejecutar la suite sin heredar credenciales ni cargar el .env real."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime,timezone


def main():
    environment=os.environ.copy()
    environment.pop('OPENAI_API_KEY',None)
    environment['GHOST_CURSOR_AUTOCLONE']='0'
    with tempfile.TemporaryDirectory(prefix='panda-test-env-') as folder:
        empty=Path(folder)/'.env'
        empty.write_text('',encoding='utf-8')
        environment['PANDA_ENV_FILE']=str(empty)
        options=sys.argv[1:] or ['-q']
        root=Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0,str(root))
        from core.source_state import huella_codigo
        before=huella_codigo(root)
        result=subprocess.call([sys.executable,'-m','unittest','discover','-s','tests',*options],
            cwd=Path(__file__).resolve().parents[1],env=environment)
        if all(option in ('-q','-v') for option in options):
            from core.audit_artifacts import reporte_bloqueado
            unchanged=before==huella_codigo(root)
            with reporte_bloqueado(root/'runs/resultado_global.json') as report:
                report['global_tests']={'status':'passed' if result==0 and unchanged else 'failed',
                    'exit_code':result,'source_digest':before,'source_unchanged':unchanged,
                    'completed_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'python unittest discover tests'}
        return result


if __name__=='__main__':
    raise SystemExit(main())

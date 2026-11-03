"""Ejecutar la suite sin heredar credenciales ni cargar el .env real."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime,timezone


def log_files(folder):
    return {path.relative_to(folder) for path in folder.rglob('*') if path.is_file()}


def guard_logs(folder,before):
    if log_files(folder)-before:
        raise AssertionError('Suite created files in project logs; use tmp_path')


def run_isolated_unittest(options,root=None):
    """Process-local unittest fixture; production journals keep their ROOT."""
    import unittest
    from core import decision_telemetry
    root=Path(root or Path(__file__).resolve().parents[1])
    (root/'runs').mkdir(parents=True,exist_ok=True)
    previous=decision_telemetry.ROOT
    with tempfile.TemporaryDirectory(prefix='unittest-journals-',dir=root/'runs') as folder:
        try:
            decision_telemetry.ROOT=Path(folder)
            result=unittest.main(module=None,argv=['unittest','discover','-s','tests',*options],exit=False).result
            return 0 if result.wasSuccessful() else 1
        finally:
            decision_telemetry.ROOT=previous


def main():
    environment=os.environ.copy()
    environment.pop('OPENAI_API_KEY',None)
    environment['GHOST_CURSOR_AUTOCLONE']='0'
    root=Path(__file__).resolve().parents[1]
    (root/'runs').mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='panda-test-env-',dir=root/'runs') as folder:
        empty=Path(folder)/'.env'
        empty.write_text('',encoding='utf-8')
        environment['PANDA_ENV_FILE']=str(empty)
        options=sys.argv[1:] or ['-q']
        if str(root) not in sys.path:
            sys.path.insert(0,str(root))
        from core.source_state import huella_codigo
        before=huella_codigo(root)
        logs_before=log_files(root/'logs')
        child='import sys; from scripts.run_tests import run_isolated_unittest; sys.exit(run_isolated_unittest(sys.argv[1:]))'
        result=subprocess.call([sys.executable,'-c',child,*options],
            cwd=Path(__file__).resolve().parents[1],env=environment)
        try:
            guard_logs(root/'logs',logs_before)
        except AssertionError as exc:
            print(str(exc),file=sys.stderr)
            result=1
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

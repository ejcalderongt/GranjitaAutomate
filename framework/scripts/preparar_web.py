"""Preparación reproducible del modo web. Ejecutar con Python 3.11 o superior."""
import argparse
from pathlib import Path
import subprocess
import sys
import re

ROOT=Path(__file__).resolve().parents[1]


def validar_fuente_cursor(source):
    if not re.fullmatch(r'git\+https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+(?:@[A-Za-z0-9_.-]+)?',source):
        raise ValueError('La fuente requiere una URL Git HTTPS completa, con organización y repositorio')
    return source


def instalar_cursor(executable,source):
    """Un fallo opcional conserva operativo el navegador estándar."""
    validar_fuente_cursor(source)
    try:
        subprocess.run([str(executable),'-m','pip','install',source],check=True,
            timeout=120,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run([str(executable),'-c',
            'from playwright_ghost_cursor import create_cursor; assert callable(create_cursor)'],
            check=True,timeout=15,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (OSError,subprocess.SubprocessError) as exc:
        print(f'[Preparación] Cursor opcional no disponible ({type(exc).__name__}); método estándar activo.')
        return False
    print('[Preparación] Paquete de cursor instalado e importación verificada; validar su API en la prueba local.')
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true',help='Crear .venv e instalar requisitos y Chromium')
    parser.add_argument('--cursor-source',help='URL Git HTTPS completa del paquete Python opcional; preferir un commit fijo')
    args=parser.parse_args()
    if args.cursor_source:
        if not args.install:
            parser.error('--cursor-source requiere --install')
        try:
            validar_fuente_cursor(args.cursor_source)
        except ValueError as exc:
            parser.error(str(exc))
    if sys.version_info<(3,11):
        raise RuntimeError('Se requiere Python 3.11 o superior')
    executable=ROOT/'.venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if args.install:
        if not executable.exists():
            subprocess.run([sys.executable,'-m','venv',str(ROOT/'.venv')],check=True)
        subprocess.run([str(executable),str(ROOT/'scripts/preparar_tun2socks.py')],check=True,cwd=ROOT)
        subprocess.run([str(executable),'-m','pip','install','-r',str(ROOT/'requirements.txt'),
            '-r',str(ROOT/'requirements-web.txt')],check=True,cwd=ROOT)
        if args.cursor_source:
            instalar_cursor(executable,args.cursor_source)
        subprocess.run([str(executable),'-m','patchright','install','chromium'],check=True,cwd=ROOT)
    if not executable.exists():
        print('Entorno pendiente. Ejecuta: python scripts/preparar_web.py --install')
        return 2
    return subprocess.call([str(executable),'-c',
        "import importlib.util,sys; from importlib.metadata import version; "
        "ready=importlib.util.find_spec('patchright') is not None; "
        "print('Patchright:',version('patchright') if ready else 'pendiente de instalación'); "
        "print('Cursor Python opcional instalado:',importlib.util.find_spec('playwright_ghost_cursor') is not None); "
        "sys.exit(0 if ready else 2)"],cwd=ROOT)


if __name__=='__main__':
    raise SystemExit(main())

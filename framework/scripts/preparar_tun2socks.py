"""Instalación local verificable del binding oficial; sin compilar Go en Windows."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='https://github.com/LorenEteval/tun2socks-python.git'
VERSION='2.7.0.1'
BASE='https://files.pythonhosted.org/packages/'
SOURCE=('6d/24/c35ec3a396441b0f638926a55f7e635d0659b49133fda20ddffbf963d1ea/tun2socks-2.7.0.1.tar.gz',
        '067ff7d1fba74e261e461e8bd19b9b7c2ee6179bbfd630e39deebe3283574cba')
WHEELS={
    (3,11):('b7/c3/49f67ef768274e06a534b89877e2e093415da41ded32f2d7930335345f33/tun2socks-2.7.0.1-cp311-cp311-win_amd64.whl',
            '7cb257b9da69294dd6f8e9e3b92a88c26cf998f4d041cc3320802d5cf6e4277e'),
    (3,12):('46/f9/2b0f99cd71bd6d56c3c3ad9a8145bf590a86c1a1e6ce98642578f792adac/tun2socks-2.7.0.1-cp312-cp312-win_amd64.whl',
            '0ff64e570ecfb1d06a6b63c6ab33c777c70bc9488a54a99bb46a17c85f6da96f'),
    (3,13):('a0/5d/a0c19ed5474337ac2f7969d162a5acb5ce5957a50cb78354a594adecc6e4/tun2socks-2.7.0.1-cp313-cp313-win_amd64.whl',
            'f1f9306d76508e87c3af74d45e3ecebd32de89673919cd9cc0197d70ff15280d'),
    (3,14):('79/60/7e3e871b66ef4c80970bd7096af20a1d49fdce696b10db2057cd33ec758e/tun2socks-2.7.0.1-cp314-cp314-win_amd64.whl',
            '0418f34be1f3b2d0699994c8ed1f852894d761c7fcdaf34dd66571ffb49622e7'),
}


def descargar(relative,expected):
    with urllib.request.urlopen(BASE+relative,timeout=30) as response:
        content=response.read(12000001)
    if len(content)>12000000 or hashlib.sha256(content).hexdigest()!=expected:
        raise ValueError('Tamaño o SHA-256 del artefacto oficial no coincide')
    return content


def extraer_fuentes(content,target):
    target=Path(target).resolve()
    with tarfile.open(fileobj=io.BytesIO(content),mode='r:gz') as archive:
        total=0
        for member in archive.getmembers():
            if member.isdir():
                continue
            parts=Path(member.name).parts[1:]
            total+=member.size
            if (not member.isfile() or not parts or '..' in parts or member.size>2000000 or total>30000000
                    or any(':' in s or '\\' in s for s in parts)):
                raise ValueError('Archivo del sdist no permitido')
            output=target.joinpath(*parts).resolve()
            if not output.is_relative_to(target):
                raise ValueError('Archivo fuera del destino')
            data=archive.extractfile(member).read()
            if output.exists() and output.read_bytes()!=data:
                raise ValueError('Se conserva una fuente local modificada: '+output.name)
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_bytes(data)


def main():
    if sys.platform!='win32' or platform.machine().lower() not in ('amd64','x86_64') or sys.version_info[:2] not in WHEELS:
        raise RuntimeError('Wheel verificada disponible para CPython 3.11–3.14 Windows AMD64 convencional')
    target=ROOT/'tools/tun2socks-python'
    target.mkdir(parents=True,exist_ok=True)
    source=target/'upstream-src'
    cloned=(source/'.git').is_dir()
    if not source.exists():
        with tempfile.TemporaryDirectory(prefix='agx-tun2socks-') as temporary:
            checkout=Path(temporary)/'source'
            environment=os.environ.copy();environment['GIT_TERMINAL_PROMPT']='0';environment['GCM_INTERACTIVE']='Never'
            try:
                subprocess.run(['git','clone','--depth','1',REPOSITORY,str(checkout)],check=True,timeout=30,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=environment)
                shutil.copytree(checkout,source)
                cloned=True
            except (OSError,subprocess.SubprocessError):
                print('[Dependencias] GitHub no accesible; recuperando sdist oficial verificado.')
                extraer_fuentes(descargar(*SOURCE),source)
    elif not cloned:
        extraer_fuentes(descargar(*SOURCE),source)
    wheel,expected=WHEELS[sys.version_info[:2]]
    wheelhouse=target/'wheelhouse';wheelhouse.mkdir(exist_ok=True)
    output=wheelhouse/wheel.rsplit('/',1)[-1]
    if not output.is_file() or hashlib.sha256(output.read_bytes()).hexdigest()!=expected:
        content=descargar(wheel,expected)
        temporary=output.with_suffix('.tmp');temporary.write_bytes(content);temporary.replace(output)
    subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps',str(output)],check=True,cwd=ROOT)
    subprocess.run([sys.executable,'-c','import tun2socks; assert callable(tun2socks.startFromArgs); print(tun2socks.startFromArgs.__doc__)'],check=True)
    if str(ROOT) not in sys.path:
        sys.path.insert(0,str(ROOT))
    from core.audit_artifacts import reporte_bloqueado
    with reporte_bloqueado(ROOT/'runs/tun2socks-install.json') as report:
        report.update(repository=REPOSITORY,git_clone_succeeded=cloned,version=VERSION,
            source_mode='git' if cloned else 'published_sdist',source_archive_sha256=SOURCE[1],
            wheel=str(output),wheel_sha256=expected,api_import_verified=True,scope='host_windows',
            android_engine_installed=False)
    print('[Dependencias] Binding instalado desde wheel local verificada. El motor Android es independiente.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

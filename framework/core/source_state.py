"""Huella del código bajo prueba; excluye credenciales y artefactos de ejecución."""
import hashlib
from pathlib import Path
from core.database import ROOT


def huella_codigo(root=ROOT):
    root=Path(root)
    files={root/'main.py',root/'main_panda.py',root/'requirements.txt'}
    for directory in ('core','config','ui','scripts','tests'):
        files.update((root/directory).glob('*.py'))
    digest=hashlib.sha256()
    for path in sorted(p for p in files if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()

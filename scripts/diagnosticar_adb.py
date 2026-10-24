"""Comparar servidores ADB sin reiniciar ni modificar conexiones.

Ejecutar desde la raíz: .venv/Scripts/python.exe -m scripts.diagnosticar_adb
"""
import argparse
from collections import Counter

from granjita.core import Adb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ports', nargs='+', type=int, default=[5037, 5038])
    args = parser.parse_args()
    union = set()
    for port in dict.fromkeys(args.ports):
        try:
            adb = Adb(port)
            devices = adb.devices()
            identifiers = {d['serial'] for d in devices}
            results = adb.scan()
            print(f'Puerto {port}: {len(devices)} detectados; estados {dict(Counter(d["state"] for d in devices))}')
            print(f'  Validación: {dict(Counter(d["status"] for d in results))}')
            print(f'  Coincidencias con servidores anteriores: {len(union & identifiers)}')
            union.update(identifiers)
        except Exception as exc:
            print(f'Puerto {port}: no se pudo consultar ({type(exc).__name__}).')
    print(f'Dispositivos distintos detectados: {len(union)}')


if __name__ == '__main__':
    main()

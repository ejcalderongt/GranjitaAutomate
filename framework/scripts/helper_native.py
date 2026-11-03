"""Descarga y validación de bibliotecas Android declaradas por un manifiesto fijado."""
import hashlib
import json
from pathlib import Path
import re
import struct
import urllib.request
from urllib.parse import urlparse

ABIS = {'arm64-v8a': (2, 183), 'armeabi-v7a': (1, 40)}
MAX_LIBRARY_BYTES = 32 * 1024 * 1024
MIRRORS = ('https://mirror.ghproxy.com/', 'https://ghproxy.com/')


def descargar_verificado(url, expected):
    """Los mirrors son transportes alternativos, nunca autoridades del hash."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Se requiere HTTPS sin credenciales')
    if not re.fullmatch('[a-fA-F0-9]{64}', expected):
        raise ValueError('Falta SHA-256 fijado')
    candidates = [url]
    if parsed.hostname == 'github.com':
        if not re.fullmatch(r'/[^/]+/[^/]+/releases/download/[^/]+/[^/]+', parsed.path):
            raise ValueError('Se requiere URL completa de un archivo de release GitHub')
        candidates = [prefix + url for prefix in MIRRORS] + [url]
    errors = []
    for candidate in candidates:
        try:
            with urllib.request.urlopen(candidate, timeout=30) as response:
                if urlparse(response.geturl()).scheme != 'https':
                    raise ValueError('Redirección de descarga sin HTTPS')
                data = response.read(MAX_LIBRARY_BYTES + 1)
            if len(data) > MAX_LIBRARY_BYTES:
                raise ValueError('Biblioteca excede el límite de descarga')
            if hashlib.sha256(data).hexdigest() != expected.lower():
                raise ValueError('SHA-256 de biblioteca no coincide')
            return data, candidate
        except (OSError, ValueError) as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
    raise ValueError('Descarga verificada fallida: ' + '; '.join(errors))


def validar_elf(data, abi):
    """Rechaza ejecutables, arquitecturas incorrectas y archivos truncados."""
    expected_class, expected_machine = ABIS[abi]
    minimum = 64 if expected_class == 2 else 52
    if len(data) < minimum or data[:4] != b'\x7fELF':
        raise ValueError('Biblioteca ELF ausente o truncada: ' + abi)
    if data[4] != expected_class or data[5] != 1 or data[6] != 1:
        raise ValueError('Clase o codificación ELF incompatible: ' + abi)
    kind, machine = struct.unpack_from('<HH', data, 16)
    if kind != 3 or machine != expected_machine:
        raise ValueError('Se requiere ELF compartido de la arquitectura ' + abi)


def preparar_bibliotecas(manifest_path, staging):
    """Acepta URLs HTTPS directas a .so; no inventa repositorios ni hashes."""
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    entries = manifest.get('libraries', {})
    if set(entries) != set(ABIS):
        raise ValueError('El manifiesto debe definir exactamente las dos ABI Android')
    result = {}
    for abi in ABIS:
        entry = entries[abi]
        url, expected = entry.get('url', ''), entry.get('sha256', '')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Se requiere una URL HTTPS de release sin credenciales')
        if not re.fullmatch('[a-fA-F0-9]{64}', expected):
            raise ValueError('Falta SHA-256 fijado para ' + abi)
        data, downloaded_from = descargar_verificado(url, expected)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected.lower():
            raise ValueError('SHA-256 de biblioteca no coincide: ' + abi)
        validar_elf(data, abi)
        destination = Path(staging) / 'src/main/jniLibs' / abi / 'libtun2socks.so'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        result[abi] = {'path': destination, 'sha256': digest, 'url': url,
                       'downloaded_from': downloaded_from}
    return result


def verificar_bibliotecas_apk(package, required=False):
    result = {}
    for abi in ABIS:
        name = 'lib/' + abi + '/libtun2socks.so'
        count = package.namelist().count(name)
        if count > 1:
            raise ValueError('Biblioteca duplicada: ' + name)
        if count:
            data = package.read(name)
            validar_elf(data, abi)
            result[abi] = {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
    if (required or result) and set(result) != set(ABIS):
        raise ValueError('APK incompleto: faltan bibliotecas de las dos ABI requeridas')
    return result

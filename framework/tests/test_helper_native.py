import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.helper_native import validar_elf, preparar_bibliotecas, verificar_bibliotecas_apk, descargar_verificado


def elf(abi):
    data = bytearray(64)
    data[:7] = b'\x7fELF' + bytes([2 if abi == 'arm64-v8a' else 1, 1, 1])
    struct.pack_into('<HH', data, 16, 3, 183 if abi == 'arm64-v8a' else 40)
    return bytes(data)


class NativePackagingTests(unittest.TestCase):
    def test_mirror_hash_mismatch_falls_through_to_next_mirror(self):
        good = elf('arm64-v8a')
        first, second = io.BytesIO(b'HTML'), io.BytesIO(good)
        first.geturl = second.geturl = lambda: 'https://ghproxy.com/file'
        with patch('scripts.helper_native.urllib.request.urlopen', side_effect=[first, second]) as download:
            data, source = descargar_verificado('https://github.com/owner/repo/releases/download/v1/lib.so', hashlib.sha256(good).hexdigest())
        self.assertEqual(data, good)
        self.assertTrue(source.startswith('https://ghproxy.com/'))
        self.assertEqual(download.call_count, 2)

    def test_rejects_domain_without_release(self):
        with self.assertRaises(ValueError):
            descargar_verificado('https://github.com', 'ab' * 32)

    def test_rejects_wrong_architecture_and_executable(self):
        with self.assertRaises(ValueError):
            validar_elf(elf('arm64-v8a'), 'armeabi-v7a')
        data = bytearray(elf('arm64-v8a'))
        struct.pack_into('<H', data, 16, 2)
        with self.assertRaises(ValueError):
            validar_elf(data, 'arm64-v8a')

    def test_requires_both_architectures_before_signing(self):
        with zipfile.ZipFile(io.BytesIO(), 'w') as package:
            package.writestr('lib/arm64-v8a/libtun2socks.so', elf('arm64-v8a'))
            with self.assertRaises(ValueError):
                verificar_bibliotecas_apk(package, required=True)

    def test_checks_hash_before_staging_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / 'native.json'
            manifest.write_text(json.dumps({'libraries': {abi: {
                'url': 'https://example.org/' + abi + '.so', 'sha256': '00' * 32
            } for abi in ('arm64-v8a', 'armeabi-v7a')}}))
            response = io.BytesIO(elf('arm64-v8a'))
            response.geturl = lambda: 'https://example.org/library.so'
            with patch('scripts.helper_native.urllib.request.urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    preparar_bibliotecas(manifest, root)
            self.assertFalse((root / 'src').exists())

    def test_complete_apk_records_exact_library_hashes(self):
        with zipfile.ZipFile(io.BytesIO(), 'w') as package:
            for abi in ('arm64-v8a', 'armeabi-v7a'):
                package.writestr('lib/' + abi + '/libtun2socks.so', elf(abi))
            result = verificar_bibliotecas_apk(package, required=True)
            self.assertEqual(result['arm64-v8a']['sha256'], hashlib.sha256(elf('arm64-v8a')).hexdigest())

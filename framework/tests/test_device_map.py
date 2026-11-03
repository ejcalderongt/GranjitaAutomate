from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from core import device_map

GENERATED_PAIRS = []


def encrypt_stub(payload):
    return hashlib.sha256(payload).digest() + bytes(value ^ 173 for value in payload)


def decrypt_stub(payload):
    plain = bytes(value ^ 173 for value in payload[32:])
    if hashlib.sha256(plain).digest() != payload[:32]:
        raise ValueError('Blob invalido')
    return plain


class DeviceMapTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.salt = uuid4().hex
        self.serials = [uuid4().hex for _ in range(2)]
        self.servers = [{'host': 'localhost', 'port': 5037, 'devices_count': 2}]
        self.plates = [{'plate': 'p' + str(index + 1).zfill(2), 'server': 'localhost:5037',
                        'device_serial_plain': serial} for index, serial in enumerate(self.serials)]
        for patcher in (patch.dict(os.environ, {'PANDA_DEVICE_SALT': self.salt, 'PANDA_DEVICE_MAP_KEEP': '5'}),
                        patch.object(device_map, '_dpapi_encrypt', side_effect=encrypt_stub),
                        patch.object(device_map, '_dpapi_decrypt', side_effect=decrypt_stub)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(device_map._release_active_maps)

    def save(self):
        pair = device_map.save_map(self.plates, self.servers, self.salt, self.root)
        GENERATED_PAIRS.append(dict(pair))
        return pair

    def test_t_dev_1_real_dpapi_roundtrip_when_available(self):
        try:
            device_map._dpapi(b'probe', False)
        except RuntimeError:
            self.skipTest('DPAPI no disponible')
        with patch.object(device_map, '_dpapi_encrypt', side_effect=lambda value: device_map._dpapi(value, False)), \
                patch.object(device_map, '_dpapi_decrypt', side_effect=lambda value: device_map._dpapi(value, True)):
            pair = self.save()
            recovered = device_map.load_latest_map(self.root)
            self.assertIsNotNone(recovered)
            self.assertTrue([item['device_serial_plain'] for item in recovered['plates']] == self.serials)
            blob = (self.root / pair['private']).read_bytes()
            self.assertTrue(all(serial.encode('ascii') not in blob for serial in self.serials))

    def test_t_dev_2_corrupt_blob_preserved_and_logged(self):
        pair = self.save()
        path = self.root / pair['private']
        payload = bytearray(path.read_bytes())
        payload[-1] ^= 1
        path.write_bytes(payload)
        with self.assertLogs('device_map', level='WARNING') as records:
            self.assertIsNone(device_map.load_latest_map(self.root))
        self.assertEqual(records.records[0].getMessage(), 'device_map_corrupt')
        self.assertTrue(path.exists())
        self.assertTrue((self.root / pair['public']).exists())

    def test_t_dev_3_encrypt_failure_writes_nothing(self):
        with patch.object(device_map, '_dpapi_encrypt', side_effect=RuntimeError('fixture')):
            with self.assertRaisesRegex(RuntimeError, '^DPAPI fallo$'):
                self.save()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_t_dev_4_rotation_keeps_latest_pairs(self):
        with patch.dict(os.environ, {'PANDA_DEVICE_MAP_KEEP': '2'}):
            pairs = [self.save() for _ in range(4)]
        self.assertEqual(sorted(path.name for path in (self.root / 'runs').glob('*.json')),
                         sorted(Path(pair['public']).name for pair in pairs[-2:]))
        self.assertEqual(sorted(path.name for path in (self.root / 'secrets').glob('*.bin')),
                         sorted(Path(pair['private']).name for pair in pairs[-2:]))

    def test_t_dev_5_forced_ref_collision_aborts(self):
        with patch.object(device_map, '_derive_ref', return_value='0' * 16):
            with self.assertRaisesRegex(ValueError, '^Colision de referencias$'):
                self.save()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_t_dev_6_refs_are_salted_sixteen_hex(self):
        pair = self.save()
        public = json.loads((self.root / pair['public']).read_text(encoding='ascii'))
        self.assertEqual(public['hash_length_hex'], 16)
        for row, serial in zip(public['plates'], self.serials):
            self.assertRegex(row['device_ref'], '^[0-9a-f]{16}$')
            expected = hashlib.sha256((serial + self.salt).encode('ascii')).hexdigest()[:16]
            self.assertEqual(row['device_ref'], expected)

    def test_t_dev_7_public_output_and_cipher_have_no_plaintext(self):
        pair = self.save()
        for path in self.root.rglob('*'):
            if path.is_file():
                payload = path.read_bytes()
                self.assertTrue(all(serial.encode('ascii') not in payload for serial in self.serials))
                self.assertNotIn(b'device_serial_plain', payload)
        self.assertEqual(set(pair), {'public', 'private'})
        self.assertTrue(pair['public'].startswith('runs/device_map_'))
        self.assertTrue(pair['private'].startswith('secrets/device_map_'))

    def test_t_dev_8_secrets_is_ignored(self):
        ignore = Path(__file__).resolve().parents[1] / '.gitignore'
        self.assertIn('secrets/', ignore.read_text(encoding='ascii').splitlines())

    def test_stub_roundtrip_and_missing_salt_rejected(self):
        self.save()
        recovered = device_map.load_latest_map(self.root)
        self.assertTrue([row['device_serial_plain'] for row in recovered['plates']] == self.serials)
        with patch.dict(os.environ, {'PANDA_DEVICE_SALT': ''}), self.assertLogs('device_map', level='WARNING'):
            self.assertIsNone(device_map.load_latest_map(self.root))

    def test_pair_consistency_rejects_public_tampering(self):
        pair = self.save()
        path = self.root / pair['public']
        original = json.loads(path.read_text(encoding='ascii'))
        for field, replacement in (('device_ref', 'f' * 16), ('server', 'localhost:5038'), ('plate', 'p99')):
            changed = json.loads(json.dumps(original))
            changed['plates'][0][field] = replacement
            path.write_text(json.dumps(changed), encoding='ascii')
            with self.assertLogs('device_map', level='WARNING'):
                self.assertIsNone(device_map.load_latest_map(self.root))
        path.write_text(json.dumps(dict(original, hash_length_hex=8)), encoding='ascii')
        with self.assertLogs('device_map', level='WARNING'):
            self.assertIsNone(device_map.load_latest_map(self.root))
        path.write_text(json.dumps(dict(original, hash_algorithm='invalid')), encoding='ascii')
        with self.assertLogs('device_map', level='WARNING'):
            self.assertIsNone(device_map.load_latest_map(self.root))

    def test_latest_corrupt_pair_does_not_fall_back(self):
        self.save()
        newest = self.save()
        (self.root / newest['private']).write_bytes(b'invalid')
        with self.assertLogs('device_map', level='WARNING'):
            self.assertIsNone(device_map.load_latest_map(self.root))
        device_map.rotate(self.root, 1)
        self.assertTrue((self.root / newest['private']).exists())

    def test_serial_validation_and_duplicate_identities(self):
        for value in (None, 'a' * 3, 'a' * 129, chr(233) * 4, 'a\nbc'):
            with self.assertRaisesRegex(ValueError, '^Serial invalido$'):
                device_map._derive_ref(value, self.salt)
        for key in ('plate', 'device_serial_plain'):
            plates = [dict(row) for row in self.plates]
            plates[1][key] = plates[0][key]
            with self.assertRaisesRegex(ValueError, '^Identidad duplicada$'):
                device_map.save_map(plates, self.servers, self.salt, self.root)

    def test_server_validation_and_duplicate_servers(self):
        for host, port in (('invalid', 5037), ('localhost', True), ('localhost', 1023), ('localhost', 65536)):
            with self.assertRaisesRegex(ValueError, '^Servidor invalido$'):
                device_map.save_map(self.plates, [{'host': host, 'port': port}], self.salt, self.root)
        with self.assertRaisesRegex(ValueError, '^Servidor duplicado$'):
            device_map.save_map(self.plates, self.servers * 2, self.salt, self.root)
        with self.assertRaisesRegex(ValueError, '^Conteo de dispositivos invalido$'):
            device_map.save_map(self.plates, [dict(self.servers[0], devices_count=1)], self.salt, self.root)

    def test_pair_write_failure_rolls_back_without_plaintext(self):
        original = device_map.os.replace
        def fail_public(source, target):
            if Path(target).suffix == '.json':
                raise OSError('fixture')
            return original(source, target)
        with patch.object(device_map.os, 'replace', side_effect=fail_public):
            with self.assertRaisesRegex(RuntimeError, '^Mapa de dispositivos no guardado$'):
                self.save()
        self.assertEqual([path for path in self.root.rglob('*') if path.is_file()], [])

    def test_loaded_and_other_active_pid_pairs_survive_rotation(self):
        first = self.save()
        self.assertIsNotNone(device_map.load_latest_map(self.root))
        second = self.save()
        device_map.rotate(self.root, 1)
        self.assertTrue((self.root / first['public']).exists())
        device_map._release_active_maps()
        with patch.object(device_map, '_pid_active', return_value=True):
            path = self.root / first['public']
            data = json.loads(path.read_text(encoding='ascii'))
            data['owner_pid'] = os.getpid() + 1
            path.write_text(json.dumps(data), encoding='ascii')
            device_map.rotate(self.root, 1)
        self.assertTrue(path.exists())
        self.assertTrue((self.root / first['private']).exists())
        if os.name == 'nt':
            # A separate reader must retain its map even after the writer's lifetime.
            ready = self.root / 'reader-ready'
            code = ('import sys,time; from pathlib import Path; from core import device_map; '
                    'from tests.test_device_map import decrypt_stub; '
                    'device_map._dpapi_decrypt=decrypt_stub; '
                    'assert device_map.load_latest_map(Path(sys.argv[1])) is not None; '
                    'Path(sys.argv[2]).write_text("ready",encoding="ascii"); '
                    'sys.stdin.readline()')
            process = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.root), str(ready)],
                                       cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                self.save()
                with self.assertLogs('device_map', level='WARNING'):
                    device_map.rotate(self.root, 1)
                self.assertTrue((self.root / second['private']).exists())
                self.assertTrue((self.root / second['public']).exists())
            finally:
                try:
                    process.communicate('\n', timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

    def test_timestamp_salt_and_invalid_retention_rejected(self):
        pair = self.save()
        path = self.root / pair['public']
        original = json.loads(path.read_text(encoding='ascii'))
        changed = dict(original, timestamp=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        path.write_text(json.dumps(changed), encoding='ascii')
        with self.assertLogs('device_map', level='WARNING'):
            self.assertIsNone(device_map.load_latest_map(self.root))
        path.write_text(json.dumps(original), encoding='ascii')
        with patch.dict(os.environ, {'PANDA_DEVICE_SALT': uuid4().hex}), self.assertLogs('device_map', level='WARNING'):
            self.assertIsNone(device_map.load_latest_map(self.root))
        with patch.dict(os.environ, {'PANDA_DEVICE_MAP_KEEP': 'invalid'}):
            with self.assertRaisesRegex(ValueError, '^Retencion invalida$'):
                self.save()

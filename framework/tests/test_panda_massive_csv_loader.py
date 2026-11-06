import tempfile
import unittest
from pathlib import Path

from main_panda_masivo import cargar_placas_activas_desde_csv


class CsvDeviceRefTests(unittest.TestCase):
    def load(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'inventory.csv'
            path.write_text('numero_panda,serial_fisico,transporte,alias,estado,device_ref\n'
                            + '\n'.join(rows) + '\n', encoding='ascii')
            return cargar_placas_activas_desde_csv(path)

    def test_loader_preserves_device_ref_when_present(self):
        reference = '1234567890abcdef'
        plates = self.load([f'02,fixture-a,usb-a,Alias,vinculado,{reference}'])
        self.assertEqual(plates[0]['device_ref'], reference)

    def test_loader_rejects_bad_device_ref(self):
        for reference in ('', 'not-hex', 'g' * 16):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(ValueError, 'Referencia de dispositivo invalida'):
                    self.load([f'02,fixture-a,usb-a,Alias,vinculado,{reference}'])
        with self.assertRaisesRegex(ValueError, 'Referencia de dispositivo invalida'):
            self.load(['02,fixture-a,usb-a,Alias,vinculado,1234567890abcdef',
                       '04,fixture-b,usb-b,Alias,vinculado,1234567890abcdef'])

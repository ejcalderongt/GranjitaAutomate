import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import main_panda_masivo as main
from config.farm_policy import FarmPolicy


class StandaloneFarmInventoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.inventory = self.root / 'inventory.csv'
        self.references = [f'{index:016x}' for index in range(1, 4)]
        self.mapping = {'plates': [
            {'plate': f'p{index:02}', 'device_ref': reference,
             'device_serial_plain': f'fixture-{index}', 'server': 'localhost:5037'}
            for index, reference in enumerate(self.references, 1)]}

    def write_inventory(self, *, include_ref=True, mismatch=False):
        fields = ['numero_panda', 'serial_fisico', 'transporte', 'estado']
        if include_ref:
            fields.append('device_ref')
        with self.inventory.open('w', encoding='ascii', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            for index, reference in enumerate(self.references, 1):
                row = [f'{index+1:02}', f'fixture-{index}', f'usb-{index}', 'vinculado']
                writer.writerow(row + ([('f'*16 if mismatch and index == 3 else reference)] if include_ref else []))

    def invoke(self, *, explicit=True):
        args = ['main_panda_masivo.py', '--preflight-farm', '--preflight-proxy',
                '--expected-count', '3', '--db', str(self.root/'scratch.db')]
        if explicit:
            args.extend(['--inventory', str(self.inventory)])
        ctx = {'devices': ['02', '03', '04'], 'synthetic': False}
        with patch('sys.argv', args), patch.object(main, 'ROOT', self.root), \
                patch.object(main, 'load_project_environment'), \
                patch.object(main, 'load_latest_map', return_value=self.mapping) as mapping, \
                patch.object(main, 'load_farm_policy', return_value=FarmPolicy(country='ES')), \
                patch.object(main.ProxyManager, 'desde_panda'), \
                patch.object(main, 'ejecutar_preflight_proxy_solo', new=AsyncMock(return_value=0)) as proxy, \
                patch.object(main, 'build_real_context', new=AsyncMock(return_value=ctx)) as build, \
                patch.object(main, 'run_farm_preflight', new=AsyncMock(return_value=[])) as preflight, \
                patch.object(main, 'decide', return_value='proceed'), \
                patch.object(main, 'write_evidence'):
            code = main.main()
        return code, mapping, proxy, build, preflight

    def assert_rejected(self):
        code, _, proxy, build, preflight = self.invoke()
        self.assertEqual(code, main.EXIT_CONFIG_ERROR)
        proxy.assert_not_awaited()
        build.assert_not_awaited()
        preflight.assert_not_awaited()

    def test_preflight_farm_alone_uses_csv_when_inventory_provided(self):
        self.write_inventory()
        code, mapping, _, build, preflight = self.invoke()
        self.assertEqual(code, main.EXIT_OK)
        mapping.assert_called_once_with(self.root)
        build.assert_awaited_once()
        selected = build.await_args.kwargs['selected_plates']
        self.assertEqual([row['device_ref'] for row in selected], self.references)
        self.assertEqual([row['serial'] for row in selected],
                         [row['device_serial_plain'] for row in self.mapping['plates']])
        preflight.assert_awaited_once()

    def test_preflight_farm_alone_without_inventory_preserves_pool_discovery(self):
        code, mapping, _, build, _ = self.invoke(explicit=False)
        self.assertEqual(code, main.EXIT_OK)
        mapping.assert_not_called()
        build.assert_awaited_once()
        self.assertIsNone(build.await_args.kwargs['selected_plates'])

    def test_preflight_farm_alone_rejects_inventory_mismatch(self):
        self.write_inventory(mismatch=True)
        self.assert_rejected()

    def test_preflight_farm_alone_rejects_missing_device_ref_column(self):
        self.write_inventory(include_ref=False)
        self.assert_rejected()

    def test_preflight_farm_alone_rejects_missing_map(self):
        self.write_inventory()
        self.mapping = None
        self.assert_rejected()

import unittest
from unittest.mock import patch

from config.android_app import TIKTOK_PACKAGE,TIKTOK_ACTIVITY,normalizar_activity,validar_componente_instalado
from config.proxies import ADBError


class GlobalAppTests(unittest.TestCase):
    @patch('sys.argv',['main.py','--smoke-test','3','--cycles','1'])
    def test_smoke_defaults_to_global_component(self):
        from main import argumentos
        args=argumentos()
        self.assertEqual(args.package,TIKTOK_PACKAGE)
        self.assertEqual(args.activity,TIKTOK_ACTIVITY)

    @patch('sys.argv',['main.py','--smoke-test','3','--activity',f'{TIKTOK_PACKAGE}/{TIKTOK_ACTIVITY}'])
    def test_cli_accepts_full_component_without_duplicating_package(self):
        from main import argumentos
        self.assertEqual(argumentos().activity,TIKTOK_ACTIVITY)

    def test_class_namespace_can_differ_from_apk_package(self):
        self.assertEqual(normalizar_activity(TIKTOK_PACKAGE,TIKTOK_ACTIVITY),TIKTOK_ACTIVITY)
        with self.assertRaisesRegex(ValueError,'pertenece'):
            normalizar_activity(TIKTOK_PACKAGE,f'com.ss.android.ugc.aweme/{TIKTOK_ACTIVITY}')
        with self.assertRaisesRegex(ValueError,'ajena'):
            normalizar_activity(TIKTOK_PACKAGE,'org.other.MainActivity')

    @patch('config.device_test.shell')
    def test_resolves_on_device_without_launching(self,shell):
        component=f'{TIKTOK_PACKAGE}/{TIKTOK_ACTIVITY}'
        shell.side_effect=['package:/data/app/base.apk',component]
        self.assertEqual(validar_componente_instalado('usb',TIKTOK_PACKAGE,TIKTOK_ACTIVITY),component)
        self.assertFalse(any('start' in call.args for call in shell.call_args_list))

    @patch('config.device_test.shell',return_value='')
    def test_missing_package_stops_before_resolving_activity(self,shell):
        with self.assertRaisesRegex(ADBError,'no instalada'):
            validar_componente_instalado('usb',TIKTOK_PACKAGE,TIKTOK_ACTIVITY)
        self.assertEqual(shell.call_count,1)

    @patch('config.device_test.shell',side_effect=['package:/data/app/base.apk','No activity found'])
    def test_missing_activity_is_rejected(self,shell):
        with self.assertRaisesRegex(ADBError,'no resuelta'):
            validar_componente_instalado('usb',TIKTOK_PACKAGE,TIKTOK_ACTIVITY)

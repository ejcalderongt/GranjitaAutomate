import subprocess
import unittest
from unittest.mock import patch

from config.proxies import ADBError, adb, verificar_adb
from config.device_test import (
    consultar_ip, ejecutar_prueba_dispositivo, primer_dispositivo_usb, proxy_temporal,
)


class DevicePreflightTests(unittest.TestCase):
    @patch.dict('os.environ',{'ADB_PATH':''})
    @patch('config.proxies.shutil.which')
    def test_project_platform_tools_detected_without_path(self, which):
        which.side_effect=lambda candidate: candidate if 'platform-tools' in candidate else None
        self.assertIn('platform-tools',verificar_adb())
        self.assertIn('tools',verificar_adb())

    @patch.dict('os.environ',{'ADB_PATH':'missing-adb.exe'})
    @patch('config.proxies.shutil.which',return_value=None)
    def test_invalid_explicit_adb_path_is_actionable(self, which):
        with self.assertRaisesRegex(ADBError,'ADB_PATH'):
            verificar_adb()

    @patch('config.device_test.verificar_adb')
    @patch('config.device_test.primer_dispositivo_usb', return_value='usb')
    @patch('config.device_test.configurar_proxy_dispositivo')
    @patch('config.device_test.limpiar_proxy_dispositivo')
    @patch('config.device_test.consultar_ip', return_value='203.0.113.9')
    @patch('config.device_test.shell', return_value='')
    @patch('config.network_guard.trafico_restringido', side_effect=ADBError('Sin root'))
    def test_guard_failure_prevents_launch_and_cleans_proxy(self, guard, shell, ip, cleanup, configure, usb, check):
        with self.assertRaisesRegex(ADBError, 'Sin root'):
            ejecutar_prueba_dispositivo('192.0.2.1:80','203.0.113.9',package='app',activity='.Main')
        self.assertFalse(any('start' in call.args for call in shell.call_args_list))
        cleanup.assert_called_once_with('usb')

    @patch('config.proxies.shutil.which', return_value=None)
    def test_missing_adb_has_install_instructions(self, which):
        with self.assertRaisesRegex(ADBError, 'Platform-Tools'):
            verificar_adb()

    @patch('config.proxies.verificar_adb', return_value='adb.exe')
    @patch('config.proxies.subprocess.run', side_effect=subprocess.TimeoutExpired('adb', 20))
    def test_usb_timeout(self, run, check):
        with self.assertRaisesRegex(ADBError, 'Timeout ADB'):
            adb('devices')

    @patch('config.device_test.adb', return_value=(
        'List of devices attached\n127.0.0.1:5555 device product:x\n'
        'bad unauthorized usb:1-1\nphysical device usb:1-2 product:x\n'))
    def test_first_usb_excludes_tcp_and_unauthorized(self, adb):
        self.assertEqual(primer_dispositivo_usb(), 'physical')

    @patch('config.device_test.adb', return_value='bad offline usb:1-1')
    def test_no_authorized_usb(self, adb):
        with self.assertRaisesRegex(ADBError, 'No hay dispositivo USB'):
            primer_dispositivo_usb()

    @patch('config.device_test.shell', side_effect=['curl 8', '203.0.113.9'])
    def test_curl_forces_proxy_no_direct_fallback(self, shell):
        self.assertEqual(consultar_ip('usb','host:8080'), '203.0.113.9')
        args = shell.call_args.args
        self.assertEqual(args[args.index('--proxy')+1], 'http://host:8080')
        self.assertEqual(args[args.index('--noproxy')+1], '')
        self.assertIn('https://api.ipify.org', args)

    @patch('config.device_test.shell', side_effect=['curl 8', '<html>error</html>'])
    def test_invalid_ip_response(self, shell):
        with self.assertRaisesRegex(ADBError, 'IP válida'):
            consultar_ip('usb','host:80')

    @patch('config.device_test.limpiar_proxy_dispositivo')
    @patch('config.device_test.configurar_proxy_dispositivo', side_effect=ADBError('partial write'))
    def test_cleanup_after_partial_configuration(self, configure, cleanup):
        with self.assertRaises(ADBError):
            with proxy_temporal('usb','host',80):
                self.fail('No debería entrar')
        cleanup.assert_called_once_with('usb')

    @patch('config.device_test.time.sleep')
    @patch('config.device_test.limpiar_proxy_dispositivo', side_effect=ADBError('USB offline'))
    @patch('config.device_test.configurar_proxy_dispositivo')
    def test_cleanup_failure_reports_manual_recovery(self, configure, cleanup, sleep):
        with self.assertRaisesRegex(ADBError, 'NO se pudo confirmar cleanup'):
            with proxy_temporal('usb','host',80):
                pass
        self.assertEqual(cleanup.call_count, 3)

    @patch('config.device_test.limpiar_proxy_dispositivo')
    @patch('config.device_test.configurar_proxy_dispositivo')
    def test_cleanup_on_keyboard_interrupt(self, configure, cleanup):
        with self.assertRaises(KeyboardInterrupt):
            with proxy_temporal('usb','host',80):
                raise KeyboardInterrupt()
        cleanup.assert_called_once_with('usb')

    @patch('config.device_test.verificar_adb')
    @patch('config.device_test.primer_dispositivo_usb', return_value='usb')
    @patch('config.device_test.configurar_proxy_dispositivo')
    @patch('config.device_test.limpiar_proxy_dispositivo')
    @patch('config.device_test.consultar_ip', return_value='203.0.113.9')
    @patch('config.device_test.shell')
    def test_mismatch_prevents_tiktok_and_cleans(self, shell, ip, cleanup, configure, usb, check):
        with self.assertRaisesRegex(ADBError, 'inesperada'):
            ejecutar_prueba_dispositivo('host:80','203.0.113.8',package='tiktok',activity='.Main')
        shell.assert_not_called()
        cleanup.assert_called_once_with('usb')

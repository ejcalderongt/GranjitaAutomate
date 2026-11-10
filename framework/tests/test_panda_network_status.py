import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.panda_lab_status import read_dashboard, write_status
from core.panda_network import prepare_plate, probe_plate


class PandaNetworkStatusTests(unittest.TestCase):
    def setUp(self):
        self.plate = {'server': 'localhost:5037', 'transporte': 'fake-route', 'serial': 'fake-device'}

    def test_ping_is_used_when_curl_is_missing(self):
        with patch('core.panda_network.leer_identidad_fisica', return_value='fake-device'), \
                patch('core.panda_network.adb', side_effect=['', '1 received']) as adb:
            self.assertEqual(probe_plate(self.plate), 'ping_ok')
            self.assertEqual(adb.call_args.args[-6:], ('ping', '-c', '1', '-W', '3', 'ipv4.icanhazip.com'))

    def test_curl_output_is_validated_without_returning_an_address(self):
        with patch('core.panda_network.leer_identidad_fisica', return_value='fake-device'), \
                patch('core.panda_network.adb', side_effect=['curl', 'invalid']) as adb:
            self.assertEqual(probe_plate(self.plate), 'network_failed')
            self.assertEqual(adb.call_count, 2)

    def test_identity_mismatch_prevents_probe(self):
        with patch('core.panda_network.leer_identidad_fisica', return_value='wrong-device'), \
                patch('core.panda_network.adb') as adb:
            self.assertEqual(probe_plate(self.plate), 'identity_unverified')
            adb.assert_not_called()

    def test_prepare_opens_tiktok_and_marks_unsupported_android_settings(self):
        with patch('core.panda_network.leer_identidad_fisica', return_value='fake-device'), \
                patch('core.panda_network.foreground', side_effect=[False, True]), \
                patch('core.panda_network.shell_route', side_effect=[
                    'com.zhiliaoapp.musically/com.example.SplashActivity', '', '', 'es-GT\n',
                    'America/Guatemala', ''
                ]) as shell:
            self.assertEqual(prepare_plate(self.plate,'ES','Europe/Madrid'),
                             {'app':'ok','locale':'manual','timezone':'manual'})
            self.assertEqual(shell.call_args_list[2].args[-2:],
                             ('-n','com.zhiliaoapp.musically/com.example.SplashActivity'))

    def test_prepare_uses_supported_manual_timezone_and_verifies(self):
        with patch('core.panda_network.leer_identidad_fisica', return_value='fake-device'), \
                patch('core.panda_network.foreground', return_value=True), \
                patch('core.panda_network.shell_route', side_effect=[
                    'es-ES', 'America/Guatemala', 'suggest_manual_time_zone --zone_id',
                    'false', '', 'Europe/Madrid'
                ]) as shell:
            self.assertEqual(prepare_plate(self.plate,'ES','Europe/Madrid'),
                             {'app':'ok','locale':'ok','timezone':'ok'})
            self.assertIn('suggest_manual_time_zone',shell.call_args_list[4].args)

    def test_dashboard_omits_raw_fields_and_keeps_previous_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = {'plate':'p01','alias':'Test','device_ref':'a'*16,'serial':'private'}
            first = '2026-01-01T00:00:00+00:00'
            write_status(root,'first',dict(checked_at=first,state='completed',started=True,
                estimated_usd=.01,devices=[{**device,'network':'https_ok'}]))
            write_status(root,'second',dict(checked_at='2026-01-02T00:00:00+00:00',state='blocked',
                started=False,estimated_usd=0,devices=[{**device,'network':'network_failed'}]))
            status=read_dashboard(root,[])
            self.assertEqual((status['online'],status['ready'],status['alerts']),(1,0,2))
            self.assertEqual(status['devices'][0]['last_run'],first)
            self.assertNotIn('serial',status['devices'][0])

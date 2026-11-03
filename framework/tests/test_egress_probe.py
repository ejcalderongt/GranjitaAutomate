import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.device_test import consultar_ip
from config.proxies import ADBError
from core.egress_probe import consultar_salida_nativa


class NativeProbeTests(unittest.TestCase):
    @patch('config.device_test.shell',side_effect=ADBError('curl missing'))
    @patch('core.egress_probe.consultar_salida_nativa',return_value='203.0.113.1')
    def test_native_probe_is_only_enabled_explicitly(self,probe,shell):
        with self.assertRaises(ADBError):consultar_ip('device','192.168.1.199:8001')
        probe.assert_not_called()
        self.assertEqual(consultar_ip('device','192.168.1.199:8001',allow_native=True),'203.0.113.1')

    @patch('core.egress_probe.adb')
    @patch('config.device_test.shell')
    def test_probe_hash_is_verified_before_vm_execution(self,shell,adb):
        with tempfile.TemporaryDirectory() as folder:
            artifact=Path(folder)/'probe.jar'
            artifact.write_bytes(b'test-compiled-probe')
            digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
            shell.side_effect=[ADBError('absent'),digest+' remote','PANDA_EGRESS_IP=203.0.113.1']
            result=consultar_salida_nativa('device','192.168.1.199:8001',artifact=artifact)
            self.assertEqual(result,'203.0.113.1')
            self.assertIn('app_process',shell.call_args.args)
            self.assertIn('org.panda.qa.EgressProbe',shell.call_args.args)
            adb.assert_called_once()

    @patch('core.egress_probe.adb')
    @patch('config.device_test.shell',side_effect=[ADBError('absent'),'different-hash remote'])
    def test_corrupted_uploaded_probe_is_never_executed(self,shell,adb):
        with tempfile.TemporaryDirectory() as folder:
            artifact=Path(folder)/'probe.jar';artifact.write_bytes(b'compiled')
            with self.assertRaisesRegex(ADBError,'integridad'):
                consultar_salida_nativa('device','192.168.1.199:8001',artifact=artifact)
            self.assertFalse(any('app_process' in call.args for call in shell.call_args_list))

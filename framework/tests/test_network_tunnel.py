import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

from core.network_tunnel import TunnelError,validar_preflight,iniciar_motor_tunel_tcp,_worker,MotorTunel
from core.source_state import huella_codigo
from scripts.preparar_tun2socks import extraer_fuentes


class NetworkTunnelTests(unittest.TestCase):
    def test_preflight_requires_actual_apk_hash_and_current_global_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'tools').mkdir();apk=root/'tools/agx_vpn_helper.apk';apk.write_bytes(b'fixture')
            path=root/'report.json';report={'helper_apk_hash':hashlib.sha256(apk.read_bytes()).hexdigest()}
            path.write_text(json.dumps(report))
            with self.assertRaises(TunnelError):validar_preflight(path,root=root)
            report['global_tests']={'status':'passed','exit_code':0,'source_digest':huella_codigo(root)}
            path.write_text(json.dumps(report));self.assertEqual(validar_preflight(path,root=root),report)
            apk.write_bytes(b'changed')
            with self.assertRaises(TunnelError):validar_preflight(path,root=root)

    def test_host_engine_never_unlocks_android_deployment(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.json';path.write_text(json.dumps({'helper_apk_info':{'tcp_engine_included':False}}))
            with patch('core.network_tunnel.validar_preflight',return_value={}):
                with self.assertRaises(TunnelError):
                    iniciar_motor_tunel_tcp(report_path=path,scope='android')
            report=json.loads(path.read_text())
            self.assertEqual(report['motor_tcp_estado'],'bloqueado')
            self.assertFalse(report['motor_tcp_android_deployment_ready'])
            self.assertFalse(report['helper_apk_info']['tcp_engine_included'])

    def test_invalid_report_is_not_replaced_with_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.json';path.write_text('invalid')
            with self.assertRaises(TunnelError):iniciar_motor_tunel_tcp(report_path=path)
            self.assertEqual(path.read_text(),'invalid')

    def test_binding_runs_in_daemon_thread_in_worker(self):
        captured=[]
        def native(*args):
            captured.append((args,threading.current_thread().daemon,threading.current_thread().ident))
        module=SimpleNamespace(startFromArgs=native)
        with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',{'tun2socks':module}):
            path=Path(folder)/'options.json'
            path.write_text(json.dumps(dict(device='tun0',networkInterface='',logLevel='info',proxy='http://127.0.0.1:8001',restAPI='127.0.0.1:6060')))
            self.assertEqual(_worker(path),0)
        self.assertEqual(captured[0][0],('tun0','','info','http://127.0.0.1:8001','127.0.0.1:6060'))
        self.assertTrue(captured[0][1]);self.assertNotEqual(captured[0][2],threading.current_thread().ident)

    def test_source_archive_cannot_write_outside_target(self):
        import io,tarfile
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w:gz') as archive:
            item=tarfile.TarInfo('package/../../outside');item.size=1;archive.addfile(item,io.BytesIO(b'x'))
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):
            extraer_fuentes(output.getvalue(),Path(folder)/'source')

    def test_rest_and_interface_without_data_probe_do_not_mark_active(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);report=root/'report.json';report.write_text('{}');(root/'motor.log').write_text('')
            process=Mock();process.poll.return_value=None
            with patch('core.network_tunnel._rest_ready',return_value=True),patch('core.network_tunnel._interfaz',return_value=True):
                motor=MotorTunel(process,root,report,'test',{'device':'tun0','restAPI':'127.0.0.1:6060'},.01,None)
                self.assertTrue(motor.finalizado.wait(2))
            self.assertEqual(motor.estado,'fallido')
            self.assertFalse(json.loads(report.read_text())['motor_tcp_android_deployment_ready'])
            process.terminate.assert_called_once()

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from config.proxies import ADBError
from core.network_isolation import proxy_laboratorio_sin_root,restaurar_red_dispositivo


class NonrootNetworkTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)
        self.state={'http_proxy':'null','mobile_data':'1'}
        self.calls=[]
        self.fail_enable=False
        def shell(device,*args,**kwargs):
            self.calls.append(args)
            if args[:3]==('settings','get','global'):
                return self.state.get(args[3],'null')
            if args[:3]==('settings','put','global'):
                self.state[args[3]]=args[4]
                return ''
            if args[:3]==('settings','delete','global'):
                self.state[args[3]]='null'
                return ''
            if args[:2]==('svc','data'):
                if self.fail_enable and args[2]=='enable':
                    raise ADBError('restore unavailable')
                self.state['mobile_data']='0' if args[2]=='disable' else '1'
                return ''
            raise AssertionError(args)
        self.shell=patch('core.network_isolation.shell',side_effect=shell)
        self.shell.start()
        self.addCleanup(self.shell.stop)
        self.configure=patch('core.network_isolation.configurar_proxy_dispositivo',
            side_effect=lambda device,host,port:self.state.update(http_proxy=f'{host}:{port}'))
        self.configure.start()
        self.addCleanup(self.configure.stop)

    def test_restores_original_state_and_does_not_claim_isolation(self):
        with proxy_laboratorio_sin_root('device','192.168.1.199',8001,sessions=self.path) as verify:
            verify()
            self.assertEqual(self.state,{'http_proxy':'192.168.1.199:8001','mobile_data':'0'})
            import json
            self.assertFalse(json.loads((self.path/'proxy_lease.json').read_text())['isolation_verified'])
        self.assertEqual(self.state,{'http_proxy':'null','mobile_data':'1'})
        self.assertFalse((self.path/'proxy_lease.json').exists())
        self.assertFalse(any('su' in call for call in self.calls))

    def test_restores_when_body_fails(self):
        with self.assertRaises(RuntimeError):
            with proxy_laboratorio_sin_root('device','192.168.1.199',8001,sessions=self.path):
                raise RuntimeError('feed failed')
        self.assertEqual(self.state['mobile_data'],'1')
        self.assertEqual(self.state['http_proxy'],'null')

    def test_failed_restore_keeps_lease_for_recovery(self):
        with self.assertRaises(ADBError):
            with proxy_laboratorio_sin_root('device','192.168.1.199',8001,sessions=self.path):
                self.fail_enable=True
        self.assertTrue((self.path/'proxy_lease.json').exists())
        self.assertTrue((self.path/'network_restore_required.json').exists())
        self.fail_enable=False
        self.assertTrue(restaurar_red_dispositivo('device',sessions=self.path))

    def test_unknown_mobile_state_changes_nothing(self):
        self.state['mobile_data']='null'
        with self.assertRaises(ADBError):
            with proxy_laboratorio_sin_root('device','192.168.1.199',8001,sessions=self.path):
                self.fail('must not enter')
        self.assertEqual(self.state['http_proxy'],'null')
        self.assertFalse((self.path/'proxy_lease.json').exists())

    def test_external_proxy_change_is_not_overwritten(self):
        with self.assertRaises(ADBError):
            with proxy_laboratorio_sin_root('device','192.168.1.199',8001,sessions=self.path):
                self.state['http_proxy']='192.168.1.88:9000'
        self.assertEqual(self.state['http_proxy'],'192.168.1.88:9000')
        self.assertTrue((self.path/'proxy_lease.json').exists())

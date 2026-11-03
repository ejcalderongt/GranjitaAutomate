import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from config.proxies import ADBError
from core.network_lockdown import establecer_lockdown_vpn_sin_root,liberar_lockdown_dispositivo,lockdown_vpn,KEYS,PACKAGE


class LockdownTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)
        self.state={key:'null' for key in KEYS}
        self.calls=[]
        self.flags_only=False
        self.fail_restore=False
        self.running=False
        def shell(device,*args,**kwargs):
            self.calls.append(args)
            if args[:2]==('pm','path'):
                return 'package:/data/app/helper.apk'
            if args[:3]==('pm','list','packages'):
                return 'package:'+PACKAGE
            if args[:3]==('settings','get','secure'):
                return self.state[args[3]]
            if args[:3]==('settings','put','secure'):
                self.state[args[3]]=args[4]
                return ''
            if args[:3]==('settings','delete','secure'):
                if self.fail_restore:
                    raise ADBError('restore denied')
                self.state[args[3]]='null'
                return ''
            if args[0]=='am':
                self.running=args[-1]!='stop'
                return 'Service operation completed'
            if args[:2]==('content','call'):
                if self.flags_only and self.running:
                    return 'Bundle[{}]'
                status={'nonce':args[-1].split(':',2)[2],'package':PACKAGE,'host':'192.168.1.199','port':8001,
                    'interface':'tun0','public_ip':'8.8.8.8','routes':['0.0.0.0/0','::/0']}
                status.update({key:True for key in ('consent_granted','vpn_active','always_on','lockdown','dns_protected','probe_through_vpn')})
                status['vpn_active']=self.running
                return 'Bundle[{status='+json.dumps(status)+'}]'
            raise AssertionError(args)
        mock=patch('core.network_lockdown.shell',side_effect=shell)
        mock.start();self.addCleanup(mock.stop)
        adb=patch('core.network_lockdown.adb',return_value='usb:1-1')
        adb.start();self.addCleanup(adb.stop)

    def test_valid_helper_is_not_a_certificate_of_no_leaks(self):
        result=establecer_lockdown_vpn_sin_root('usb','192.168.1.199',8001,sessions=self.path)
        self.assertTrue(result['configuracion_vpn_verificada'])
        self.assertFalse(result['aislamiento_acreditado'])
        self.assertTrue(liberar_lockdown_dispositivo('usb',sessions=self.path))
        self.assertEqual(self.state,{key:'null' for key in KEYS})

    def test_flag_one_without_tunnel_is_rejected_and_rolled_back(self):
        self.flags_only=True
        with self.assertRaises(ADBError):
            establecer_lockdown_vpn_sin_root('usb','192.168.1.199',8001,sessions=self.path)
        self.assertEqual(self.state,{key:'null' for key in KEYS})
        self.assertFalse((self.path/'vpn_lease.json').exists())

    def test_missing_apk_does_not_change_settings(self):
        with patch('core.network_lockdown.shell',return_value=''), self.assertRaises(ADBError):
            establecer_lockdown_vpn_sin_root('usb','192.168.1.199',8001,sessions=self.path,
                apk_path=self.path/'absent.apk')
        self.assertFalse((self.path/'vpn_lease.json').exists())

    def test_tcp_only_cannot_enable_lockdown(self):
        with self.assertRaises(ADBError):
            establecer_lockdown_vpn_sin_root('192.168.1.171:5555','192.168.1.199',8001,sessions=self.path)
        self.assertFalse(any(call[:2]==('settings','put') for call in self.calls))

    def test_existing_vpn_is_preserved(self):
        self.state[KEYS[0]]='org.other.vpn'
        with self.assertRaises(ADBError):
            establecer_lockdown_vpn_sin_root('usb','192.168.1.199',8001,sessions=self.path)
        self.assertEqual(self.state[KEYS[0]],'org.other.vpn')
        self.assertFalse(any(call[0]=='am' and call[-1]=='stop' for call in self.calls))

    def test_cleanup_failure_retains_evidence(self):
        with self.assertRaises(ADBError):
            with lockdown_vpn('usb','192.168.1.199',8001,sessions=self.path):
                self.fail_restore=True
        self.assertTrue((self.path/'vpn_lease.json').exists())
        self.assertTrue((self.path/'vpn_restore_required.json').exists())
        self.fail_restore=False
        self.assertTrue(liberar_lockdown_dispositivo('usb',sessions=self.path))

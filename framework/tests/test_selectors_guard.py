import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.network_guard import trafico_restringido
from config.proxies import ADBError
from core.selectors import analizar_xml, capturar_pantalla_y_xml


XML = '''<hierarchy rotation="0">
<node resource-id="app:id/caption" text="un video de prueba" bounds="[0,800][800,950]"/>
<node resource-id="app:id/a1" clickable="true" content-desc="Me gusta, 20" bounds="[800,400][1000,600]"/>
<node resource-id="app:id/a2" clickable="true" content-desc="Comentarios, 3" bounds="[800,600][1000,800]"/>
<node resource-id="app:id/zz" clickable="true" bounds="[0,0][200,100]"/>
</hierarchy>'''


class SelectorTests(unittest.TestCase):
    def test_candidates_and_obfuscated_clickable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'ui.xml'
            path.write_text(XML,encoding='utf-8')
            report = analizar_xml(path,screen_size=(1000,1000))
        self.assertEqual(len(report['candidates']['description']),1)
        self.assertEqual(len(report['candidates']['like']),1)
        self.assertEqual(len(report['candidates']['comments']),1)
        self.assertEqual(len(report['clickable_components']),3)
        self.assertEqual(report['candidates']['like'][0]['center_relative'],[.9,.5])

    def test_reject_entities(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'ui.xml'
            path.write_text('<!DOCTYPE foo><hierarchy/>')
            with self.assertRaises(ValueError):
                analizar_xml(path)

    @patch('core.selectors.adb')
    def test_dump_pull_report(self, adb):
        def run(*args, **kwargs):
            if 'dump' in args:
                return 'UI hierchary dumped to: /sdcard/window_dump.xml'
            if 'pull' in args and args[-2].endswith('.xml'):
                Path(args[-1]).write_text(XML,encoding='utf-8')
            if args[-2:] == ('wm','size'):
                return 'Physical size: 1000x1000'
            return ''
        adb.side_effect = run
        with tempfile.TemporaryDirectory() as temp:
            capturar_pantalla_y_xml('usb',temp)
            report = json.loads((Path(temp)/'components.json').read_text(encoding='utf-8'))
            self.assertEqual(report['udid'],'usb')
            self.assertTrue((Path(temp)/'window_dump.xml').exists())

    @patch('core.selectors.adb',return_value='ERROR: could not get idle state')
    def test_failed_dump_does_not_pull_stale_file(self, adb):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ADBError):
                capturar_pantalla_y_xml('usb',temp)
        self.assertFalse(any('pull' in call.args for call in adb.call_args_list))


class GuardTests(unittest.TestCase):
    @patch('config.network_guard.shell')
    def test_no_root_refuses_and_saves_netpolicy(self, shell):
        shell.side_effect = ['policy diagnostics','2000',ADBError('su not found')]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ADBError,'Sin root'):
                with trafico_restringido('usb','192.0.2.1',8080,temp):
                    self.fail('No debería abrir app')
            self.assertTrue((Path(temp)/'netpolicy.txt').exists())

    @patch('config.network_guard.shell')
    def test_ipv4_ipv6_allowlist_and_cleanup(self, shell):
        shell.side_effect = lambda device,*args: '0' if args==('id','-u') else ''
        with tempfile.TemporaryDirectory() as temp:
            with trafico_restringido('usb','192.0.2.1',8080,temp) as check:
                check()
                self.assertTrue((Path(temp)/'firewall_cleanup_required.txt').exists())
            self.assertFalse((Path(temp)/'firewall_cleanup_required.txt').exists())
        calls = [c.args for c in shell.call_args_list]
        self.assertTrue(any('ip6tables' in c and '-I' in c for c in calls))
        self.assertTrue(any('iptables' in c and 'ACCEPT' in c and '192.0.2.1' in c for c in calls))
        self.assertEqual(sum('-X' in c for c in calls),2)
        self.assertFalse(any('-F' in c and 'OUTPUT' in c for c in calls))

    @patch('config.network_guard.shell')
    def test_partial_install_rolls_back(self, shell):
        def run(device,*args):
            if args==('id','-u'):
                return '0'
            if args[0]=='ip6tables' and '-A' in args:
                raise ADBError('install failure')
            return ''
        shell.side_effect = run
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ADBError):
                with trafico_restringido('usb','192.0.2.1',80,temp):
                    self.fail('No debería abrir app')
        self.assertEqual(sum('-X' in c.args for c in shell.call_args_list),2)

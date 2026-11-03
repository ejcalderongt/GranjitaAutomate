import json
from pathlib import Path
import tempfile
import unittest

from scripts.local_proxy_runtime import prepare_settings


class LocalProxyRuntimeTests(unittest.TestCase):
    def fixture(self,root,mode='laboratory'):
        (root/'config').mkdir()
        (root/'config/local_proxy.local.json').write_text(json.dumps({'host':'192.168.1.199','ports':[8001,8002,8003],
            'allowed_clients':['192.168.1.131','192.168.1.199']}))
        pool={'mode':mode,'lab_host':'192.168.1.199','proxies':[{'host':'192.168.1.199','port':8001,'exit_ip':'8.8.8.8','enabled':True}]}
        (root/'config/proxy_pool.json').write_text(json.dumps(pool))
        return pool

    def test_login_updates_lab_for_changed_dhcp_and_real_observed_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            settings=prepare_settings(root,detect=lambda s:'192.168.1.200',observe=lambda:'9.9.9.9')
            self.assertEqual(settings['host'],'192.168.1.200')
            pool=json.loads((root/'config/proxy_pool.json').read_text())
            self.assertEqual(pool['lab_host'],'192.168.1.200')
            self.assertEqual(pool['proxies'][0]['exit_ip'],'9.9.9.9')
            self.assertTrue(pool['proxies'][0]['enabled'])

    def test_auto_configuration_never_changes_production_pool(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);original=self.fixture(root,'production')
            prepare_settings(root,detect=lambda s:'192.168.1.200',observe=lambda:'9.9.9.9')
            self.assertEqual(json.loads((root/'config/proxy_pool.json').read_text()),original)

    def test_invalid_observations_do_not_replace_known_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);original=self.fixture(root)
            settings=prepare_settings(root,detect=lambda s:'0.0.0.0',observe=lambda:'192.168.1.1')
            self.assertEqual(settings['host'],'192.168.1.199')
            self.assertEqual(json.loads((root/'config/proxy_pool.json').read_text()),original)

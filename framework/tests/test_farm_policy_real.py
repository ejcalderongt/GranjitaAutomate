import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.farm_policy import FarmPolicy, load_farm_policy


class RealPolicyTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_new_policy_values_load_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'.env'
            path.write_text('PANDA_POLICY_PROXY_MIN_DISTINCT_EXIT_IPS=2\nPANDA_POLICY_PROXY_STICKY_TTL=120\nPANDA_POLICY_MAX_CAPTCHAS=1\nPANDA_POLICY_MAX_SOFTBLOCKS=2\nPANDA_POLICY_MAX_LOGOUTS=3\nPANDA_POLICY_MIN_METRIC_SAMPLES=4\n',encoding='ascii')
            policy = load_farm_policy(path)
        self.assertEqual((policy.proxy_min_distinct_exit_ips,policy.proxy_sticky_ttl), (2,120))
        self.assertEqual((policy.max_captchas,policy.max_softblocks,policy.max_logouts,policy.min_metric_samples), (1,2,3,4))

    def test_invalid_policy_limits_are_rejected(self):
        for values in ({'proxy_min_distinct_exit_ips':33}, {'proxy_sticky_ttl':-1},
                       {'max_captchas':-1}, {'max_softblocks':-1}, {'max_logouts':-1}, {'min_metric_samples':0}):
            with self.assertRaisesRegex(ValueError, '^Politica de granja invalida$'):
                FarmPolicy(**values)

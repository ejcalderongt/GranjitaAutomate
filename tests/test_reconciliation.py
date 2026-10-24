from unittest import TestCase
from unittest.mock import patch
from granjita.reconciliation import endpoint, diagnosis, reconcile

class ReconciliationTests(TestCase):
    def test_endpoint_rejects_commands_and_nonprivate(self):
        for value in ['example:5555','8.8.8.8:5555','127.0.0.1:5555','0.0.0.0:1','192.168.1.2:0','192.168.1.2:5555;bad']:
            self.assertFalse(endpoint(value),value)
        self.assertTrue(endpoint('192.168.1.2:5555'))

    def test_absence_is_not_power_failure(self):
        recognition, advice=diagnosis(dict(status='Desconectado',hardware_serial='TEST'),[],False)
        self.assertEqual(recognition,'Sin comprobar')
        self.assertIn('energía no comprobada',advice)

    def test_only_missing_known_origin_is_retried(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        first=dict(devices=[dict(serial='192.168.1.1:5555',status='Validado')],servers=[dict(port=5037,status='ADB responde')],warning='')
        known=[dict(port=5037,serial='192.168.1.1:5555'),dict(port=5037,serial='192.168.1.2:5555'),dict(port=5038,serial='192.168.1.3:5555')]
        with TemporaryDirectory() as folder, patch('granjita.reconciliation.DATA',Path(folder)), patch('granjita.reconciliation.ensure_panda',return_value='OK'), patch('granjita.reconciliation.list_devices',side_effect=RuntimeError('No API')), patch('granjita.reconciliation.scan_fleet',side_effect=[first,dict(first)]), patch('granjita.reconciliation.reconnect',return_value={'result':'intentado'}) as retry:
            result=reconcile([5037],known,'unused')
            retry.assert_called_once_with(5037,'192.168.1.2:5555')
            self.assertEqual(result['reconciliation']['panda_error'],'No API')

    def test_physical_duplicates_and_active_aliases_are_skipped(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        first=dict(devices=[dict(serial='192.168.1.1:5555',status='Validado',hardware_serial='ACTIVE')],servers=[dict(port=5037,status='ADB responde')],warning='')
        known=[dict(port=5037,serial='192.168.1.2:5555',hardware_serial='ACTIVE'),dict(port=5037,serial='192.168.1.3:5555',hardware_serial='MISSING'),dict(port=5037,serial='192.168.1.4:5555',hardware_serial='MISSING')]
        with TemporaryDirectory() as folder, patch('granjita.reconciliation.DATA',Path(folder)), patch('granjita.reconciliation.ensure_panda',return_value='OK'), patch('granjita.reconciliation.list_devices',return_value=[]), patch('granjita.reconciliation.scan_fleet',side_effect=[first,dict(first)]), patch('granjita.reconciliation.reconnect',return_value={}) as retry:
            reconcile([5037],known,'unused')
            retry.assert_called_once_with(5037,'192.168.1.3:5555')

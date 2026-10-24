from unittest import TestCase
from scripts.deploy_tools import supplement_from_panda


class DeploymentIdentityTests(TestCase):
    def test_panda_and_live_serial_must_agree(self):
        observed=dict(serial='192.0.2.1:5555',port=5037,hardware_serial='TESTSERIAL01',status='Validado')
        panda=dict(serial=observed['serial'],onlySerial='TESTSERIAL01')
        rows=supplement_from_panda({'devices':[observed]},[],[],[panda])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['hardware_serial'],'TESTSERIAL01')
        self.assertEqual(supplement_from_panda({'devices':[observed]},[],[],[dict(panda,onlySerial='OTHERSERIAL')]),[])

    def test_duplicate_and_conflicting_serials_are_not_accepted(self):
        observed=dict(serial='192.0.2.1:5555',port=5037,hardware_serial='TESTSERIAL01',status='Validado')
        panda=dict(serial=observed['serial'],onlySerial='TESTSERIAL01')
        self.assertEqual(supplement_from_panda({'devices':[observed]},[],[],[panda,dict(panda,serial='other')]),[])
        self.assertEqual(supplement_from_panda({'devices':[dict(observed,identity_conflict=True)]},[],[],[panda]),[])

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core.audit_artifacts import inyectar_perfil_en_auditoria
from core.network_lockdown import _boton_consentimiento_vpn
from scripts.compilar_helper import calcular_hash_apk,verificar_y_registrar_helper


class ArtifactTests(unittest.TestCase):
    def test_hardware_metadata_does_not_change_network_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'runs/diagnostico-real-test/resultado.json'
            path.parent.mkdir(parents=True)
            original={'proxy_audit':[{'device_id':'plate','ip_observada':'8.8.8.8','alcance':'sondeo HTTPS',
                                     'resultado':'fallido'}],'remaining_leases':[{'estado':'cuarentena'}]}
            path.write_text(json.dumps(original))
            self.assertTrue(inyectar_perfil_en_auditoria('test',{'device_id':'plate','sdk_level':31,
                'width':1080,'height':1920,'density':420},root=root))
            report=json.loads(path.read_text())
            self.assertEqual(report['proxy_audit'],original['proxy_audit'])
            self.assertEqual(report['remaining_leases'],original['remaining_leases'])
            self.assertFalse(report['hardware_profiles']['plate']['network_isolation_verified'])
            with self.assertRaises(ValueError):
                inyectar_perfil_en_auditoria('../outside',{},root=root)

    def test_only_identified_helper_permission_dialog_is_clickable(self):
        xml='<hierarchy><node text="AGX VPN Lockdown Helper"/><node package="com.android.vpndialogs" resource-id="android:id/button1" enabled="true" clickable="true" bounds="[100,100][200,200]"/></hierarchy>'
        focus='mCurrentFocus=Window{com.android.vpndialogs/.ConfirmDialog}'
        self.assertEqual(_boton_consentimiento_vpn(xml,focus),(150,150))
        self.assertIsNone(_boton_consentimiento_vpn(xml,'mCurrentFocus=Window{org.other/.Activity}'))
        self.assertIsNone(_boton_consentimiento_vpn(xml.replace('AGX VPN Lockdown Helper','Other VPN'),focus))

    def test_nonempty_file_is_not_enough_to_validate_apk(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'helper.apk';path.write_bytes(b'not an apk')
            with self.assertRaises(zipfile.BadZipFile):
                verificar_y_registrar_helper(path,Path(folder)/'result.json')
            self.assertFalse((Path(folder)/'result.json').exists())

    def test_hash_report_preserves_prior_audit_and_does_not_certify_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);apk=root/'helper.apk';report=root/'resultado.json'
            with zipfile.ZipFile(apk,'w') as package:
                package.writestr('classes.dex',b'dex\n035\0')
                package.writestr('AndroidManifest.xml',b'\x03\x00fake-unit-fixture')
            report.write_text(json.dumps({'proxy_audit':[{'resultado':'fallido'}]}))
            with patch('scripts.compilar_helper.localizar_sdk',return_value=root), \
                 patch('scripts.compilar_helper.herramientas',return_value=(root,root/'android.jar',{'java':'java'})), \
                 patch('scripts.compilar_helper.ejecutar',side_effect=[
                     'Signer #1 certificate SHA-256 digest: '+'ab'*32,"package: name='org.agx.vpntunnel'"]):
                verificar_y_registrar_helper(apk,report)
            data=json.loads(report.read_text())
            self.assertEqual(data['helper_apk_hash'],calcular_hash_apk(apk))
            self.assertEqual(data['proxy_audit'],[{'resultado':'fallido'}])
            self.assertFalse(data['helper_apk_info']['network_isolation_verified'])

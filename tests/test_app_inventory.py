import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch,MagicMock
from xml.sax.saxutils import escape
from granjita.app_inventory import AppInventory,classify_screen,account_handle,collect_technical,inspect_screen,InspectionSession
from granjita.inventory import FleetStore
from test_inventory import device,report

PKG='com.zhiliaoapp.musically'

def screen(texts,profile=False,other_package=None):
    nodes=['<node package="'+(other_package or PKG)+'" text="'+escape(t,{'"':'&quot;'})+'" clickable="'+('true' if t in ('Editar perfil','Edit profile') else 'false')+'" />' for t in texts]
    if profile:nodes.append('<node package="'+PKG+'" text="Perfil" selected="true" />')
    return '<hierarchy>'+''.join(nodes)+'</hierarchy>'

class AppInventoryTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=FleetStore(Path(self.tmp.name)/'fleet.sqlite3')
        self.device=dict(device(5037,'192.0.2.1:5555'),hardware_serial='TESTSERIAL',manufacturer='samsung',hardware_model='Board')
        self.store.save_fleet(report([self.device]));self.row=self.store.fleet_devices()[0];self.inv=AppInventory(self.store)
    def observe(self,texts,profile=False):self.inv.observe(self.row,'tiktok','screen',classify_screen(screen(texts,profile),'tiktok'),'uiautomator2')
    def test_feed_mentions_never_become_own_account(self):
        result=classify_screen(screen(['Para ti','Siguiendo','@cuenta_ajena']),'tiktok')
        self.assertEqual(result['screen_state'],'feed_visible');self.assertEqual(result['account_state'],'unknown');self.assertEqual(result['observed_account'],'')
    def test_profile_requires_selected_tab_edit_button_and_unique_handle(self):
        result=classify_screen(screen(['Editar perfil','@cuenta_prueba'],True),'tiktok')
        self.assertEqual(result['observed_account'],'@cuenta_prueba');self.assertEqual(result['account_state'],'session_observed')
        self.assertEqual(classify_screen(screen(['Editar perfil','@cuenta_prueba']),'tiktok')['observed_account'],'')
        self.assertEqual(classify_screen(screen(['Editar perfil','@cuenta_prueba','@otra'],True),'tiktok')['screen_state'],'ambiguous')
    def test_onboarding_login_and_permission_are_distinct(self):
        for texts,wanted in [(['Cuéntanos más cosas sobre ti'],'onboarding'),(['Iniciar sesión en TikTok'],'login_prompt')]:
            self.assertEqual(classify_screen(screen(texts),'tiktok')['screen_state'],wanted)
        self.assertEqual(classify_screen(screen(['Permitir'],other_package='com.android.permissioncontroller'),'tiktok')['screen_state'],'permission_dialog')
    def test_other_apps_have_no_invented_account_adapter(self):
        result=classify_screen(screen(['@cuenta'],other_package='com.instagram.android'),'instagram')
        self.assertEqual(result['account_state'],'unknown');self.assertEqual(result['signals'],['account_adapter_pending'])
    def test_assignment_is_not_an_observed_session(self):
        self.inv.assign(self.row,'tiktok','@esperada')
        value=self.inv.view(self.row,'tiktok')
        self.assertEqual(value['observed_account'],'');self.assertEqual(value['match'],'unverified');self.assertEqual(value['account_state'],'unknown')
    def test_manual_confirmation_comparison_and_immutable_history(self):
        self.inv.assign(self.row,'tiktok','@esperada')
        self.inv.confirm(self.row,'tiktok','@diferente','session_observed')
        self.assertEqual(self.inv.view(self.row,'tiktok')['match'],'mismatch')
        self.inv.confirm(self.row,'tiktok','@ESPERADA','session_observed')
        self.assertEqual(self.inv.view(self.row,'tiktok')['match'],'match')
        self.assertEqual(len(self.inv.history(self.row,'tiktok')['observations']),2)
        self.inv.assign(self.row,'tiktok','')
        self.assertEqual(self.inv.view(self.row,'tiktok')['match'],'unassigned')
        self.assertEqual(len(self.inv.history(self.row,'tiktok')['assignments']),2)
    def test_technical_refresh_does_not_erase_account_observation(self):
        self.inv.confirm(self.row,'tiktok','@cuenta','session_observed')
        for _ in range(205):self.inv.observe(self.row,'tiktok','technical',dict(status='error',error_class='TimeoutError'),'adb')
        value=self.inv.view(self.row,'tiktok')
        self.assertEqual(value['observed_account'],'@cuenta');self.assertEqual(value['technical_status'],'error')
        self.assertEqual(value['installation'],'unknown')
    def test_missing_app_and_old_evidence_cannot_confirm_current_assignment(self):
        self.inv.assign(self.row,'tiktok','@cuenta');self.inv.confirm(self.row,'tiktok','@cuenta','session_observed')
        self.inv.observe(self.row,'tiktok','technical',dict(status='ok',installation='not_installed',variants=[],foreground=False),'adb')
        self.assertEqual(self.inv.view(self.row,'tiktok')['match'],'unverified')
        with self.store.connect() as db:db.execute("UPDATE device_app_observations SET at='2020-01-01T00:00:00-06:00' WHERE scope='screen'")
        self.assertFalse(self.inv.view(self.row,'tiktok')['fresh'])
    def test_new_assignment_requires_a_subsequent_observation(self):
        self.inv.confirm(self.row,'tiktok','@cuenta','session_observed');self.inv.assign(self.row,'tiktok','@cuenta')
        self.assertEqual(self.inv.view(self.row,'tiktok')['match'],'unverified')
    def test_private_payload_is_restricted_and_identity_changes_block_writes(self):
        with self.assertRaises(ValueError):self.inv.observe(self.row,'tiktok','screen',dict(password='secret'),'manual')
        with self.assertRaises(ValueError):account_handle('correo@example.com')
        with self.assertRaises(ValueError):self.inv.confirm(self.row,'tiktok','','session_observed')
        changed=dict(self.row,hardware_serial='OTHERSERIAL')
        with self.assertRaises(ValueError):self.inv.assign(changed,'tiktok','cuenta')
    def test_android_failure_is_not_absence_of_apps(self):
        with patch('granjita.automation.validate_target'),patch('granjita.app_inventory.shell',return_value='Error: not permitted'):
            with self.assertRaises(RuntimeError):collect_technical(self.row)
    def test_reading_current_screen_never_launches_or_navigates(self):
        resumed='ResumedActivity: '+PKG+'/.Main'
        fake=MagicMock();fake.__enter__.return_value.source.return_value=screen(['Para ti','Siguiendo'])
        with patch('granjita.automation.validate_target'),patch('granjita.app_inventory.query',return_value=resumed) as query,patch('granjita.app_inventory.InspectionSession',return_value=fake):
            result=inspect_screen(self.row,'tiktok')
        self.assertEqual(result['screen_state'],'feed_visible');self.assertTrue(all(c.args[2]=='dumpsys activity activities' for c in query.call_args_list))
    def test_inspection_session_cannot_inherit_lab_launch_capabilities(self):
        with patch('granjita.automation.validate_target'),patch('granjita.automation.start_appium'),patch('granjita.automation.http',return_value=dict(sessionId='test')) as http:
            with InspectionSession(self.row):pass
        caps=http.call_args_list[0].args[2]['capabilities']['alwaysMatch']
        for key in ('appium:app','appium:appPackage','appium:appActivity'):self.assertNotIn(key,caps)
        self.assertFalse(caps['appium:autoLaunch']);self.assertFalse(caps['appium:shouldTerminateApp'])
    def test_aliased_fiche_resolves_observations(self):
        with self.store.connect() as db:
            db.execute("INSERT INTO inventory_devices VALUES('old','', '2026-01-01')")
            db.execute("INSERT INTO device_identity_aliases VALUES('old',?,'2026-01-01','{}')",(self.row['id'],))
        self.inv.assign(dict(self.row,id='old'),'tiktok','cuenta')
        self.assertEqual(self.inv.view(self.row,'tiktok')['expected_account'],'@cuenta')

    def test_declaration_is_separate_persistent_and_atomic(self):
        self.inv.declare_batch([(self.row,True,6)],'tiktok','user_report')
        self.observe(['Para ti','Siguiendo'])
        value=self.inv.view(self.row,'tiktok')
        self.assertEqual(value['declared_presence'],'present')
        self.assertEqual(value['account_state'],'unknown')
        self.assertEqual(value['observed_account'],'')
        with self.assertRaises(ValueError):self.inv.declare_batch([(self.row,False,6),(self.row,True,6)],'tiktok','user_report')
        self.assertEqual(self.inv.view(self.row,'tiktok')['declared_presence'],'present')
        self.inv.declare_batch([(self.row,False,6)],'tiktok','user_report')
        self.assertEqual(self.inv.view(self.row,'tiktok')['declared_presence'],'absent')
        self.assertEqual(len(self.inv.history(self.row,'tiktok')['observations']),3)

    def test_panda_report_mapping_rejects_ambiguity(self):
        from scripts.registrar_cuentas_declaradas import resolve_entries
        panda=[dict(sort=6,onlySerial='TESTSERIAL')]
        self.assertEqual(resolve_entries({'6':True},panda,[self.row])[0][0]['id'],self.row['id'])
        with self.assertRaises(ValueError):resolve_entries({'6':True},panda*2,[self.row])
        with self.assertRaises(ValueError):resolve_entries({'7':False},panda,[self.row])

from pathlib import Path
import tempfile
import unittest
from core.database import Database
from core.network_audit import verificar_proxy_auditable
from config.proxies import ProxyAllocator


class NetworkAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db=Database(Path(self.folder.name)/'test.db')
        self.allocator=ProxyAllocator(self.db)
        self.endpoint='192.168.1.199:8001'
        self.allocator.sincronizar([{'endpoint':self.endpoint,'host':'192.168.1.199','port':8001,
            'exit_ip':'8.8.8.8','enabled':True,'lab_shared_exit':True}])
        self.allocator.reservar('plate','run',self.endpoint)

    def verify(self,config=None,probe=None):
        return verificar_proxy_auditable(self.db,self.allocator,'run','plate',self.endpoint,
            leer_configuracion=config or (lambda:self.endpoint),
            consultar_salida=probe or (lambda:'8.8.8.8'),expected_ip='8.8.8.8')

    def test_confirmed_exit_has_expected_observed_and_latency(self):
        self.assertEqual(self.verify(),'8.8.8.8')
        row=self.db.auditoria_proxies('run')[0]
        self.assertEqual((row['resultado'],row['etapa']),('confirmado','salida_https'))
        self.assertEqual(row['ip_observada'],row['ip_esperada'])
        self.assertGreaterEqual(row['latencia_ms'],0)

    def test_configuration_mismatch_is_persisted_without_observed_ip(self):
        with self.assertRaises(ValueError):
            self.verify(config=lambda:'null')
        row=self.db.auditoria_proxies()[0]
        self.assertEqual(row['resultado'],'fallido')
        self.assertEqual(row['etapa'],'configuracion')
        self.assertIsNone(row['ip_observada'])

    def test_timeout_and_wrong_exit_never_confirm(self):
        def timeout():
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            self.verify(probe=timeout)
        self.assertEqual(self.db.auditoria_proxies()[0]['error_tipo'],'TimeoutError')
        with self.assertRaises(ValueError):
            self.verify(probe=lambda:'1.1.1.1')
        row=self.db.auditoria_proxies()[0]
        self.assertEqual(row['ip_observada'],'1.1.1.1')
        self.assertEqual(row['resultado'],'fallido')

    def test_web_mapping_is_not_an_idle_lease(self):
        self.allocator.finalizar('plate','run',cleanup_ok=True)
        with self.db.conexion() as con:
            con.execute('INSERT INTO proxy_perfiles VALUES (?,?)',('web:cuenta_01',self.endpoint))
        self.assertEqual(self.allocator.disponibles(),1)
        self.assertIsNotNone(self.allocator.reservar('physical','physical-run'))
        self.assertIsNone(self.allocator.reservar('web:cuenta_01','web-run',self.endpoint))
        self.allocator.finalizar('physical','physical-run',cleanup_ok=True)
        self.assertIsNotNone(self.allocator.reservar('web:cuenta_01','web-run',self.endpoint))
        self.assertIsNone(self.allocator.reservar('physical','other-run',self.endpoint))

    def test_action_intent_and_sent_command_are_distinct(self):
        interaction=self.db.registrar_interaccion('plate',run_id='feed',ciclo=1,
            descripcion_video='test',decision_ia={'interactuar':True},latencia_ms=2)
        self.db.registrar_accion(interaction,'like_attempt')
        self.assertEqual(self.db.auditoria_de_acciones()[0]['resultado'],'intentada')
        self.db.finalizar_interaccion(interaction,error='ADBError')
        rows,_=self.db.interacciones()
        self.assertFalse(rows[0]['dio_like'])
        self.db.registrar_accion(interaction,'like_click',server_acceptance_verified=False)
        action=self.db.auditoria_de_acciones()[0]
        self.assertEqual(action['resultado'],'comando_enviado')
        self.assertIn('false',action['detalle'])

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.database import Database
from config.proxies import ProxyAllocator
from scripts.inicializar_pool_sqlite import inicializar
from core.project_env import load_project_environment


class LaboratoryInitializationTests(unittest.TestCase):
    def test_mapping_idempotence_and_exclusive_leases(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            pool=root/'pool.json'
            pool.write_text(json.dumps({'mode':'laboratory','lab_host':'192.168.1.199',
                'proxies':[{'host':'192.168.1.199','port':8000+i,'exit_ip':'8.8.8.8','enabled':True}
                           for i in range(1,4)]}))
            db=Database(root/'test.db')
            accounts=root/'accounts.json'
            inicializar(db,pool,accounts)
            inicializar(db,pool,accounts)
            allocator=ProxyAllocator(db)
            self.assertIsNone(allocator.reservar('web:cuenta_02','run','192.168.1.199:8001'))
            self.assertIsNone(allocator.reservar('web:other','run','192.168.1.199:8001'))
            self.assertEqual(allocator.reservar('web:cuenta_01','run')['endpoint'],'192.168.1.199:8001')
            self.assertIsNone(allocator.reservar('web:cuenta_01','other-run'))
            with self.assertRaises(ValueError):
                inicializar(db,pool,accounts)
            with db.conexion() as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM proxy_perfiles').fetchone()[0],3)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM proxy_reservas').fetchone()[0],1)

    def test_repository_loads_even_with_api_key_present(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'OPENAI_API_KEY':'test'},clear=True):
            env=Path(folder)/'.env'
            env.write_text('OPENAI_API_KEY=other\nGHOST_CURSOR_REPOSITORY=https://github.com\nUNRELATED=value\n')
            self.assertTrue(load_project_environment(env))
            self.assertEqual(os.getenv('OPENAI_API_KEY'),'test')
            self.assertEqual(os.getenv('GHOST_CURSOR_REPOSITORY'),'https://github.com')
            self.assertIsNone(os.getenv('UNRELATED'))

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.project_env import load_project_environment


class ProjectEnvironmentTests(unittest.TestCase):
    @patch.dict(os.environ,{'OPENAI_API_KEY':''})
    def test_project_secret_becomes_environment_without_expansion(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            path.write_text('UNRELATED=ignore\nOPENAI_API_KEY="test-project-key"\n')
            self.assertTrue(load_project_environment(path))
            self.assertEqual(os.environ['OPENAI_API_KEY'],'test-project-key')
            self.assertNotIn('UNRELATED',os.environ)

    @patch.dict(os.environ,{'OPENAI_API_KEY':'explicit-process-key'})
    def test_explicit_environment_has_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env';path.write_text('OPENAI_API_KEY=project-key')
            self.assertTrue(load_project_environment(path))
            self.assertEqual(os.environ['OPENAI_API_KEY'],'explicit-process-key')

    @patch.dict(os.environ,{'OPENAI_API_KEY':''})
    def test_missing_or_invalid_file_does_not_invent_a_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            self.assertFalse(load_project_environment(path))
            path.write_text('OPENAI_API_KEY=invalid whitespace value')
            self.assertFalse(load_project_environment(path))

    @patch.dict(os.environ, {}, clear=True)
    def test_panda_proxy_country_loads_from_project_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            path.write_text('PANDA_PROXY_COUNTRY=ES\n',encoding='ascii')
            load_project_environment(path)
            self.assertEqual(os.environ['PANDA_PROXY_COUNTRY'],'ES')

    @patch.dict(os.environ, {'PANDA_PROXY_COUNTRY':'FR'}, clear=True)
    def test_panda_proxy_country_preserves_nonempty_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            path.write_text('PANDA_PROXY_COUNTRY=ES\n',encoding='ascii')
            load_project_environment(path)
            self.assertEqual(os.environ['PANDA_PROXY_COUNTRY'],'FR')

    @patch.dict(os.environ, {}, clear=True)
    def test_panda_proxy_country_does_not_allow_unrelated_variable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            path.write_text('PANDA_PROXY_COUNTRY=ES\nUNRELATED=ignore\n',encoding='ascii')
            load_project_environment(path)
            self.assertEqual(os.environ['PANDA_PROXY_COUNTRY'],'ES')
            self.assertNotIn('UNRELATED',os.environ)

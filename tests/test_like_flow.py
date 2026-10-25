from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch,MagicMock
from granjita.automation import run_like,PACKAGE
from granjita.recipes import load_recipe
from granjita.core import ROOT

class LikeFlowTests(TestCase):
    def exercise(self,before):
        session=MagicMock()
        session.call.side_effect=lambda method,path,data=None:PACKAGE if path=='/appium/device/current_package' else 'cHJ1ZWJh'
        session.text.side_effect=[before,'ME GUSTA: SI']
        context=MagicMock();context.__enter__.return_value=session
        with TemporaryDirectory() as folder,patch('granjita.automation.Session',return_value=context),patch('granjita.automation.DATA',Path(folder)):
            result=run_like({},'test')
            self.assertTrue((Path(folder)/'lab-evidence/test.png').exists())
        return session,result
    def test_applies_only_if_not_marked(self):
        session,result=self.exercise('ME GUSTA: NO')
        session.click.assert_called_once_with('lab_like_01')
        self.assertIn('aplicado',result)
        self.assertFalse(any('scroll' in str(c) for c in session.call.call_args_list))
    def test_already_liked_does_not_toggle(self):
        session,result=self.exercise('ME GUSTA: SI')
        session.click.assert_not_called()
        self.assertIn('Ya estaba',result)
    def test_recipe_is_local_and_has_no_comment(self):
        recipe=load_recipe(ROOT/'recipes/lab-like.json')
        self.assertEqual(recipe['action'],'lab_like')
        self.assertNotIn('comment',recipe['parameters'])

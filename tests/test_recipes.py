import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from granjita.core import ROOT
from granjita.recipes import load_recipe


class RecipeTests(TestCase):
    def test_repo_recipe_is_valid(self):
        self.assertEqual(load_recipe(ROOT/'recipes/lab-smoke.json')['action'],'lab_smoke')

    def check_rejected(self,update):
        value=json.loads((ROOT/'recipes/lab-smoke.json').read_text(encoding='utf-8'))
        value.update(update)
        with TemporaryDirectory() as folder:
            path=Path(folder)/'recipe.json'
            path.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaises(ValueError):
                load_recipe(path)

    def test_arbitrary_shell_is_rejected(self):
        self.check_rejected({'action':'shell'})
        self.check_rejected({'shell':'anything'})

    def test_profile_path_traversal_is_rejected(self):
        self.check_rejected({'profile':'../../data/secret'})

    def test_invalid_parameters_are_rejected(self):
        self.check_rejected({'parameters':{'comment':'x'*281}})
        self.check_rejected({'execution':{'concurrency':50}})

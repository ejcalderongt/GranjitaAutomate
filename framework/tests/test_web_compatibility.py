import subprocess
import unittest
from unittest.mock import Mock,patch

from core.actions import simular_entrada_tactil,ejecutar_swipe_feed
from scripts.preparar_web import validar_fuente_cursor,instalar_cursor


class WebCompatibilityTests(unittest.TestCase):
    def test_incomplete_source_rejected_without_installing(self):
        with patch('scripts.preparar_web.subprocess.run') as run:
            with self.assertRaises(ValueError):
                instalar_cursor('python','git+https://github.com')
            run.assert_not_called()

    def test_optional_install_failure_keeps_standard_mode(self):
        with patch('scripts.preparar_web.subprocess.run',side_effect=subprocess.TimeoutExpired('pip',120)):
            self.assertFalse(instalar_cursor('python','git+https://github.com/example/cursor.git@v1'))

    def test_success_requires_import_check(self):
        source='git+https://github.com/example/cursor.git@v1'
        self.assertEqual(validar_fuente_cursor(source),source)
        with patch('scripts.preparar_web.subprocess.run') as run:
            self.assertTrue(instalar_cursor('python',source))
            self.assertEqual(run.call_count,2)
            self.assertIn('from playwright_ghost_cursor',run.call_args.args[0][-1])

    def test_invisible_target_does_not_click(self):
        page=Mock()
        page.locator.return_value.first.is_visible.return_value=False
        self.assertFalse(simular_entrada_tactil(page,'#target'))
        page.locator.return_value.first.click.assert_not_called()

    def test_cursor_position_failure_falls_back_before_single_click(self):
        page=Mock()
        with patch('core.actions.cursor_global',side_effect=RuntimeError('optional module')):
            self.assertTrue(simular_entrada_tactil(page,'#target'))
        page.locator.return_value.first.click.assert_called_once()

    def test_uncertain_click_is_not_repeated(self):
        page=Mock()
        page.locator.return_value.first.click.side_effect=TimeoutError()
        with patch('core.actions.cursor_global',return_value=None),self.assertRaises(TimeoutError):
            simular_entrada_tactil(page,'#target')
        page.locator.return_value.first.click.assert_called_once()

    def test_swipe_compatibility_preserves_existing_capture_path(self):
        page=Mock()
        with patch('core.actions.hacer_swipe_feed_tiktok',return_value={'cursor':False}) as swipe:
            self.assertEqual(ejecutar_swipe_feed(page,'cuenta_01'),{'cursor':False})
        swipe.assert_called_once_with(page,'cuenta_01')
        self.assertTrue(1000<=page.wait_for_timeout.call_args.args[0]<=2500)

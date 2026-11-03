import random
import unittest
import tempfile
from pathlib import Path
import subprocess
import threading
from unittest.mock import Mock, patch
from core.actions import hacer_swipe_down_movil, escribir_comentario_movil, preparar_ghost_cursor


class GesturesTests(unittest.TestCase):
    def setUp(self):
        capture = patch('core.actions.guardar_evidencia_visual')
        self.capture = capture.start()
        self.addCleanup(capture.stop)
    def page(self):
        page = Mock()
        page.viewport_size = {'width':390, 'height':844}
        return page

    def test_missing_adapter_uses_mouse(self):
        page = self.page()
        with patch('core.actions.create_cursor', None):
            result = hacer_swipe_down_movil(page, 'cuenta_01', rng=random.Random(2))
        self.assertFalse(result['cursor'])
        self.assertTrue(180 <= result['start'][0] <= 220)
        self.assertTrue(620 <= result['start'][1] <= 720)
        self.assertTrue(abs(result['end'][0]-result['start'][0]) <= 15)
        self.assertTrue(180 <= result['end'][1] <= 280)
        self.assertTrue(18 <= page.wait_for_timeout.call_count <= 30)
        self.assertTrue(420 <= sum(c.args[0] for c in page.wait_for_timeout.call_args_list) <= 680)
        page.mouse.up.assert_called_once()
        self.capture.assert_called_once_with(page, 'cuenta_01', 'post_swipe')

    def test_adapter_preferred(self):
        page, cursor = self.page(), Mock()
        with patch('core.actions.create_cursor', return_value=cursor):
            result = hacer_swipe_down_movil(page, 'cuenta_01')
        self.assertTrue(result['cursor'])
        cursor.move_to.assert_called_once_with(*result['start'])
        self.assertTrue(18 <= page.mouse.move.call_count <= 30)
        self.capture.assert_called_once_with(page, 'cuenta_01', 'post_swipe')

    def test_release_on_failed_drag(self):
        page = self.page()
        page.mouse.move.side_effect = [None, RuntimeError('test')]
        with patch('core.actions.create_cursor', None), self.assertRaises(RuntimeError):
            hacer_swipe_down_movil(page, 'cuenta_01')
        page.mouse.up.assert_called_once()
        self.capture.assert_called_once_with(page, 'cuenta_01', 'post_swipe')

    def test_character_delay_in_milliseconds(self):
        page, field = self.page(), Mock()
        escribir_comentario_movil(page, field, 'hola', rng=random.Random(2))
        calls = page.keyboard.type.call_args_list
        self.assertEqual(''.join(c.args[0] for c in calls), 'hola')
        self.assertTrue(all(60 <= c.kwargs['delay'] <= 190 for c in calls))

    def test_broken_adapter_falls_back(self):
        page = self.page()
        with patch('core.actions.create_cursor', side_effect=TypeError()):
            result = hacer_swipe_down_movil(page, 'cuenta_01')
        self.assertFalse(result['cursor'])
        page.mouse.down.assert_called_once()

    def test_invalid_github_root_does_not_clone(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.actions.subprocess.run') as run:
            self.assertFalse(preparar_ghost_cursor(folder, 'https://github.com'))
            run.assert_not_called()

    def test_clone_timeout_cleans_staging_and_lock(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict('os.environ', {'GHOST_CURSOR_AUTOCLONE':'1'}), \
             patch('core.actions.subprocess.run', side_effect=subprocess.TimeoutExpired('git',15)):
            self.assertFalse(preparar_ghost_cursor(folder, 'https://github.com/example/cursor'))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_clone_publish_and_existing_directory_preserved(self):
        def clone(command, **kwargs):
            checkout = Path(command[-1])
            checkout.mkdir()
            (checkout/'ghost_cursor.py').write_text('def create_cursor(page): pass')
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict('os.environ', {'GHOST_CURSOR_AUTOCLONE':'1'}), \
             patch('core.actions.subprocess.run', side_effect=clone) as run:
            self.assertTrue(preparar_ghost_cursor(folder, 'https://github.com/example/cursor'))
            self.assertTrue(preparar_ghost_cursor(folder, 'https://github.com/example/cursor'))
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs['timeout'], 15)

    def test_another_installer_uses_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.actions.subprocess.run') as run:
            (Path(folder)/'.ghost-cursor-install.lock').touch()
            self.assertFalse(preparar_ghost_cursor(folder, 'https://github.com/example/cursor'))
            run.assert_not_called()

    def test_background_setup_does_not_wait_for_download(self):
        from core.actions import iniciar_preparacion_cursor
        entered, release = threading.Event(), threading.Event()
        def download(**kwargs):
            entered.set()
            release.wait(2)
            return False
        with patch('core.actions.create_cursor', None), \
             patch.dict('os.environ', {'GHOST_CURSOR_AUTOCLONE':'1',
                        'GHOST_CURSOR_REPOSITORY':'https://github.com/example/cursor'}), \
             patch('core.actions.preparar_ghost_cursor', side_effect=download):
            thread = iniciar_preparacion_cursor()
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(thread.is_alive())
                self.assertTrue(thread.daemon)
            finally:
                release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())

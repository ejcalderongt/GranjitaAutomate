import asyncio
import logging
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest

from core.poc_runner import POCSettings
from ui.poc_dashboard import POCController, QueueLogHandler


class POCControllerTests(unittest.TestCase):
    def test_worker_loop_is_separate_and_cancellation_finishes_cleanup(self):
        events = queue.Queue()
        ready = threading.Event()
        cleaned = threading.Event()
        identifiers = []
        async def runner(settings,stop,login,notify,path):
            identifiers.append(threading.get_ident())
            ready.set()
            try:
                await asyncio.Future()
            finally:
                cleaned.set()
                notify('result',{'clean':True,'failed':False,'cancelled':stop.is_set()})
        controller = POCController(lambda kind,data:events.put((kind,data)),runner)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'selectors.json'
            path.write_text('{}')
            settings = POCSettings(selectors_path=path)
            self.assertTrue(controller.start(settings,Path(folder)/'metrics.db'))
            self.assertTrue(ready.wait(3))
            self.assertFalse(controller.start(settings,path))
            controller.cancel()
            controller.thread.join(3)
        self.assertFalse(controller.running)
        self.assertTrue(cleaned.is_set())
        self.assertNotEqual(identifiers[0],threading.get_ident())
        self.assertTrue(any(row[0]=='finished' for row in list(events.queue)))

    def test_console_redacts_url_credentials_and_api_tokens(self):
        output = []
        handler = QueueLogHandler(lambda kind,data:output.append(data))
        record = logging.LogRecord('qa.test',logging.INFO,'',1,'http://user:secret@example.org sk-test_key',(),None)
        handler.emit(record)
        self.assertNotIn('secret',output[0])
        self.assertNotIn('sk-test',output[0])

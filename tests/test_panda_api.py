import json
from unittest import TestCase
from unittest.mock import patch,MagicMock
from granjita.panda_api import list_devices


class PandaApiTests(TestCase):
    def test_only_read_action_is_sent(self):
        connection=MagicMock()
        connection.recv.return_value=json.dumps({'code':10000,'data':[{'onlySerial':'TESTSERIAL','mode':2}]})
        with patch('granjita.panda_api.websocket.create_connection',return_value=connection):
            result=list_devices()
        self.assertEqual(result[0]['mode'],2)
        self.assertEqual(json.loads(connection.send.call_args.args[0]),{'action':'list','devices':'all'})
        connection.close.assert_called_once()

    def test_remote_endpoints_and_url_credentials_are_rejected(self):
        for url in ['ws://example.com:22222/','ws://user:pass@localhost:22222/','https://localhost/']:
            with self.assertRaises(ValueError):
                list_devices(url)

    def test_rejection_is_not_reported_as_success(self):
        connection=MagicMock()
        connection.recv.return_value=json.dumps({'code':10001,'data':None})
        with patch('granjita.panda_api.websocket.create_connection',return_value=connection):
            with self.assertRaises(RuntimeError):
                list_devices()
        connection.close.assert_called_once()

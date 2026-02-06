import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import sys
import os
import socket
sys.path.append("/home/joel/code/PepperBox/py3-naoqi-bridge")
from naoqi_proxy import NaoqiClient, NaoqiProxyError

class TestProxyTimeout(unittest.TestCase):
    @patch('urllib.request.urlopen')
    def test_timeout_is_passed_to_urlopen(self, mock_urlopen):
        """Verify that the timeout argument is correctly passed to urlopen."""
        client = NaoqiClient("localhost", 9559, timeout=2.0)
        
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = b'{"result": "success"}'
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        client.ALMotion.wakeUp()
        
        args, kwargs = mock_urlopen.call_args
        # Should be exactly what was passed in __init__
        self.assertEqual(kwargs['timeout'], 2.0)

if __name__ == '__main__':
    unittest.main()

import socket,ssl,unittest
from unittest.mock import patch,MagicMock
from urllib.request import Request
from http.client import HTTPSConnection
from yahoo_transport import connect_ipv4,YahooHandler,YahooConnection

class YahooTransportTests(unittest.TestCase):
 def test_ipv4_resolution_retries_and_closes_failed_socket(self):
  first=MagicMock();first.connect.side_effect=OSError('offline');second=MagicMock()
  answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in ('192.0.2.1','192.0.2.2')]
  with patch('yahoo_transport.socket.getaddrinfo',return_value=answers) as resolver,patch('yahoo_transport.socket.socket',side_effect=[first,second]):
   self.assertIs(connect_ipv4(('tw.bid.yahoo.com',443),12),second)
   resolver.assert_called_once_with('tw.bid.yahoo.com',443,socket.AF_INET,socket.SOCK_STREAM)
  first.close.assert_called_once();second.settimeout.assert_called_once_with(12)
 def test_no_addresses_fails_instead_of_silently_using_ipv6(self):
  with patch('yahoo_transport.socket.getaddrinfo',return_value=[]):
   with self.assertRaises(OSError):connect_ipv4(('tw.bid.yahoo.com',443))
 def test_only_yahoo_connection_changes_and_tls_validation_remains(self):
  context=ssl.create_default_context();handler=YahooHandler(context=context)
  with patch.object(handler,'do_open') as opening:
   handler.https_open(Request('https://tw.bid.yahoo.com/search/auction/product?p=CD'))
   self.assertIs(opening.call_args.args[0],YahooConnection)
   self.assertIs(opening.call_args.kwargs['context'],context)
   self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
   handler.https_open(Request('https://tower.jp/'))
   self.assertIs(opening.call_args.args[0],HTTPSConnection)

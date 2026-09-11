"""Yahoo TW's IPv6 search route returns 404; resolve its IPv4 addresses normally.

Connection-scoped only: no fixed IPs, global DNS changes or TLS bypass.
"""
import socket
import ssl
from http.client import HTTPSConnection
from urllib.request import HTTPSHandler,build_opener


def connect_ipv4(address,timeout=25,source_address=None):
    host,port=address
    error=None
    for family,kind,proto,_,destination in socket.getaddrinfo(host,port,socket.AF_INET,socket.SOCK_STREAM):
        sock=socket.socket(family,kind,proto)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:sock.settimeout(timeout)
            if source_address:sock.bind(source_address)
            sock.connect(destination)
            return sock
        except OSError as exc:
            error=exc
            sock.close()
    if error:raise error
    raise OSError('Yahoo IPv4 address unavailable')


class YahooConnection(HTTPSConnection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._create_connection=connect_ipv4


class YahooHandler(HTTPSHandler):
    def https_open(self,req):
        if req.host!='tw.bid.yahoo.com':return super().https_open(req)
        return self.do_open(YahooConnection,req,context=self._context)


def open_yahoo(req,timeout=25):
    return build_opener(YahooHandler(context=ssl.create_default_context())).open(req,timeout=timeout)

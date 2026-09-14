"""Optional bearer authentication for an HTTPS reverse-proxied deployment."""
import os,secrets
from password_login import PasswordLogin
from urllib.parse import urlsplit

class RemoteAccess:
    def __init__(self):
        self.passwords=PasswordLogin()
        self.token=os.getenv('REMOTE_ACCESS_TOKEN','')
        self.origin=os.getenv('FRONTEND_ORIGIN','').rstrip('/')
        self.api_origin=os.getenv('PUBLIC_API_ORIGIN','').rstrip('/')
        if self.token:
            if len(self.token)<32:raise ValueError('REMOTE_ACCESS_TOKEN must contain at least 32 characters')
            for value in (self.origin,self.api_origin):
                u=urlsplit(value)
                if u.scheme!='https' or not u.netloc or u.username or u.password or u.path or u.query or u.fragment:raise ValueError('Remote origins must be exact HTTPS origins')
        elif self.origin or self.api_origin:raise ValueError('Remote deployment requires authentication')

    def allowed(self,headers):
        host=urlsplit('//'+headers.get('Host','')).netloc
        origin=headers.get('Origin','')
        if self.token:
            hosts={urlsplit(self.api_origin).netloc,'127.0.0.1:8765','localhost:8765'}
            if host not in hosts or (origin and origin!=self.origin):return 403
            authorization=headers.get('Authorization','')
            legacy=secrets.compare_digest(authorization.encode(),('Bearer '+self.token).encode())
            session=authorization.startswith('Bearer ') and self.passwords.valid(authorization[7:])
            if not (legacy or session):return 401
            return 200
        if urlsplit('//'+host).hostname not in ('127.0.0.1','localhost','::1'):return 403
        if origin and urlsplit(origin).hostname not in ('127.0.0.1','localhost','::1'):return 403
        return 200

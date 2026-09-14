"""Single-admin password authentication. No business data or raw passwords stored."""
import hashlib,json,secrets,threading,time,os,tempfile,fcntl
from pathlib import Path

AUTH_FILE=Path(__file__).resolve().parent/'secrets'/'admin-login.json'

def password_hash(password,salt):
 return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=32).hex()

class PasswordLogin:
 def __init__(self,path=AUTH_FILE,clock=time.monotonic):
  self.path=Path(path);self.clock=clock;self.lock=threading.Lock();self.attempts=[];self.sessions={};self.reset_path=self.path.with_name("admin-reset.json")
 def login(self,username,password):
  if not isinstance(username,str) or not isinstance(password,str) or not 1<=len(username)<=100 or not 1<=len(password)<=1024:return 401,{'error':'帳號或密碼不正確'}
  with self.lock:
   now=self.clock();self.attempts=[t for t in self.attempts if now-t<60]
   if len(self.attempts)>=10:return 429,{'error':'登入嘗試過多，請一分鐘後再試'}
   self.attempts.append(now)
   try:
    config=json.loads(self.path.read_text());salt=config['salt'];expected=config['hash'];account=config['username']
    if not all(isinstance(x,str) for x in (salt,expected,account)) or len(salt)!=32 or len(expected)!=64:raise ValueError()
    actual=password_hash(password,salt)
   except Exception:return 503,{'error':'帳號密碼登入尚未設定，請先使用管理者存取碼'}
   if not (secrets.compare_digest(actual,expected) and secrets.compare_digest(username.encode(),account.encode())):return 401,{'error':'帳號或密碼不正確'}
   self.sessions={k:v for k,v in self.sessions.items() if v>now}
   if len(self.sessions)>=128:return 429,{'error':'登入連線過多，請稍後再試'}
   token=secrets.token_urlsafe(32);self.sessions[hashlib.sha256(token.encode()).hexdigest()]=now+8*3600
   return 200,{'session_token':token,'expires_in':8*3600}
 def valid(self,token):
  with self.lock:
   return self.sessions.get(hashlib.sha256(token.encode()).hexdigest(),0)>self.clock()
 def revoke(self,token):
  with self.lock:self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)

 def issue_reset(self):
  with self.lock:
   self.path.parent.mkdir(mode=0o700,exist_ok=True)
   with open(self.path.with_name('.account-reset.lock'),'a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    token=secrets.token_urlsafe(32)
    self._write(self.reset_path,{'hash':hashlib.sha256(token.encode()).hexdigest(),'expires':time.time()+1800})
    return token
 def _write(self,path,data):
  path.parent.mkdir(mode=0o700,exist_ok=True)
  fd,name=tempfile.mkstemp(dir=path.parent,prefix='.auth-')
  try:
   with os.fdopen(fd,'w') as stream:json.dump(data,stream);stream.flush();os.fsync(stream.fileno())
   os.replace(name,path)
  finally:
   if os.path.exists(name):os.unlink(name)
 def reset(self,token,username,password):
  if not isinstance(token,str) or not 32<=len(token)<=128:return 400,{'error':'重設連結無效或已過期'}
  if not isinstance(username,str) or not 1<=len(username.strip())<=100 or not isinstance(password,str) or not 15<=len(password)<=1024:
   return 400,{'error':'請填寫帳號及15至1024字元的新密碼'}
  with self.lock:
   self.path.parent.mkdir(mode=0o700,exist_ok=True)
   with open(self.path.with_name('.account-reset.lock'),'a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    try:record=json.loads(self.reset_path.read_text())
    except (OSError,ValueError):return 400,{'error':'重設連結無效或已過期'}
    if not isinstance(record.get('expires'),(int,float)) or record['expires']<=time.time() or not secrets.compare_digest(str(record.get('hash','')),hashlib.sha256(token.encode()).hexdigest()):
     return 400,{'error':'重設連結無效或已過期'}
    salt=secrets.token_hex(16)
    data={'username':username.strip(),'salt':salt,'hash':password_hash(password,salt)}
    # Consume first: an interrupted password write must never leave a reusable link.
    self._write(self.reset_path,{'hash':'','expires':0})
    self._write(self.path,data)
    self.sessions.clear();self.attempts.clear()
    return 200,{'message':'帳號密碼已更新，請使用新帳密登入'}

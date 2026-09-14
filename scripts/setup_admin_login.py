#!/usr/bin/env python3
"""Run interactively on the authorized backend. Never pass passwords as arguments."""
import getpass,json,os,secrets,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from password_login import AUTH_FILE,password_hash

def main():
 if not sys.stdin.isatty():raise SystemExit('請在互動終端執行，由管理者親自設定。')
 username=input('帳號 [admin]: ').strip() or 'admin'
 if len(username)>100:raise SystemExit('帳號過長')
 password=getpass.getpass('新密碼（至少15字元）: ')
 if len(password)<15 or len(password)>1024:raise SystemExit('密碼須15至1024字元')
 if password!=getpass.getpass('再次輸入新密碼: '):raise SystemExit('兩次密碼不同，沒有儲存')
 salt=secrets.token_hex(16);data={'username':username,'salt':salt,'hash':password_hash(password,salt)}
 AUTH_FILE.parent.mkdir(mode=0o700,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=AUTH_FILE.parent,prefix='.admin-login-')
 try:
  with os.fdopen(fd,'w') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
  os.replace(tmp,AUTH_FILE)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print('已儲存密碼雜湊。重啟music-business可撤銷既有登入連線；舊管理者存取碼保留。')
if __name__=='__main__':main()

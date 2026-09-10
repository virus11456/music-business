"""Start the local dashboard and stop only processes created by this launcher."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
ROOT=Path(__file__).resolve().parent

def available(url):
 try:
  with urllib.request.urlopen(url,timeout=2) as response:return response.status==200
 except Exception:return False

def main():
 env=os.environ.copy()
 runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
 env['PATH']=str(runtime/'node/bin')+os.pathsep+str(runtime/'bin/fallback')+os.pathsep+env.get('PATH','')
 pnpm=shutil.which('pnpm',path=env['PATH'])
 if not pnpm:raise SystemExit('請先安裝 Node.js 22 與 pnpm，或在 Codex 中啟動。')
 if not (ROOT/'frontend/node_modules').exists():raise SystemExit('前端套件尚未安裝，請先在 frontend 資料夾執行 pnpm install。')
 children=[]
 try:
  if not available('http://127.0.0.1:8765/api/state'):
   python=str(ROOT/'.venv/bin/python') if (ROOT/'.venv/bin/python').exists() else sys.executable
   children.append(subprocess.Popen([python,'server.py'],cwd=ROOT,env=env))
  if not available('http://127.0.0.1:5173/'):
   children.append(subprocess.Popen([pnpm,'dev'],cwd=ROOT/'frontend',env=env))
  for _ in range(60):
   if any(p.poll() is not None for p in children):raise SystemExit('服務未能啟動，請查看上方訊息。')
   if available('http://127.0.0.1:5173/') and available('http://127.0.0.1:8765/api/state'):break
   time.sleep(1)
  else:raise SystemExit('啟動逾時，請查看服務訊息。')
  webbrowser.open('http://127.0.0.1:5173/')
  print('唱片工作室已啟動。請保持此視窗開啟；按 Control-C 關閉本次啟動的服務。')
  if children:
   while all(p.poll() is None for p in children):time.sleep(1)
 except KeyboardInterrupt:pass
 finally:
  for p in children:
   if p.poll() is None:p.terminate()
  for p in children:
   try:p.wait(timeout=8)
   except subprocess.TimeoutExpired:p.kill()
if __name__=='__main__':main()

"""Run the API and the Streamlit frontend as one local application."""
import os,subprocess,signal,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
api_port=os.environ.get('PORT','4173');ui_port=os.environ.get('STUDIO_UI_PORT','4180')
python=Path(os.environ.get('STUDIO_PYTHON', ROOT/'.venv/bin/python'))
api_python=python if os.environ.get('STUDIO_PYTHON') else ROOT/'.venv-api/bin/python'
if not python.exists() or not api_python.exists():raise SystemExit('请先运行 ./install-quick.sh')
processes=[]
def stop(*args):
 for p in processes:
  if p.poll() is None:p.terminate()
 for p in processes:
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill()
signal.signal(signal.SIGTERM,lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
try:
 processes.append(subprocess.Popen([str(api_python),str(ROOT/'server.py')],env={**os.environ,'STUDIO_UI_PORT':ui_port}))
 processes.append(subprocess.Popen([str(python),'-m','streamlit','run',str(ROOT/'streamlit_app.py'),'--server.address='+os.environ.get('STUDIO_BIND','127.0.0.1'),'--server.port='+ui_port,'--server.headless=true','--browser.gatherUsageStats=false'],cwd=ROOT,env={**os.environ,'STUDIO_API':'http://127.0.0.1:'+api_port}))
 while all(p.poll() is None for p in processes):time.sleep(.5)
except KeyboardInterrupt:pass
finally:stop()
if any(p.returncode not in (0, -15, -2) for p in processes):
 raise SystemExit(1)

"""Bundled engine readiness; no separate upstream WebUI is launched."""
from pathlib import Path
from studio.paths import PYTHON,VENDOR_ROOT

class QuickEngine:
 def __init__(self,root=VENDOR_ROOT):self.root=Path(root)
 def status(self):
  ready=PYTHON.is_file() and (self.root/'app/services/task.py').is_file()
  return {'running':False,'ready':ready,'url':None,'engine':'bundled'}
 def start(self):
  status=self.status()
  if not status['ready']:raise RuntimeError('快速生成依赖尚未安装，请运行 video-studio/install-quick.sh')
  return status
 def close(self):pass

"""Verify bundled sources and a real offline media render outside the original checkout."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(os.environ.get('STUDIO_TEST_ROOT',Path(__file__).resolve().parent))
PYTHON=Path(os.environ.get('STUDIO_TEST_PYTHON',ROOT/'.venv/bin/python'))
VENDOR=ROOT/'vendor/moneyprinterturbo'

class BundledEngine(unittest.TestCase):
 def test_vendor_manifest_and_license(self):
  manifest=json.loads((VENDOR/'MANIFEST.json').read_text())
  self.assertIn('MIT License',(VENDOR/'LICENSE').read_text())
  for name,digest in manifest['files'].items():
   self.assertEqual(hashlib.sha256((VENDOR/name).read_bytes()).hexdigest(),digest,name)
  self.assertFalse((VENDOR/'config.toml').exists())
  self.assertFalse((VENDOR/'.venv').exists())
 def test_dependency_policy_has_only_documented_override(self):
  from importlib.metadata import distributions,version,PackageNotFoundError
  from packaging.requirements import Requirement
  conflicts=[]
  for package in distributions():
   for raw in package.requires or []:
    requirement=Requirement(raw)
    if requirement.marker and not requirement.marker.evaluate({'extra':''}):continue
    try:installed=version(requirement.name)
    except PackageNotFoundError:
     conflicts.append((package.metadata['Name'].lower(),requirement.name.lower(),'missing'));continue
    if requirement.specifier and not requirement.specifier.contains(installed):conflicts.append((package.metadata['Name'].lower(),requirement.name.lower(),installed))
  self.assertEqual(conflicts,[('moviepy','pillow','13.0.0')])
 def test_real_offline_render_in_standalone_directory(self):
  with tempfile.TemporaryDirectory(prefix='studio-standalone-') as temp:
   standalone=Path(temp)/'application';standalone.mkdir()
   def copy(src,dst):
    try:os.link(src,dst)
    except OSError:shutil.copy2(src,dst)
    return dst
   for directory in ('studio','vendor'):
    shutil.copytree(ROOT/directory,standalone/directory,copy_function=copy,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   # Python belongs to this application; no upstream checkout or virtual environment is used.
   (standalone/'.venv').symlink_to(PYTHON.parent.parent,target_is_directory=True)
   runtime=Path(temp)/'runtime';inputs=runtime/'quick-engine/storage/inputs';inputs.mkdir(parents=True)
   clip=inputs/'clip.mp4';audio=inputs/'voice.wav'
   import imageio_ffmpeg
   ffmpeg=str(ROOT.parent/'tools/ffmpeg') if (ROOT.parent/'tools/ffmpeg').exists() else imageio_ffmpeg.get_ffmpeg_exe()
   for args,target in [(['-f','lavfi','-i','color=c=blue:s=640x480:r=24:d=1','-c:v','libx264','-pix_fmt','yuv420p'],clip),(['-f','lavfi','-i','sine=frequency=440:duration=1','-c:a','pcm_s16le'],audio)]:
    subprocess.run([ffmpeg,'-v','error',*args,str(target)],check=True,capture_output=True)
   payload={'mode':'video','task_id':'offline-bundle-test','settings':{},'params':{'video_subject':'Offline render','video_script':'Local media only','video_source':'local','video_materials':[{'provider':'local','url':str(clip),'duration':1}],'custom_audio_file':str(audio),'video_aspect':'16:9','video_count':1,'video_clip_duration':1,'video_concat_mode':'sequential','subtitle_enabled':False,'bgm_type':'','font_name':'MicrosoftYaHeiBold.ttc'}}
   bootstrap='''import socket,sys
from pathlib import Path
def blocked(*args,**kwargs):raise AssertionError("Network is disabled in the standalone test")
socket.socket.connect=blocked
socket.create_connection=blocked
from studio.engine.worker import main
main()
root=Path.cwd()/"vendor/moneyprinterturbo"
for name,module in list(sys.modules.items()):
 if name=="app" or name.startswith("app."):
  file=getattr(module,"__file__",None)
  if file:assert Path(file).resolve().is_relative_to(root),file
'''
   result=subprocess.run([str(PYTHON),'-c',bootstrap],input=json.dumps(payload),text=True,capture_output=True,cwd=standalone,env={**os.environ,'STUDIO_DATA':str(runtime),'PYTHONPATH':str(standalone),'IMAGEIO_FFMPEG_EXE':ffmpeg},timeout=180)
   self.assertEqual(result.returncode,0,result.stderr[-5000:])
   response=json.loads(result.stdout)
   paths=[]
   def collect(value):
    if isinstance(value,str) and value.endswith('.mp4'):paths.append(Path(value))
    elif isinstance(value,dict):
     for x in value.values():collect(x)
    elif isinstance(value,list):
     for x in value:collect(x)
   collect(response['result'])
   self.assertTrue(paths,response)
   self.assertTrue(all(p.is_file() and p.resolve().is_relative_to(runtime.resolve()) for p in paths),str([(str(p),p.exists(),str(p.resolve()),str(runtime.resolve())) for p in paths]))
   probe=subprocess.run([ffmpeg,'-hide_banner','-i',str(paths[0])],capture_output=True)
   self.assertIn('Video:',probe.stderr.decode())

if __name__=='__main__':unittest.main()

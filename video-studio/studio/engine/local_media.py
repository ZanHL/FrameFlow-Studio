"""Stage validated uploads inside the upstream engine's allowed local-video directory."""
from contextlib import contextmanager
from pathlib import Path
import copy,shutil,uuid
from studio.paths import ENGINE_RUNTIME

@contextmanager
def staged_materials(params):
 value=copy.deepcopy(params);created=[]
 try:
  if value.get('video_source')=='local':
   directory=ENGINE_RUNTIME/'storage/local_videos';directory.mkdir(parents=True,exist_ok=True)
   for material in value.get('video_materials',[]):
    source=Path(material['url']).resolve()
    if not source.is_file() or source.suffix.lower()!='.mp4':raise ValueError('本地视频必须是已上传的 MP4 文件')
    target=directory/(uuid.uuid4().hex+'.mp4');created.append(target)
    shutil.copy2(source,target);material['url']=str(target)
  yield value
 finally:
  for path in created:path.unlink(missing_ok=True)

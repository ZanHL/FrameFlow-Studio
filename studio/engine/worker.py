"""Isolated adapter to the bundled MIT-licensed media engine."""
import contextlib,json,sys,uuid,os
from pathlib import Path
from studio.paths import VENDOR_ROOT,ENGINE_RUNTIME

def main():
 ENGINE_RUNTIME.mkdir(parents=True,exist_ok=True)
 os.environ['MPT_HOME']=str(ENGINE_RUNTIME)
 sys.path.insert(0,str(VENDOR_ROOT))
 payload=json.load(sys.stdin)
 with contextlib.redirect_stdout(sys.stderr):
  from loguru import logger
  logger.remove()  # Do not persist provider payloads or credentials.
  from app.config import config
  config.app.update(payload.get('settings',{}))
  config.app['enable_redis']=False
  config.app['cross_post_enabled']=False
  config.app['auto_publish']=False
  config.app['upload_post_auto_upload']=False
  config.azure.update({'speech_key':config.app.get('speech_key',''),'speech_region':config.app.get('speech_region','')})
  config.whisper.update(payload.get('whisper',{}))
  mode=payload['mode'];params=payload.get('params',{});result=None
  if mode=='script':
   from app.services import llm
   result={'script':llm.generate_script(params['topic'],language='zh-CN',paragraph_number=1)}
  elif mode=='search':
   from app.services import material
   from app.models.schema import VideoAspect
   provider=params.get('provider','pexels')
   fn={'pexels':material.search_videos_pexels,'pixabay':material.search_videos_pixabay,'coverr':material.search_videos_coverr}[provider]
   items=fn(params['query'],minimum_duration=1,video_aspect=VideoAspect(params.get('ratio','9:16')))
   result=[{'provider':i.provider,'url':i.url,'duration':i.duration,'source_info':i.source_info} for i in items[:20]]
  elif mode in ('video','audio'):
   from app.services import task,state
   from app.models.schema import VideoParams
   task_id=payload.get('task_id') or str(uuid.uuid4())
   from studio.engine.local_media import staged_materials
   with staged_materials(params) as staged:
    value=task.start(task_id,VideoParams(**staged),stop_at=mode,allow_server_file_input=True)
   snapshot=state.state.get_task(task_id) or {}
   if not value or snapshot.get('state')==-1:
    raise RuntimeError('生成失败，请检查素材、配音服务和字幕配置')
   outputs={key:value[key] for key in ('videos','audio_file','subtitle_path') if value.get(key)}
   result={'task_id':task_id,'result':outputs,'state':{'state':snapshot.get('state'),'progress':snapshot.get('progress')}}
 print(json.dumps(result,ensure_ascii=False,default=str))

if __name__=='__main__':main()

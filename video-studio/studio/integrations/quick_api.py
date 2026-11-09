"""Studio-owned quick creation API; upstream is used only as a media engine."""
import json,subprocess,uuid,sys
from pathlib import Path
from fastapi import Request
from fastapi.responses import FileResponse

DEFAULT={'material_provider':'pexels','voice_name':'zh-CN-XiaoxiaoNeural-Female','voice_rate':1.0,'subtitle_provider':'edge','whisper_model_size':'small','whisper_device':'cpu','whisper_compute_type':'int8','azure_region':''}
KEYS={'pexels':'pexels_api_keys','pixabay':'pixabay_api_keys','coverr':'coverr_api_keys','azure':'speech_key'}

def register(s):
 from studio.paths import ENGINE_RUNTIME,PYTHON,APP_ROOT
 app=s.app;root=ENGINE_RUNTIME;root.mkdir(parents=True,exist_ok=True);work=s.DATA/'quick';work.mkdir(exist_ok=True)
 def settings():return DEFAULT|s.setting('quick:settings',{})
 def worker(mode,params,task_id=None):
  cfg=settings();engine={'subtitle_provider':cfg['subtitle_provider'],'speech_region':cfg['azure_region']}
  for name,key in KEYS.items():
   value=s.SECRETS.get('quick:'+name)
   engine[key]=([value] if name!='azure' else value) if value else ([] if name!='azure' else '')
  python=PYTHON
  if not python.exists():s.fail('请先安装快速生成依赖',503)
  payload={'mode':mode,'params':params,'task_id':task_id,'settings':engine,'whisper':{'model_size':cfg['whisper_model_size'],'device':cfg['whisper_device'],'compute_type':cfg['whisper_compute_type']}}
  try:
   r=subprocess.run([str(python),'-m','studio.engine.worker'],input=json.dumps(payload),capture_output=True,text=True,cwd=APP_ROOT,timeout=1800 if mode=='video' else 180)
  except subprocess.TimeoutExpired:s.fail('处理超时，请检查网络或使用更短的素材',504)
  if r.returncode:s.fail('处理失败，请检查服务密钥、网络和输入素材；Whisper 首次使用需要下载模型',502)
  try:return json.loads(r.stdout)
  except ValueError:s.fail('视频引擎未返回有效结果',502)

 # Move older standalone quick tasks into projects once; preserve their original outputs.
 with s.db() as conn:
  legacy=conn.execute("SELECT id,data FROM jobs WHERE project='quick' AND kind IN ('quick-video','quick-audio') AND status NOT IN ('queued','running')").fetchall()
 for row in legacy:
  data=json.loads(row['data']);p=s.create({'name':str(data.get('subject') or '快速生成项目')[:120],'mode':'quick'})
  aids=[]
  for output in data.get('outputs',[]):
   path=work/str(output.get('url','')).rsplit('/',1)[-1]
   if path.is_file() and path.suffix=='.mp4':aids.append(s.add_asset(p['id'],'quick-video','',output.get('name','成片'),path.read_bytes(),'video/mp4'))
  if aids:p['final_video']=aids[-1];s.put(p)
  with s.db() as conn:conn.execute('UPDATE jobs SET project=? WHERE id=?',(p['id'],row['id']))

 with s.db() as conn:
  snapshots=conn.execute("SELECT project,data FROM jobs WHERE kind='quick-video' ORDER BY rowid DESC").fetchall()
 seen=set()
 for row in snapshots:
  pid=row['project']
  if pid in seen or pid=='quick':continue
  seen.add(pid);inputs=json.loads(row['data']).get('inputs')
  if inputs:
   p=s.project(pid)
   if not p.get('last_video_inputs'):p['last_video_inputs']=inputs;s.put(p)

 @app.get('/api/quick/settings')
 def get_settings():
  return settings()|{'keys':{name:bool(s.SECRETS.get('quick:'+name)) for name in KEYS}}
 @app.post('/api/quick/settings')
 def save_settings(body:dict):
  cfg=settings()
  for k in DEFAULT:
   if k in body:cfg[k]=body[k]
  if cfg['material_provider'] not in ('pexels','pixabay','coverr','local'):s.fail('素材平台无效')
  if cfg['subtitle_provider'] not in ('edge','whisper'):s.fail('字幕方式无效')
  if cfg['whisper_model_size'] not in ('tiny','base','small','medium','large-v3'):s.fail('识别模型无效')
  if cfg['whisper_device']!='cpu' or cfg['whisper_compute_type']!='int8':s.fail('本机字幕使用 CPU / int8')
  try:cfg['voice_rate']=float(cfg['voice_rate'])
  except (ValueError,TypeError):s.fail('语速无效')
  if not .5<=cfg['voice_rate']<=2:s.fail('语速范围为 0.5–2')
  if len(str(cfg['voice_name']))>150:s.fail('配音声音名称过长')
  try:
   for name,value in body.get('keys',{}).items():
    if name not in KEYS:s.fail('服务不存在')
    if value is None:s.SECRETS.delete('quick:'+name)
    elif isinstance(value,str) and value.strip():s.SECRETS.set('quick:'+name,value.strip())
  except s.SecretStoreError as e:s.fail(str(e),503)
  s.store_setting('quick:settings',cfg);return get_settings()
 @app.post('/api/quick/script')
 def script(body:dict):
  topic=str(body.get('topic','')).strip()
  if not topic or len(topic)>2000:s.fail('请输入 1–2000 字的视频主题')
  try:duration=int(body.get('duration',30))
  except (TypeError,ValueError):s.fail('目标片长必须是整数')
  if not 5<=duration<=600:s.fail('目标片长需为 5–600 秒')
  project={'idea':topic,'duration':duration,'ratio':'9:16','style':''}
  pid=body.get('project')
  if pid:
   p=s.project(pid)
   if p.get('mode')!='quick':s.fail('请选择快速生成项目')
   project['id']=pid
  text=s.llm(project,'story',f'为快速短视频撰写中文旁白，主题：{topic}。目标 {duration} 秒，约 {duration*4} 字。只返回可直接配音的文案正文，不要分镜、标题、说明或 Markdown。')
  return {'script':text.strip()}
 @app.post('/api/quick/search')
 def search(body:dict):
  provider=body.get('provider','pexels');query=str(body.get('query','')).strip()
  if provider not in ('pexels','pixabay','coverr'):s.fail('请选择在线素材平台')
  if not query or len(query)>200:s.fail('搜索词需为 1–200 字')
  if body.get('ratio','9:16') not in ('9:16','16:9','1:1'):s.fail('画幅无效')
  if not s.SECRETS.get('quick:'+provider):s.fail('请在设置中配置该素材平台 Key')
  return worker('search',body)
 @app.post('/api/quick/upload')
 async def upload(request:Request,kind:str='video'):
  mime=request.headers.get('content-type','').split(';')[0]
  allowed={'video':{'video/mp4':'.mp4'},'audio':{'audio/mpeg':'.mp3','audio/wav':'.wav','audio/x-wav':'.wav'},'music':{'audio/mpeg':'.mp3','audio/wav':'.wav','audio/x-wav':'.wav'}}
  if kind not in allowed or mime not in allowed[kind]:s.fail('视频支持 MP4，音频支持 MP3 / WAV')
  chunks=[];size=0
  async for chunk in request.stream():
   size+=len(chunk)
   if size>100*1024*1024:s.fail('文件不得超过 100 MB',413)
   chunks.append(chunk)
  content=b''.join(chunks)
  if kind=='video' and b'ftyp' not in content[:32]:s.fail('不是有效 MP4 文件')
  name=uuid.uuid4().hex+allowed[kind][mime];(work/name).write_bytes(content)
  return {'id':name,'name':request.headers.get('x-file-name','本地素材'),'kind':kind}
 def local(name):
  path=(work/str(name)).resolve()
  if path.parent!=work.resolve() or not path.is_file():s.fail('上传素材不存在')
  return str(path)
 @app.get('/api/quick/file/{name}')
 def get_file(name:str):return FileResponse(local(name))
 @app.post('/api/quick/archive')
 def archive(body:dict):
  path=Path(local(body.get('name','')))
  if path.suffix!='.mp4':s.fail('只能归档 MP4 成片')
  p=s.create({'name':str(body.get('subject','快速生成'))[:100]})
  aid=s.add_asset(p['id'],'quick-video','','快速生成成片',path.read_bytes(),'video/mp4')
  s.log(p['id'],'归档快速生成成片');return {'project':p['id'],'asset':aid}
 @app.get('/api/quick/jobs')
 def jobs(project:str=''):
  if project:s.project(project)
  with s.db() as c:rows=c.execute("SELECT * FROM jobs WHERE kind IN ('quick-audio','quick-video')"+(' AND project=?' if project else '')+' ORDER BY rowid DESC LIMIT 30',(project,) if project else ()).fetchall()
  return [dict(r)|{'data':json.loads(r['data'])} for r in rows]
 def save_draft(pid,body):
  with s.LOCK:
   p=s.project(pid)
   if p.get('mode')!='quick':s.fail('请选择快速生成项目')
   fields={'video_subject','video_script','video_terms','video_source','video_aspect','video_fit_mode','video_concat_mode','video_transition_mode','video_clip_duration','video_count','voice_name','voice_rate','bgm_type','bgm_volume','subtitle_enabled','subtitle_position','subtitle_display_mode','font_size','text_fore_color','audio','music','materials','target_duration','audio_mode'}
   inputs={k:v for k,v in body.items() if k in fields}
   subject=str(inputs.get('video_subject','')).strip()
   if not subject or len(subject)>2000:s.fail('视频主题需为 1–2000 字，项目名称将与主题保持一致')
   inputs['video_subject']=subject
   if len(json.dumps(inputs))>100000:s.fail('项目内容过长')
   if inputs.get('video_aspect','9:16') not in ('9:16','16:9','1:1'):s.fail('画幅无效')
   for field in ('audio','music'):
    if inputs.get(field):local(inputs[field])
   for name in inputs.get('materials',[]):local(name)
   p.update(name=subject,quick_inputs=inputs,idea=subject,story=inputs.get('video_script',''),ratio=inputs.get('video_aspect','9:16'))
   s.put(p);return p
 @app.post('/api/projects/{pid}/quick-draft')
 def draft(pid:str,body:dict):
  return save_draft(pid,body)
 @app.post('/api/quick/generate')
 def generate(body:dict):
  cfg=settings();script=str(body.get('video_script','')).strip()
  if not script or len(script)>15000:s.fail('请先填写或生成文案（最多 15000 字）')
  allowed={'video_subject','video_script','video_terms','video_source','video_aspect','video_fit_mode','video_concat_mode','video_transition_mode','video_clip_duration','video_clip_speed','video_count','voice_name','voice_rate','voice_volume','bgm_type','bgm_volume','subtitle_enabled','subtitle_position','subtitle_display_mode','subtitle_animation','font_size','text_fore_color','stroke_color','stroke_width'}
  params={k:v for k,v in body.items() if k in allowed};params['video_subject']=str(params.get('video_subject') or script[:80]).strip();params['voice_name']=body.get('voice_name',cfg['voice_name']);params['font_name']='MicrosoftYaHeiBold.ttc'
  if not params['video_subject'] or len(params['video_subject'])>2000:s.fail('视频主题需为 1–2000 字')
  if params.get('video_source','pexels') not in ('pexels','pixabay','coverr','local'):s.fail('素材来源无效')
  if params.get('video_aspect','9:16') not in ('9:16','16:9','1:1'):s.fail('画幅无效')
  try:
   count=int(params.get('video_count',1));clip=int(params.get('video_clip_duration',5));size=int(params.get('font_size',60))
  except (ValueError,TypeError):s.fail('合成参数无效')
  if not 1<=count<=3 or not 1<=clip<=30 or not 20<=size<=100:s.fail('视频数量、片段时长或字号超出范围')
  params.update(video_count=count,video_clip_duration=clip,font_size=size)
  params['video_terms']=params.get('video_terms') or params['video_subject']
  if body.get('audio'):params['custom_audio_file']=local(body['audio'])
  if body.get('music'):params['bgm_file']=local(body['music']);params['bgm_type']='custom'
  files=body.get('materials',[])
  if params.get('video_source')=='local' and not body.get('preview'):
   if not files:s.fail('请上传至少一段 MP4 素材')
   params['video_materials']=[{'provider':'local','url':local(f),'duration':0} for f in files[:30]]
  elif not body.get('preview') and not s.SECRETS.get('quick:'+params.get('video_source','pexels')):s.fail('请先在设置中配置素材平台 Key')
  pid=body.get('project')
  if pid:
   p=s.project(pid)
   if p.get('mode')!='quick':s.fail('请选择快速生成类型的项目')
  else:p=s.create({'name':str(params['video_subject'])[:120],'mode':'quick'});pid=p['id']
  save_draft(pid,{**body,'video_subject':params['video_subject']})
  with s.LOCK:
   p=s.project(pid)
   if not body.get('preview'):p['last_video_inputs']=json.loads(json.dumps(p['quick_inputs']))
   p.update(quick_params={k:v for k,v in params.items() if k in allowed},story=script,idea=params['video_subject'],ratio=params.get('video_aspect','9:16'));s.put(p)
  mode='audio' if body.get('preview') else 'video'
  def run(jid):
   result=worker(mode,params,str(uuid.uuid4()))
   paths=[]
   def collect(v):
    if isinstance(v,str) and Path(v).suffix in ('.mp4','.mp3','.wav','.srt'):
     p=Path(v)
     if p.is_file() and p.resolve().is_relative_to((root/'storage').resolve()):
      name=uuid.uuid4().hex+p.suffix; s.shutil.copyfile(p,work/name);paths.append({'name':p.name,'url':'/api/quick/file/'+name})
    elif isinstance(v,dict):
     for x in v.values():collect(x)
    elif isinstance(v,list):
     for x in v:collect(x)
   output=result.get('result',{})
   collect(output.get('result',output) if isinstance(output,dict) else output)
   asset_ids=[]
   for output in paths:
    path=work/output['url'].rsplit('/',1)[-1]
    if path.suffix=='.mp4':asset_ids.append(s.add_asset(pid,'quick-video','',output['name'],path.read_bytes(),'video/mp4'))
   if asset_ids:
    with s.LOCK:
     p=s.project(pid);p['final_video']=asset_ids[-1];s.put(p)
   s.job_update(jid,'succeeded',outputs=paths,assets=asset_ids)
  snapshot=json.loads(json.dumps(s.project(pid)['quick_inputs']))
  task=s.new_job(pid,'quick-audio' if mode=='audio' else 'quick-video',{'subject':params['video_subject'],'inputs':snapshot},run)
  return task

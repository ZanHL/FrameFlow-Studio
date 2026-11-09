"""Local single-user video studio. Run with .venv/bin/python server.py."""
import base64, hashlib, sys, ipaddress, json, math, os, re, shutil, socket, sqlite3, subprocess, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse, quote, unquote
import requests
sys.path.insert(0,str(Path(__file__).resolve().parent))
from secret_store import KeychainStore, MemoryStore, FileStore, SecretStoreError
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from studio.models import codex_cli
from studio.models.image_prompts import frame_prompt,style_sample_prompt,validate_frame_description

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('STUDIO_DATA',ROOT/'data')); DATA.mkdir(parents=True,exist_ok=True); os.chmod(DATA,0o700)
MEDIA=DATA/'media'; MEDIA.mkdir(exist_ok=True)
SECRETS=(MemoryStore() if os.environ.get('STUDIO_KEY_STORE')=='memory' else FileStore(DATA/'secrets.json') if __import__('sys').platform != 'darwin' else KeychainStore((DATA/'.keychain-service').read_text().strip() if (DATA/'.keychain-service').exists() else 'com.pianchang.studio.'+hashlib.sha256(str(DATA.resolve()).encode()).hexdigest()[:16]))
KEY_ERRORS={}
DB=DATA/'studio.db'; LOCK=threading.RLock(); KEYS={}; POOL=ThreadPoolExecutor(max_workers=3)
FFMPEG=str(ROOT.parent/'tools/ffmpeg') if (ROOT.parent/'tools/ffmpeg').exists() else shutil.which('ffmpeg')
if not FFMPEG:
    import imageio_ffmpeg
    FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()
DEFAULTS=json.loads((ROOT/'prompts.json').read_text())
CATALOG=json.loads((ROOT/'model-catalog.json').read_text())
ROLES=['director','artist','animator','modeler']; STEPS=['创意与故事','分镜设计','画风与设定','首尾帧','提交前审核','视频生成','剪辑与调色','复核与交付']

def db():
    c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row; return c
with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project TEXT,kind TEXT,status TEXT,data TEXT);
    CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,project TEXT,kind TEXT,shot TEXT,name TEXT,path TEXT,mime TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS repair_versions(id TEXT PRIMARY KEY,project TEXT,step INTEGER,shot TEXT,created REAL,label TEXT,data TEXT);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT,time REAL,text TEXT);''')
    c.execute("UPDATE jobs SET status='interrupted' WHERE status IN ('queued','running') AND kind NOT IN ('video','3d')")
os.chmod(DB,0o600)
from studio.engine.runtime import QuickEngine
from studio.paths import ENGINE_RUNTIME
QUICK_ROOT=ENGINE_RUNTIME
QUICK=QuickEngine()
app=FastAPI(title='映序 AI 视频创作工作室 API')

@app.middleware('http')
async def local_only(request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'): return JSONResponse({'detail':'仅限本机访问'},403)
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.headers.get('host'): return JSONResponse({'detail':'不允许跨站请求'},403)
        if request.headers.get('x-studio-client')!='1': return JSONResponse({'detail':'缺少客户端标识'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    return response

def fail(message,code=400): raise HTTPException(code,message)
def uid(): return uuid.uuid4().hex
def log(pid,text):
    with db() as c: c.execute('INSERT INTO audit(project,time,text) VALUES(?,?,?)',(pid,time.time(),text))
def project(pid):
    with db() as c: r=c.execute('SELECT data FROM projects WHERE id=?',(pid,)).fetchone()
    if not r: fail('项目不存在',404)
    return json.loads(r['data'])
def put(p):
    p['updated']=time.time()
    with db() as c: c.execute('INSERT OR REPLACE INTO projects VALUES(?,?)',(p['id'],json.dumps(p,ensure_ascii=False)))
    return p

def setting(key,default=None):
    with db() as c: r=c.execute('SELECT data FROM settings WHERE id=?',(key,)).fetchone()
    return json.loads(r['data']) if r else default

def store_setting(key,value):
    with db() as c:c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
def secret_account(role,platform,base=None):
    return role+':'+platform+(':'+hashlib.sha256(str(base).encode()).hexdigest()[:16] if platform=='custom' else '')

def restore_keys():
    for role in ROLES:
        c=setting('model:'+role,{})
        platform=c.get('platform') or next((k for k,v in CATALOG.items() if v['base']==c.get('base')),None)
        if platform and c.get('protocol')!='codex_cli':
            try:
                value=SECRETS.get(secret_account(role,platform,c.get('base')))
                if value:KEYS[role]=value
            except SecretStoreError as e:KEY_ERRORS[role]=str(e)
restore_keys()

def prompt(name,p):
    text=setting('prompt:'+name,DEFAULTS[name][1])
    for k,v in {'idea':p['idea'],'duration':p['duration'],'ratio':p['ratio'],'style':p.get('style','')}.items():text=text.replace('{{'+k+'}}',str(v))
    return text

def safe_url(url):
    u=urlparse(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password: fail('API 地址必须是无密码的 HTTPS 地址')
    try:
        addresses=socket.getaddrinfo(u.hostname,u.port or 443)
        if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): fail('API 地址不能指向本机或内部网络')
    except socket.gaierror: fail('无法解析服务商地址')
    return url.rstrip('/')
def config(role):
    if KEY_ERRORS.get(role):fail(KEY_ERRORS[role],503)
    c=setting('model:'+role,{})
    if not c.get('model') or (c.get('protocol')!='codex_cli' and not KEYS.get(role)):fail('请先配置'+{'director':'总导演','artist':'画师','animator':'动画师','modeler':'3D 素材师'}[role]+'模型与 API Key')
    return c

def redact_error(value):
    text=str(value or '')
    for key in sorted((k for k in KEYS.values() if k),key=len,reverse=True):text=text.replace(key,'[密钥已隐藏]')
    text=re.sub(r'(?i)bearer\s+[^\s,;"<>]+','Bearer [已隐藏]',text)
    text=re.sub(r'(?i)(?:sk|AIza)[-_a-zA-Z0-9*…]{8,}','[密钥已隐藏]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|authorization)\s*[=:]\s*)[^\s,;"<>]+',r'\1[已隐藏]',text)
    return text[:1800]

def provider_error(c,r):
    try:body=r.json()
    except ValueError:body={}
    if not isinstance(body,dict):body={}
    error=body.get('error',body)
    if isinstance(error,dict):
        message=error.get('message') or error.get('msg') or error.get('detail') or body.get('message')
        code=error.get('code') or error.get('type') or body.get('code')
    else:message=error;code=body.get('code')
    if not message and isinstance(body.get('base_resp'),dict):
        message=body['base_resp'].get('status_msg');code=body['base_resp'].get('status_code')
    if isinstance(message,(dict,list)):message=json.dumps(message,ensure_ascii=False)
    if not message:message='服务商未提供可读的具体原因；不能仅凭 HTTP 状态判断 Key 是否填写错误。'
    titles={401:'身份验证失败',403:'访问被拒绝',402:'账户余额或计费异常',429:'额度或请求频率受限',404:'模型或接口不存在',400:'请求参数被拒绝'}
    hints={401:'检查 Key 是否完整、是否已失效，以及是否属于所选平台/区域；ChatGPT 网页订阅不能作为 API Key。',403:'检查模型开通权限、项目/组织权限、区域及服务商访问限制。',402:'查看服务商账户余额与计费状态；系统不会自动充值。',429:'检查服务商返回的是速率限制还是额度不足，按具体原因处理后再提交。',404:'检查该账户是否拥有所选模型，或该模型是否已下线。',400:'按服务商错误说明检查模型支持的参数与输入素材。'}
    request_id=body.get('request_id') or body.get('requestId') or r.headers.get('x-request-id') or r.headers.get('request-id') or r.headers.get('x-tt-logid')
    platform=CATALOG.get(c.get('platform'),{}).get('name',c.get('platform','模型服务商'))
    lines=[titles.get(r.status_code,'服务商请求失败')+'（HTTP '+str(r.status_code)+'）','平台：'+str(platform)+' / 模型：'+str(c.get('model',''))]
    if code:lines.append('错误码：'+str(code))
    lines.append('服务商原因：'+str(message))
    if request_id:lines.append('请求 ID：'+str(request_id))
    if str(code).startswith('InputImageSensitiveContentDetected'):
        frame='首帧（content[1]）' if "content[1]" in str(message) else '尾帧（content[2]）' if "content[2]" in str(message) else '输入图片'
        lines.append('定位：'+frame+'被服务商内容规则拦截；不是 API Key 或审核流程错误。')
        lines.append('建议：停止重复提交。若认为是真人识别误判，携带请求 ID 联系火山方舟支持；如确含真人，请使用平台明确支持且具备所需授权的流程，或更换符合平台要求的素材。人工跳过本地审核不能跳过服务商检查。')
    else:lines.append('建议：'+hints.get(r.status_code,'保留请求 ID，检查服务商状态或联系服务商支持。'))
    return redact_error('\n'.join(lines))

from studio.models.call_logs import CallLogs
CALL_LOGS=CallLogs(db,redact_error)

@app.get('/api/call-logs')
def call_log_list(role:str='',platform:str='',status:str='',project:str='',model:str='',days:int=7,page:int=1,page_size:int=12):
    return CALL_LOGS.list(role,platform,status,project,model,days,page,page_size)

def call(c,method,path,**kwargs):
    handle=CALL_LOGS.start(c,method,path,kwargs.get('json'));r=None;payload=None
    try:
        base=safe_url(c['base']);role=c.get('role');headers={'Authorization':'Bearer '+KEYS.get(role,'')}
        if c['protocol']=='anthropic':headers={'x-api-key':KEYS.get(role,''),'anthropic-version':'2023-06-01'}
        try:r=requests.request(method,base+path,headers=headers,timeout=(15,c.get('timeout',240)),allow_redirects=False,**kwargs)
        except requests.RequestException:fail('模型服务连接失败或超时；未自动重试，请检查任务记录后再决定重试',502)
        try:payload=r.json()
        except ValueError:payload=None
        if not 200<=r.status_code<300:
            error=HTTPException(status_code=502,detail=provider_error(c,r));error.definitive_rejection=400<=r.status_code<500 and r.status_code!=408;raise error
        if payload is None:fail('服务商没有返回有效 JSON',502)
        logical_failure=isinstance(payload,dict) and payload.get('status') in ('failed','incomplete','cancelled','expired')
        CALL_LOGS.finish(handle,c,'failed' if logical_failure else 'succeeded',payload,r.status_code,error='服务商任务状态：'+str(payload.get('status')) if logical_failure else '',request_id=r.headers.get('x-request-id',''))
        return payload
    except Exception as e:
        CALL_LOGS.finish(handle,c,'failed',payload,getattr(r,'status_code',None),getattr(e,'detail',str(e)))
        raise

def data_image(a):return 'data:'+a['mime']+';base64,'+base64.b64encode((MEDIA/a['path']).read_bytes()).decode()
def asset(aid,pid=None):
    with db() as c:r=c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
    if not r or (pid and r['project']!=pid):fail('素材不存在',404)
    return dict(r)
def list_assets(pid):
    with db() as c:rows=c.execute('SELECT * FROM assets WHERE project=? ORDER BY created DESC',(pid,)).fetchall()
    warnings=setting('asset-warnings:'+pid,{})
    return [dict(r)|{'url':'/media/'+r['id'],'warning':warnings.get(r['id'],'')} for r in rows]
def add_asset(pid,kind,shot,name,content,mime):
    aid=uid(); ext={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','video/mp4':'.mp4','audio/mpeg':'.mp3','audio/wav':'.wav','application/zip':'.zip'}.get(mime)
    if not ext:fail('不支持该素材格式')
    path=aid+ext;(MEDIA/path).write_bytes(content)
    with db() as c:c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)',(aid,pid,kind,shot,name,path,mime,time.time()))
    return aid

def model_info(c,role):
    return next((m for m in CATALOG.get(c.get('platform'),{}).get('models',{}).get(role,[]) if m['id']==c['model']),{})

def image_payload(c,p,text,size=None):
    payload={'model':c['model'],'prompt':text,'n':1}
    if c.get('platform')=='volcengine':
        payload.pop('n',None);payload.update(size='2K',watermark=False,response_format='b64_json')
        if not any(x in c['model'] for x in ['5-0-pro','5-0-flash']):payload['sequential_image_generation']='disabled'
    elif c.get('platform')=='xai':payload.update(aspect_ratio=p['ratio'],response_format='b64_json')
    else:payload['size']=size or '1536x1024'
    return payload

def video_resolutions(c):
    return model_info(c,'animator').get('resolutions',['480p','720p'])

def video_payload(c,p,sh,resolution='720p'):
    first=data_image(asset(sh['first'],p['id']));last=data_image(asset(sh['last'],p['id']))
    if c.get('platform')=='xai':
        return '/videos/generations',{'model':c['model'],'prompt':sh['prompt'],'image':{'url':first},'last_frame':{'url':last},'duration':int(sh['duration']),'resolution':resolution,'aspect_ratio':p['ratio']}
    content=[{'type':'text','text':sh['prompt']},{'type':'image_url','image_url':{'url':first},'role':'first_frame'}]
    if model_info(c,'animator').get('last_frame',True):content.append({'type':'image_url','image_url':{'url':last},'role':'last_frame'})
    return '/contents/generations/tasks',{'model':c['model'],'content':content,'duration':int(sh['duration']),'resolution':resolution,'ratio':'adaptive','watermark':False}

def llm(p,name,instruction,images=None):
    with CALL_LOGS.context(project=p.get('id')):return _llm(p,name,instruction,images)

def _llm(p,name,instruction,images=None):
    c=config('director')
    if images and model_info(c,'director').get('vision') is False:fail('当前总导演模型仅支持文本，视觉审核请切换支持读图的模型')
    text=prompt('director',p)+'\n\n'+prompt(name,p)+'\n\n'+instruction
    if c['protocol']=='codex_cli':
        if images:fail('Codex 本机渠道当前用于文本创作，请使用画师生成图片')
        handle=CALL_LOGS.start(c,'CLI','codex/exec');codex_cli.LAST_USAGE.set(None)
        try:
            value=codex_cli.generate_text(text,c['model'],c.get('timeout',300),c.get('reasoning','auto'))
            CALL_LOGS.finish(handle,c,'succeeded',{'usage':codex_cli.LAST_USAGE.get() or {}});return value
        except Exception as e:
            CALL_LOGS.finish(handle,c,'failed',error=str(e));fail(str(e),502)
    if c['protocol']=='responses':
        parts=[{'type':'input_text','text':text}]+[{'type':'input_image','image_url':data_image(a)} for a in images or []]
        payload={'model':c['model'],'input':[{'role':'user','content':parts}],'store':False}
        if c.get('reasoning','auto')!='auto':payload['reasoning']={'effort':c['reasoning']}
        result=call(c,'POST','/responses',json=payload)
        if result.get('status') in ('failed','incomplete'):fail('模型未完成响应，请检查额度与输入',502)
        value=''.join(part.get('text','') for item in result.get('output',[]) if item.get('type')=='message' for part in item.get('content',[]) if part.get('type')=='output_text') or result.get('output_text','')
        if not value:fail('Responses 接口未返回文本，请检查模型是否支持当前请求',502)
        return value
    if c['protocol']=='anthropic':
        parts=[{'type':'text','text':text}]
        for a in images or []:parts.append({'type':'image','source':{'type':'base64','media_type':a['mime'],'data':base64.b64encode((MEDIA/a['path']).read_bytes()).decode()}})
        result=call(c,'POST','/messages',json={'model':c['model'],'max_tokens':6000,'messages':[{'role':'user','content':parts}]})
        return '\n'.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')
    parts=[{'type':'text','text':text}]+[{'type':'image_url','image_url':{'url':data_image(a)}} for a in images or []]
    result=call(c,'POST','/chat/completions',json={'model':c['model'],'messages':[{'role':'user','content':parts}]})
    try:return result['choices'][0]['message']['content']
    except (KeyError,IndexError,TypeError):fail('无法读取模型文本响应',502)

def parse_json(text):
    text=text.strip()
    if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
    try:return json.loads(text)
    except ValueError:fail('模型未按约定返回 JSON。可调整提示词后重新执行',502)

def job_update(jid,status,**values):
    with db() as c:
        row=c.execute('SELECT data FROM jobs WHERE id=?',(jid,)).fetchone(); data=json.loads(row['data']);data.update(values)
        c.execute('UPDATE jobs SET status=?,data=? WHERE id=?',(status,json.dumps(data,ensure_ascii=False),jid))
def job(jid):
    with db() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if not r:fail('任务不存在',404)
    return dict(r)|{'data':json.loads(r['data'])}
def new_job(pid,kind,data,fn):
    jid=uid()
    with db() as c:c.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(jid,pid,kind,'queued',json.dumps(data)))
    def run():
        job_update(jid,'running')
        try:
            with CALL_LOGS.context(project=pid,job=jid):fn(jid)
        except HTTPException as e:
            with LOCK:
                job_update(jid,'failed',error=e.detail)
                if kind=='video' and getattr(e,'definitive_rejection',False):settle_video_reservation(jid,False)
            log(pid,kind+'失败：'+str(e.detail))
        except Exception:job_update(jid,'failed',error='处理失败，请检查输入素材与服务配置');log(pid,kind+'处理失败')
    POOL.submit(run); return {'id':jid}

def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)

def check_video_budget(p,cost):
    used=money(p['spent']);reserved=money(p['reserved']);budget=money(p['budget']);cost=money(cost)
    if used+reserved+cost>budget:
        fail(f'超出项目预算：总预算 ¥{budget:.2f}，已记账 ¥{used:.2f}，任务预留 ¥{reserved:.2f}，本次 ¥{cost:.2f}，还差 ¥{used+reserved+cost-budget:.2f}')

def settle_video_reservation(jid,charged):
    # Caller holds LOCK; settlement must happen once, even after repeated refresh/release.
    j=job(jid);d=j['data']
    if d.get('settled'):return
    p=project(j['project']);cost=money(d['quote'])
    p['reserved']=float(max(Decimal(0),money(p['reserved'])-cost))
    if charged:p['spent']=float(money(p['spent'])+cost)
    with db() as conn:
        d.update(settled=True,settlement='charged' if charged else 'not_charged')
        conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),p['id']))
        conn.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(d,ensure_ascii=False),jid))

def repair_legacy_video_reservations():
    with LOCK:
        with db() as conn:
            rows=conn.execute("SELECT id,status,data FROM jobs WHERE kind='video'").fetchall()
        for row in rows:
            d=json.loads(row['data']);error=str(d.get('error',''))
            rejected=not d.get('remote_id') and re.search(r'HTTP (400|401|402|403|404|409|422|429)\b',error)
            if row['status']=='failed' and not d.get('settled'):
                if error.startswith('服务商任务状态：'):
                    # Old polling code already released these; only mark to prevent a second deduction.
                    job_update(row['id'],'failed',settled=True,settlement='not_charged')
                elif rejected:settle_video_reservation(row['id'],False)

repair_legacy_video_reservations()

def invalidate(p,step):
    for i in range(step,8):p['confirmed'].pop(str(i),None)
    p['reviews']={k:v for k,v in p.get('reviews',{}).items() if int(k)<step}
    if step<=6:p.pop('export_asset',None)
    if step<=5:p.pop('final_video',None)
    if step<=4:
        for s in p.get('shots',[]):s.pop('review',None)

@app.get('/api/bootstrap')
def bootstrap():
    with db() as c:projects=[json.loads(r['data']) for r in c.execute('SELECT data FROM projects')]
    return {'catalog':CATALOG,'projects':sorted(projects,key=lambda p:p['updated'],reverse=True),'models':{r:setting('model:'+r,{})|{'has_key':bool(KEYS.get(r)),'key_error':KEY_ERRORS.get(r,'')} for r in ROLES},'prompts':{k:{'name':v[0],'default':v[1],'value':setting('prompt:'+k,v[1])} for k,v in DEFAULTS.items()},'ffmpeg':bool(FFMPEG)}

@app.post('/api/projects')
def create(body:dict):
    name=str(body.get('name','')).strip()
    if not name or len(name)>120:fail('项目名称需为 1–120 字')
    mode=body.get('mode','custom')
    if mode not in ('quick','custom'):fail('项目类型无效')
    p={'mode':mode,'id':uid(),'name':name,'idea':body.get('idea',''),'duration':30,'ratio':'16:9','budget':200,'structure':'片段式','music':False,'subtitles':False,'style':'','story':'','notes':'','shots':[],'confirmed':{},'reviews':{},'spent':0,'reserved':0,'revision':0,'stage':0,'created':time.time()}
    if mode=='quick':p['ratio']='9:16'
    put(p);log(p['id'],'创建项目');return p

@app.get('/api/projects/{pid}')
def get_project(pid:str):return project(pid)
@app.delete('/api/projects/{pid}')
def delete_project(pid:str):
    with LOCK:
        project(pid)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM jobs WHERE project=? AND status IN ('queued','running','submitted')",(pid,)).fetchone():
                fail('项目有正在制作的任务，请等待任务结束后再删除',409)
            paths=[r['path'] for r in c.execute('SELECT path FROM assets WHERE project=?',(pid,))]
            for table in ('assets','jobs','repair_versions','audit'):
                c.execute(f'DELETE FROM {table} WHERE project=?',(pid,))
            for key in ('asset-warnings:'+pid,):c.execute('DELETE FROM settings WHERE id=?',(key,))
            c.execute('DELETE FROM projects WHERE id=?',(pid,))
        for name in paths:
            path=(MEDIA/name).resolve()
            if path.is_relative_to(MEDIA.resolve()):
                with db() as c:shared=c.execute('SELECT 1 FROM assets WHERE path=?',(name,)).fetchone()
                if not shared:
                    try:path.unlink(missing_ok=True)
                    except OSError:pass
    return {'ok':True,'message':'项目已删除'}

@app.patch('/api/projects/{pid}')
def update_project(pid:str,body:dict):
    with LOCK:
        p=project(pid);expected=body.pop('_revision',None)
        if expected is not None and expected!=p['revision']:fail('项目已更新，请刷新后重试',409)
        allowed={'name':0,'idea':0,'duration':0,'ratio':0,'budget':5,'generation_resolution':8,'structure':0,'music':0,'subtitles':0,'story':0,'style':2,'shots':1,'notes':7,'stage':8}
        changed=[allowed[k] for k,v in body.items() if k in allowed and k!='shots' and p.get(k)!=v]
        if 'shots' in body and body['shots']!=p['shots']:
            before={s['id']:s for s in p['shots']}; after=body['shots']
            if [s['id'] for s in after]!=[s['id'] for s in p['shots']]:changed.append(1)
            for sh in after:
                old=before.get(sh['id'],{})
                if any(sh.get(k)!=old.get(k) for k in ['title','duration','description']):changed.append(1)
                if any(sh.get(k)!=old.get(k) for k in ['first','last','frame_plan']):changed.append(3)
                if sh.get('prompt')!=old.get('prompt'):changed.append(4)
                if sh.get('selected')!=old.get('selected'):changed.append(5)
                # Reviews are server-owned and cannot be forged by a project PATCH.
                if old.get('review'):sh['review']=old['review']
                else:sh.pop('review',None)
        for k,v in body.items():
            if k in allowed:p[k]=v
        if not str(p['name']).strip():fail('项目名称不能为空')
        try:
            if not 1<=float(p['budget'])<=1000000 or not 5<=int(p['duration'])<=600:fail('预算需为 1–1000000 元，片长需为 5–600 秒')
        except (ValueError,TypeError):fail('预算和片长必须是有效数字')
        if p.get('generation_resolution','720p') not in ('480p','720p','1080p'):fail('不支持此生成分辨率')
        if p['ratio'] not in ['16:9','9:16','1:1']:fail('不支持此画幅')
        if len(p['shots'])>100:fail('最多支持 100 个镜头')
        for sh in p['shots']:
            if not isinstance(sh.get('id'),str) or not 2<=float(sh.get('duration',0))<=30:fail('每镜生成时长需为 2–30 秒，提交时还将检查模型时长限制')
            for k in ['first','last','selected']:
                if sh.get(k):
                    a=asset(sh[k],pid)
                    if k in ['first','last'] and not a['mime'].startswith('image/'):fail('首尾帧必须为图片')
                    if k=='selected' and a['mime']!='video/mp4':fail('选定版本必须为 MP4 视频')
        if changed:
            if min(changed)<8:invalidate(p,min(changed))
            p['revision']+=1
        return put(p)

@app.post('/api/prompts/{name}')
def save_prompt(name:str,body:dict):
    if name not in DEFAULTS:fail('模板不存在',404)
    text=str(body.get('value','')).strip()
    if not text or len(text)>30000:fail('模板不能为空且不超过 30000 字')
    store_setting('prompt:'+name,text);return {'saved':True}

@app.post('/api/models/{role}')
def save_model(role:str,body:dict):
    if role not in ROLES:fail('角色不存在')
    platform=body.get('platform')
    old=setting('model:'+role,{})
    if not platform:
        platform=next((k for k,v in CATALOG.items() if v['base']==old.get('base')),None)
    if platform not in CATALOG:fail('请选择支持的平台')
    platform_config=CATALOG[platform];model=str(body.get('model','')).strip()
    available=platform_config['models'].get(role,[])
    if not available:fail('当前平台不支持此角色')
    if model not in [m['id'] for m in available] and not ((role=='director' or platform_config.get('auth')=='cli') and body.get('custom_model')):fail('所选模型不支持当前角色或平台')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,199}',model):fail('模型 ID 格式无效')
    base=platform_config['base']
    if platform=='custom':
        base=str(body.get('base',old.get('base',''))).strip().rstrip('/')
        if urlparse(base).query or urlparse(base).fragment:fail('接口地址不能包含查询参数或片段')
        base=safe_url(base)
    protocol=platform_config['protocol']
    if role=='director' and protocol in ('compatible','responses'):
        protocol=next((m.get('api',protocol) for m in available if m['id']==model),protocol)
        if body.get('api') in ('compatible','responses'):protocol=body['api']
    try:timeout=int(body.get('timeout',old.get('timeout',300)))
    except (TypeError,ValueError):fail('超时必须为整数秒')
    if not 30<=timeout<=1800:fail('超时范围为 30–1800 秒')
    reasoning=body.get('reasoning','auto')
    if reasoning not in ('auto','low','medium','high','xhigh'):fail('不支持的推理强度')
    try:rate=float(body.get('rate',old.get('rate',0)))
    except (ValueError,TypeError):fail('预算单价必须是有效数字')
    if not math.isfinite(rate) or rate<0:fail('预算单价必须大于或等于零')
    key=str(body.get('key','')).strip()
    account=secret_account(role,platform,base)
    try:
        if protocol=='codex_cli':stored=None
        elif body.get('clear_key'):
            SECRETS.delete(account);stored=None
        elif key:
            SECRETS.set(account,key);stored=key
        else:stored=SECRETS.get(account)
    except SecretStoreError as e:fail(str(e),503)
    if protocol!='codex_cli' and old.get('base')!=base and not stored and KEYS.get(role) and not body.get('clear_key'):fail('该平台尚无已保存的 Key，请填写后再切换')
    c={'role':role,'platform':platform,'protocol':protocol,'base':base,'model':model,'rate':rate,'timeout':timeout,'reasoning':reasoning,'custom_model':model not in [m['id'] for m in available]}
    store_setting('model:'+role,c)
    if stored:KEYS[role]=stored
    else:KEYS.pop(role,None)
    KEY_ERRORS.pop(role,None)
    return c|{'has_key':bool(KEYS.get(role))}
@app.post('/api/models/{role}/test')
def test_model(role:str):
    c=config(role)
    if c.get('protocol')=='codex_cli':
        status=codex_cli.status()
        return status|{'models':[m['id'] for m in status['models']],'model_found':c['model'] in [m['id'] for m in status['models']]}
    result=call(c,'GET','/models')
    models=[x.get('id','') for x in result.get('data',[])]
    return {'connected':True,'models':models,'model_found':c['model'] in models,'message':'已连接。模型列表可能不包含所有接入点，生成能力以实际请求为准。'}

@app.get('/api/models/codex/status')
def codex_status():return codex_cli.status()|{'login':codex_cli.login_state()}

@app.post('/api/models/codex/login')
def codex_login():
    try:return codex_cli.begin_login()
    except codex_cli.CodexError as e:fail(str(e))

@app.post('/api/projects/{pid}/review/{step}')
def review_step(pid:str,step:int):
    p=project(pid)
    if step in [3,7]:fail('图片与成片不使用模型审核，请人工查看后直接确认本步')
    if step not in [0,1,2]:fail('该环节可使用逐镜文字检查')
    config('director');revision=p['revision']
    materials={'story':p['story'],'style':p['style'],'shots':[{k:v for k,v in sh.items() if k!='review'} for sh in p['shots']]}
    if step==0 and not p['story'].strip():fail('请先编写故事')
    if step==7:
        finals=[asset(p['export_asset'],pid)] if p.get('export_asset') else []
        if not finals:fail('请先导出成片')
    def work(jid):
        images=[]
        text=llm(p,{0:'story',1:'storyboard',2:'style',3:'frames',7:'delivery'}[step],'你是可选的文字检查，只审故事、分镜和文字设定，不查看图片和视频，不以缺少视觉核查作为不通过原因。视觉效果由用户自行确认。材料：'+json.dumps(materials,ensure_ascii=False)+'\n返回 JSON {"passed":true或false,"issues":[问题],"summary":"你理解的内容与无法检查的项目"}。只针对文字中确切存在的问题给出建议。',images)
        result=parse_json(text)
        if type(result.get('passed')) is not bool:fail('审核响应格式错误')
        with LOCK:
            q=project(pid)
            if q['revision']!=revision:fail('材料已修改，本次审核作废')
            q['reviews'][str(step)]=result;put(q)
        log(pid,STEPS[step]+'独立审核：'+('通过' if result['passed'] else '不通过'));job_update(jid,'succeeded',result=result)
    return new_job(pid,'review',{},work)

def repair_snapshot(p,step,sid,label):
    fields={'story':p['story']} if step==0 else {'style':p['style']} if step==2 else {'shots':p['shots']}
    with db() as c:c.execute('INSERT INTO repair_versions VALUES(?,?,?,?,?,?,?)',(uid(),p['id'],step,sid,time.time(),label,json.dumps(fields,ensure_ascii=False)))

def repair_cancelled(jid):
    if job(jid)['data'].get('cancel_requested'):
        job_update(jid,'cancelled',message='已停止，已保存的修订版本保留');return True
    return False

@app.get('/api/projects/{pid}/repair-versions')
def repair_versions(pid:str):
    project(pid)
    with db() as c:rows=c.execute('SELECT * FROM repair_versions WHERE project=? ORDER BY created DESC',(pid,)).fetchall()
    return [dict(r)|{'data':json.loads(r['data'])} for r in rows]

@app.post('/api/jobs/{jid}/cancel-repair')
def cancel_repair(jid:str):
    j=job(jid)
    if j['kind'] not in ['auto-repair','repair-plan'] or j['status'] not in ['queued','running']:fail('任务已经结束')
    job_update(jid,j['status'],cancel_requested=True,message='收到停止请求，当前模型请求结束后停止');return {'ok':True}

@app.post('/api/projects/{pid}/repair')
def auto_repair(pid:str,body:dict):
    with LOCK:
        p=project(pid);config('director')
        try:step=int(body.get('step',-1));rounds=int(body.get('rounds',2))
        except (ValueError,TypeError):fail('修订参数无效')
        sid=str(body.get('shot',''))
        if step not in [0,1,2,3,4,7] or not 1<=rounds<=3:fail('请选择有效环节及 1–3 轮修订')
        if not body.get('approve'):fail('请先确认自动修订及复审的模型调用费用')
        sh=next((x for x in p['shots'] if x['id']==sid),None) if sid else None
        if step==4 and not sh:fail('镜头不存在')
        review=sh.get('review') if sh else p['reviews'].get(str(step))
        if not review or review.get('passed') is not False or review_accepted(review):fail('仅支持处理尚未放行的不通过审核')
        with db() as c:
            if c.execute("SELECT 1 FROM jobs WHERE project=? AND kind IN ('auto-repair','repair-plan') AND status IN ('queued','running')",(pid,)).fetchone():fail('此项目已有自动处理任务，请等待完成或停止',409)
        baseline=p['revision'];plan_only=step in [3,7]
        def work(jid):
            nonlocal baseline
            current_review=review
            for attempt in range(1,(1 if plan_only else rounds)+1):
                if repair_cancelled(jid):return
                q=project(pid)
                if q['revision']!=baseline:fail('项目已被修改，自动处理停止，未覆盖你的修改')
                job_update(jid,'running',attempt=attempt,phase='分析问题' if plan_only else '修订内容',message='第 '+str(attempt)+' 轮 / 最多 '+str(rounds)+' 轮')
                material={'story':q['story'],'style':q['style'],'shots':[{k:v for k,v in x.items() if k!='review'} for x in q['shots']]}
                if sid:material={'style':q['style'],'shot':{k:v for k,v in next(x for x in q['shots'] if x['id']==sid).items() if k!='review'}}
                images=[]
                # User opted out of model-based visual review: never send image bytes here.
                if plan_only:
                    text=llm(q,'frames' if step==3 else 'post','只根据审核不通过的意见，给出逐条可执行处理方案，注明需要改图、剪辑或重拍的项目。不得声称已经完成操作。不会自动生成图片或视频。材料：'+json.dumps(material,ensure_ascii=False)+'\n审核意见：'+json.dumps(current_review,ensure_ascii=False))
                    if repair_cancelled(jid):return
                    job_update(jid,'succeeded',result=text,message='处理方案已生成，需人工确认后执行');log(pid,'生成审核整改方案，未生成图片或视频');return
                instruction='根据审核意见修订当前内容。保留已确认的上游要求，只修改当前环节。材料：'+json.dumps(material,ensure_ascii=False)+'\n审核意见：'+json.dumps(current_review,ensure_ascii=False)
                if step in [0,2]:instruction+='\n只返回修订后的完整'+('故事' if step==0 else '画风与角色设定')+'正文，不要解释。'
                elif step==1:instruction+='\n只返回 JSON 数组，每镜 id,title,duration,description,prompt。必须保留原有镜头 id、顺序和数量，只修订内容。duration 为 2–30 秒整数。'
                else:instruction+='\n只返回当前镜头修订后的完整七段式视频提示词。图片若存在无法用文字修复的问题，仍须在复审中判定不通过。'
                text=llm(q,{0:'story',1:'storyboard',2:'style',4:'video'}[step],instruction,images)
                if repair_cancelled(jid):return
                if not isinstance(text,str) or not text.strip():fail('模型未返回修订内容，原版本保留')
                fixed=None
                if step==1:
                    fixed=parse_json(text)
                    if not isinstance(fixed,list) or [x.get('id') for x in fixed]!=[x['id'] for x in q['shots']]:fail('模型改变了镜头标识或顺序，未覆盖原版本')
                    for x in fixed:
                        if not isinstance(x.get('duration'),(int,float)) or not 2<=x['duration']<=30:fail('修订后的镜头时长不合法，未覆盖原版本')
                        if any(not isinstance(x.get(k),str) for k in ['title','description','prompt']):fail('修订后的分镜格式不合法')
                with LOCK:
                    latest=project(pid)
                    if latest['revision']!=baseline:fail('项目已被修改，自动修订结果未覆盖')
                    repair_snapshot(latest,step,sid,'自动修订前 · 第 '+str(attempt)+' 轮')
                    other_reviews={x['id']:x.get('review') for x in latest['shots'] if x['id']!=sid}
                    if step==0:latest['story']=text
                    elif step==2:latest['style']=text
                    elif step==1:
                        for old,new in zip(latest['shots'],fixed):
                            for key in ['title','duration','description','prompt']:old[key]=new[key]
                    else:next(x for x in latest['shots'] if x['id']==sid)['prompt']=text
                    invalidate(latest,step)
                    if step==4:
                        for x in latest['shots']:
                            if other_reviews.get(x['id']):x['review']=other_reviews[x['id']]
                    latest['revision']+=1;baseline=latest['revision'];put(latest);repair_snapshot(latest,step,sid,'自动修订后 · 第 '+str(attempt)+' 轮')
                log(pid,'自动修订第 '+str(attempt)+' 轮：'+STEPS[step]+'；原版本已保留')
                if repair_cancelled(jid):return
                job_update(jid,'running',phase='独立复审')
                fresh=project(pid)
                clean={'story':fresh['story'],'style':fresh['style'],'shots':[{k:v for k,v in x.items() if k!='review'} for x in fresh['shots']]}
                if sid:clean={'style':fresh['style'],'shot':{k:v for k,v in next(x for x in fresh['shots'] if x['id']==sid).items() if k!='review'}}
                result=parse_json(llm(fresh,'review','你是可选的独立文字检查，只检查文字逻辑，不查看或验证图片，不因缺少视觉核查而判定失败。材料：'+json.dumps(clean,ensure_ascii=False)+'\n返回 JSON {"passed":true或false,"issues":[],"summary":"说明"}。不得在材料不充分时通过。',images))
                if type(result.get('passed')) is not bool or not isinstance(result.get('issues'),list):fail('复审返回格式错误，修订版本已保存，可手动再次审核')
                if repair_cancelled(jid):return
                with LOCK:
                    latest=project(pid)
                    if latest['revision']!=baseline:fail('项目已变更，复审结果作废')
                    if sid:next(x for x in latest['shots'] if x['id']==sid)['review']=result
                    else:latest['reviews'][str(step)]=result
                    put(latest)
                current_review=result;log(pid,'自动修订后独立复审：'+('通过' if result['passed'] else '不通过'))
                if result['passed']:
                    job_update(jid,'succeeded',result=result,message='修订并复审通过，请查看内容后手动确认本步');return
            job_update(jid,'succeeded',result=current_review,message='已达修订轮次上限，仍未通过；请根据意见手动处理')
        return new_job(pid,'repair-plan' if plan_only else 'auto-repair',{'step':step,'shot':sid,'rounds':rounds},work)

def review_accepted(review):
    return bool(review and (review.get('passed') is True or review.get('override',{}).get('approved') is True))

@app.post('/api/projects/{pid}/force-review')
def force_review(pid:str,body:dict):
    with LOCK:
        p=project(pid)
        if body.get('revision')!=p['revision']:fail('内容已变更，请刷新并检查最新材料后再放行',409)
        try:step=int(body.get('step',-1))
        except (ValueError,TypeError):fail('审核环节无效')
        if step not in [0,1,2,3,4,7]:fail('该环节没有独立审核')
        sid=str(body.get('shot',''));reason=str(body.get('reason','')).strip()
        if not reason or len(reason)>1000:fail('请填写人工放行原因（1–1000 字）')
        if step==4:
            sh=next((x for x in p['shots'] if x['id']==sid),None)
            if not sh:fail('镜头不存在')
            review=sh.get('review')
        else:review=p['reviews'].get(str(step))
        if not review or review.get('passed') is not False:fail('仅能对已有的不通过审核人工放行')
        if review_accepted(review):fail('此审核已经人工放行')
        p['revision']+=1
        review['override']={'approved':True,'reason':reason,'time':time.time(),'revision':p['revision'],'by':'用户'}
        with db() as c:
            rows=c.execute("SELECT id,data FROM jobs WHERE project=? AND kind IN ('auto-repair','repair-plan') AND status IN ('queued','running')",(pid,)).fetchall()
            for row in rows:
                data=json.loads(row['data']);data['cancel_requested']=True
                c.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(data),row['id']))
        put(p);log(pid,'人工强制通过：'+STEPS[step]+(' / '+sh['title'] if step==4 else '')+'；原因：'+reason+'；AI 原不通过意见保留，自动处理已停止')
        return p

@app.post('/api/projects/{pid}/confirm/{step}')
def confirm_step(pid:str,step:int):
    with LOCK:
        p=project(pid)
        if step not in range(8):fail('步骤不存在')
        if step and not p['confirmed'].get(str(step-1)):fail('请先确认上一环节')
        if step==0 and not p['story']:fail('请先写故事')
        if step==1 and not p['shots']:fail('请先添加分镜')
        if step==2 and not p['style']:fail('请先确定画风与设定')
        if step==3 and any(not s.get('first') or not s.get('last') for s in p['shots']):fail('每个镜头必须选择首尾帧')
        if step==4 and any(not s.get('first') or not s.get('last') or not s.get('prompt') for s in p['shots']):fail('人工放行不能替代首尾帧与视频提示词，请补齐材料')
        if step==5 and any(not s.get('selected') for s in p['shots']):fail('请为每镜选定一个视频版本')
        if step==6 and not p.get('export_asset'):fail('请先为当前素材导出成片，旧版成片不能代替本次导出')
        p['confirmed'][str(step)]=True;p['stage']=min(step+1,7);put(p);log(pid,'用户确认：'+STEPS[step]+'（模型审核可选，人工确认继续）');return p

@app.post('/api/projects/{pid}/generate/{kind}')
def generate_text(pid:str,kind:str):
    p=project(pid);config('director');revision=p['revision']
    if kind not in ['story','storyboard','style','video','frames']:fail('不支持此生成类型')
    required={'storyboard':0,'style':1,'frames':2,'video':3}.get(kind)
    if required is not None and not p['confirmed'].get(str(required)):fail('请先确认前置环节')
    def work(jid):
        instruction='项目需求：'+json.dumps({k:v for k,v in p.items() if k not in ['reviews','confirmed']},ensure_ascii=False)
        if kind=='storyboard':instruction+='\n仅返回 JSON 数组，每镜字段 title,duration(2–15秒，整数),description(包含景别、机位、运镜、画面左右、运动主体、转场、配色),prompt(视频七段式)，所有镜头时长合计接近目标片长。'
        if kind=='frames':instruction+='\n仅返回 JSON 数组，每镜字段 id,first_prompt,last_prompt,motion。保留已有镜头 id。每个 first_prompt/last_prompt 只能描述当前镜头的一个静止瞬间，不含其他镜头、不含 A/B 子镜、不写审核或制作流程，也不要求排版成多格图。motion 单独写中间动作。需要两个机位或两个子镜时应先拆分镜头，不可塞进一张首帧或尾帧。与画风和分镜一致。'
        if kind=='video':instruction+='\n仅返回 JSON 数组，每镜字段 id,prompt。按项目已有镜头 id 返回，提示词使用七段式。'
        text=llm(p,'storyboard' if kind=='storyboard' else kind,instruction)
        with LOCK:
            q=project(pid)
            if q['revision']!=revision:fail('项目材料已修改，结果未覆盖；请在任务中查看原始结果')
            if kind=='storyboard':
                shots=parse_json(text)
                if not isinstance(shots,list) or not shots or len(shots)>100:fail('分镜返回格式错误')
                q['shots']=[{'id':uid(),'title':str(x.get('title','镜头')),'duration':max(2,min(15,math.ceil(float(x.get('duration',5))))),'description':str(x.get('description','')),'prompt':str(x.get('prompt',''))} for x in shots]
                invalidate(q,1)
            elif kind=='frames':
                results=parse_json(text)
                if not isinstance(results,list) or {x.get('id') for x in results}!={x['id'] for x in q['shots']}:fail('首尾帧规划镜头不完整，未覆盖原内容')
                for sh in q['shots']:
                    item=next(x for x in results if x['id']==sh['id'])
                    sh['frame_plan']={k:str(item.get(k,'')) for k in ['first_prompt','last_prompt','motion']}
                invalidate(q,3)
            elif kind=='video':
                results=parse_json(text)
                for sh in q['shots']:
                    match=next((x for x in results if x.get('id')==sh['id']),None)
                    if match:sh['prompt']=match['prompt']
                invalidate(q,4)
            else:q[kind]=text;invalidate(q,0 if kind=='story' else 2)
            q['revision']+=1;put(q)
        log(pid,'模型完成：'+kind);job_update(jid,'succeeded',result=text)
    return new_job(pid,kind,{},work)

@app.post('/api/projects/{pid}/upload')
async def upload(pid:str,request:Request,kind:str='reference',shot:str=''):
    project(pid)
    if kind not in ['reference','first','last','video','music','final','style']:fail('素材类别无效')
    mime=request.headers.get('content-type','').split(';')[0]
    limit=100*1024*1024;chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>limit:fail('单个素材不能超过 100 MB',413)
        chunks.append(chunk)
    content=b''.join(chunks)
    if mime.startswith('image/'):
        valid=(mime=='image/png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/jpeg' and content.startswith(b'\xff\xd8\xff')) or (mime=='image/webp' and content[:4]==b'RIFF' and content[8:12]==b'WEBP')
        if not valid:fail('图片文件格式无效')
    elif mime=='video/mp4':
        if b'ftyp' not in content[:32]:fail('请选择有效 MP4 视频')
    elif mime not in ['audio/mpeg','audio/wav']:fail('支持 PNG/JPEG/WebP、MP4、MP3/WAV')
    aid=add_asset(pid,kind,shot,unquote(request.headers.get('x-file-name','素材'))[:150],content,mime)
    log(pid,'导入素材：'+kind);return asset(aid)|{'url':'/media/'+aid}

def select_generated_frame(pid,sid,kind,aid,revision):
    with LOCK:
        q=project(pid)
        if q['revision']!=revision:return None
        sh=next((x for x in q['shots'] if x['id']==sid),None)
        if not sh:return None
        sh[kind]=aid;invalidate(q,3);q['revision']+=1;put(q)
        return q['revision']

@app.post('/api/projects/{pid}/image')
def generate_image(pid:str,body:dict):
    p=project(pid);c=config('artist');kind=body.get('kind','style');sid=body.get('shot','')
    if kind not in ['style','first','last']:fail('图片类型不支持')
    if not p['confirmed'].get('0'):fail('确认故事后才能画图')
    if kind!='style' and not p['confirmed'].get('2'):fail('确认画风后才能画正式镜头')
    text=str(body.get('prompt') or body.get('feedback') or '').strip()
    if not text:fail('请填写图片提示词或修改意见')
    if (sid or kind in ('first','last')) and not any(s['id']==sid for s in p['shots']):fail('请选择一个有效镜头后再生成首尾帧')
    if kind in ('first','last'):
        try:validate_frame_description(text)
        except ValueError as e:fail(str(e))
    reference=body.get('reference')
    if reference:
        if not asset(reference,pid)['mime'].startswith('image/'):fail('重绘参考必须为图片')
    feedback=str(body.get('feedback','')).strip()
    if feedback:text+='\n本次单帧修改意见：'+feedback+'\n保持未提及的角色、画风、背景和构图一致。'
    def work(jid):
        aid=render_image_asset(p,c,kind,sid,text,body.get('size'),reference)
        selected=select_generated_frame(pid,sid,kind,aid,p['revision']) if kind in ['first','last'] and sid else None
        log(pid,'生成图片新版本：'+kind+('，已默认选用' if selected is not None else '，保留为新版本'))
        job_update(jid,'succeeded',asset=aid,auto_selected=selected is not None,message='图片已生成并默认选用' if selected is not None else '图片已生成；项目已变化或无需选帧，请在版本列表查看')
    return new_job(pid,'image',{'shot':sid,'frame_kind':kind,'feedback':feedback,'reference':reference},work)

def render_image_asset(p,c,kind,sid,text,size=None,reference=None):
    pid=p['id']
    shot=next((s for s in p['shots'] if s['id']==sid),None)
    if kind in ('first','last') and not shot:fail('请选择一个有效镜头后再生成首尾帧')
    try:text_prompt=frame_prompt(p,shot,kind,text,prompt('frame_image',p)) if kind in ('first','last') else style_sample_prompt(p,text)
    except ValueError as e:fail(str(e))
    if c.get('protocol')=='codex_cli':
        references=[(MEDIA/asset(reference,pid)['path']).read_bytes()] if reference else []
        if kind=='first' and shot.get('last'):references.append((MEDIA/asset(shot['last'],pid)['path']).read_bytes())
        handle=CALL_LOGS.start(c,'CLI','codex/image');codex_cli.LAST_USAGE.set(None)
        try:
            content=codex_cli.generate_image(text_prompt+'\n画幅：'+p.get('ratio','16:9'),c['model'],c.get('timeout',600),c.get('reasoning','auto'),references)
            CALL_LOGS.finish(handle,c,'succeeded',{'usage':codex_cli.LAST_USAGE.get() or {}})
        except codex_cli.CodexError as e:
            CALL_LOGS.finish(handle,c,'failed',{'error':str(e)});fail(str(e),502)
        mime='image/jpeg' if content.startswith(b'\xff\xd8') else 'image/webp' if content[:4]==b'RIFF' else 'image/png'
        return add_asset(pid,kind,sid,'生成图片 '+time.strftime('%H:%M:%S'),content,mime)
    payload=image_payload(c,p,text_prompt,size)
    warnings=setting('asset-warnings:'+pid,{})
    if c.get('platform')=='volcengine' and kind in ['first','last']:
        references=[data_image(asset(reference,pid))] if reference and not warnings.get(reference) else []
        shot=next((s for s in p['shots'] if s['id']==sid),{})
        if kind=='first' and shot.get('last') and not warnings.get(shot['last']):references.append(data_image(asset(shot['last'],pid)))
        style_refs=[a for a in list_assets(pid) if a['kind']=='style' and a['mime'].startswith('image/') and not warnings.get(a['id'])]
        if style_refs:references.append(data_image(style_refs[0]))
        if references:payload['image']=references
    result=call(c,'POST','/images/generations',json=payload)
    data=result.get('data',[{}])[0]
    if data.get('b64_json'):content=base64.b64decode(data['b64_json'])
    elif data.get('url'):content=download_remote(data['url'],25*1024*1024)
    else:fail('图片接口未返回图片',502)
    mime='image/jpeg' if content.startswith(b'\xff\xd8') else 'image/webp' if content[:4]==b'RIFF' else 'image/png'
    aid=add_asset(pid,kind,sid,'生成图片 '+time.strftime('%H:%M:%S'),content,mime)
    return aid

@app.post('/api/projects/{pid}/shots/{sid}/generate-frame-pair')
def generate_frame_pair(pid:str,sid:str,body:dict):
    p=project(pid);c=config('artist')
    if not p['confirmed'].get('2'):fail('请先确认画风与设定')
    if not body.get('approve'):fail('请确认本次调用画师生成两张图片，费用按服务商规则计收')
    sh=next((x for x in p['shots'] if x['id']==sid),None)
    if not sh:fail('镜头不存在')
    plan=sh.get('frame_plan',{})
    if not all(str(plan.get(k,'')).strip() for k in ['last_prompt','first_prompt']):fail('请先生成并保存本镜首尾帧规划')
    try:
        for key in ('first_prompt','last_prompt'):validate_frame_description(plan[key])
    except ValueError as e:fail(str(e))
    with db() as conn:
        active=conn.execute("SELECT data FROM jobs WHERE project=? AND kind IN ('image','frame-pair') AND status IN ('queued','running')",(pid,)).fetchall()
    if any(json.loads(r['data']).get('shot')==sid for r in active):fail('本镜图片仍在生成中，请勿重复提交',409)
    feedback=str(body.get('feedback','')).strip()
    if len(feedback)>6000:fail('镜头修改意见请控制在 6000 字以内')
    def work(jid):
        result={};expected_revision=p['revision'];all_selected=True
        for kind in ['last','first']:
            job_update(jid,'running',phase='生成尾帧' if kind=='last' else '生成首帧',message='实际出图中（'+str(len(result)+1)+'/2），不是文字规划')
            text=plan[kind+'_prompt']
            if feedback:text+='\n本镜首尾帧共同修改意见：'+feedback+'\n仅调整本镜头，保持未提及的角色、画风与场景一致，并确保首尾帧动作连贯。'
            aid=render_image_asset(p,c,kind,sid,text,reference=sh.get(kind) if feedback else None)
            result[kind]=aid
            selected_revision=select_generated_frame(pid,sid,kind,aid,expected_revision) if expected_revision is not None else None
            expected_revision=selected_revision
            all_selected=all_selected and selected_revision is not None
            next(x for x in p['shots'] if x['id']==sid)[kind]=aid
            job_update(jid,'running',result=result)
        log(pid,'本镜首尾帧两张图片已生成，保留历史版本');job_update(jid,'succeeded',result=result,message='首尾帧图片已生成并默认选用' if all_selected else '首尾帧已生成；期间项目发生修改，请手动选择新版本')
    return new_job(pid,'frame-pair',{'shot':sid,'feedback':feedback},work)

def download_remote(url,limit=100*1024*1024):
    safe_url(url)
    try:
        with requests.get(url,timeout=(15,120),stream=True,allow_redirects=False) as r:
            if r.status_code!=200:fail('媒体下载失败',502)
            data=bytearray()
            for chunk in r.iter_content(65536):
                data.extend(chunk)
                if len(data)>limit:fail('远程媒体超出大小限制')
            return bytes(data)
    except requests.RequestException:fail('媒体下载超时，可刷新远程任务后重试',502)

@app.post('/api/projects/{pid}/3d')
def generate_3d(pid:str,body:dict):
    p=project(pid);c=config('modeler')
    if not body.get('approve'):fail('请确认图生 3D 按服务商规则计费')
    source=asset(str(body.get('image','')),pid)
    if not source['mime'].startswith('image/'):fail('图生 3D 需要一张图片')
    def work(jid):
        result=call(c,'POST','/contents/generations/tasks',json={'model':c['model'],'content':[{'type':'image_url','image_url':{'url':data_image(source)}}]})
        if not result.get('id'):fail('服务商未返回 3D 任务 ID',502)
        job_update(jid,'submitted',remote_id=result['id']);log(pid,'提交图生 3D 任务：'+c['model'])
    return new_job(pid,'3d',{'model':c,'source':source['id']},work)

@app.post('/api/jobs/{jid}/refresh-3d')
def refresh_3d(jid:str):
    with LOCK:
        j=job(jid)
        if j['kind']!='3d' or j['status']!='submitted':return j
        c={**j['data']['model'],'_log_project':j['project'],'_log_job':jid};active=config('modeler')
        if active['base']!=c['base']:fail('请切回该任务所属平台')
        result=call(c,'GET','/contents/generations/tasks/'+quote(j['data']['remote_id'],safe=''))
        if result.get('status')=='succeeded':
            url=result.get('content',{}).get('file_url')
            if not url:fail('任务完成但未返回 3D 文件地址',502)
            content=download_remote(url,300*1024*1024)
            if not content.startswith(b'PK'):fail('服务商未返回预期 ZIP 格式的 3D 文件',502)
            aid=add_asset(j['project'],'3d','',c['model']+' 3D 素材',content,'application/zip')
            job_update(jid,'succeeded',asset=aid);log(j['project'],'3D 素材已保存，可下载 ZIP')
        elif result.get('status') in ['failed','cancelled']:
            err=result.get('error',{});message=err.get('message','3D 生成失败') if isinstance(err,dict) else str(err)
            job_update(jid,'failed',error=redact_error(message))
        return job(jid)

@app.post('/api/projects/{pid}/assets/{aid}/crop')
def crop_image(pid:str,aid:str):
    p=project(pid);a=asset(aid,pid)
    if not a['mime'].startswith('image/'):fail('只能裁切图片')
    if not FFMPEG:fail('FFmpeg 未安装')
    w,h={'16:9':(1280,720),'9:16':(720,1280),'1:1':(1024,1024)}[p['ratio']]
    temp=DATA/(uid()+'.png')
    try:
        cmd=[FFMPEG,'-v','error','-i',str(MEDIA/a['path']),'-vf',f'scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}','-frames:v','1',str(temp)]
        if subprocess.run(cmd,capture_output=True,timeout=60).returncode:fail('裁切失败，请检查图片')
        new=add_asset(pid,a['kind'],a['shot'],a['name']+' 裁切版',temp.read_bytes(),'image/png')
        log(pid,'按项目画幅居中裁切图片，保留原图');return asset(new)|{'url':'/media/'+new}
    finally:temp.unlink(missing_ok=True)

@app.post('/api/projects/{pid}/shots/{sid}/review')
def review_shot(pid:str,sid:str):
    p=project(pid);config('director');sh=next((s for s in p['shots'] if s['id']==sid),None)
    if not sh or not sh.get('first') or not sh.get('last') or not sh.get('prompt'):fail('请准备首尾帧与视频提示词')
    revision=p['revision'];images=[]
    def work(jid):
        text=llm(p,'review','仅检查当前镜头的文字提示词，不核查图片、不要求视觉审核，不因无法验证图片而判定失败。材料：'+json.dumps({'shot':{k:v for k,v in sh.items() if k!='review'},'style':p['style']},ensure_ascii=False)+'。返回 JSON {"passed":true或false,"issues":[],"summary":"说明"}。',images)
        result=parse_json(text)
        if type(result.get('passed')) is not bool:fail('审核格式错误')
        with LOCK:
            q=project(pid)
            if q['revision']!=revision:fail('镜头已变更，审核结果作废')
            next(s for s in q['shots'] if s['id']==sid)['review']=result;put(q)
        log(pid,'镜头审核 '+sh['title']+'：'+('通过' if result['passed'] else '不通过'));job_update(jid,'succeeded',result=result)
    return new_job(pid,'shot-review',{},work)

@app.post('/api/projects/{pid}/shots/{sid}/video')
def generate_video(pid:str,sid:str,body:dict):
    with LOCK:
        p=project(pid);c=config('animator');sh=next((s for s in p['shots'] if s['id']==sid),None)
        if not p['confirmed'].get('4') or not sh:fail('请先确认提交前准备；模型审核不作为提交条件')
        info=model_info(c,'animator');duration=float(sh['duration'])
        resolution=body.get('resolution',p.get('generation_resolution','720p'))
        if resolution not in video_resolutions(c):fail('当前模型不支持该生成分辨率')
        if not info.get('min_duration',2)<=duration<=info.get('max_duration',15):fail('该模型仅支持 '+str(info.get('min_duration',2))+'–'+str(info.get('max_duration',15))+' 秒，请调整本镜时长')
        cost=float(money(Decimal(str(c.get('rate',0)))*Decimal(str(duration))))
        if cost<=0:fail('请在动画师配置中填写每秒预算单价')
        if not body.get('approve') or float(body.get('quote',-1))!=cost:fail('报价发生变化，请重新确认')
        check_video_budget(p,cost)
        with db() as conn:
            active=conn.execute("SELECT id FROM jobs WHERE project=? AND kind='video' AND status IN ('queued','running','submitted')",(pid,)).fetchall()
            if any(job(x['id'])['data'].get('shot')==sid for x in active):fail('该镜头已有进行中的任务，请勿重复提交',409)
        warnings=setting('asset-warnings:'+pid,{})
        if any(warnings.get(sh.get(k)) for k in ('first','last')):fail('首尾帧中有已标记的分镜拼图，请重新生成单镜头画面后再提交视频')
        validate_frames(asset(sh['first'],pid),asset(sh['last'],pid),p['ratio'])
        submit_path,payload=video_payload(c,p,sh,resolution)
        p['generation_resolution']=resolution
        p['reserved']=float(money(p['reserved'])+money(cost));put(p)
        def work(jid):
            # Never automatically repeat a POST: timeout may still have incurred provider charges.
            result=call(c,'POST',submit_path,json=payload)
            remote_id=result.get('request_id') if c.get('platform')=='xai' else result.get('id')
            if not remote_id:fail('服务商未返回任务 ID，请核对服务商控制台',502)
            job_update(jid,'submitted',remote_id=remote_id);log(pid,'视频提交成功 '+sh['title']+'；预算预留 ¥'+str(cost))
        return new_job(pid,'video',{'shot':sid,'quote':cost,'model':c,'revision':p['revision'],'resolution':resolution},work)

@app.post('/api/projects/{pid}/full-video')
def generate_full_video(pid:str,body:dict):
    with LOCK:
        p=project(pid);c=config('animator');info=model_info(c,'animator')
        if not p['confirmed'].get('4'):fail('请先确认提交前准备')
        if not p['shots']:fail('请先准备分镜与首尾帧')
        try:duration=int(body.get('duration',p['duration']));seed=int(body.get('seed',-1))
        except (ValueError,TypeError):fail('时长和随机种子必须是整数')
        minimum,maximum=info.get('min_duration',2),info.get('max_duration',15)
        if not minimum<=duration<=maximum:fail(f'当前模型单次仅支持 {minimum}–{maximum} 秒；请调整整片时长或选择支持更长视频的模型，不会自动拆镜头提交')
        if not -1<=seed<=4294967295:fail('随机种子超出范围')
        resolution=body.get('resolution','720p')
        if resolution not in (['480p','720p'] if c.get('platform')=='volcengine' else ['720p']):fail('当前模型不支持该分辨率')
        text=str(body.get('prompt','')).strip()
        if not text:fail('请填写整片生成提示词')
        first=p['shots'][0].get('first');last=p['shots'][-1].get('last')
        if not first or not last:fail('需要第一镜的首帧和最后一镜的尾帧')
        validate_frames(asset(first,pid),asset(last,pid),p['ratio'])
        rate=Decimal(str(c.get('rate',0)));cost=float(money(rate*duration))
        if cost<=0:fail('请先在动画师设置中填写视频预算单价')
        if not body.get('approve') or round(float(body.get('quote',-1)),2)!=cost:fail('请确认当前整片报价')
        check_video_budget(p,cost)
        with db() as conn:
            if conn.execute("SELECT 1 FROM jobs WHERE project=? AND kind='video' AND status IN ('queued','running','submitted')",(pid,)).fetchone():fail('项目已有生成中的视频任务，请等待完成',409)
        path,payload=video_payload(c,p,{'first':first,'last':last,'prompt':text,'duration':duration})
        payload['resolution']=resolution
        if c.get('platform')=='volcengine':payload.update(seed=seed,watermark=bool(body.get('watermark',False)))
        p['reserved']=round(p['reserved']+cost,2);put(p)
        def work(jid):
            result=call(c,'POST',path,json=payload)
            remote=result.get('request_id') if c.get('platform')=='xai' else result.get('id')
            if not remote:fail('服务商未返回任务 ID，请检查服务商控制台',502)
            job_update(jid,'submitted',remote_id=remote,message='整片已提交，一次生成完整视频');log(pid,'整片视频已提交，预算预留 ¥'+str(cost))
        return new_job(pid,'video',{'shot':'full-film','full_film':True,'quote':cost,'model':c,'revision':p['revision'],'parameters':{'duration':duration,'resolution':resolution,'seed':seed,'watermark':bool(body.get('watermark',False)),'prompt':text}},work)

@app.post('/api/jobs/{jid}/refresh')
def refresh_job(jid:str):
    with LOCK:
        j=job(jid);d=j['data']
        if j['kind']!='video' or j['status']!='submitted':return j
        c={**d['model'],'_log_project':j['project'],'_log_job':jid};active=config('animator')
        if active['base']!=c['base']:fail('该任务属于另一平台，请切回原平台并填写对应 Key 后刷新')
        prefix='/videos/' if c.get('platform')=='xai' else '/contents/generations/tasks/'
        result=call(c,'GET',prefix+quote(d['remote_id'],safe=''))
        status=result.get('status')
        if c.get('platform')=='xai' and status=='done':status='succeeded'
        if status=='succeeded':
            url=result.get('video',{}).get('url') if c.get('platform')=='xai' else result.get('content',{}).get('video_url')
            if not url:fail('任务已完成，但未返回视频 URL',502)
            content=download_remote(url);aid=add_asset(j['project'],'full-video' if d.get('full_film') else 'video',d['shot'],('整片视频 ' if d.get('full_film') else '生成视频 ')+time.strftime('%m-%d %H:%M'),content,'video/mp4')
            settle_video_reservation(jid,True)
            p=project(j['project'])
            if d.get('full_film') and p['revision']==d['revision']:
                p['final_video']=aid;p['confirmed']['5']=True;p['stage']=5
            put(p)
            job_update(jid,'succeeded',asset=aid,usage=result.get('usage'));log(j['project'],'视频已保存；预算记账 ¥'+str(d['quote'])+'（非账单实付）')
        elif status in ['failed','cancelled','expired']:
            settle_video_reservation(jid,False);job_update(jid,'failed',error='服务商任务状态：'+status);log(j['project'],'远程视频任务失败，已释放预算预留')
        return job(jid)

@app.post('/api/jobs/{jid}/release')
def release_uncertain(jid:str,body:dict):
    with LOCK:
        j=job(jid)
        if j['kind']!='video' or j['status'] not in ['failed','interrupted']:fail('只能处理失败或中断的视频请求')
        if j['data'].get('settled'):fail('该预留已处理')
        if body.get('resolution') not in ['not_charged','charged']:fail('请核对服务商账单并选择结果')
        settle_video_reservation(jid,body['resolution']=='charged');log(j['project'],'用户核对异常任务账单：'+body['resolution']);return {'ok':True}

def validate_frames(first,last,ratio):
    if not FFMPEG:fail('缺少 FFmpeg，无法检查首尾帧尺寸')
    sizes=[]
    for a in [first,last]:
        result=subprocess.run([FFMPEG,'-hide_banner','-i',str(MEDIA/a['path'])],capture_output=True,timeout=20)
        match=re.search(r'Video:.*?[, ](\d{2,5})x(\d{2,5})',result.stderr.decode(errors='replace'))
        if not match:fail('首尾帧无法解码，请重新上传有效图片')
        sizes.append(tuple(map(int,match.groups())))
    if sizes[0]!=sizes[1]:fail('首尾帧尺寸不一致，请裁切到相同尺寸后上传')
    target={'16:9':16/9,'9:16':9/16,'1:1':1}[ratio]
    if abs(sizes[0][0]/sizes[0][1]-target)>0.025:fail('首尾帧画幅与项目不一致，请先裁切')

def sample_video(path,pid):
    if not FFMPEG:fail('FFmpeg 未安装')
    target=DATA/('frames-'+uid());target.mkdir();out=[]
    try:
        cmd=[FFMPEG,'-v','error','-i',str(path),'-vf','fps=1/3,scale=960:-2','-frames:v','12',str(target/'%03d.jpg')]
        result=subprocess.run(cmd,capture_output=True,timeout=180)
        if result.returncode:fail('视频抽帧失败，请检查视频文件')
        for f in sorted(target.glob('*.jpg')):
            aid=add_asset(pid,'review-frame','',f.name,f.read_bytes(),'image/jpeg');out.append(asset(aid))
        return out
    finally:shutil.rmtree(target,ignore_errors=True)

@app.post('/api/projects/{pid}/export')
def export(pid:str,body:dict):
    p=project(pid)
    if not p['confirmed'].get('5'):fail('请先为每镜选定视频并确认生成环节')
    if not FFMPEG:fail('FFmpeg 未安装')
    resolution=body.get('resolution','1080p')
    if resolution not in ('720p','1080p'):fail('合成输出分辨率仅支持 720p 或 1080p')
    videos=[asset(s['selected'],pid) for s in p['shots']]
    music=asset(body['music'],pid) if body.get('music') else None
    if music and not music['mime'].startswith('audio/'):fail('配乐素材必须为音频')
    edits=body.get('edits',{})
    if not isinstance(edits,dict):fail('后期参数无效')
    for sh in p['shots']:
        e=edits.get(sh['id'],{})
        try:
            values=[float(e.get(k,d)) for k,d in [('start',0),('duration',sh['duration']),('brightness',0),('saturation',1)]]
        except (ValueError,TypeError):fail('后期参数必须为数字')
        start,length,brightness,saturation=values
        if not all(math.isfinite(v) for v in values) or start<0 or not 0.1<=length<=30 or not -0.3<=brightness<=0.3 or not 0<=saturation<=2:fail('后期参数超出范围')
    def work(jid):
        workdir=DATA/('export-'+jid);workdir.mkdir();width,height={'1080p':{'16:9':(1920,1080),'9:16':(1080,1920),'1:1':(1080,1080)},'720p':{'16:9':(1280,720),'9:16':(720,1280),'1:1':(720,720)}}[resolution][p['ratio']]
        try:
            for i,a in enumerate(videos):
                sh=p['shots'][i];edit=edits.get(sh['id'],{});length=float(edit.get('duration',sh['duration']));start=float(edit.get('start',0));brightness=float(edit.get('brightness',0));saturation=float(edit.get('saturation',1));src=MEDIA/a['path'];dest=workdir/f'{i}.mp4'
                vf=f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,eq=brightness={brightness}:saturation={saturation},unsharp=3:3:0.25'
                cmd=[FFMPEG,'-v','error','-ss',str(start),'-i',str(src),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(length),'-vf',vf,'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-pix_fmt','yuv420p','-color_primaries','bt709','-colorspace','bt709','-color_trc','bt709','-shortest',str(dest)]
                result=subprocess.run(cmd,capture_output=True,timeout=600)
                if result.returncode:fail('镜头转码失败，请检查选定视频')
            listing=workdir/'concat.txt';listing.write_text('\n'.join("file '"+str(workdir/f'{i}.mp4')+"'" for i in range(len(videos))))
            out=workdir/'final.mp4';cmd=[FFMPEG,'-v','error','-f','concat','-safe','0','-i',str(listing)]
            if music:cmd+=['-stream_loop','-1','-i',str(MEDIA/music['path']),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-shortest']
            else:cmd+=['-c','copy']
            cmd+=['-movflags','+faststart',str(out)]
            if subprocess.run(cmd,capture_output=True,timeout=600).returncode:fail('成片合成失败')
            aid=add_asset(pid,'final','',p['name']+' 成片',out.read_bytes(),'video/mp4')
            with LOCK:
                latest=project(pid)
                if latest['revision']==p['revision']:
                    latest['export_asset']=aid;put(latest)
            log(pid,'导出 '+resolution+' 新版成片，保留所有旧版本');job_update(jid,'succeeded',asset=aid)
        finally:shutil.rmtree(workdir,ignore_errors=True)
    return new_job(pid,'export',{'edits':edits,'resolution':resolution,'upscale':'lanczos'},work)

@app.get('/api/projects/{pid}/activity')
def activity(pid:str):
    project(pid)
    with db() as c:
        jobs=[dict(r)|{'data':json.loads(r['data'])} for r in c.execute('SELECT * FROM jobs WHERE project=? ORDER BY rowid DESC',(pid,))]
        audit=[dict(r) for r in c.execute('SELECT * FROM audit WHERE project=? ORDER BY id DESC',(pid,))]
    # Stored model details never contain the API key.
    return {'assets':list_assets(pid),'jobs':jobs,'audit':audit}
@app.get('/media/{aid}')
def media(aid:str):
    a=asset(aid);return FileResponse(MEDIA/a['path'],media_type=a['mime'],filename=a['name']+Path(a['path']).suffix,content_disposition_type='inline')
@app.get('/api/health')
def health():return {'ok':True,'ffmpeg':bool(FFMPEG)}
@app.get('/api/quick/status')
def quick_status():return QUICK.status()

@app.post('/api/quick/start')
def quick_start():
    try:return QUICK.start()
    except RuntimeError as e:fail(str(e),503)

@app.get('/api/quick/outputs')
def quick_outputs():
    root=QUICK_ROOT/'storage/tasks'
    if not root.exists():return []
    files=sorted(root.glob('*/final*.mp4'),key=lambda p:p.stat().st_mtime,reverse=True)
    return [{'id':str(p.relative_to(root)),'name':p.parent.name+'/'+p.name,'size':p.stat().st_size} for p in files[:100] if not p.is_symlink()]

@app.post('/api/quick/import')
def quick_import(body:dict):
    root=(QUICK_ROOT/'storage/tasks').resolve()
    path=(root/str(body.get('id',''))).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix!='.mp4':fail('成片不存在',404)
    if not path.name.startswith('final'):fail('只能导入成片')
    pid=body.get('project')
    if pid:p=project(pid)
    else:p=create({'name':'快速视频 · '+path.parent.name[:24]})
    aid=add_asset(p['id'],'quick-video','','快速生成成片',path.read_bytes(),'video/mp4')
    log(p['id'],'导入快速生成成片')
    return {'project':p['id'],'asset':aid}

from studio.integrations.quick_api import register as register_quick_api
from types import SimpleNamespace
register_quick_api(sys.modules.get(__name__) or SimpleNamespace(**globals()))
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.get('/')
def index():return RedirectResponse('http://127.0.0.1:'+os.environ.get('STUDIO_UI_PORT','4180'))
@app.get('/editor')
def editor(project:str=''):
    target='http://127.0.0.1:'+os.environ.get('STUDIO_UI_PORT','4180')
    return RedirectResponse(target+('/?page=workspace&project='+quote(project,safe='') if project else '/?page=workspace'))
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host=os.environ.get('STUDIO_BIND','127.0.0.1'),port=int(os.environ.get('PORT','4173')),access_log=False)

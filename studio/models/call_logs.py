"""Persistent model telemetry with allowlisted metadata and idempotent remote usage."""
import json,time,uuid,hashlib,math
from contextlib import contextmanager
from contextvars import ContextVar

_scope=ContextVar('studio_call_scope',default={})

def normalize_usage(payload):
    raw=payload.get('usage',{}) if isinstance(payload,dict) else {}
    if not isinstance(raw,dict):return {}
    out={}
    def number(key,value):
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:out[key]=value
    for dest,aliases in {'input_tokens':['input_tokens','prompt_tokens'],'output_tokens':['output_tokens','completion_tokens'],'total_tokens':['total_tokens'],'cached_tokens':['cache_read_input_tokens','cached_input_tokens'],'cache_write_tokens':['cache_creation_input_tokens']}.items():
        for key in aliases:
            if key in raw:number(dest,raw[key]);break
    for key in ('prompt_tokens_details','input_tokens_details'):
        details=raw.get(key,{})
        if isinstance(details,dict) and 'cached_tokens' in details:number('cached_tokens',details['cached_tokens'])
    for key in ('completion_tokens_details','output_tokens_details'):
        details=raw.get(key,{})
        if isinstance(details,dict) and 'reasoning_tokens' in details:number('reasoning_tokens',details['reasoning_tokens'])
    if 'total_tokens' not in out and ('input_tokens' in out or 'output_tokens' in out):out['total_tokens']=out.get('input_tokens',0)+out.get('output_tokens',0)
    for dest,aliases in {'images':['images','image_count','generated_images'],'video_seconds':['video_seconds','duration']}.items():
        for key in aliases:
            if key in raw:number(dest,raw[key]);break
    if 'duration' in payload and payload.get('status') in ('succeeded','done'):number('video_seconds',payload['duration'])
    return out

class CallLogs:
    def __init__(self,db,redact):
        self.db,self.redact=db,redact
        with db() as conn:
            conn.executescript('''CREATE TABLE IF NOT EXISTS model_calls(id TEXT PRIMARY KEY,created REAL,role TEXT,platform TEXT,model TEXT,project TEXT,job TEXT,operation TEXT,status TEXT,data TEXT);
CREATE INDEX IF NOT EXISTS model_calls_time ON model_calls(created);
CREATE TABLE IF NOT EXISTS model_usage(id TEXT PRIMARY KEY,call_id TEXT,usage TEXT);''')
            conn.execute("UPDATE model_calls SET status='interrupted' WHERE status='running'")
    @contextmanager
    def context(self,**values):
        token=_scope.set({**_scope.get(),**{k:v for k,v in values.items() if v}})
        try:yield
        finally:_scope.reset(token)
    def start(self,c,method,path,params=None):
        identity=uuid.uuid4().hex;scope=_scope.get();params=params or {}
        metadata={k:params[k] for k in ('duration','resolution','n','size') if isinstance(params.get(k),(int,float,str)) and len(str(params[k]))<60}
        metadata={k:self.redact(v) if isinstance(v,str) else v for k,v in metadata.items()}
        data={'method':method,'path':self.redact(path),'parameters':metadata}
        with self.db() as conn:conn.execute('INSERT INTO model_calls VALUES(?,?,?,?,?,?,?,?,?,?)',(identity,time.time(),self.redact(c.get('role','director')),self.redact(c.get('platform','')),self.redact(c.get('model','')),c.get('_log_project') or scope.get('project',''),c.get('_log_job') or scope.get('job',''),self.redact(path),'running',json.dumps(data)))
        return identity,time.monotonic()
    def finish(self,handle,c,status,payload=None,http_status=None,error='',request_id=''):
        identity,started=handle;payload=payload if isinstance(payload,dict) else {};usage=normalize_usage(payload)
        with self.db() as conn:
            row=conn.execute('SELECT data FROM model_calls WHERE id=?',(identity,)).fetchone();data=json.loads(row['data'])
            path=data['path'];method=data['method']
            is_remote='/contents/generations/tasks' in path or '/videos' in path
            remote_id=(payload.get('id') or payload.get('request_id')) if method=='POST' and is_remote else path.rsplit('/',1)[-1] if method=='GET' and is_remote else None
            if not usage and status=='succeeded' and method=='POST' and '/images/generations' in path and isinstance(payload.get('data'),list) and payload['data']:usage['images']=len(payload['data'])
            data.update(elapsed_ms=round((time.monotonic()-started)*1000),http_status=http_status,error=self.redact(error) if error else '',request_id=self.redact(str(request_id or payload.get('request_id') or '')),usage=usage,remote_id=self.redact(str(remote_id or '')),usage_counted=False)
            if usage:
                key=hashlib.sha256((c.get('platform','')+':'+c.get('base','')+':'+str(remote_id)).encode()).hexdigest() if remote_id else identity
                # Polls may return the same cumulative usage repeatedly. Replace, never add it again.
                previous=conn.execute('SELECT call_id,usage FROM model_usage WHERE id=?',(key,)).fetchone()
                ledger_usage={**(json.loads(previous['usage']) if previous else {}),**usage}
                if previous and previous['call_id']!=identity:
                    prior=conn.execute('SELECT data FROM model_calls WHERE id=?',(previous['call_id'],)).fetchone()
                    if prior:
                        prior_data=json.loads(prior['data']);prior_data['usage_counted']=False
                        conn.execute('UPDATE model_calls SET data=? WHERE id=?',(json.dumps(prior_data),previous['call_id']))
                conn.execute('INSERT OR REPLACE INTO model_usage VALUES(?,?,?)',(key,identity,json.dumps(ledger_usage)))
                data['usage_counted']=True
            conn.execute('UPDATE model_calls SET status=?,data=? WHERE id=?',(status,json.dumps(data),identity))
    def list(self,role='',platform='',status='',project='',model='',days=7,page=1,page_size=12):
        page=max(1,int(page));page_size=min(100,max(1,int(page_size)));conditions=[];args=[]
        for key,value in (('role',role),('platform',platform),('status',status),('project',project)):
            if value:conditions.append('c.'+key+'=?');args.append(value)
        if model:conditions.append('c.model LIKE ?');args.append('%'+model[:200]+'%')
        if days:conditions.append('c.created>=?');args.append(time.time()-min(max(int(days),1),3650)*86400)
        where=(' WHERE '+' AND '.join(conditions)) if conditions else ''
        with self.db() as conn:
            total=conn.execute('SELECT COUNT(*) FROM model_calls c'+where,args).fetchone()[0]
            failed=conn.execute('SELECT COUNT(*) FROM model_calls c'+where+(' AND ' if where else ' WHERE ')+"c.status='failed'",args).fetchone()[0]
            page=min(page,max(1,(total+page_size-1)//page_size))
            rows=conn.execute('SELECT c.* FROM model_calls c'+where+' ORDER BY c.created DESC LIMIT ? OFFSET ?',(*args,page_size,(page-1)*page_size)).fetchall()
            usage_rows=conn.execute('SELECT u.usage FROM model_usage u JOIN model_calls c ON c.id=u.call_id'+where,args).fetchall()
        totals={}
        for row in usage_rows:
            for key,value in json.loads(row['usage']).items():totals[key]=totals.get(key,0)+value
        items=[]
        for row in rows:
            entry=dict(row);entry.update(json.loads(entry.pop('data')));items.append(entry)
        return {'items':items,'total':total,'page':page,'page_size':page_size,'totals':totals,'failed':failed}

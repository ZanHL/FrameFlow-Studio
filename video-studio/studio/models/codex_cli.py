"""Official Codex CLI adapter. Never reads credentials or rewrites user configuration."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import re
import time
from pathlib import Path
from contextvars import ContextVar
LAST_USAGE=ContextVar('codex_usage',default=None)

class CodexError(RuntimeError):
    pass

def cli_path():
    return shutil.which('codex')

def cached_models():
    path=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'models_cache.json'
    try:
        payload=json.loads(path.read_text())
        if not isinstance(payload,dict):return []
        return [{'id':m['slug'],'name':m.get('display_name') or m['slug'],'vision':False} for m in payload.get('models',[]) if isinstance(m,dict) and isinstance(m.get('slug'),str) and len(m['slug'])<150][:100]
    except (OSError,ValueError,TypeError):
        return []

def clean_env():
    return {k:v for k,v in os.environ.items() if k not in ('OPENAI_API_KEY','CODEX_API_KEY','CODEX_ACCESS_TOKEN')}

def status():
    executable=cli_path()
    if not executable:return {'installed':False,'connected':False,'models':[],'message':'未找到 Codex CLI，请先安装官方 Codex CLI。'}
    try:
        result=subprocess.run([executable,'login','status'],capture_output=True,text=True,timeout=10,env=clean_env())
        connected=result.returncode==0
        return {'installed':True,'connected':connected,'models':cached_models(),'message':'已登录，可复用本机 Codex 认证。' if connected else '尚未登录，请完成 Codex 登录。'}
    except (OSError,subprocess.TimeoutExpired):
        return {'installed':True,'connected':False,'models':cached_models(),'message':'无法读取登录状态，请在终端运行 codex login status 检查。'}

def generate_text(text,model,timeout=300,reasoning='auto'):
    LAST_USAGE.set(None)
    executable=cli_path()
    if not executable:raise CodexError('未找到 Codex CLI，请先安装并登录。')
    with tempfile.TemporaryDirectory(prefix='studio-codex-') as directory:
        output=Path(directory)/'response.txt'
        command=[executable,'exec','--ignore-user-config','--skip-git-repo-check','--sandbox','read-only','--ephemeral','--json','--color','never','--disable','shell_tool','--disable','unified_exec','--disable','plugins','--disable','multi_agent','-c','approval_policy="never"','-c','web_search="disabled"','-m',model,'--output-last-message',str(output)]
        if reasoning!='auto':command+=['-c','model_reasoning_effort='+json.dumps(reasoning)]
        command+=['-']
        try:
            result=subprocess.run(command,input='只返回请求的最终文本，不使用工具、不读取文件、不运行命令。\n\n'+text,cwd=directory,env=clean_env(),capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:raise CodexError('Codex 请求超时，未自动重试。') from None
        except OSError:raise CodexError('无法启动本机 Codex CLI。') from None
        if result.returncode:
            diagnostic=(result.stderr or '').lower()
            if any(term in diagnostic for term in ('rate limit','quota','usage limit')):reason='账户额度或请求频率受限'
            elif any(term in diagnostic for term in ('unauthorized','not logged','authentication','401')):reason='登录已失效，请重新登录'
            elif any(term in diagnostic for term in ('model not','unsupported model','not supported')):reason='当前账户或登录方式不支持所选模型'
            elif any(term in diagnostic for term in ('network','connect','timed out')):reason='网络连接失败'
            else:reason='请检查登录状态、所选模型和账户额度'
            raise CodexError('Codex 调用失败：'+reason+'；未自动重试。')
        for line in (result.stdout or '').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if isinstance(event,dict) and event.get('type')=='thread.completed' and isinstance(event.get('usage'),dict):LAST_USAGE.set(event['usage'])
        value=output.read_text().strip() if output.exists() else ''
        if not value:raise CodexError('Codex 未返回最终文本，请检查模型和账户状态。')
        return value

_login_lock=threading.Lock()
_login_process=None
_login_view={}

def begin_login():
    """Start only on explicit UI action; never log out or replace existing credentials ourselves."""
    global _login_process,_login_view
    if status().get('connected'):return {'state':'connected'}
    with _login_lock:
        if _login_process and _login_process.poll() is None:return login_state()
        executable=cli_path()
        if not executable:raise CodexError('请先安装官方 Codex CLI。')
        _login_view={'state':'starting','started':time.time()}
        try:_login_process=subprocess.Popen([executable,'login','--device-auth'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=clean_env())
        except OSError:raise CodexError('无法启动官方 Codex 登录，请在终端检查 codex login。') from None
        process=_login_process
        def read():
            text=''
            for line in process.stdout:
                text=(text+re.sub(r'\x1b\[[0-9;]*m','',line))[-6000:]
                url=re.search(r'https://auth\.openai\.com/[^\s]+',text)
                code=re.search(r'\b[A-Z0-9]{4,6}-[A-Z0-9]{4,6}\b',text)
                if url:_login_view['url']=url.group(0)
                if code:_login_view['code']=code.group(0)
                if url and code:_login_view['state']='pending'
            _login_view['state']='connected' if process.wait()==0 else 'failed'
        threading.Thread(target=read,daemon=True).start()
        return dict(_login_view)

def login_state():
    return dict(_login_view)

def generate_image(text,model,timeout=600,reasoning='auto',references=None):
    """Use the authenticated CLI's built-in image generator and import its output."""
    LAST_USAGE.set(None)
    executable=cli_path()
    if not executable:raise CodexError('未找到 Codex CLI，请先安装并登录。')
    with tempfile.TemporaryDirectory(prefix='studio-codex-image-') as directory:
        root=Path(directory).resolve();output=root/'response.json'
        command=[executable,'exec','--ignore-user-config','--skip-git-repo-check','--sandbox','workspace-write','--ephemeral','--json','--color','never','--enable','image_generation','--disable','shell_tool','--disable','unified_exec','--disable','plugins','--disable','multi_agent','-c','approval_policy="never"','-c','web_search="disabled"','-m',model,'--output-last-message',str(output)]
        if reasoning!='auto':command+=['-c','model_reasoning_effort='+json.dumps(reasoning)]
        for index,reference in enumerate(references or []):
            target=root/f'reference-{index}.png';target.write_bytes(reference);command+=['--image',str(target)]
        command+=['-']
        instruction='使用内置 image_gen 图片生成工具生成一张图片，必须实际调用工具，不要用代码绘图。将结果保存到当前目录，或保留工具返回的原始图片路径。最终只返回 JSON：{"path":"图片的绝对路径"}。不运行命令，不读取无关文件。\n\n'+text
        try:result=subprocess.run(command,input=instruction,cwd=directory,env=clean_env(),capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:raise CodexError('Codex 图片生成超时，未自动重试。') from None
        except OSError:raise CodexError('无法启动本机 Codex CLI。') from None
        if result.returncode:raise CodexError('Codex 图片生成失败，请检查登录状态、模型和图片工具可用性；未自动重试。')
        for line in (result.stdout or '').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('type')=='thread.completed':LAST_USAGE.set(event.get('usage'))
        try:
            value=output.read_text().strip()
            if value.startswith('```'):value='\n'.join(value.splitlines()[1:-1])
            path=Path(json.loads(value)['path']).resolve()
            generated=(Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'generated_images').resolve()
            if not (path.is_relative_to(root) or path.is_relative_to(generated)) or path.is_symlink() or path.stat().st_size>25*1024*1024:raise ValueError()
            content=path.read_bytes()
            if not (content.startswith(b'\x89PNG\r\n\x1a\n') or content.startswith(b'\xff\xd8') or (content[:4]==b'RIFF' and content[8:12]==b'WEBP')):raise ValueError()
            return content
        except (OSError,ValueError,KeyError,TypeError):raise CodexError('Codex 未返回有效的生成图片，请检查图片工具是否可用。') from None

"""Streamlit front end for the local video studio."""
import os,time
from html import escape
from urllib.parse import quote
import requests
import streamlit as st
API=os.environ.get('STUDIO_API','http://127.0.0.1:4173')
st.set_page_config(page_title='映序 AI 视频创作工作室',page_icon='🎬',layout='wide')
st.markdown('''<style>
:root{--ink:#252b40;--accent:#6953c6} .stApp{background:#f6f7fb;color:var(--ink)}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid #e3e6ef}
.block-container{max-width:1450px;padding-top:2.8rem;padding-bottom:5rem}
h1{font-size:2.25rem!important;letter-spacing:-.06rem}h2{font-size:1.3rem!important}h3{font-size:1.05rem!important}
[data-testid="stVerticalBlockBorderWrapper"]>div{background:#fff;border-radius:12px}
[data-testid="stMetric"]{border-left:3px solid #8270d4;padding-left:18px}
.stButton button[kind="primary"]{background:#6953c6;border-color:#6953c6}
[data-testid="stSidebar"] .stRadio label{padding:9px 0}
[class*="st-key-asset-card-"] img{height:160px;object-fit:contain;width:100%}
[class*="st-key-asset-card-"] video{max-height:160px;width:100%}

[class*="st-key-project-card-"] [data-testid="stVerticalBlock"]:has(> [class*="st-key-delete-project:"]){position:relative}
[class*="st-key-delete-project:"]{position:absolute!important;top:8px;right:8px;width:34px!important;z-index:5}
[class*="st-key-delete-project:"] button{width:34px;min-height:34px;height:34px;padding:0;border:1px solid #e0e4ef;border-radius:9px;background:#ffffffed;color:#737d93;box-shadow:0 1px 3px #252b4010}
[class*="st-key-delete-project:"] button [data-testid="stMarkdownContainer"]{display:none}
[class*="st-key-delete-project:"] button:hover{color:#a52f42;border-color:#e3b6bf;background:#fff1f3}
[class*="st-key-delete-project:"] button:focus-visible{outline:2px solid #a52f42;outline-offset:3px}
[class*="st-key-project-card-"]{background:#fff;border:1px solid #e0e4ef!important;border-radius:14px!important}
[class*="st-key-project-card-"] [data-testid="stVerticalBlock"]{gap:12px}
[class*="st-key-project-card-"] video{height:180px!important;width:100%;object-fit:contain;background:#151a29;border-radius:8px}
[class*="st-key-project-card-"] [data-testid="stVideo"]{height:180px!important}
.project-placeholder{height:180px;border-radius:8px;background:#eef0f6;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:#8992a9;font-size:12px}
.project-play{width:42px;height:42px;border-radius:50%;border:1px solid #cbd1df;display:flex;align-items:center;justify-content:center;font-size:17px;padding-left:3px}
.project-info{height:54px;overflow:hidden}.project-title{font-size:16px;font-weight:650;color:#252b40;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:25px}
.project-meta{display:flex;justify-content:space-between;align-items:center;font-size:12px;line-height:24px;color:#7b8498;gap:8px}
.project-state{font-size:11px;color:#6953c6;background:#f0edfb;padding:0 8px;border-radius:4px;white-space:nowrap}


:root{--studio-surface:#fff;--studio-border:#e2e6ef;--studio-muted:#768096}
.block-container{padding-top:2rem;max-width:1450px}
h1{font-size:1.85rem!important;letter-spacing:-.035rem}
[data-testid="stMetric"]{border:0;padding:0}
[data-testid="stMetricValue"]{font-size:1.65rem}
[data-testid="stMetricLabel"]{color:var(--studio-muted);font-size:12px}
[class*="st-key-pagination-"]{border-top:1px solid var(--studio-border);padding-top:18px;margin-top:20px}
[class*="st-key-pagination-"] button{min-height:36px;font-size:13px;white-space:nowrap}
[class*="st-key-pagination-"] [data-testid="stCaptionContainer"] p{margin:0;font-size:12px}
[class*="st-key-project-card-"],[class*="st-key-asset-card-"]{box-shadow:none}
[class*="st-key-asset-card-"] .asset-name{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;height:24px}
[class*="st-key-asset-card-"] [data-testid="stImage"], [class*="st-key-asset-card-"] [data-testid="stVideo"]{height:160px}
.workspace-summary{display:flex;gap:28px;align-items:center;padding:12px 0 16px;border-bottom:1px solid var(--studio-border);margin-bottom:12px;font-size:12px;color:var(--studio-muted)}
.workspace-summary strong{font-size:15px;color:#252b40;margin-left:8px;font-weight:600}
@media(max-width:760px){.workspace-summary{gap:12px;flex-wrap:wrap}.block-container{padding-left:1rem;padding-right:1rem}[class*="st-key-pagination-"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap}}


[data-testid="stTabs"] [data-baseweb="tab-list"]{gap:24px;border-bottom:1px solid var(--studio-border);margin-bottom:20px}
[data-testid="stTabs"] [data-baseweb="tab"]{font-size:14px;padding:8px 2px 12px}
[class*="st-key-settings-"]{background:#fff;border-color:var(--studio-border)!important;border-radius:12px!important}
[class*="st-key-settings-"] [data-testid="stForm"]{border:0;padding:0}
.settings-state{display:inline-block;font-size:12px;line-height:24px;padding:0 9px;border-radius:5px;margin-bottom:10px}
.settings-state.ready{color:#26745b;background:#edf7f2}.settings-state.empty{color:#7b8498;background:#f0f2f6}
[class*="st-key-settings-material-"]{min-height:310px}
.stButton button:focus-visible,[data-testid="stFormSubmitButton"] button:focus-visible{outline:3px solid #bcb0ee;outline-offset:2px}

.stTextArea textarea{line-height:1.9}.stCaption{color:#777e92}
</style>''',unsafe_allow_html=True)

def api(path,method='GET',body=None,content=None,headers=None):
 try:
  r=requests.request(method,API+'/api'+path,json=body if content is None else None,data=content,headers={'X-Studio-Client':'1',**(headers or {})},timeout=1900 if path.endswith('/quick/script') else 200)
  r.raise_for_status();result=r.json()
  if method!='GET':
   if path.endswith('/refresh') or path.endswith('/refresh-3d'):
    status=result.get('status','') if isinstance(result,dict) else ''
    message='状态已刷新：'+{'submitted':'服务商仍在处理中，请稍后刷新','succeeded':'已完成，产物已保存','failed':'生成失败，请查看任务详情'}.get(status,status or '已更新')
   elif isinstance(result,dict) and result.get('id') and not result.get('name') and not result.get('mime'):message='任务已提交，请在制作任务区域查看进度与结果。'
   elif path.endswith('/test'):message='连接测试完成：'+str(result.get('message','连接成功'))
   elif path.endswith('/quick/script'):message='视频文案已生成，已填入旁白文案。'
   elif path.endswith('/quick/search'):message='素材搜索完成，请查看下方搜索结果。'
   elif path.endswith('/codex/login'):message='已启动官方登录流程，请完成验证。'
   elif '/confirm/' in path:message='本步已确认，已进入下一环节。'
   elif path.endswith('force-review'):message='已人工放行，原审核意见已保留。'
   elif path.endswith('cancel-repair'):message='已请求停止，当前模型调用结束后不再继续。'
   else:message='操作成功，内容已保存。'
   st.session_state['_action_feedback']=message
   st.toast(message,icon='✅')
  return result
 except requests.HTTPError:
  try:message=r.json().get('detail','操作失败')
  except ValueError:message='操作失败'
  raise RuntimeError(message)
 except requests.RequestException:raise RuntimeError('无法连接映序服务，请检查服务是否启动')
def do(fn):
 try:
  with st.spinner('处理中…'):return fn()
 except Exception as e:
  st.session_state.pop('_action_feedback',None)
  st.toast('操作未完成：'+str(e),icon='⚠️');st.error(str(e));return None

def paginate(items,key,show_controls=True):
 total=len(items);page_key=key+':page';size_key=key+':size'
 size=st.session_state.get(size_key,6)
 pages=max(1,(total+size-1)//size)
 if st.session_state.get(page_key,1)>pages:st.session_state[page_key]=pages
 if show_controls:
  def move(delta):st.session_state[page_key]=max(1,min(pages,st.session_state.get(page_key,1)+delta))
  def reset_page():st.session_state[page_key]=1
  with st.container(key='pagination-'+key.replace(':','-')):
   count,per,prev,current,next_col=st.columns([3,1.5,1,1.3,1],vertical_alignment='center')
   page=st.session_state.get(page_key,1)
   count.caption(f'共 {total} 项　/　第 {page} 页，共 {pages} 页')
   per.selectbox('每页数量',[6,12,24],key=size_key,format_func=lambda n:f'{n} 项 / 页',label_visibility='collapsed',on_change=reset_page)
   prev.button('上一页',key=key+':prev',disabled=page<=1,on_click=move,args=(-1,),use_container_width=True)
   current.number_input('页码',min_value=1,max_value=pages,step=1,key=page_key,label_visibility='collapsed')
   next_col.button('下一页',key=key+':next',disabled=page>=pages,on_click=move,args=(1,),use_container_width=True)
 page=st.session_state.get(page_key,1)
 return items[(page-1)*size:page*size]

def upload(file,kind):
 if file is None:return None
 import hashlib
 key='upload:'+kind+hashlib.sha256(file.getvalue()).hexdigest()
 if key not in st.session_state:
  mime={'mp4':'video/mp4','mp3':'audio/mpeg','wav':'audio/wav'}[file.name.rsplit('.',1)[-1].lower()]
  st.session_state[key]=api('/quick/upload?kind='+kind,'POST',content=file.getvalue(),headers={'Content-Type':mime,'X-File-Name':quote(file.name)})['id']
 return st.session_state[key]

boot=do(lambda:api('/bootstrap'))
if not boot:st.stop()
if st.session_state.get('_action_feedback'):st.success(st.session_state.pop('_action_feedback'))
if st.query_params.get('page')=='workspace':
 st.session_state['page']='分镜工作区'
 st.query_params.pop('page',None)
if st.query_params.get('project'):
 st.session_state['workspace_project']=st.query_params['project']
 st.session_state['page']='分镜工作区'
 st.query_params.pop('project',None)
with st.sidebar:
 st.title('◧ 映序')
 st.caption('把创意留给你，把制作交给映序。')
 navigation=['项目总览','分镜工作区','素材与版本','调用日志','设置']
 requested_page=st.query_params.get('page')
 if requested_page in ('settings','logs','overview'):
  st.session_state['page']={'settings':'设置','logs':'调用日志','overview':'项目总览'}[requested_page];st.query_params.pop('page',None)
 current=st.session_state.get('page','项目总览')
 st.session_state['navigation']=current if current in navigation else '项目总览'
 def change_page():st.session_state['page']=st.session_state['navigation']
 st.radio('工作空间',navigation,label_visibility='collapsed',key='navigation',index=None,on_change=change_page)
 page=st.session_state.get('page','项目总览')
 st.divider();st.caption('本机工作空间')

# Preserve the quick draft when Streamlit removes inactive-page widget state.
if st.session_state.get('_last_page')=='快速生成视频':
 for field in ('quick_topic','quick_script','quick_terms','quick_ratio'):
  if field in st.session_state:st.session_state['_draft:'+field]=st.session_state[field]
if page=='快速生成视频':
 for field in ('quick_topic','quick_script','quick_terms','quick_ratio'):
  if field not in st.session_state and '_draft:'+field in st.session_state:st.session_state[field]=st.session_state['_draft:'+field]
st.session_state['_last_page']=page

ROLES={'director':'总导演 / 分镜审核','artist':'画师','animator':'动画师','modeler':'3D 素材师'}
VOICES={'晓晓 · 女声':'zh-CN-XiaoxiaoNeural-Female','云希 · 男声':'zh-CN-YunxiNeural-Male','晓伊 · 女声':'zh-CN-XiaoyiNeural-Female','Jenny · English':'en-US-JennyNeural-Female'}
if page=='设置':
 st.title('设置');st.caption('为每个创作角色连接模型，管理素材服务与默认制作偏好。')
 def saved(action):
  if do(action) is not None:st.rerun(scope='app')
 def state_label(ready):
  st.markdown('<span class="settings-state '+('ready' if ready else 'empty')+'">'+('已配置' if ready else '待配置')+'</span>',unsafe_allow_html=True)
 tabs=st.tabs(['模型与连接','素材服务','配音与字幕','提示词'])
 with tabs[0]:
  st.subheader('角色模型');st.caption('快速生成和自定义分镜共用角色配置，每个角色独立保存。')
  role=st.segmented_control('创作角色',list(ROLES),format_func=lambda r:ROLES[r],default='director') or 'director'
  cfg=boot['models'].get(role,{})
  editor,guide=st.columns([2,1],gap='large')
  with editor:
   if st.session_state.get('_model_test_feedback'):st.success(st.session_state.pop('_model_test_feedback'))
   with st.container(border=True,key='settings-model'):
    providers={k:v for k,v in boot['catalog'].items() if v.get('models',{}).get(role)}
    choices=list(providers);default=cfg.get('platform') if cfg.get('platform') in choices else choices[0]
    st.subheader(ROLES[role])
    provider=st.selectbox('服务平台',choices,index=choices.index(default),format_func=lambda k:providers[k].get('name',k),key='provider:'+role)
    selected_platform=providers[provider];is_cli=selected_platform.get('auth')=='cli';is_custom=selected_platform.get('custom_endpoint',False)
    cli_state=do(lambda:api('/models/codex/status')) if is_cli else None
    if is_cli:state_label(bool(cli_state and cli_state.get('connected')))
    else:state_label(bool(cfg.get('has_key') and cfg.get('platform')==provider))
    options_key='model-options:'+role+provider+cfg.get('base','')
    models=list(selected_platform['models'][role]);seen={m['id'] for m in models}
    extras=(cli_state or {}).get('models',[]) if is_cli else []
    extras=extras+[{'id':m,'name':m} for m in st.session_state.get(options_key,[])]
    for m in extras:
     if m['id'] not in seen:models.append(m);seen.add(m['id'])
    ids=[m['id'] for m in models]
    manual=st.toggle('手动填写模型 ID',value=is_custom or (cfg.get('platform')==provider and cfg.get('model') not in ids),key='manual-model:'+role+provider) if role=='director' or is_cli else False
    if manual:model=st.text_input('模型 ID',value=cfg.get('model','') if cfg.get('platform')==provider else '',placeholder='填写平台可用的模型 ID 或接入点',key='custom-model:'+role+provider)
    else:model=st.selectbox('模型',ids,index=ids.index(cfg['model']) if cfg.get('model') in ids else 0,format_func=lambda k:next((m.get('name',k) for m in models if m['id']==k),k),key='model:'+role+provider)
    if is_cli:
     st.caption('复用官方 Codex CLI 的本机登录，不需要填写 API Key。' + ('使用本机 Codex 内置图片工具生成图片。' if role=='artist' else '用于文字创作与分镜。') + '')
     @st.fragment(run_every='3s')
     def codex_auth_panel():
      state=do(lambda:api('/models/codex/status'))
      if not state:return
      st.caption(state['message'])
      if not state.get('connected'):
       if st.button('使用 ChatGPT 登录 Codex',disabled=not state.get('installed'),key='codex-login'):
        if do(lambda:api('/models/codex/login','POST',{})):st.rerun(scope='app')
       login=state.get('login',{})
       if login.get('state')=='starting':st.info('正在获取设备登录码…')
       if login.get('url'):st.link_button('打开官方登录页面',login['url'])
       if login.get('code'):st.code(login['code'],language=None)
       if login.get('state')=='failed':st.warning('登录未完成，请重新尝试，或在终端运行 codex login。')
      st.caption('也可在终端运行 codex login；登录信息由官方客户端管理。')
     codex_auth_panel()
    with st.form('settings-model-form:'+role+provider):
     base=st.text_input('兼容接口地址',value=cfg.get('base','') if cfg.get('platform')==provider else '',placeholder='https://你的服务商/v1') if is_custom else selected_platform['base']
     key=st.text_input('API Key',type='password',key='key:'+role+provider,placeholder='留空保留已保存密钥' if cfg.get('has_key') and provider==cfg.get('platform') else '填写当前平台的 API Key') if not is_cli else ''
     if not is_cli:st.caption('密钥保存在 macOS 钥匙串，重启后继续使用。')
     rate=st.number_input('预算单价（元 / 秒）',min_value=0.,value=float(cfg.get('rate',0)),step=.01,key='rate:'+role+provider) if role=='animator' else 0
     timeout=300;reasoning='auto';transport=None
     if role=='director' or is_cli:
      with st.expander('调用参数',expanded=False):
       timeout=st.number_input('请求超时（秒）',30,1800,int(cfg.get('timeout',300)),30,key='timeout:'+role+provider)
       if is_cli or selected_platform['protocol']=='responses':reasoning=st.selectbox('推理强度',['auto','low','medium','high','xhigh'],index=['auto','low','medium','high','xhigh'].index(cfg.get('reasoning','auto')),format_func=lambda x:'自动' if x=='auto' else x,key='reasoning:'+role+provider)
       if selected_platform['protocol'] in ('compatible','responses'):
        default_api=next((m.get('api',selected_platform['protocol']) for m in models if m['id']==model),selected_platform['protocol'])
        transport=st.selectbox('接口协议',['auto','compatible','responses'],index=0,format_func=lambda x:{'auto':'自动匹配模型','compatible':'Chat Completions','responses':'Responses'}[x],key='api:'+role+provider)
        if transport=='auto':transport=cfg.get('protocol',default_api) if is_custom and cfg.get('platform')==provider else default_api
     if st.form_submit_button('保存模型配置',type='primary',use_container_width=True):saved(lambda:api('/models/'+role,'POST',{'platform':provider,'model':model,'key':key,'rate':rate,'base':base,'custom_model':manual or model not in [m['id'] for m in selected_platform['models'][role]],'api':transport,'timeout':timeout,'reasoning':reasoning}))
    ready=bool(cfg.get('model') and cfg.get('platform')==provider and (cfg.get('has_key') or is_cli))
    if st.button('测试已保存连接',use_container_width=True,disabled=not ready):
     result=do(lambda:api('/models/'+role+'/test','POST',{}))
     if result:
      st.session_state[options_key]=[m for m in result.get('models',[]) if isinstance(m,str) and len(m)<200][:1000]
      if result.get('connected'):
       st.session_state['_model_test_feedback']=result['message'];st.rerun(scope='app')
      else:st.warning(result['message'])
    st.caption('测试连接会读取已保存平台的模型列表；重新打开模型下拉框即可选择。模型实际权限以服务商响应为准。')
    if not is_cli:
     with st.expander('密钥管理',expanded=False):
      st.caption('清除当前所选平台的密钥后，需要重新配置才能调用。')
      if st.button('清除当前平台 Key',disabled=not cfg.get('has_key') or cfg.get('platform')!=provider):saved(lambda:api('/models/'+role,'POST',{'platform':provider,'model':model,'clear_key':True,'rate':rate,'base':base,'custom_model':manual or cfg.get('custom_model',False),'timeout':timeout,'api':transport}))
  with guide:
   st.write('**角色职责**')
   st.write({'director':'完善故事、设计分镜、编写提示词，也用于快速生成视频文案。','artist':'生成画风样张、角色设定，以及每个镜头的首尾帧。','animator':'根据镜头首尾帧和提示词生成视频片段。','modeler':'将参考图片转换为可下载的 3D 素材。'}[role])
   st.divider();st.write('**连接信息**');st.caption('接口根据平台自动匹配，无需填写地址。');st.code('官方 Codex CLI · 本机认证' if is_cli else base or '自定义 HTTPS 接口',language=None,wrap_lines=True)
   st.caption('先保存配置，再测试连接。测试使用已保存的模型与密钥。')
 with tabs[1]:
  settings=api('/quick/settings')
  st.subheader('素材来源');st.caption('连接素材平台后，可在快速项目中搜索和匹配视频。每个平台单独保存。')
  columns=st.columns(3)
  for col,provider,label,description in [(columns[0],'pexels','Pexels','按关键词搜索视频素材'),(columns[1],'pixabay','Pixabay','为文案匹配视频片段'),(columns[2],'coverr','Coverr','搜索可用于创作的视频')]:
   with col:
    with st.container(border=True,key='settings-material-'+provider):
     st.subheader(label);state_label(settings['keys'][provider]);st.caption(description)
     with st.form('material-form:'+provider):
      k=st.text_input(label+' API Key',type='password',key='material:'+provider,placeholder='留空保留已保存密钥')
      if st.form_submit_button('保存 '+label,type='primary',use_container_width=True):saved(lambda:api('/quick/settings','POST',{'keys':{provider:k}}))
     if st.button('清除 Key',key='clear:'+provider,disabled=not settings['keys'][provider],use_container_width=True):saved(lambda:api('/quick/settings','POST',{'keys':{provider:None}}))
  st.caption('素材 Key 保存到本机钥匙串；使用本地素材时无需配置素材平台。')
 with tabs[2]:
  cfg=api('/quick/settings');st.subheader('默认配音与字幕');st.caption('为新项目设置默认值，项目中已保存的参数优先使用。两部分可分别保存。')
  audio_col,subtitle_col=st.columns(2,gap='large')
  with audio_col:
   with st.container(border=True,key='settings-voice'):
    st.subheader('配音偏好')
    with st.form('voice-settings'):
     voice=st.selectbox('默认声音',list(VOICES.values()),index=list(VOICES.values()).index(cfg['voice_name']) if cfg['voice_name'] in VOICES.values() else 0,format_func=lambda v:next(k for k,x in VOICES.items() if x==v))
     rate=st.slider('默认语速',.5,2.,float(cfg['voice_rate']),.05)
     st.caption('1.0 为正常速度，项目内可单独调整。')
     if st.form_submit_button('保存配音设置',type='primary',use_container_width=True):saved(lambda:api('/quick/settings','POST',{'voice_name':voice,'voice_rate':rate}))
  with subtitle_col:
   with st.container(border=True,key='settings-subtitles'):
    st.subheader('字幕识别')
    subtitle=st.radio('字幕生成方式',['edge','whisper'],index=0 if cfg['subtitle_provider']=='edge' else 1,format_func=lambda x:'配音时间戳' if x=='edge' else 'Whisper 本地识别',horizontal=True)
    with st.form('subtitle-settings'):
     model=st.selectbox('Whisper 模型',['tiny','base','small','medium','large-v3'],index=['tiny','base','small','medium','large-v3'].index(cfg['whisper_model_size']),disabled=subtitle!='whisper')
     st.caption('轻量快速，使用配音时间戳生成字幕。' if subtitle=='edge' else 'CPU / int8 本地识别，首次需要下载模型；较大模型占用更多内存。')
     if st.form_submit_button('保存字幕设置',type='primary',use_container_width=True):saved(lambda:api('/quick/settings','POST',{'subtitle_provider':subtitle,'whisper_model_size':model}))
 with tabs[3]:
  st.subheader('提示词模板');st.caption('按制作用途独立维护，保存后用于后续模型调用。')
  selector,editor=st.columns([1,2.5],gap='large')
  with selector:
   names=list(boot['prompts']);name=st.selectbox('提示词用途',names,format_func=lambda k:boot['prompts'][k]['name'])
   st.write('**可用变量**')
   st.code('{{idea}}      创意与主题\n{{duration}}  目标片长\n{{ratio}}     视频画幅\n{{style}}     画风设定',language=None)
   st.caption('保留变量占位符，调用时会替换为项目中的实际内容。')
  with editor:
   with st.container(border=True,key='settings-prompts'):
    with st.form('prompt-form:'+name):
     value=st.text_area('提示词模板',boot['prompts'][name]['value'],height=390,key='prompt:'+name)
     if st.form_submit_button('保存提示词',type='primary',use_container_width=True):saved(lambda:api('/prompts/'+name,'POST',{'value':value}))


elif page=='调用日志':
 from studio.ui.call_logs import render as render_call_logs
 render_call_logs(api,do,boot,ROLES)

elif page=='快速生成视频':
 pid=st.session_state.get('quick_project')
 project=next((p for p in boot['projects'] if p['id']==pid and p.get('mode')=='quick'),None)
 if not project:
  st.info('请在项目总览创建快速生成项目。');st.stop()
 from studio.ui.editor_navigation import render as render_editor_navigation
 render_editor_navigation(pid,project['name'],'快速生成视频',[('文案编辑','quick-script'),('画面素材','quick-materials'),('生成参数','quick-parameters'),('生成结果','quick-results')])
 if st.session_state.get('_quick_loaded')!=pid:
  for field in ('quick_topic','quick_script','quick_terms','quick_ratio'):
   st.session_state.pop(field,None);st.session_state.pop('_draft:'+field,None)
  saved=project.get('last_video_inputs',project.get('quick_inputs',project.get('quick_params',{})))
  st.session_state.update(quick_topic=saved.get('video_subject',project.get('idea','')),quick_script=saved.get('video_script',project.get('story','')),quick_terms=saved.get('video_terms',''),quick_ratio=saved.get('video_aspect',project.get('ratio','9:16')),_quick_loaded=pid)
 cfg=api('/quick/settings')
 saved=project.get('last_video_inputs',project.get('quick_inputs',project.get('quick_params',{})))
 st.caption('已恢复上一次提交生成时的内容与参数。' if project.get('last_video_inputs') else '编辑已保存的项目内容。')
 def q(field,default):
  key='quick-param:'+pid+':'+field
  if key not in st.session_state:st.session_state[key]=saved.get(field,default)
  return key
 st.title(project['name']);st.caption('快速生成视频 · 编辑文案、选择素材与声音，完成后直接合成。')
 left,right=st.columns([1.65,1],gap='large')
 with left:
  with st.container(border=True):
   st.subheader('文案工作台',anchor='quick-script')
   topic_col,duration_col=st.columns([3,1])
   topic=topic_col.text_input('视频主题',placeholder='例如：每天走路半小时，会发生什么？',key='quick_topic')
   duration=duration_col.selectbox('目标片长',[15,30,45,60,90,120],format_func=lambda n:str(n)+' 秒',key=q('target_duration',30))
   if not topic:st.caption('先填写视频主题，才能生成文案。')
   if st.button('生成视频文案',disabled=not topic):
    result=do(lambda:api('/quick/script','POST',{'topic':topic,'duration':duration,'project':pid}))
    if result:st.session_state['quick_script']=result['script']
   script=st.text_area('旁白文案',height=170,key='quick_script',placeholder='直接粘贴文案，或根据主题生成。')
   st.caption('保存时，项目名称会自动与视频主题同步。')
   st.caption(f'{len(script)} 字 · 约 {max(1,round(len(script)/4))} 秒朗读')
  with st.container(border=True):
   st.subheader('画面素材',anchor='quick-materials')
   provider=st.segmented_control('素材来源',['pexels','pixabay','coverr','local'],format_func=lambda x:{'local':'本地素材','pexels':'Pexels','pixabay':'Pixabay','coverr':'Coverr'}[x],key=q('video_source','pexels')) or 'pexels'
   terms=st.text_input('素材关键词',placeholder='例如 walking, park, healthy lifestyle',key='quick_terms')
   files=[]
   if provider=='local':
    files=st.file_uploader('上传视频片段',type=['mp4'],accept_multiple_files=True,key='quick-files:'+pid+':'+str(st.session_state.get('quick-upload-version:'+pid,0)))
    if saved.get('materials'):st.caption(f'已保存 {len(saved["materials"])} 个本地片段；不上传新文件将继续使用。')
   else:
    if st.button('搜索素材',disabled=not terms):
     result=do(lambda:api('/quick/search','POST',{'provider':provider,'query':terms,'ratio':st.session_state.get('quick_ratio','9:16')}))
     if result is not None:st.session_state['search_results']=result;st.session_state['search_provider']=provider
    if st.session_state.get('search_provider')==provider:
     results=st.session_state.get('search_results',[])
     if not results:st.caption('没有找到素材，可换一组关键词再试。')
     for i,item in enumerate(results[:6]):
      with st.expander(f'素材 {i+1} · {item.get("duration",0)} 秒'):
       st.video(item['url']);st.caption('搜索用于预览；生成时按当前关键词自动匹配片段。')
 with right:
  with st.container(border=True):
   st.subheader('生成参数',anchor='quick-parameters')
   st.write('**输出规格**')
   a,b=st.columns(2)
   ratio=a.selectbox('画幅',['9:16','16:9','1:1'],key='quick_ratio')
   count=b.number_input('生成数量',1,3,key=q('video_count',1))
   st.write('**配音与音乐**')
   a,b=st.columns(2)
   audio_mode=a.selectbox('配音方式',['文字配音','上传配音'],key=q('audio_mode','文字配音'))
   voice=b.selectbox('配音声音',list(VOICES.values()),format_func=lambda v:next(k for k,x in VOICES.items() if x==v),key=q('voice_name',cfg['voice_name'] if cfg['voice_name'] in VOICES.values() else next(iter(VOICES.values()))))
   audio=st.file_uploader('上传配音音频',type=['mp3','wav'],key='quick-audio:'+pid+':'+str(st.session_state.get('quick-upload-version:'+pid,0))) if audio_mode=='上传配音' else None
   if audio_mode=='上传配音' and saved.get('audio'):st.caption('已保存配音音频；不上传新文件将继续使用。')
   a,b=st.columns(2)
   bgm=a.selectbox('背景音乐',['不使用','随机音乐','上传音乐'],key=q('bgm_label',{'':'不使用','random':'随机音乐','custom':'上传音乐'}.get(saved.get('bgm_type',''),'不使用')))
   volume=b.slider('背景音乐音量',0,100,key=q('bgm_percent',int(saved.get('bgm_volume',.2)*100)))
   music=st.file_uploader('上传背景音乐',type=['mp3','wav'],key='quick-music:'+pid+':'+str(st.session_state.get('quick-upload-version:'+pid,0))) if bgm=='上传音乐' else None
   if bgm=='上传音乐' and saved.get('music'):st.caption('已保存背景音乐；不上传新文件将继续使用。')
   subtitles=st.toggle('启用字幕',key=q('subtitle_enabled',True))
   if st.button('生成配音试听',disabled=not script or not topic.strip(),width='stretch'):st.session_state['preview_requested']=True
   with st.expander('声音参数',expanded=False):
    rate=st.slider('语速',.5,2.,step=.05,key=q('voice_rate',float(cfg['voice_rate'])))
   with st.expander('画面与转场',expanded=False):
    fit=st.selectbox('画面适配',['cover','contain'],format_func=lambda x:'居中裁切，铺满画面' if x=='cover' else '完整画面，保留边距',key=q('video_fit_mode','cover'))
    transition=st.selectbox('转场',[None,'FadeIn','FadeOut','SlideIn','SlideOut','ZoomIn','ZoomOut','Shuffle'],format_func=lambda x:{None:'直接切换','FadeIn':'淡入','FadeOut':'淡出','SlideIn':'滑入','SlideOut':'滑出','ZoomIn':'推近','ZoomOut':'拉远','Shuffle':'随机转场'}[x],key=q('video_transition_mode',None))
    clip=st.slider('单片段最长时长（秒）',1,30,key=q('video_clip_duration',5))
    concat=st.radio('拼接顺序',['random','sequential'],format_func=lambda x:'随机组合' if x=='random' else '按素材顺序',horizontal=True,key=q('video_concat_mode','random'))
   with st.expander('字幕排版',expanded=False):
    st.caption('识别方式：'+('Whisper 本地识别' if cfg['subtitle_provider']=='whisper' else '配音时间戳'))
    position=st.selectbox('字幕位置',['bottom','center','top'],format_func=lambda x:{'bottom':'底部','center':'居中','top':'顶部'}[x],key=q('subtitle_position','bottom'))
    font=st.slider('字幕字号',20,100,key=q('font_size',60))
    color=st.color_picker('文字颜色',key=q('text_fore_color','#FFFFFF'))
    display=st.selectbox('显示方式',['sentence','word_by_word'],format_func=lambda x:'整句' if x=='sentence' else '逐词',key=q('subtitle_display_mode','sentence'))
 preview=st.session_state.pop('preview_requested',False)
 if not script:st.info('填写或生成旁白文案后，即可开始生成视频。')
 generate=st.button('开始生成视频',type='primary',use_container_width=True,disabled=not script or not topic.strip())
 save_draft=st.button('保存项目内容',use_container_width=True,disabled=not topic.strip())
 if generate or preview or save_draft:
  def submit():
   params={'project':pid,'target_duration':duration,'audio_mode':audio_mode,'video_subject':topic or script[:80],'video_script':script,'video_terms':terms or topic,'video_source':provider,'video_aspect':ratio,'video_fit_mode':fit,'video_transition_mode':transition,'video_clip_duration':clip,'video_concat_mode':concat,'video_count':count,'voice_name':voice,'voice_rate':rate,'subtitle_enabled':subtitles,'subtitle_position':position,'subtitle_display_mode':display,'font_size':font,'text_fore_color':color,'bgm_type':{'不使用':'','随机音乐':'random','上传音乐':'custom'}[bgm],'bgm_volume':volume/100,'preview':preview}
   if files:params['materials']=[upload(f,'video') for f in files]
   elif saved.get('materials'):params['materials']=saved['materials']
   if audio:params['audio']=upload(audio,'audio')
   elif audio_mode=='上传配音' and saved.get('audio'):params['audio']=saved['audio']
   if music:params['music']=upload(music,'music')
   elif bgm=='上传音乐' and saved.get('music'):params['music']=saved['music']
   return api('/projects/'+pid+'/quick-draft' if save_draft else '/quick/generate','POST',params)
  if do(submit):
   st.session_state['_action_feedback']='项目已保存，名称已与视频主题同步。' if save_draft else '任务已提交，项目名称已与视频主题同步。'
   st.rerun(scope='app')
 st.divider();st.subheader('生成结果',anchor='quick-results')
 @st.fragment(run_every='3s')
 def jobs_panel():
  jobs=api('/quick/jobs?project='+pid)
  if not jobs:st.caption('提交生成后，任务状态与视频会显示在这里。')
  for job in jobs[:5]:
   data=job['data'];status=job['status']
   label={'queued':'等待制作','running':'正在制作','succeeded':'已完成','failed':'失败','interrupted':'中断'}.get(status,status)
   with st.expander(data.get('subject','快速生成')+' · '+label,expanded=status in ('running','failed')):
    if status in ('queued','running'):st.status('正在制作，完成后自动更新预览…',state='running')
    if data.get('error'):st.error(data['error'])
    for output in data.get('outputs',[]):
     url=API+output['url']
     if url.endswith('.mp4'):st.video(url)
     elif url.endswith(('.mp3','.wav')):st.audio(url)
     st.link_button('下载 '+output['name'],url)
 jobs_panel()

elif page=='分镜工作区':
 from storyboard_ui import render as render_workspace
 render_workspace(api,do,API,{**boot,'projects':[p for p in boot['projects'] if p.get('mode','custom')=='custom']})
elif page=='项目总览':
 header,action=st.columns([4,1],vertical_alignment='center')
 header.title('项目总览')
 st.caption('统一管理快速生成与自定义分镜项目，查看制作进度和成片。')
 def close_creation_dialog():st.session_state['_create_dialog_open']=False
 @st.dialog('创建视频项目',width='large',on_dismiss=close_creation_dialog)
 def create_project_dialog():
  st.write('选择视频创建路径')
  mode=st.radio('制作方式',['quick','custom'],format_func=lambda m:'快速生成视频' if m=='quick' else '自定义',horizontal=True,key='create-mode')
  st.caption('快速生成：填写文案、选择素材与配音，直接合成视频。' if mode=='quick' else '自定义：从故事与分镜开始，逐镜生成首尾帧和视频，最后合成。')
  with st.form('create-project'):
   name=st.text_input('项目名称');idea=st.text_area('视频主题' if mode=='quick' else '创意 / 故事想法',height=100)
   submit,cancel=st.columns(2)
   created_clicked=submit.form_submit_button('创建并进入',type='primary',use_container_width=True)
   cancelled=cancel.form_submit_button('取消',use_container_width=True)
   if cancelled:
    close_creation_dialog();st.rerun(scope='app')
   if created_clicked:
    created=do(lambda:api('/projects','POST',{'name':name,'idea':idea,'mode':mode}))
    if created:
     close_creation_dialog()
     if mode=='quick':st.session_state['quick_project']=created['id'];st.session_state['page']='快速生成视频'
     else:st.session_state['workspace_project']=created['id'];st.session_state['page']='分镜工作区'
     st.rerun(scope='app')
 if action.button('＋ 创建项目',type='primary',use_container_width=True,key='create-project-open'):st.session_state['_create_dialog_open']=True
 if st.session_state.get('_create_dialog_open'):create_project_dialog()
 a,b=st.columns(2);a.metric('全部项目',len(boot['projects']));b.metric('已生成成片',sum(bool(p.get('final_video') or p.get('export_asset')) for p in boot['projects']))
 def open_project(project_id,mode):
  if mode=='quick':
   st.session_state['quick_project']=project_id;st.session_state['page']='快速生成视频'
   st.session_state['_quick_loaded']=None
   for key in list(st.session_state):
    if key.startswith('quick-param:'+project_id+':'):del st.session_state[key]
   st.session_state['quick-upload-version:'+project_id]=st.session_state.get('quick-upload-version:'+project_id,0)+1
  else:st.session_state['workspace_project']=project_id;st.session_state['page']='分镜工作区'
 @st.dialog('删除项目')
 def delete_project_dialog(project_id,project_name):
  st.write('确定删除「'+project_name+'」？')
  st.warning('将永久删除项目、项目素材和制作记录，无法恢复。已下载的文件不受影响。')
  cancel,confirm=st.columns(2)
  if cancel.button('取消',key='delete-cancel',use_container_width=True):st.rerun(scope='app')
  if confirm.button('确认删除',key='delete-confirm',type='primary',use_container_width=True):
   result=do(lambda:api('/projects/'+project_id,'DELETE'))
   if result:
    for key in ('workspace_project','quick_project','_quick_loaded'):
     if st.session_state.get(key)==project_id:st.session_state.pop(key,None)
    st.session_state['_action_feedback']='项目「'+project_name+'」已删除'
    st.rerun(scope='app')
 @st.fragment(run_every='3s')
 def project_cards():
  filters=st.columns([3,1])
  search=filters[0].text_input('搜索项目',placeholder='搜索项目名称或主题',label_visibility='collapsed')
  mode=filters[1].selectbox('项目类型',['全部项目','快速生成','自定义分镜'],label_visibility='collapsed')
  all_projects=[p for p in api('/bootstrap')['projects'] if (not search or search.lower() in (p['name']+' '+p.get('idea','')).lower()) and (mode=='全部项目' or (p.get('mode')=='quick')==(mode=='快速生成'))]
  projects=paginate(all_projects,'projects',show_controls=False)
  columns=st.columns(3)
  for i,p in enumerate(projects):
   with columns[i%3]:
    with st.container(border=True,height=350,key='project-card-'+p['id']):
     if st.button('删除项目',icon=':material/delete:',help='删除项目',key='delete-project:'+p['id']):delete_project_dialog(p['id'],p['name'])
     is_quick=p.get('mode')=='quick'
     final=p.get('export_asset') or p.get('final_video')
     status='已有成片' if final else '待开始'
     if not final and is_quick:
      jobs=api('/projects/'+p['id']+'/activity')['jobs']
      if jobs:status={'running':'正在制作','queued':'等待制作','failed':'制作失败','succeeded':'已完成','interrupted':'制作中断'}.get(jobs[0]['status'],'待开始')
     elif not final:
      completed=sum(bool(p['confirmed'].get(str(i))) for i in range(7))
      if completed:status=f'制作进度 {completed}/7'
     if final:st.video(API+'/media/'+final)
     else:st.markdown('<div class="project-placeholder"><span class="project-play" aria-hidden="true">▶</span><span>生成后在此预览视频</span></div>',unsafe_allow_html=True)
     name=escape(p['name'],quote=True);kind='快速生成' if is_quick else '自定义分镜'
     st.markdown(f'<div class="project-info"><div class="project-title" title="{name}">{name}</div><div class="project-meta"><span>{kind} / {escape(p["ratio"])}</span><span class="project-state">{status}</span></div></div>',unsafe_allow_html=True)
     edit,download=st.columns([1.3,1])
     if edit.button('编辑项目',key='open-workspace:'+p['id'],use_container_width=True):
      open_project(p['id'],p.get('mode','custom'));st.rerun(scope='app')
     if final:download.link_button('下载成片',API+'/media/'+final,use_container_width=True)
     else:download.button('暂无成片',key='no-final:'+p['id'],disabled=True,use_container_width=True)

  if not projects:st.info('没有符合条件的项目，可调整筛选或创建新项目。')
  paginate(all_projects,'projects')
 project_cards()

else:
 st.title('素材与版本');st.caption('集中预览、下载并管理项目的图片、视频与音频素材。')
 projects=boot['projects']
 if not projects:st.info('创建项目或生成第一部视频后，这里会展示素材。')
 else:
  project_filter,type_filter=st.columns([2,1])
  pid=project_filter.selectbox('项目',[p['id'] for p in projects],format_func=lambda x:next(p['name'] for p in projects if p['id']==x))
  activity=api('/projects/'+pid+'/activity')
  from storyboard_ui import asset_tools
  with st.expander('素材上传与 3D 工具',expanded=False):asset_tools(api,do,API,pid,activity)
  filter_kind=type_filter.selectbox('显示类型',['全部','图片','视频','音频','成片','3D'])
  def matches(asset):
   return filter_kind=='全部' or (filter_kind=='图片' and asset['mime'].startswith('image/')) or (filter_kind=='视频' and asset['mime'].startswith('video/')) or (filter_kind=='音频' and asset['mime'].startswith('audio/')) or (filter_kind=='成片' and asset['kind'] in ('final','quick-video')) or (filter_kind=='3D' and asset['kind']=='3d')
  matching=[a for a in activity['assets'] if matches(a)]
  visible=paginate(matching,'assets:'+pid+filter_kind,show_controls=False)
  columns=st.columns(3)
  for i,asset in enumerate(visible):
   with columns[i%3]:
    with st.container(border=True,height=340,key='asset-card-'+asset['id']):
     st.markdown('<div class="asset-name" title="'+escape(asset['name'],quote=True)+'">'+escape(asset['name'])+'</div>',unsafe_allow_html=True);url=API+'/media/'+asset['id']
     with st.container(height=170,border=False):
      if asset['mime'].startswith('image/'):st.image(url,width='stretch')
      elif asset['mime'].startswith('video/'):st.video(url)
      elif asset['mime'].startswith('audio/'):st.audio(url)
      else:st.caption('3D 素材 · 下载后预览')
     st.caption(asset['kind']);st.link_button('下载素材',url,use_container_width=True)
  if not visible:st.caption('暂无符合条件的素材。')
  paginate(matching,'assets:'+pid+filter_kind)

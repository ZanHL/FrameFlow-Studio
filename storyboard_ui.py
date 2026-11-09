"""Streamlit implementation of the complete eight-stage production workspace."""
import copy,json,uuid
from datetime import datetime
from urllib.parse import quote
import streamlit as st
STEPS=['创意与故事','分镜设计','画风与设定','首尾帧','提交前审核','视频生成','视频合成']

def normalize_stage(value):
 try:return max(0,min(int(value),len(STEPS)-1))
 except (ValueError,TypeError,OverflowError):return 0

def image_versions(assets,sid,selected='',include_project=False):
 images=[a for a in assets if a.get('mime','').startswith('image/')]
 return sorted([a for a in images if include_project or a.get('shot')==sid or a['id']==selected],key=lambda a:a.get('created',0),reverse=True)

def render(api,do,base,boot):
 projects=boot['projects']
 if not projects:st.info('先在项目总览创建一个项目。');return
 ids=[p['id'] for p in projects]
 if st.session_state.get('workspace_project') not in ids:st.session_state['workspace_project']=ids[0]
 pid=st.session_state['workspace_project']
 requested=st.query_params.get('stage')
 if requested is not None:
  if str(requested).isdigit() and 0<=int(requested)<7:st.session_state['next_stage:'+pid]=int(requested)
  st.query_params.pop('stage',None)
 p=api('/projects/'+pid);activity=api('/projects/'+pid+'/activity');assets=activity['assets'];rev=p['revision'];prefix=pid+':'+str(rev)
 from studio.ui.editor_navigation import render as render_editor_navigation
 render_editor_navigation(pid,p['name'],'自定义分镜')
 with st.expander('切换项目',expanded=False):
  st.selectbox('当前项目',ids,format_func=lambda x:next(p['name'] for p in projects if p['id']==x),key='workspace_project')
 def send(path,body=None,method='POST'):
  value=do(lambda:api(path,method,body or {}))
  if value is not None:st.rerun(scope='app')
 def patch(body):return api('/projects/'+pid,'PATCH',{'_revision':rev,**body})
 def save(body):
  if do(lambda:patch(body)) is not None:st.rerun()
 def save_and_generate(body,path):
  def perform():
   patch(body)
   return api(path,'POST',{})
  if do(perform) is not None:st.rerun()
 def update_shot(sid,**fields):
  shots=copy.deepcopy(p['shots']);next(x for x in shots if x['id']==sid).update(fields);return patch({'shots':shots})
 def change_frame_version(sid,kind,widget):
  selected=st.session_state.get(widget)
  if selected:
   result=do(lambda:update_shot(sid,**{kind:selected}))
   if result is not None:st.session_state['_action_feedback']='图片版本已切换并保存。'
 def media_preview(url,caption='',loading=False,video=False,key='preview'):
  with st.container(key=key):
   if video:st.video(url)
   else:st.image(url,caption=caption,width='stretch')
   if loading:
    st.markdown('<style>.st-key-'+key+'{position:relative}.st-key-'+key+' [data-testid="stImage"],.st-key-'+key+' [data-testid="stVideo"]{opacity:.45}.media-loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;background:#ffffff44;pointer-events:none;z-index:2}.media-wheel{width:20px;height:20px;border:3px solid #ddd;border-top-color:#6953c6;border-radius:50%;animation:media-spin 1s linear infinite}@keyframes media-spin{to{transform:rotate(360deg)}}</style><div class="media-loading" role="status"><span class="media-wheel"></span>正在生成，完成后自动更新</div>',unsafe_allow_html=True)
 def show_asset(a):
  url=base+'/media/'+a['id']
  if a['mime'].startswith('image/'):st.image(url,width='stretch')
  elif a['mime'].startswith('video/'):st.video(url)
  elif a['mime'].startswith('audio/'):st.audio(url)
  st.caption(a['name']+' / '+a['kind']);st.link_button('下载文件',url)
 def upload(kind,sid='',key=''):
  extensions=['mp4'] if kind=='video' else ['mp3','wav'] if kind=='music' else ['png','jpg','jpeg','webp']
  file=st.file_uploader('上传'+{'first':'首帧','last':'尾帧','video':'视频','music':'配乐','style':'画风参考','reference':'参考图片'}[kind],type=extensions,key='upload:'+pid+kind+sid+key)
  if st.button('保存上传文件',key='upload-save:'+pid+kind+sid+key,disabled=file is None):
   def perform():
    ext=file.name.rsplit('.',1)[-1].lower();mime={'mp4':'video/mp4','mp3':'audio/mpeg','wav':'audio/wav','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp'}[ext]
    a=api('/projects/'+pid+'/upload?kind='+kind+'&shot='+sid,'POST',content=file.getvalue(),headers={'Content-Type':mime,'X-File-Name':quote(file.name)})
    if kind in ('first','last'):update_shot(sid,**{kind:a['id']})
    return a
   if do(perform):st.rerun()
 def report(review,step,sid=''):
  if not review:st.caption('尚未审核');return
  accepted=review.get('passed') or review.get('override',{}).get('approved')
  (st.success if accepted else st.warning)('审核通过' if accepted else '审核未通过')
  with st.expander('审核详情'):st.json(review)
  if review.get('passed') is False and not accepted:
   with st.expander('修订与人工放行'):
    rounds=st.number_input('最多修订轮数',1,3,2,key=f'round:{pid}:{step}:{sid}')
    approve=st.checkbox('同意按总导演模型规则计费',key=f'approve:{pid}:{step}:{sid}')
    label='生成整改方案' if step in (3,7) else '自动修订并复审'
    if st.button(label,key=f'repair:{pid}:{step}:{sid}',disabled=not approve):send('/projects/'+pid+'/repair',{'step':step,'shot':sid,'rounds':rounds,'approve':True})
    reason=st.text_area('人工放行原因',key=f'reason:{pid}:{step}:{sid}')
    if st.button('人工强制通过',key=f'force:{pid}:{step}:{sid}',disabled=not reason.strip()):send('/projects/'+pid+'/force-review',{'step':step,'shot':sid,'revision':rev,'reason':reason})

 st.title(p['name'])
 completed=sum(bool(p['confirmed'].get(str(i))) for i in range(7))
 st.markdown(f'<div class="workspace-summary"><span>制作进度<strong>{completed} / 7</strong></span><span>视频已记账<strong>¥{p["spent"]:.2f}</strong></span><span>任务预留<strong>¥{p["reserved"]:.2f}</strong></span><span>总预算<strong>¥{p["budget"]:.2f}</strong></span></div>',unsafe_allow_html=True)
 if 'next_stage:'+pid in st.session_state:st.session_state['stage:'+pid]=st.session_state.pop('next_stage:'+pid)
 stage_key='stage:'+pid
 if stage_key in st.session_state:
  value=st.session_state[stage_key];normalized=normalize_stage(value)
  if type(value) is not int or value!=normalized:st.session_state[stage_key]=normalized
 with st.expander('切换制作环节',expanded=False):
  step=st.selectbox('制作环节',range(7),index=normalize_stage(p.get('stage',0)),format_func=lambda i:f'{"✓ " if p["confirmed"].get(str(i)) else ""}{i+1}. {STEPS[i]}',key='stage:'+pid)
 st.progress(sum(bool(p['confirmed'].get(str(i))) for i in range(7))/7)
 nav=st.columns(7)
 for i,col in enumerate(nav):
  if col.button(('✓ ' if p['confirmed'].get(str(i)) else str(i+1)+' ')+STEPS[i],key='step-nav:'+pid+str(i),type='primary' if i==step else 'secondary',use_container_width=True):
   st.session_state['next_stage:'+pid]=i;st.rerun()
 section,refresh=st.columns([4,1],vertical_alignment='center')
 section.subheader(STEPS[step]);suffix=prefix+':'+str(step)
 with st.expander('本步提示词模板'):
  template=['story','storyboard','style','frames','review','video','post','delivery'][step]
  st.code(boot['prompts'].get(template,{}).get('value',''))
 if st.session_state.get('_stage_save_error:'+pid):st.error(st.session_state.pop('_stage_save_error:'+pid))
 if step and not p['confirmed'].get(str(step-1)):
  st.warning('当前可预览与编辑；请先确认「'+STEPS[step-1]+'」，再生成或确认本环节。')
 if refresh.button('刷新内容',key='refresh-top:'+pid,use_container_width=True):
  st.session_state['_action_feedback']='项目内容、审核结果与素材已刷新。';st.rerun()
 allow=True
 if step==0:
  with st.form('story:'+suffix,enter_to_submit=False):
   content,settings=st.columns([1.7,1])
   with content:
    name=st.text_input('项目名称',p['name']);idea=st.text_area('故事想法',p['idea'])
    st.caption('写下一句话或初步剧情，让 AI 导演帮你展开为完整故事。')
    generate_story=st.form_submit_button('调用导演完善故事',type='primary',disabled=not allow,use_container_width=True)
    story=st.text_area('完整故事',p['story'],height=240)
   with settings:
    with st.container(border=True):
     st.subheader('项目规格')
     a,b=st.columns(2)
     duration=a.number_input('片长（秒）',5,600,int(p['duration']))
     ratio=b.selectbox('画幅',['16:9','9:16','1:1'],index=['16:9','9:16','1:1'].index(p['ratio']))
     animator=boot['models'].get('animator',{})
     model_info=next((m for m in boot['catalog'].get(animator.get('platform'),{}).get('models',{}).get('animator',[]) if m['id']==animator.get('model')),{})
     resolutions=model_info.get('resolutions',['480p','720p'])
     generation_resolution=st.selectbox('生成分辨率',resolutions,index=resolutions.index(p.get('generation_resolution','720p')) if p.get('generation_resolution','720p') in resolutions else 0)
     budget=st.number_input('总预算（元）',1.,1000000.,float(p['budget']))
     structure=st.radio('故事结构',['片段式','连贯式'],index=0 if p['structure']=='片段式' else 1,horizontal=True)
     a,b=st.columns(2)
     music=a.checkbox('需要配乐',p['music']);subtitles=b.checkbox('需要字幕',p['subtitles'])
     st.caption('片长是全片目标；单镜时长在分镜设计中设置。画幅沿用至所有镜头。')
     st.caption('当前分镜流程导出支持硬切与配乐；字幕及复杂转场可使用快速生成。')
   body=dict(generation_resolution=generation_resolution,name=name,idea=idea,duration=duration,ratio=ratio,budget=budget,structure=structure,music=music,subtitles=subtitles,story=story)
   note,continue_col=st.columns([4,1.3],vertical_alignment='center')
   note.caption('保存当前故事与项目规格，进入分镜设计。')
   if continue_col.form_submit_button('保存继续',type='primary',use_container_width=True):
    def save_story_and_continue():
     patch(body)
     try:return api('/projects/'+pid+'/confirm/0','POST',{})
     except Exception as error:
      st.session_state.pop('_action_feedback',None)
      st.session_state['_stage_save_error:'+pid]='内容已保存，暂未进入下一步：'+str(error)
      return {'stage':0}
    result=do(save_story_and_continue)
    if result:
     st.session_state['next_stage:'+pid]=normalize_stage(result.get('stage',0));st.rerun()
   if generate_story:save_and_generate(body,'/projects/'+pid+'/generate/story')
 elif step==1:
  total=sum(float(sh.get('duration',0)) for sh in p['shots'])
  with st.form('shots:'+suffix,border=False,enter_to_submit=False):
   generate_col,hint=st.columns([1.2,3],vertical_alignment='center')
   generate=generate_col.form_submit_button('生成分镜表',type='primary',use_container_width=True)
   hint.caption('让 AI 导演将已确认的故事展开成镜头，生成后可在下方调整。')
   st.divider()
   summary,add_col,delete_col=st.columns([3,1,1.4],vertical_alignment='center')
   summary.caption(f"{len(p['shots'])} 个镜头 · 合计 {total:g} 秒 · 目标 {p['duration']} 秒")
   add=add_col.form_submit_button('添加镜头',use_container_width=True)
   deleted=delete_col.form_submit_button('删除勾选镜头',use_container_width=True,disabled=not p['shots'])
   rows=[{'id':sh['id'],'remove':False,'title':sh['title'],'duration':int(sh['duration']),'description':sh.get('description','')} for sh in p['shots']]
   edited=st.data_editor(rows,key='shot-table:'+suffix,hide_index=True,num_rows='fixed',width='stretch',height=min(450,max(150,38*len(rows)+42)),column_order=['remove','title','duration','description'],column_config={
    'id':None,
    'remove':st.column_config.CheckboxColumn('选择',width='small'),
    'title':st.column_config.TextColumn('镜头名称',width='medium',required=True),
    'duration':st.column_config.NumberColumn('秒数',min_value=2,max_value=30,step=1,width='small',required=True),
    'description':st.column_config.TextColumn('画面 / 动作 / 机位 / 配色',width='large')})
   if not rows:st.info('点击上方「生成分镜表」开始，也可以手动添加镜头。')
   note,continue_col=st.columns([4,1.3],vertical_alignment='center')
   note.caption('确认镜头内容后，保存并进入「画风与设定」。')
   continued=continue_col.form_submit_button('保存并继续',type='primary',use_container_width=True)
   if add or generate or deleted or continued:
    def apply_table():
     originals={sh['id']:sh for sh in p['shots']};shots=[]
     for row in edited:
      if deleted and row.get('remove'):continue
      sh=copy.deepcopy(originals[row['id']]);sh.update({k:row[k] for k in ['title','duration','description']});shots.append(sh)
     if add:shots.append({'id':uuid.uuid4().hex,'title':'新镜头','duration':5,'description':'','prompt':''})
     value=patch({'shots':shots})
     if deleted:st.session_state['_action_feedback']=f'已删除 {len(originals)-len(shots)} 个镜头。'
     if generate:return api('/projects/'+pid+'/generate/storyboard','POST',{})
     if continued:
      value=api('/projects/'+pid+'/confirm/1','POST',{})
      st.session_state['next_stage:'+pid]=value['stage']
     return value
    if deleted and not any(row.get('remove') for row in edited):st.warning('请先勾选要删除的镜头。')
    elif do(apply_table) is not None:st.rerun()
  if p['shots']:
   with st.expander('查看镜头完整内容与提示词',expanded=False):
    sid=st.selectbox('选择镜头',[sh['id'] for sh in p['shots']],format_func=lambda x:next(sh['title'] for sh in p['shots'] if sh['id']==x),key='shot-detail:'+pid)
    selected_shot=next(sh for sh in p['shots'] if sh['id']==sid)
    st.write(selected_shot.get('description',''));st.caption('视频提示词可在「提交前审核」中编辑。');st.code(selected_shot.get('prompt','') or '尚未生成视频提示词')
 elif step==2:
  entry,hint=st.columns([1.4,3],vertical_alignment='center')
  generate_style=entry.button('生成画风与角色方案',type='primary',use_container_width=True)
  hint.caption('先让 AI 导演设计画风与角色，再编辑设定、生成样张。')
  style=st.text_area('画风与角色设定',p['style'],height=230,key='style-edit:'+suffix)
  if generate_style:save_and_generate({'style':style},'/projects/'+pid+'/generate/style')
  st.divider()
  text=st.text_area('样张图片提示词',key='style-image:'+pid,height=90)
  if st.button('生成画风样张',disabled=not allow or not text.strip()):
   def sample():
    if style!=p['style']:patch({'style':style})
    return api('/projects/'+pid+'/image','POST',{'kind':'style','prompt':text})
   if do(sample) is not None:st.rerun()
  with st.expander('上传画风参考',expanded=False):upload('style')
  style_running=any(j['kind']=='image' and j['status'] in ('queued','running') and j['data'].get('frame_kind')=='style' for j in activity['jobs'])
  for a in assets:
   if a['kind']=='style':media_preview(base+'/media/'+a['id'],a['name'],style_running,key='style-preview-'+a['id'])
 elif step==3:
  drafts=st.session_state.setdefault('frame-plan-drafts:'+pid,{})
  fields=('first_prompt','last_prompt','motion')
  for shot in p['shots']:
   base_plan=shot.get('frame_plan',{})
   keys={field:'frame-plan-input:'+suffix+shot['id']+field for field in fields}
   if any(key in st.session_state for key in keys.values()):
    drafts[shot['id']]={'base':copy.deepcopy(base_plan),'value':{field:st.session_state.get(key,base_plan.get(field,'')) for field,key in keys.items()}}
  entry,hint=st.columns([1.4,3],vertical_alignment='center')
  if entry.button('生成每镜首尾帧规划',type='primary',disabled=not allow,use_container_width=True):send('/projects/'+pid+'/generate/frames')
  hint.caption('先生成文字构图规划，再选择镜头生成图片；图片完成后自动选用。')
  st.divider()
  completed=sum(bool(sh.get('first') and sh.get('last')) for sh in p['shots'])
  st.caption(f"已完成 {completed} / {len(p['shots'])} 组首尾帧 · 可按帧填写修改意见并重新生成。")
  shot_ids=[sh['id'] for sh in p['shots']]
  if not shot_ids:st.info('暂无镜头，请先到分镜设计添加或生成分镜。')
  selected_sid=st.selectbox('当前镜头',shot_ids,format_func=lambda sid:next(str(i+1)+'. '+sh['title']+(' · 已选齐' if sh.get('first') and sh.get('last') else ' · 待生成') for i,sh in enumerate(p['shots']) if sh['id']==sid),key='frame-shot:'+pid) if shot_ids else None
  for i,sh in [(i,sh) for i,sh in enumerate(p['shots']) if sh['id']==selected_sid]:
   with st.container(border=True):
    st.subheader(f'{i+1}. {sh["title"]}');st.caption(sh['description'])
    base_plan=sh.get('frame_plan',{});draft=drafts.get(sh['id'],{})
    plan=draft.get('value',base_plan) if draft.get('base')==base_plan else base_plan
    with st.expander('构图规划与中间动作',expanded=not bool(base_plan)):
     first_col,last_col=st.columns(2)
     first_prompt=first_col.text_area('首帧画面与构图',plan.get('first_prompt',''),key='frame-plan-input:'+suffix+sh['id']+'first_prompt')
     last_prompt=last_col.text_area('尾帧画面与构图',plan.get('last_prompt',''),key='frame-plan-input:'+suffix+sh['id']+'last_prompt')
     motion=st.text_area('中间动作与变化',plan.get('motion',''),height=80,key='frame-plan-input:'+suffix+sh['id']+'motion')
    plan=dict(first_prompt=first_prompt,last_prompt=last_prompt,motion=motion)
    drafts[sh['id']]={'base':copy.deepcopy(base_plan),'value':plan}
    running=[j for j in activity['jobs'] if j['kind'] in ('image','frame-pair') and j['status'] in ('queued','running') and j['data'].get('shot')==sh['id']]
    if running:st.info(running[0]['data'].get('message','本镜图片生成中，完成后会自动显示。'))
    if st.button('实际生成首尾帧图片（2 张）',key='frame-pair:'+sh['id'],disabled=bool(running) or not allow or not all(plan.get(k,'').strip() for k in ['first_prompt','last_prompt'])):
     def generate_pair():
      if plan!=base_plan:update_shot(sh['id'],frame_plan=plan)
      return api('/projects/'+pid+'/shots/'+sh['id']+'/generate-frame-pair','POST',{'approve':True})
     if do(generate_pair) is not None:st.rerun()
    st.caption('调用画师实际生成图片，按平台图片价格计费；先尾帧、后首帧。')
    feedback_store=st.session_state.setdefault('shot-frame-feedback:'+pid,{})
    feedback_key='shot-frame-feedback-input:'+pid+sh['id']
    def keep_shot_feedback(sid=sh['id'],key=feedback_key):feedback_store[sid]=st.session_state[key]
    shot_feedback=st.text_area('本镜头修改意见',value=feedback_store.get(sh['id'],''),key=feedback_key,on_change=keep_shot_feedback,placeholder='例如：人物改为坐姿，首尾帧都保留窗边构图。只修改当前镜头。',height=90)
    if st.button('按意见重新生成本镜首尾帧',key='frame-pair-redraw:'+sh['id'],disabled=bool(running) or not allow or not shot_feedback.strip() or not all(plan.get(k,'').strip() for k in ('first_prompt','last_prompt')),use_container_width=True):
     def redraw_pair():
      if plan!=base_plan:update_shot(sh['id'],frame_plan=plan)
      return api('/projects/'+pid+'/shots/'+sh['id']+'/generate-frame-pair','POST',{'approve':True,'feedback':shot_feedback})
     if do(redraw_pair) is not None:st.rerun()
    st.caption('仅重新生成当前镜头的两张图片，按画师服务商规则计费，旧版本保留。')

    columns=st.columns(2)
    for col,kind in zip(columns,('first','last')):
     with col:
      st.write('**'+('首帧' if kind=='first' else '尾帧')+'**')
      chosen=next((a for a in assets if a['id']==sh.get(kind)),None)
      related=image_versions(assets,sh['id'],sh.get(kind,''))
      include_project=st.checkbox('显示项目全部图片（含参考图与其他镜头）',value=False,key='all-images:'+pid+sh['id']+kind)
      candidates=image_versions(assets,sh['id'],sh.get(kind,''),include_project);candidates.sort(key=lambda a:(a.get('kind')==kind,a.get('created',0)),reverse=True);ids=['']+[a['id'] for a in candidates]
      labels={'first':'首帧','last':'尾帧','style':'设定参考','reference':'参考图'}
      version_key=suffix+sh['id']+kind+':'+str(len(candidates))
      selected=st.selectbox('已有图片版本',ids,index=ids.index(sh[kind]) if sh.get(kind) in ids else 0,format_func=lambda x:next((a['name']+' / '+labels.get(a['kind'],a['kind'])+' / '+a['id'][:6] for a in candidates if a['id']==x),'请选择图片'),key=version_key,on_change=change_frame_version,args=(sh['id'],kind,version_key))
      preview=next((a for a in candidates if a['id']==selected),None)
      if preview:
       if preview.get('warning'):st.warning(preview['warning'])
       frame_loading=any(j['kind']=='frame-pair' or j['data'].get('frame_kind')==kind for j in running)
       media_preview(base+'/media/'+preview['id'],'版本预览 · '+preview['name'],frame_loading,key='frame-preview-'+sh['id']+kind)
      if not preview:st.info('本镜头尚未选用'+('首帧' if kind=='first' else '尾帧')+'，请生成新图片或手动选择本镜头版本。')
      with st.form('frame-feedback:'+pid+sh['id']+kind):
       feedback=st.text_area('首帧修改意见' if kind=='first' else '尾帧修改意见',height=80,placeholder='例如：人物向左移动，背景与服装保持不变。')
       redraw=st.form_submit_button('按意见重绘首帧' if kind=='first' else '按意见重绘尾帧',disabled=bool(running),use_container_width=True)
       if redraw:
        if not feedback.strip():st.warning('请先填写这张图的修改意见。')
        else:send('/projects/'+pid+'/image',{'kind':kind,'shot':sh['id'],'prompt':plan.get(kind+'_prompt','') or sh.get('description',''),'feedback':feedback,'reference':selected or sh.get(kind)})
      st.caption('生成后自动选用，仅更新此帧；旧版本保留。Seedream 支持参考图重绘，其他平台按文字重新生成。')
      if candidates:
       with st.expander('图片版本缩略图（'+str(len(candidates))+' 张）',expanded=False):
        for a in candidates:
         st.image(base+'/media/'+a['id'],caption=a['name']+' / '+labels.get(a['kind'],a['kind'])+' / '+a['id'][:6],width='stretch')
      with st.expander('上传与裁切',expanded=False):
       if chosen and st.button('按项目画幅裁切',key='crop:'+sh['id']+kind):
        result=do(lambda:api('/projects/'+pid+'/assets/'+chosen['id']+'/crop','POST',{}))
        if result and do(lambda:update_shot(sh['id'],**{kind:result['id']})):st.rerun()
       upload(kind,sh['id'])
    with st.expander('单张重绘与补充要求',expanded=False):
     text=st.text_area('补充图片要求（可选）',key='image-prompt:'+sh['id'])
     a,b=st.columns(2)
     for col,kind,label in [(a,'last','生成尾帧新版本'),(b,'first','生成首帧新版本')]:
      image_prompt=plan.get('last_prompt' if kind=='last' else 'first_prompt','')+'\n'+text
      if col.button(label,key='image:'+kind+sh['id'],disabled=not allow or not image_prompt.strip()):send('/projects/'+pid+'/image',{'kind':kind,'shot':sh['id'],'prompt':image_prompt})
 elif step==4:
  prompt_drafts=st.session_state.setdefault('prompt-drafts:'+pid,{})
  for shot in p['shots']:
   key='video-prompt-input:'+suffix+shot['id']
   if key in st.session_state:prompt_drafts[shot['id']]={'base':shot.get('prompt',''),'value':st.session_state[key]}
  def persist_prompts():
   shots=copy.deepcopy(p['shots']);changed=False
   for shot in shots:
    draft=prompt_drafts.get(shot['id'],{})
    if draft.get('base')==shot.get('prompt','') and draft.get('value')!=shot.get('prompt',''):
     shot['prompt']=draft['value'];changed=True
   if changed:patch({'shots':shots})
  entry,hint=st.columns([1.4,3],vertical_alignment='center')
  generate_prompts=entry.button('生成七段式视频提示词',type='primary',disabled=not allow,use_container_width=True)
  hint.caption('先生成提示词，再逐镜检查与修改；文字检查可选。')
  st.divider()
  ids=[sh['id'] for sh in p['shots']]
  selected_prompt_sid=st.selectbox('当前镜头',ids,format_func=lambda sid:next(f'{i+1}. '+sh['title'] for i,sh in enumerate(p['shots']) if sh['id']==sid),key='prompt-shot:'+pid) if ids else None
  if not ids:st.info('暂无镜头，请先完成分镜与首尾帧。')
  for i,sh in [(i,sh) for i,sh in enumerate(p['shots']) if sh['id']==selected_prompt_sid]:
   with st.container(border=True):
    st.subheader(f'{i+1}. {sh["title"]}')
    draft=prompt_drafts.get(sh['id'],{})
    default=draft.get('value',sh.get('prompt','')) if draft.get('base')==sh.get('prompt','') else sh.get('prompt','')
    text=st.text_area('视频提示词',default,height=250,key='video-prompt-input:'+suffix+sh['id'])
    prompt_drafts[sh['id']]={'base':sh.get('prompt',''),'value':text}
    with st.expander('首尾帧对照',expanded=False):
     cols=st.columns(2)
     for col,kind in zip(cols,('first','last')):
      if sh.get(kind):col.image(base+'/media/'+sh[kind],caption='首帧' if kind=='first' else '尾帧',use_container_width=True)
    if st.button('可选：检查文字提示词',key='review:'+sh['id'],disabled=not allow):
     def check_prompt():
      persist_prompts();return api('/projects/'+pid+'/shots/'+sh['id']+'/review','POST',{})
     if do(check_prompt) is not None:st.rerun()
    report(sh.get('review'),step,sh['id'])
  if generate_prompts:
   def generate_all_prompts():
    persist_prompts();return api('/projects/'+pid+'/generate/video','POST',{})
   if do(generate_all_prompts) is not None:st.rerun()
 elif step==5:
  cfg=boot['models'].get('animator',{});info=next((m for m in boot['catalog'].get(cfg.get('platform'),{}).get('models',{}).get('animator',[]) if m['id']==cfg.get('model')),{} )
  minimum,maximum=info.get('min_duration',2),info.get('max_duration',15)
  entry,hint=st.columns([1.4,3],vertical_alignment='center')
  video_generate_slot=entry.empty()
  hint.caption('选择镜头并确认参数与报价，再提交生成；完成后在右侧预览。')
  approval_slot=hint.empty()
  st.divider()
  video_choices=st.session_state.setdefault('video-choice-drafts:'+pid,{})
  for shot in p['shots']:
   key='video-version:'+suffix+shot['id']
   if key in st.session_state:video_choices[shot['id']]={'base':shot.get('selected'),'value':st.session_state[key]}
  shot_ids=[sh['id'] for sh in p['shots']]
  if not shot_ids:st.info('暂无镜头，请先在分镜设计中添加镜头。')
  if st.session_state.get('video-shot:'+pid) not in shot_ids:st.session_state.pop('video-shot:'+pid,None)
  selected_video_sid=st.selectbox('当前镜头',shot_ids,format_func=lambda sid:next(f'{i+1}. '+sh['title']+f' · {sh["duration"]} 秒' for i,sh in enumerate(p['shots']) if sh['id']==sid),key='video-shot:'+pid) if shot_ids else None
  for i,sh in [(i,sh) for i,sh in enumerate(p['shots']) if sh['id']==selected_video_sid]:
   sid=sh['id'];videos=[a for a in assets if a.get('shot')==sid and a['mime'].startswith('video/')]
   running=any(j['kind']=='video' and j['data'].get('shot')==sid and j['status'] in ('queued','running','submitted') for j in activity['jobs'])
   with st.container(border=True):
    st.subheader(f'{i+1}. {sh["title"]} · {sh["duration"]} 秒')
    frames,output=st.columns(2)
    with frames:
     st.write('**生成参数**')
     a,b=st.columns(2)
     a.metric('本镜时长',f'{sh["duration"]} 秒');b.metric('项目画幅',p['ratio'])
     st.caption('动画师模型：'+cfg.get('model','未配置')+f' · 支持 {minimum}–{maximum} 秒')
     resolutions=info.get('resolutions',['480p','720p'])
     resolution=st.selectbox('生成分辨率',resolutions,index=resolutions.index(p.get('generation_resolution','720p')) if p.get('generation_resolution','720p') in resolutions else 0,key='video-resolution:'+suffix+sid)
     st.caption('预算按已配置的每秒单价估算；不同分辨率实际费用以服务商账单为准。')
     st.caption('时长在「分镜设计」修改，画幅在「创意与故事 → 项目规格」修改，模型在「设置」修改。')
     first,last=st.columns(2)
     for col,kind,label in [(first,'first','首帧'),(last,'last','尾帧')]:
      if sh.get(kind):col.image(base+'/media/'+sh[kind],caption=label,width='stretch')
      else:col.caption('缺少'+label)
     with st.expander('本镜视频提示词'):st.write(sh.get('prompt','') or '请先在提交前审核中生成或填写提示词。')
     cost=round(float(cfg.get('rate',0))*float(sh['duration']),2)
     valid=minimum<=float(sh['duration'])<=maximum
     if not valid:st.warning(f'本镜时长不在 {minimum}–{maximum} 秒范围内，请在分镜设计调整。')
     if running:st.info('本镜生成中，可在下方制作任务刷新服务商状态。')
     st.caption(f'本镜预估 ¥{cost:.2f}（¥{float(cfg.get("rate",0)):.2f}/秒） · 剩余预算 ¥{max(0,p["budget"]-p["spent"]-p["reserved"]):.2f}，实际费用以账单为准。')
     approved=approval_slot.checkbox(f'确认本镜报价（约 ¥{cost:.2f}）',key='video-approve:'+suffix+cfg.get('model','')+str(cost)+resolution+sid)
     if video_generate_slot.button('提交本镜生成',key='video-generate:'+sid,type='primary',disabled=running or not approved or not valid or cost<=0 or not sh.get('first') or not sh.get('last') or not sh.get('prompt') or not p['confirmed'].get('4')):
      send('/projects/'+pid+'/shots/'+sid+'/video',{'approve':True,'quote':cost,'resolution':resolution})
    with output:
     if videos:
      options=[a['id'] for a in videos]
      pending=video_choices.get(sid,{})
      preferred=pending.get('value') if pending.get('base')==sh.get('selected') and pending.get('value') in options else sh.get('selected')
      selected=st.selectbox('本镜视频版本',options,index=options.index(preferred) if preferred in options else 0,format_func=lambda aid:next(a['name'] for a in videos if a['id']==aid),key='video-version:'+suffix+sid)
      media_preview(base+'/media/'+selected,loading=running,video=True,key='video-preview-'+sid)
      video_choices[sid]={'base':sh.get('selected'),'value':selected}
      st.caption('当前版本将在底部「保存并继续」时选用。')
      st.link_button('下载本镜视频',base+'/media/'+selected)
     else:st.caption('本镜尚无视频，生成完成后将在这里播放。')
  legacy=[a for a in assets if a['kind'] in ('full-video','final')]
  if legacy:
   with st.expander('已有整片视频（历史版本）'):
    for a in legacy:show_asset(a)
 elif step==6:
  chosen={a['id']:a for a in assets}
  missing=[sh['title'] for sh in p['shots'] if not sh.get('selected') or sh['selected'] not in chosen]
  active_export=any(j['kind']=='export' and j['status'] in ('queued','running') for j in activity['jobs'])
  entry,hint=st.columns([1.4,3],vertical_alignment='center')
  compose_slot=entry.empty()
  hint.caption('调整合成参数后开始合成，预览并下载成片，最后完成制作。')
  st.divider()
  settings,preview=st.columns([1.15,1])
  with settings:
   st.write('**合成设置**')
   st.caption(f'{len(p["shots"])} 个镜头 · 按分镜顺序拼接 · {p["ratio"]}')
   if missing:st.warning('以下镜头尚未选定视频：'+ '、'.join(missing))
   with st.container(border=False):
    output_resolution=st.selectbox('成片输出分辨率',['720p','1080p'],index=1,format_func=lambda r:r+' · 高清放大' if r=='1080p' else r)
    st.caption('低分辨率片段会按比例放大到目标尺寸，使用 Lanczos 缩放与轻微锐化；不调用付费模型。')
    rows=[{'id':sh['id'],'镜头':f'{i+1}. '+sh['title'],'视频版本':chosen.get(sh.get('selected'),{}).get('name','未选定'),'起始秒':0.,'使用秒数':float(sh['duration']),'亮度':0.,'饱和度':1.} for i,sh in enumerate(p['shots'])]
    edited=st.data_editor(rows,hide_index=True,width='stretch',disabled=['镜头','视频版本'],column_config={'id':None,'起始秒':st.column_config.NumberColumn(min_value=0.,step=.1),'使用秒数':st.column_config.NumberColumn(min_value=.1,max_value=30.,step=.1),'亮度':st.column_config.NumberColumn(min_value=-.3,max_value=.3,step=.01),'饱和度':st.column_config.NumberColumn(min_value=0.,max_value=2.,step=.1)},key='compose-edits:'+suffix)
    music_assets=[a for a in assets if a['mime'].startswith('audio/')]
    music=st.selectbox('背景音乐',['']+[a['id'] for a in music_assets],format_func=lambda aid:next((a['name'] for a in music_assets if a['id']==aid),'不使用配乐'))
    st.caption('使用硬切拼接；原片声音静音，可选择项目音频作为全片配乐。')
    submitted=compose_slot.button('开始合成视频',type='primary',use_container_width=True,disabled=bool(missing) or not p['shots'] or not p['confirmed'].get('5') or active_export)
    if submitted:
     edits={r['id']:{'start':r['起始秒'],'duration':r['使用秒数'],'brightness':r['亮度'],'saturation':r['饱和度']} for r in edited}
     send('/projects/'+pid+'/export',{'music':music,'edits':edits,'resolution':output_resolution})
   if active_export:st.info('视频正在合成，完成后会自动刷新成片预览。')
   with st.expander('上传背景音乐'):upload('music')
  with preview:
   st.write('**成片预览**')
   finals=[a for a in assets if a['kind']=='final']
   if finals:
    ids=[a['id'] for a in finals]
    aid=st.selectbox('成片版本',ids,index=ids.index(p['export_asset']) if p.get('export_asset') in ids else 0,format_func=lambda aid:next(a['name']+' / '+a['id'][:6] for a in finals if a['id']==aid),key='final-version:'+suffix)
    media_preview(base+'/media/'+aid,loading=active_export,video=True,key='final-preview');st.link_button('下载成片',base+'/media/'+aid)
   else:st.info('合成完成后，视频将在这里显示。所有历史版本会保留。')
 st.divider()
 if step in (0,1,2):
  with st.expander('可选：模型文字检查（不影响继续制作）'):
   if st.button('检查本环节已保存的文字',disabled=not allow):send('/projects/'+pid+'/review/'+str(step))
   report(p['reviews'].get(str(step)),step)
 if step in (3,7):st.caption('本步无需模型审核，可直接人工确认。')
 if step==6:st.caption('预览确认成片后，点击「完成制作」。')
 elif step in (4,5):st.caption('本步修改与版本选择将在「保存并继续」时统一保存。')
 else:st.caption('可跳过模型检查；即使检查不通过，也可以确认本步继续。')
 ready=step!=6 or (not active_export and bool(p.get('export_asset')))
 previous,spacer,continue_action=st.columns([1.3,2.7,1.4],vertical_alignment='center')
 if step>0 and previous.button('上一步：'+STEPS[step-1],use_container_width=True):
  st.session_state['next_stage:'+pid]=step-1;st.rerun()
 if step not in (0,1) and continue_action.button('完成制作' if step==6 else '保存并继续' if step in (2,3,4,5) else '确认本步并继续',type='primary',disabled=not ready,use_container_width=True):
  def save_and_continue():
   if step==2 and style!=p['style']:patch({'style':style})
   if step==3:
    shots=copy.deepcopy(p['shots']);changed=False
    for shot in shots:
     draft=drafts.get(shot['id'],{})
     if draft.get('base')==shot.get('frame_plan',{}) and draft.get('value')!=shot.get('frame_plan',{}):
      shot['frame_plan']=draft['value'];changed=True
    if changed:patch({'shots':shots})
   if step==4:persist_prompts()
   if step==5:
    shots=copy.deepcopy(p['shots']);body={}
    for shot in shots:
     draft=video_choices.get(shot['id'],{})
     if draft and draft.get('base')==shot.get('selected') and draft.get('value')!=shot.get('selected'):shot['selected']=draft['value'];body['shots']=shots
    if p['shots'] and resolution!=p.get('generation_resolution','720p'):body['generation_resolution']=resolution
    if body:patch(body)
   try:return api('/projects/'+pid+'/confirm/'+str(step),'POST',{})
   except Exception as error:
    if step not in (2,3,4,5):raise
    st.session_state.pop('_action_feedback',None)
    st.session_state['_stage_save_error:'+pid]='内容已保存，暂未进入下一步：'+str(error)
    return {'stage':step}
  result=do(save_and_continue)
  if result:
   st.session_state['next_stage:'+pid]=normalize_stage(result.get('stage',0));st.rerun()
 rail_closed=st.session_state.get('task-rail-closed',False)
 @st.fragment(run_every='3s')
 def tasks():
  latest=do(lambda:api('/projects/'+pid+'/activity'))
  if latest is None:
   if rail_closed:st.caption('!')
   else:st.warning('任务状态刷新失败，可稍后点击刷新；这不代表生成任务失败。')
   return
  old={j['id']:j['status'] for j in activity['jobs']}
  terminal={'succeeded','failed','cancelled','interrupted'}
  if any(j['status'] in terminal and old.get(j['id']) in ('queued','running','submitted') for j in latest['jobs']):
   st.rerun(scope='app')
  active_count=sum(j['status'] in ('queued','running','submitted') for j in latest['jobs'])
  if rail_closed:
   st.markdown('<div class="task-rail-count" title="进行中的任务">'+str(active_count)+'</div>',unsafe_allow_html=True)
   return
  with st.expander('制作任务',expanded=True):
   st.caption(f'{active_count} 项进行中 · 每 3 秒更新')
   visible_jobs=[j for j in latest['jobs'] if step!=5 or (j['kind']=='video' and j['data'].get('shot')==selected_video_sid)]
   labels={'story':'故事','storyboard':'分镜','style':'画风方案','frames':'首尾帧规划','image':'图片生成','frame-pair':'首尾帧图片','video':'视频生成','export':'视频合成','shot-review':'提示词检查','auto-repair':'自动修订','repair-plan':'修订方案','3d':'3D 素材'}
   for j in visible_jobs[:20]:
    title=labels.get(j['kind'],j['kind'])+' · '+{'queued':'排队中','running':'处理中','submitted':'服务商处理中','succeeded':'完成','failed':'失败','cancelled':'已停止','interrupted':'重启中断'}.get(j['status'],j['status'])
    with st.expander(title,expanded=j['status'] in ('queued','running','submitted','failed')):
     if j['kind']=='frames':st.caption('这是文字规划任务，不会产生图片；请在对应镜头点击实际生成首尾帧图片。')
     if j['data'].get('message'):st.caption(j['data']['message'])
     output_ids=[j['data'].get('asset')]+[v for k,v in (j['data'].get('result') or {}).items() if k in ('first','last')] if isinstance(j['data'].get('result'),dict) else [j['data'].get('asset')]
     for aid in output_ids:
      image=next((a for a in latest['assets'] if a['id']==aid and a['mime'].startswith('image/')),None)
      if image:st.image(base+'/media/'+aid,caption='生成结果 · '+image['kind'],width='stretch')
     if j['data'].get('error'):
      st.error(j['data']['error'])
      if '视觉审核' in j['data']['error']:st.caption('这是历史视觉审核错误。当前版本已取消模型视觉审核，不影响人工确认继续制作。')
     if j['data'].get('result'):
      with st.expander('查看结果'):st.write(j['data']['result'])
     if j['status']=='submitted':
      if st.button('刷新远程任务并下载产物',key='refresh:'+j['id']):send('/jobs/'+j['id']+('/refresh-3d' if j['kind']=='3d' else '/refresh'))
     if j['kind'] in ('auto-repair','repair-plan') and j['status'] in ('queued','running'):
      if st.button('停止后续修订',key='cancel:'+j['id']):send('/jobs/'+j['id']+'/cancel-repair')
     if j['kind']=='video' and j['status'] in ('failed','interrupted') and not j['data'].get('settled'):
      st.warning('请核对服务商账单后结算异常预留。')
      resolution=st.selectbox('账单核对结果',['not_charged','charged'],format_func=lambda x:'确认未扣费' if x=='not_charged' else '确认已扣费',key='settle:'+j['id'])
      approve=st.checkbox('我已核对服务商实际账单',key='settle-ok:'+j['id'])
      if st.button('结算预留',key='release:'+j['id'],disabled=not approve):send('/jobs/'+j['id']+'/release',{'resolution':resolution})
   if not visible_jobs:st.caption('本镜尚无生成任务。' if step==5 else '尚无制作任务。')
   if st.button('刷新项目内容与素材版本'):
    st.session_state['_action_feedback']='项目内容与素材版本已刷新。';st.rerun(scope='app')
  with st.expander('审核与操作记录',expanded=False):
   with st.container(height=280,border=False):
    for event in latest.get('audit',[]):
     st.caption(datetime.fromtimestamp(event['time']).strftime('%m-%d %H:%M:%S'))
     st.write(event['text'])
    if not latest.get('audit'):st.caption('暂无审核与操作记录。')
  with st.expander('自动修订历史',expanded=False):
   versions=do(lambda:api('/projects/'+pid+'/repair-versions'))
   if versions is not None:
    current=[v for v in versions if v['step']==step]
    with st.container(height=260,border=False):
     for version in current:
      st.write(version['label']);st.json(version['data'],expanded=False)
     if not current:st.caption('本步骤暂无自动修订记录。')
 rail_width=48 if rail_closed else 280
 reserve=80 if rail_closed else 316
 rail_padding=6 if rail_closed else 12
 button_padding='4px 0' if rail_closed else '4px 8px'
 st.markdown(f'<style>[class*="st-key-production-task-dock-"]{{position:fixed!important;right:12px;top:74px;width:{rail_width}px!important;max-height:calc(100dvh - 94px);overflow-y:auto;overflow-x:hidden;background:#fff;border:1px solid #e2e6ef;border-radius:10px;padding:{rail_padding}px;z-index:50;box-shadow:0 4px 20px #252b4010}}.block-container:has([class*="st-key-production-task-dock-"]){{padding-right:{reserve}px!important}}[class*="st-key-production-task-dock-"] [data-testid="stExpander"]{{font-size:12px}}[class*="st-key-production-task-dock-"] button{{font-size:12px;min-height:32px;padding:{button_padding}}}.task-rail-count{{text-align:center;color:#6953c6;background:#f0edfb;border-radius:6px;font-size:12px;line-height:26px}}@media(max-width:760px){{.block-container:has([class*="st-key-production-task-dock-"]){{padding-right:1rem!important}}[class*="st-key-production-task-dock-"]{{top:64px;max-height:calc(100dvh - 80px)}}}}</style>',unsafe_allow_html=True)
 with st.container(key='production-task-dock-'+pid):
  if rail_closed:
   toggle=st.button('动态',key='task-rail-toggle:'+pid,help='展开任务与操作记录',use_container_width=True)
  else:
   heading,action=st.columns([2.5,1],vertical_alignment='center')
   heading.markdown('**项目动态**')
   toggle=action.button('收起',key='task-rail-toggle:'+pid,help='收起任务与操作记录',use_container_width=True)
  if toggle:
   st.session_state['task-rail-closed']=not rail_closed;st.rerun(scope='app')
  tasks()

def asset_tools(api,do,base,pid,activity):
 st.subheader('素材导入与 3D')
 with st.expander('上传项目素材'):
  kind=st.selectbox('素材类别',['reference','style','video','music'],format_func=lambda x:{'reference':'参考图片','style':'画风参考','video':'视频片段','music':'背景音乐'}[x])
  file=st.file_uploader('选择素材',type={'reference':['png','jpg','jpeg','webp'],'style':['png','jpg','jpeg','webp'],'video':['mp4'],'music':['mp3','wav']}[kind],key='library-upload:'+pid+kind)
  if st.button('保存到项目',disabled=file is None):
   def perform():
    ext=file.name.rsplit('.',1)[-1].lower();mime={'mp4':'video/mp4','mp3':'audio/mpeg','wav':'audio/wav','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp'}[ext]
    return api('/projects/'+pid+'/upload?kind='+kind,'POST',content=file.getvalue(),headers={'Content-Type':mime,'X-File-Name':quote(file.name)})
   if do(perform):st.rerun()
 with st.expander('图片生成 3D 素材'):
  images=[a for a in activity['assets'] if a['mime'].startswith('image/')]
  if not images:st.caption('先上传一张参考图片。')
  else:
   image=st.selectbox('参考图片',[a['id'] for a in images],format_func=lambda x:next(a['name'] for a in images if a['id']==x))
   approved=st.checkbox('同意按 3D 模型服务商规则计费，不计入视频预算')
   if st.button('提交图生 3D',disabled=not approved):
    if do(lambda:api('/projects/'+pid+'/3d','POST',{'image':image,'approve':True})):st.rerun()
  for j in activity['jobs']:
   if j['kind']=='3d':
    st.write('3D 任务 / '+j['status'])
    if j['data'].get('error'):
     st.error(j['data']['error'])
     if '视觉审核' in j['data']['error']:st.caption('这是历史视觉审核错误。当前版本已取消模型视觉审核，不影响人工确认继续制作。')
    if j['status']=='submitted' and st.button('刷新 3D 状态',key='refresh3d:'+j['id']):
     if do(lambda:api('/jobs/'+j['id']+'/refresh-3d','POST',{})):st.rerun()

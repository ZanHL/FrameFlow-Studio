"""Exercise every Streamlit production stage with a fake backend; no paid calls."""
import json,sys,unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).parent
SOURCE='''
import sys,copy
sys.path.insert(0,ROOT)
import streamlit as st
from storyboard_ui import render
p={'id':'demo','name':'迁移测试项目','idea':'测试故事','duration':30,'ratio':'16:9','budget':200,'structure':'片段式','music':False,'subtitles':False,'story':'故事正文','style':'水彩','notes':'','spent':0,'reserved':0,'revision':0,'stage':0,'confirmed':{},'reviews':{},'shots':[{'id':'shot1','title':'开场','duration':5,'description':'公园散步','prompt':'固定镜头'}]}
if 'fixture' not in st.session_state:st.session_state['fixture']=p
p=st.session_state['fixture']
def api(path,method='GET',body=None,**kwargs):
 if 'calls' not in st.session_state:st.session_state['calls']=[]
 st.session_state['calls'].append((path,method,body))
 if path.endswith('/activity'):return {'jobs':[],'assets':st.session_state.get('asset_fixture',[]),'audit':[]}
 if path.endswith('/repair-versions'):return []
 if '/confirm/' in path:
  step=int(path.rsplit('/',1)[-1]);st.session_state['fixture']['stage']=min(step+1,6);st.session_state['fixture']['confirmed'][str(step)]=True;return st.session_state['fixture']
 if method=='PATCH':
  st.session_state['fixture'].update({k:v for k,v in body.items() if k!='_revision'});return st.session_state['fixture']
 return p
def do(fn):return fn()
render(api,do,'http://127.0.0.1:4173',{'projects':[p],'models':{},'catalog':{},'prompts':{}})
'''.replace('ROOT',repr(str(ROOT.resolve())))
class Stages(unittest.TestCase):
 def test_frame_redraw_shows_loading_overlay(self):
  source=SOURCE.replace("'jobs':[]", "'jobs':[{'id':'job1','kind':'image','status':'running','data':{'shot':'shot1','frame_kind':'first'}}]")
  app=AppTest.from_string(source)
  app.session_state['asset_fixture']=[{'id':'pic','shot':'shot1','name':'首帧','mime':'image/png','kind':'first','created':1}]
  app.run(timeout=30)
  app.session_state['fixture']['shots'][0]['first']='pic'
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  overlays=[m.value for m in app.markdown if 'class="media-loading"' in m.value]
  self.assertEqual(len(overlays),1)
 def test_stage_state_accepts_strings_and_invalid_values(self):
  for value,expected in [('5',5),('invalid',0),(None,0),(99,6),(-1,0)]:
   app=AppTest.from_string(SOURCE)
   app.session_state['stage:demo']=value
   app.run(timeout=30)
   self.assertEqual(len(app.exception),0,str(value))
   self.assertEqual(app.selectbox(key='stage:demo').value,expected)
 def test_stored_project_stage_can_be_string(self):
  app=AppTest.from_string(SOURCE.replace("'stage':0", "'stage':'6'")).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.selectbox(key='stage:demo').value,6)
 def test_all_eight_stages(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  for stage in range(7):
   app.selectbox(key='stage:demo').set_value(stage).run(timeout=30)
   self.assertEqual(len(app.exception),0,f'stage {stage}')
   expanders=list(app.expander)
   self.assertLess(next(i for i,e in enumerate(expanders) if e.label=='本步提示词模板'),next(i for i,e in enumerate(expanders) if e.label=='审核与操作记录'))
   self.assertEqual(sum(e.label=='本步提示词模板' for e in expanders),1)
  self.assertTrue(any(b.label=='开始合成视频' for b in app.button))
 def test_add_and_save_shot(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.selectbox(key='stage:demo').set_value(1).run(timeout=30)
  next(b for b in app.button if b.label=='添加镜头').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(len(app.session_state['fixture']['shots']),2)
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
 def test_navigation_buttons_restore_eight_stage_entry(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  self.assertEqual(len([b for b in app.button if b.key and b.key.startswith('step-nav:')]),7)
  app.button(key='step-nav:demo3').click().run(timeout=30)
  self.assertEqual(app.selectbox(key='stage:demo').value,3)
  self.assertTrue(any(b.label=='生成每镜首尾帧规划' for b in app.button))
 def test_generate_story_uses_unsaved_form_input(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  next(t for t in app.text_area if t.label=='故事想法').set_value('这次输入的新想法')
  next(b for b in app.button if b.label=='调用导演完善故事').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.session_state['fixture']['idea'],'这次输入的新想法')
  calls=app.session_state['calls']
  self.assertTrue(any(path.endswith('/generate/story') and method=='POST' for path,method,body in calls))
 def test_video_generation_is_per_shot(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['confirmed']={'4':True};p['shots']=[dict(p['shots'][0],first='f1',last='l1'),{'id':'shot2','title':'第二镜','duration':5,'description':'另一个场景','prompt':'慢推','first':'f2','last':'l2'}];app.session_state['fixture']=p
  # Provide a configured price without invoking any external model.
  source=SOURCE.replace("'models':{}", "'models':{'animator':{'rate':0.5}}")
  app=AppTest.from_string(source);app.session_state['fixture']=p;app.run(timeout=30)
  app.selectbox(key='stage:demo').set_value(5).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(len([b for b in app.button if b.label=='提交本镜生成']),1)
  self.assertIsNotNone(app.button(key='video-generate:shot1'))
  app.selectbox(key='video-shot:demo').set_value('shot2').run(timeout=30)
  self.assertEqual(len([b for b in app.button if b.label=='提交本镜生成']),1)
  self.assertIsNotNone(app.button(key='video-generate:shot2'))
  self.assertFalse(any(b.label=='生成完整视频' for b in app.button))
  next(v for v in app.selectbox if v.label=='生成分辨率').set_value('480p').run(timeout=30)
  next(c for c in app.checkbox if c.key.endswith('shot2')).check().run(timeout=30)
  app.button(key='video-generate:shot2').click().run(timeout=30)
  calls=[(path,body) for path,method,body in app.session_state['calls'] if method=='POST']
  self.assertEqual(calls[-1],('/projects/demo/shots/shot2/video',{'approve':True,'quote':2.5,'resolution':'480p'}))
  self.assertFalse(any(path.endswith('/full-video') for path,body in calls))
 def test_composition_submits_selected_clips_and_edits(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['confirmed']={'5':True};p['shots']=[dict(p['shots'][0],selected='v1')];app.session_state['fixture']=p
  app.session_state['asset_fixture']=[{'id':'v1','shot':'shot1','name':'镜头版本1','mime':'video/mp4','kind':'video'}]
  app.selectbox(key='stage:demo').set_value(6).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  next(b for b in app.button if b.label=='开始合成视频').click().run(timeout=30)
  calls=[body for path,method,body in app.session_state['calls'] if path.endswith('/export') and method=='POST']
  self.assertEqual(calls[-1]['edits']['shot1']['duration'],5.)
  self.assertEqual(calls[-1]['music'],'')
  self.assertEqual(calls[-1]['resolution'],'1080p')
 def test_existing_images_are_listed_previewed_and_can_be_selected(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.session_state['asset_fixture']=[{'id':'picture1','shot':'shot1','name':'已生成尾帧','mime':'image/png','kind':'last','created':1},{'id':'picture2','shot':'','name':'旧版参考图','mime':'image/png','kind':'reference','created':2}]
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  selectors=[v for v in app.selectbox if v.label=='已有图片版本']
  self.assertEqual(selectors[0].value,'')
  self.assertTrue(any('已生成尾帧' in value for value in selectors[0].options))
  self.assertFalse(any('版本预览 ·' in m.value for m in app.markdown))
  [v for v in app.selectbox if v.label=='已有图片版本'][0].set_value('picture1').run(timeout=30)
  self.assertFalse(any('当前已选用' in b.label or b.label=='选用版本' for b in app.button))
  self.assertEqual(app.session_state['fixture']['shots'][0]['first'],'picture1')
  app.checkbox(key='all-images:demoshot1last').check().run(timeout=30)
  selector=[v for v in app.selectbox if v.label=='已有图片版本'][1]
  self.assertTrue(any('旧版参考图' in value for value in selector.options))
 def test_generation_needs_no_global_authorization_checkbox(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  self.assertFalse(any(c.label.startswith('本次允许调用') for c in app.checkbox))
  self.assertFalse(next(b for b in app.button if b.label=='调用导演完善故事').disabled)
 def test_storyboard_is_compact_and_keeps_single_save_flow(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.selectbox(key='stage:demo').set_value(1).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  labels=[b.label for b in app.button]
  for label in ['添加镜头','生成分镜表','保存并继续']:self.assertIn(label,labels)
  self.assertLess(labels.index('生成分镜表'),labels.index('添加镜头'))
  self.assertNotIn('保存分镜表',labels)
  self.assertGreater(labels.index('保存并继续'),labels.index('添加镜头'))
  self.assertNotIn('确认本步并继续',labels)
  self.assertFalse(any(t.label=='画面与动作' for t in app.text_area))
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(app.session_state['fixture']['shots'][0]['prompt'],'固定镜头')
  self.assertTrue(app.session_state['fixture']['confirmed']['1'])
  self.assertEqual(app.selectbox(key='stage:demo').value,2)
 def test_frames_show_one_shot_with_secondary_controls_collapsed(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['shots']=p['shots']+[{'id':'shot2','title':'第二镜','duration':5,'description':'另一个场景','prompt':''}];app.session_state['fixture']=p
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(len([b for b in app.button if b.key and b.key.startswith('frame-pair:')]),1)
  app.selectbox(key='frame-shot:demo').set_value('shot2').run(timeout=30)
  self.assertIsNotNone(app.button(key='frame-pair:shot2'))
  self.assertTrue(any(e.label=='上传与裁切' for e in app.expander))
 def test_switching_shots_does_not_reuse_other_shot_images(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['shots']=[dict(p['shots'][0],first='first1',last='last1'),{'id':'shot2','title':'第二镜','duration':5,'description':'新场景','prompt':''}]
  app.session_state['fixture']=p
  app.session_state['asset_fixture']=[{'id':kind+'1','shot':'shot1','name':kind,'mime':'image/png','kind':kind,'created':1} for kind in ('first','last')]
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  self.assertEqual([v.value for v in app.selectbox if v.label=='已有图片版本'],['first1','last1'])
  app.selectbox(key='frame-shot:demo').set_value('shot2').run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual([v.value for v in app.selectbox if v.label=='已有图片版本'],['',''])
  self.assertFalse(any('first1' in m.value or 'last1' in m.value for m in app.markdown if '/media/' in m.value))
  self.assertTrue(all(not c.value for c in app.checkbox if c.key and c.key.startswith('all-images:')))
  app.selectbox(key='frame-shot:demo').set_value('shot1').run(timeout=30)
  self.assertEqual([v.value for v in app.selectbox if v.label=='已有图片版本'],['first1','last1'])
 def test_shot_feedback_regenerates_only_current_pair(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.session_state['fixture']['shots'][0]['frame_plan']={'first_prompt':'首帧','last_prompt':'尾帧','motion':'动作'}
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  next(t for t in app.text_area if t.label=='本镜头修改意见').set_value('人物坐下').run(timeout=30)
  app.button(key='frame-pair-redraw:shot1').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  calls=[(path,body) for path,method,body in app.session_state['calls'] if path.endswith('/generate-frame-pair') and method=='POST']
  self.assertEqual(calls[-1],('/projects/demo/shots/shot1/generate-frame-pair',{'approve':True,'feedback':'人物坐下'}))
 def test_each_frame_has_its_own_feedback_submission(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  next(t for t in app.text_area if t.label=='首帧修改意见').set_value('人物向左')
  next(b for b in app.button if b.label=='按意见重绘首帧').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  calls=[body for path,method,body in app.session_state['calls'] if path.endswith('/image') and method=='POST']
  self.assertEqual(calls[-1]['kind'],'first');self.assertEqual(calls[-1]['feedback'],'人物向左')
 def test_style_has_top_generation_and_one_save_continue(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.selectbox(key='stage:demo').set_value(2).run(timeout=30)
  labels=[b.label for b in app.button]
  self.assertIn('生成画风与角色方案',labels);self.assertNotIn('保存设定',labels)
  self.assertEqual(labels.count('保存并继续'),1);self.assertNotIn('确认本步并继续',labels)
  next(t for t in app.text_area if t.label=='画风与角色设定').set_value('新的手绘画风')
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.session_state['fixture']['style'],'新的手绘画风')
  self.assertEqual(app.selectbox(key='stage:demo').value,3)
 def test_frames_keep_edits_when_switching_shots_and_save_together(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['shots']=[{**p['shots'][0],'first':'f1','last':'l1'},{'id':'shot2','title':'第二镜','duration':5,'description':'第二个场景','prompt':'','first':'f2','last':'l2'}];app.session_state['fixture']=p
  app.selectbox(key='stage:demo').set_value(3).run(timeout=30)
  self.assertFalse(any(b.label=='保存首尾帧规划' for b in app.button))
  next(t for t in app.text_area if t.label=='首帧画面与构图').set_value('第一镜新构图').run(timeout=30)
  app.selectbox(key='frame-shot:demo').set_value('shot2').run(timeout=30)
  next(t for t in app.text_area if t.label=='首帧画面与构图').set_value('第二镜新构图').run(timeout=30)
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  shots=app.session_state['fixture']['shots']
  self.assertEqual(shots[0]['frame_plan']['first_prompt'],'第一镜新构图')
  self.assertEqual(shots[1]['frame_plan']['first_prompt'],'第二镜新构图')
  self.assertEqual(app.selectbox(key='stage:demo').value,4)
 def test_style_save_failure_to_continue_keeps_saved_content(self):
  source=SOURCE.replace(" if '/confirm/' in path:"," if path.endswith('/confirm/2'):raise RuntimeError('请先确认上一环节')\n if '/confirm/' in path:")
  app=AppTest.from_string(source).run(timeout=30)
  app.selectbox(key='stage:demo').set_value(2).run(timeout=30)
  next(t for t in app.text_area if t.label=='画风与角色设定').set_value('需要保留的画风')
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.session_state['fixture']['style'],'需要保留的画风')
  self.assertEqual(app.selectbox(key='stage:demo').value,2)
  self.assertTrue(any('内容已保存' in error.value for error in app.error))
 def test_prompt_edits_save_together_and_continue(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['shots']=[p['shots'][0],{'id':'shot2','title':'第二镜','duration':5,'description':'另一个镜头','prompt':'旧提示词'}];app.session_state['fixture']=p
  app.selectbox(key='stage:demo').set_value(4).run(timeout=30)
  self.assertFalse(any(b.label=='保存提示词' for b in app.button))
  next(t for t in app.text_area if t.label=='视频提示词').set_value('第一镜新提示词').run(timeout=30)
  app.selectbox(key='prompt-shot:demo').set_value('shot2').run(timeout=30)
  next(t for t in app.text_area if t.label=='视频提示词').set_value('第二镜新提示词').run(timeout=30)
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  shots=app.session_state['fixture']['shots']
  self.assertEqual([s['prompt'] for s in shots],['第一镜新提示词','第二镜新提示词'])
  self.assertEqual(app.selectbox(key='stage:demo').value,5)
 def test_video_versions_save_together_and_continue(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['shots']=[p['shots'][0],{'id':'shot2','title':'第二镜','duration':5,'description':'另一个镜头','prompt':'提示词'}];app.session_state['fixture']=p
  app.session_state['asset_fixture']=[{'id':'v1','shot':'shot1','name':'第一镜版本','mime':'video/mp4','kind':'video'},{'id':'v2','shot':'shot2','name':'第二镜版本','mime':'video/mp4','kind':'video'}]
  app.selectbox(key='stage:demo').set_value(5).run(timeout=30)
  self.assertFalse(any(b.label=='选用此视频' for b in app.button))
  app.selectbox(key='video-shot:demo').set_value('shot2').run(timeout=30)
  next(b for b in app.button if b.label=='保存并继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual([s['selected'] for s in app.session_state['fixture']['shots']],['v1','v2'])
  self.assertEqual(app.selectbox(key='stage:demo').value,6)
 def test_top_compose_action_uses_current_parameters(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['confirmed']={'5':True};p['shots']=[dict(p['shots'][0],selected='v1')];app.session_state['fixture']=p
  app.session_state['asset_fixture']=[{'id':'v1','shot':'shot1','name':'镜头版本','mime':'video/mp4','kind':'video'}]
  app.selectbox(key='stage:demo').set_value(6).run(timeout=30)
  labels=[b.label for b in app.button];self.assertLess(labels.index('开始合成视频'),labels.index('完成制作'))
  next(t for t in app.selectbox if t.label=='成片输出分辨率').set_value('720p').run(timeout=30)
  next(b for b in app.button if b.label=='开始合成视频').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  bodies=[body for path,method,body in app.session_state['calls'] if path.endswith('/export') and method=='POST']
  self.assertEqual(bodies[-1]['resolution'],'720p')
 def test_task_rail_can_collapse_without_stopping_status_checks(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  toggle=app.button(key='task-rail-toggle:demo');self.assertEqual(toggle.label,'收起')
  self.assertTrue(any('position:fixed' in m.value and 'production-task-dock' in m.value for m in app.markdown))
  toggle.click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.button(key='task-rail-toggle:demo').label,'动态')
  before=len(app.session_state['calls']);app.run(timeout=30)
  self.assertTrue(any(path.endswith('/activity') for path,method,body in app.session_state['calls'][before:]))
  app.button(key='task-rail-toggle:demo').click().run(timeout=30)
  self.assertEqual(app.button(key='task-rail-toggle:demo').label,'收起')
  self.assertEqual(len(app.exception),0)
 def test_story_has_one_save_continue_and_uses_current_inputs(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  labels=[b.label for b in app.button]
  self.assertIn('保存继续',labels);self.assertNotIn('保存故事与要求',labels);self.assertNotIn('确认本步并继续',labels)
  next(t for t in app.text_area if t.label=='故事想法').set_value('新的故事想法')
  next(t for t in app.text_area if t.label=='完整故事').set_value('新完成的故事')
  next(b for b in app.button if b.label=='保存继续').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.session_state['fixture']['idea'],'新的故事想法')
  self.assertEqual(app.session_state['fixture']['story'],'新完成的故事')
  self.assertEqual(app.selectbox(key='stage:demo').value,1)
 def test_delete_only_checked_shot_and_preserve_other_content(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  p=dict(app.session_state['fixture']);p['shots']=[p['shots'][0],{'id':'keep','title':'保留镜头','duration':5,'description':'保留描述','prompt':'保留提示词','first':'f','last':'l'}];app.session_state['fixture']=p
  app.selectbox(key='stage:demo').set_value(1).run(timeout=30)
  app.session_state['shot-table:demo:0:1']={'edited_rows':{0:{'remove':True}},'added_rows':[],'deleted_rows':[]}
  next(b for b in app.button if b.label=='删除勾选镜头').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  shots=app.session_state['fixture']['shots']
  self.assertEqual(len(shots),1);self.assertEqual(shots[0]['id'],'keep');self.assertEqual(shots[0]['prompt'],'保留提示词');self.assertEqual(shots[0]['first'],'f')
 def test_delete_without_selection_does_not_change_project(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  app.selectbox(key='stage:demo').set_value(1).run(timeout=30)
  next(b for b in app.button if b.label=='删除勾选镜头').click().run(timeout=30)
  self.assertEqual(len(app.session_state['fixture']['shots']),1)
  self.assertTrue(any('请先勾选' in w.value for w in app.warning))
 def test_audit_records_share_collapsible_right_rail(self):
  source=SOURCE.replace("'audit':[]", "'audit':[{'time':1000000000,'text':'审核已完成'}]")
  app=AppTest.from_string(source).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(sum(e.label=='审核与操作记录' for e in app.expander),1)
  self.assertTrue(any(e.label=='制作任务' for e in app.expander))
  self.assertEqual(sum(e.label=='自动修订历史' for e in app.expander),1)
  self.assertTrue(any('审核已完成' in m.value for m in app.markdown))
  app.button(key='task-rail-toggle:demo').click().run(timeout=30)
  self.assertFalse(any(e.label=='审核与操作记录' for e in app.expander))
  self.assertFalse(any(e.label=='自动修订历史' for e in app.expander))
  app.button(key='task-rail-toggle:demo').click().run(timeout=30)
  self.assertTrue(any(e.label=='审核与操作记录' for e in app.expander))
if __name__=='__main__':unittest.main()

"""Full-page navigation from project-card fragments, without provider calls."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class ProjectNavigation(unittest.TestCase):
 def app(self,last_inputs=None,preview=False):
  source=Path(__file__).with_name('streamlit_app.py').read_text()
  base={'id':'custom','mode':'custom','name':'自定义项目','idea':'原始想法','story':'已保存的故事','style':'水彩','duration':30,'ratio':'16:9','budget':100,'structure':'片段式','music':False,'subtitles':False,'shots':[],'confirmed':{},'reviews':{},'spent':0,'reserved':0,'revision':0,'stage':0}
  quick={**base,'id':'quick','mode':'quick','name':'快速项目','story':'原始旁白','quick_inputs':{'video_count':2,'target_duration':60}}
  if last_inputs:quick['last_video_inputs']=last_inputs
  if preview:quick['final_video']='preview-video'
  boot={'projects':[base,quick],'models':{},'catalog':{},'prompts':{},'ffmpeg':True}
  stub="""def api(path,method='GET',body=None,**kwargs):
 if path=='/projects' and method=='POST':
  st.session_state['created_body']=body
  return next(p for p in BOOT['projects'] if p['mode']==body['mode'])
 if path=='/bootstrap':return BOOT
 if path=='/quick/settings':return {'voice_name':'zh-CN-XiaoxiaoNeural-Female','voice_rate':1.0,'subtitle_provider':'edge'}
 if path.startswith('/quick/jobs'):return []
 if path.endswith('/activity'):return {'jobs':[],'assets':[],'audit':[]}
 if path.endswith('/repair-versions') or path.endswith('/quick-history'):return []
 return next(p for p in BOOT['projects'] if path=='/projects/'+p['id'])
""".replace('BOOT',repr(boot))
  start=source.index('def api(');end=source.index('def do(',start)
  source=source[:start]+stub+'\n'+source[end:]
  return AppTest.from_string(source).run(timeout=30)
 def test_edit_quick_project_opens_editor_with_saved_inputs(self):
  app=self.app();app.button(key='open-workspace:quick').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.session_state['page'],'快速生成视频')
  self.assertEqual(next(t for t in app.text_area if t.label=='旁白文案').value,'原始旁白')
  self.assertEqual(next(t for t in app.selectbox if t.label=='目标片长').value,60)
  self.assertFalse(any(t.label=='编辑项目' for t in app.button))
 def test_edit_custom_project_opens_workspace_with_saved_story(self):
  import sys
  sys.path.insert(0,str(Path(__file__).parent.resolve()))
  app=self.app();app.button(key='open-workspace:custom').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.session_state['page'],'分镜工作区')
  self.assertEqual(next(t for t in app.text_area if t.label=='完整故事').value,'已保存的故事')
  self.assertFalse(any(t.label=='编辑项目' for t in app.button))
 def test_edit_restores_last_generated_state_instead_of_draft(self):
  inputs={'video_subject':'生成时主题','video_script':'生成时旁白','target_duration':45,'voice_rate':1.3,'video_aspect':'1:1'}
  app=self.app(inputs);app.button(key='open-workspace:quick').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(next(t for t in app.text_input if t.label=='视频主题').value,'生成时主题')
  self.assertEqual(next(t for t in app.text_area if t.label=='旁白文案').value,'生成时旁白')
  self.assertEqual(next(t for t in app.selectbox if t.label=='目标片长').value,45)
  self.assertEqual(next(t for t in app.slider if t.label=='语速').value,1.3)
  self.assertFalse(any(t.value=='操作与生成历史' for t in app.subheader))
 def test_creation_dialog_routes_both_modes(self):
  import sys
  sys.path.insert(0,str(Path(__file__).parent.resolve()))
  for mode,page in [('quick','快速生成视频'),('custom','分镜工作区')]:
   app=self.app()
   self.assertFalse(any(r.label=='制作方式' for r in app.radio))
   app.button(key='create-project-open').click().run(timeout=30)
   self.assertEqual(len(app.exception),0)
   app.radio(key='create-mode').set_value(mode).run(timeout=30)
   next(t for t in app.text_input if t.label=='项目名称').set_value('弹窗新项目')
   next(b for b in app.button if b.label=='创建并进入').click().run(timeout=30)
   self.assertEqual(len(app.exception),0)
   self.assertEqual(app.session_state['created_body']['mode'],mode)
   self.assertEqual(app.session_state['page'],page)
 def test_delete_dialog_can_cancel(self):
  app=self.app();self.assertEqual(len([b for b in app.button if b.label=='删除项目']),2)
  app.button(key='delete-project:custom').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertTrue(any('确定删除「自定义项目」' in m.value for m in app.markdown))
  app.button(key='delete-cancel').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertFalse(any(b.label=='确认删除' for b in app.button))
 def test_cancel_creation_dialog_does_not_create_project(self):
  app=self.app();app.button(key='create-project-open').click().run(timeout=30)
  next(b for b in app.button if b.label=='取消').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertNotIn('created_body',app.session_state)
  self.assertFalse(any(r.label=='制作方式' for r in app.radio))
 def test_project_cards_show_inline_video_and_fixed_placeholders(self):
  app=self.app(preview=True)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(len(app.get('video')),1)
  self.assertFalse(any(e.label=='预览成片' for e in app.expander))
  self.assertEqual(len([m for m in app.markdown if '<div class="project-placeholder">' in m.value]),1)
  self.assertEqual(len([b for b in app.button if b.label=='编辑项目']),2)
  buttons=list(app.button)
  self.assertGreater(buttons.index(app.button(key='projects:next')),max(i for i,b in enumerate(buttons) if b.label=='编辑项目'))
 def test_both_editor_types_can_return_to_project_overview(self):
  import sys
  sys.path.insert(0,str(Path(__file__).parent.resolve()))
  for project in ('quick','custom'):
   app=self.app();app.button(key='open-workspace:'+project).click().run(timeout=30)
   self.assertEqual(len(app.exception),0)
   self.assertTrue(any('项目路径' in m.value for m in app.markdown))
   if project=='quick':
    self.assertTrue(any('href="#quick-script"' in m.value and 'href="#quick-results"' in m.value for m in app.markdown))
   self.assertTrue(any('href="?page=overview"' in m.value for m in app.markdown))
   self.assertFalse(any(b.label=='返回项目总览' for b in app.button))
   app.query_params['page']='overview'
   app.run(timeout=30)
   self.assertEqual(len(app.exception),0)
   self.assertEqual(app.session_state['page'],'项目总览')
   self.assertIn('项目总览',[v.value for v in app.title])
if __name__=='__main__':unittest.main()

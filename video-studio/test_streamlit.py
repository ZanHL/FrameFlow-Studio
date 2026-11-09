"""Streamlit rendering tests; read-only local API access, no provider calls."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
class Pages(unittest.TestCase):
 def test_quick_and_settings(self):
  app=AppTest.from_file(str(Path(__file__).with_name('streamlit_app.py'))).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertIn('项目总览',[v.value for v in app.title])
  self.assertNotIn('快速生成视频',app.sidebar.radio[0].options)
  self.assertFalse(any(r.label=='制作方式' for r in app.radio))
  self.assertIsNotNone(app.button(key='create-project-open'))
  app.sidebar.radio[0].set_value('设置').run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual([t.label for t in app.tabs],['模型与连接','素材服务','配音与字幕','提示词'])
  self.assertIn('角色模型',[e.value for e in app.subheader])
  self.assertNotIn('大语言模型',[e.value for e in app.subheader])
  self.assertFalse(any('备份' in t.label or '缓存' in t.label or '发布' in t.label for t in app.tabs))
 def test_quick_page_has_compact_settings(self):
  path=Path(__file__).with_name('streamlit_app.py')
  source=path.read_text().replace('if not boot:st.stop()',"if not boot:st.stop()\nboot['projects'].append({'id':'test-quick','name':'快速项目','mode':'quick','idea':'测试','story':'','ratio':'9:16'})")
  source=source.replace("jobs=api('/quick/jobs?project='+pid)",'jobs=[]')
  app=AppTest.from_string(source)
  app.session_state['page']='快速生成视频';app.session_state['quick_project']='test-quick'
  app.run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertIn('画幅',[e.label for e in app.selectbox])
  self.assertIn('目标片长',[e.label for e in app.selectbox])
  self.assertIn('开始生成视频',[e.label for e in app.button])
 def test_quick_edit_restores_saved_parameters(self):
  path=Path(__file__).with_name('streamlit_app.py')
  fixture={'id':'edit-quick','name':'编辑恢复','mode':'quick','idea':'原主题','story':'原文案','ratio':'1:1','quick_inputs':{'target_duration':60,'video_count':2,'voice_rate':1.25,'video_source':'pixabay','subtitle_enabled':False,'font_size':48,'video_fit_mode':'contain','bgm_type':'random','bgm_volume':.35}}
  source=path.read_text().replace('if not boot:st.stop()',"if not boot:st.stop()\nboot['projects'].append("+repr(fixture)+")").replace("jobs=api('/quick/jobs?project='+pid)",'jobs=[]')
  app=AppTest.from_string(source);app.session_state['page']='快速生成视频';app.session_state['quick_project']='edit-quick';app.run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(next(x for x in app.text_input if x.label=='视频主题').value,'原主题')
  self.assertEqual(next(x for x in app.text_area if x.label=='旁白文案').value,'原文案')
  self.assertEqual(next(x for x in app.selectbox if x.label=='目标片长').value,60)
  self.assertEqual(next(x for x in app.number_input if x.label=='生成数量').value,2)
  self.assertEqual(next(x for x in app.slider if x.label=='语速').value,1.25)
  self.assertEqual(next(x for x in app.selectbox if x.label=='背景音乐').value,'随机音乐')
  self.assertEqual(next(x for x in app.slider if x.label=='背景音乐音量').value,35)
 def test_card_pagination_slices_and_clamps(self):
  code=Path(__file__).with_name('streamlit_app.py').read_text()
  helper=code[code.index('def paginate('):code.index('def upload(')]
  app=AppTest.from_string("import streamlit as st\n"+helper+"\nitems=paginate(list(range(st.session_state.get('count',13))),'test')\nst.session_state['visible']=items")
  app.run();self.assertEqual(app.session_state['visible'],list(range(6)))
  app.button(key='test:next').click().run();self.assertEqual(app.session_state['visible'],list(range(6,12)))
  app.button(key='test:prev').click().run();self.assertEqual(app.session_state['visible'],list(range(6)))
  app.number_input(key='test:page').set_value(3).run();self.assertEqual(app.session_state['visible'],[12])
  app.session_state['count']=0;app.run();self.assertEqual(app.session_state['visible'],[])
  self.assertEqual(len(app.exception),0)
 def test_live_call_logs_page_is_reachable(self):
  app=AppTest.from_file(str(Path(__file__).with_name('streamlit_app.py'))).run(timeout=30)
  app.sidebar.radio[0].set_value('调用日志').run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertIn('调用日志',[v.value for v in app.title])
  self.assertTrue(any(t.label=='刷新日志' for t in app.button))
if __name__=='__main__':unittest.main()

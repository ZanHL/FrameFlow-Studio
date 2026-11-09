"""Settings rendering and independent saves, with a fake API and no provider calls."""
import json,unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).parent
class Settings(unittest.TestCase):
 def app(self):
  catalog=json.loads((ROOT/'model-catalog.json').read_text())
  model=catalog['volcengine']['models']['director'][0]['id']
  fixture={'projects':[],'models':{'director':{'platform':'volcengine','model':model,'has_key':True}},'catalog':catalog,'prompts':{'story':{'name':'故事','value':'原始提示词 {{idea}}'}},'ffmpeg':True}
  settings={'voice_name':'zh-CN-XiaoxiaoNeural-Female','voice_rate':1.,'subtitle_provider':'edge','whisper_model_size':'small','keys':{'pexels':False,'pixabay':False,'coverr':False}}
  stub='''def api(path,method='GET',body=None,**kwargs):
 if 'fake_boot' not in st.session_state:st.session_state['fake_boot']=FIXTURE
 if 'fake_settings' not in st.session_state:st.session_state['fake_settings']=SETTINGS
 if method=='POST':
  st.session_state['last_save']=(path,body)
  if path=='/quick/settings':st.session_state['fake_settings'].update({k:v for k,v in body.items() if k!='keys'})
  return {'message':'连接正常','ok':True}
 if path=='/models/codex/status':return {'installed':True,'connected':True,'models':[{'id':'local-codex-model','name':'本机模型'}],'message':'已登录','login':{}}
 if path=='/bootstrap':return st.session_state['fake_boot']
 if path=='/quick/settings':return st.session_state['fake_settings']
 raise ValueError(path)
'''.replace('FIXTURE',repr(fixture)).replace('SETTINGS',repr(settings))
  source=(ROOT/'streamlit_app.py').read_text();a=source.index('def api(');b=source.index('def do(',a)
  source=source[:a]+stub+'\n'+source[b:]
  app=AppTest.from_string(source);app.session_state['page']='设置';return app.run(timeout=30)
 def test_model_save_remains_scoped_to_role(self):
  app=self.app();self.assertEqual(len(app.exception),0)
  next(t for t in app.text_input if t.label=='API Key').set_value('test-dummy-key')
  next(b for b in app.button if b.label=='保存模型配置').click().run(timeout=30)
  self.assertEqual(len(app.exception),0)
  path,body=app.session_state['last_save'];self.assertEqual(path,'/models/director');self.assertEqual(body['key'],'test-dummy-key')
 def test_voice_and_subtitles_save_independently(self):
  app=self.app()
  next(t for t in app.slider if t.label=='默认语速').set_value(1.25)
  next(b for b in app.button if b.label=='保存配音设置').click().run(timeout=30)
  self.assertEqual(set(app.session_state['last_save'][1]),{'voice_name','voice_rate'})
  next(r for r in app.radio if r.label=='字幕生成方式').set_value('whisper').run(timeout=30)
  self.assertFalse(next(t for t in app.selectbox if t.label=='Whisper 模型').disabled)
  next(b for b in app.button if b.label=='保存字幕设置').click().run(timeout=30)
  self.assertEqual(app.session_state['last_save'][1]['subtitle_provider'],'whisper')
  self.assertNotIn('voice_name',app.session_state['last_save'][1])
  self.assertEqual(len(app.exception),0)
 def test_material_and_prompt_saves_keep_separate_payloads(self):
  app=self.app()
  next(t for t in app.text_input if t.label=='Pexels API Key').set_value('dummy-material-key')
  next(b for b in app.button if b.label=='保存 Pexels').click().run(timeout=30)
  self.assertEqual(app.session_state['last_save'],('/quick/settings',{'keys':{'pexels':'dummy-material-key'}}))
  next(t for t in app.text_area if t.label=='提示词模板').set_value('新提示词 {{idea}}')
  next(b for b in app.button if b.label=='保存提示词').click().run(timeout=30)
  self.assertEqual(app.session_state['last_save'],('/prompts/story',{'value':'新提示词 {{idea}}'}))
  self.assertEqual(len(app.exception),0)
 def test_codex_channel_has_local_models_and_no_api_key_field(self):
  app=self.app();app.selectbox(key='provider:director').set_value('openai_codex_cli').run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertFalse(any(t.label=='API Key' for t in app.text_input))
  self.assertTrue(any('本机模型' in option for option in next(t for t in app.selectbox if t.label=='模型').options))
  next(b for b in app.button if b.label=='保存模型配置').click().run(timeout=30)
  body=app.session_state['last_save'][1];self.assertEqual(body['platform'],'openai_codex_cli');self.assertEqual(body['key'],'')
 def test_custom_channel_accepts_endpoint_model_and_protocol(self):
  app=self.app();app.selectbox(key='provider:director').set_value('custom').run(timeout=30)
  self.assertEqual(len(app.exception),0)
  next(t for t in app.text_input if t.label=='模型 ID').set_value('custom-codex')
  next(t for t in app.text_input if t.label=='兼容接口地址').set_value('https://proxy.example/v1')
  next(t for t in app.selectbox if t.label=='接口协议').set_value('responses')
  next(b for b in app.button if b.label=='保存模型配置').click().run(timeout=30)
  body=app.session_state['last_save'][1]
  self.assertTrue(body['custom_model']);self.assertEqual(body['model'],'custom-codex');self.assertEqual(body['api'],'responses')
if __name__=='__main__':unittest.main()

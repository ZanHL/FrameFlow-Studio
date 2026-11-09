"""Exercise real UI API handlers without network or paid model calls."""
import ast,unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
text=Path(__file__).with_name('streamlit_app.py').read_text();tree=ast.parse(text)
handlers='\n'.join(ast.get_source_segment(text,n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['api','do'])
SOURCE='''
import streamlit as st
from types import SimpleNamespace
API='http://test.local'
class HTTPError(Exception):pass
class RequestException(Exception):pass
class Response:
 def __init__(self,path):self.path=path
 def raise_for_status(self):
  if self.path.endswith('/fail'):raise HTTPError()
 def json(self):return {'detail':'模型权限不足'} if self.path.endswith('/fail') else {'id':'job1'}
requests=SimpleNamespace(request=lambda method,path,**kw:Response(path),HTTPError=HTTPError,RequestException=RequestException)
'''+handlers+'''
if st.session_state.get('_action_feedback'):st.success(st.session_state.pop('_action_feedback'))
if st.button('提交任务'):
 if do(lambda:api('/generate','POST',{})):st.rerun()
if st.button('模拟错误'):do(lambda:api('/fail','POST',{}))
'''
class Feedback(unittest.TestCase):
 def test_submission_feedback_survives_rerun(self):
  app=AppTest.from_string(SOURCE).run();app.button[0].click().run()
  self.assertEqual(len(app.exception),0);self.assertTrue(any('任务已提交' in e.value for e in app.success))
 def test_failure_is_visible_and_not_reported_as_success(self):
  app=AppTest.from_string(SOURCE).run();app.button[1].click().run()
  self.assertEqual(len(app.exception),0);self.assertTrue(any('模型权限不足' in e.value for e in app.error));self.assertEqual(len(app.success),0)
if __name__=='__main__':unittest.main()

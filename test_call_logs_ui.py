"""Log page renders metrics, details and pagination with a fake API."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
SOURCE='''
import sys
sys.path.insert(0,ROOT)
import streamlit as st
from studio.ui.call_logs import render

def api(path):
 st.session_state['query']=path
 return {'items':[{'id':'record1','created':1000000000,'role':'director','platform':'openai','model':'test-model','operation':'/responses','status':'succeeded','elapsed_ms':200,'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15},'parameters':{},'project':'','job':''}],'total':1,'page':1,'page_size':12,'totals':{'total_tokens':15},'failed':0}
render(api,lambda fn:fn(),{'catalog':{'openai':{'name':'OpenAI'}},'projects':[]},{'director':'总导演','artist':'画师'})
'''.replace('ROOT',repr(str(Path(__file__).parent.resolve())))
class LogsUI(unittest.TestCase):
 def test_logs_page_and_filters(self):
  app=AppTest.from_string(SOURCE).run(timeout=30)
  self.assertEqual(len(app.exception),0)
  self.assertEqual(app.title[0].value,'调用日志')
  self.assertEqual(len(app.dataframe),1)
  next(t for t in app.selectbox if t.label=='创作角色').set_value('artist').run(timeout=30)
  self.assertIn('role=artist',app.session_state['query'])
  self.assertFalse(next(t for t in app.button if t.label=='上一页').disabled is False)
  self.assertTrue(any(t.label=='导出本页 CSV' for t in app.get('download_button')))
if __name__=='__main__':unittest.main()

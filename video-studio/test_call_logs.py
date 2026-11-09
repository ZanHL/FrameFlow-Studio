"""Persisted telemetry, accurate totals, remote deduplication and privacy contracts."""
import os,json,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
os.environ['STUDIO_DATA']=tempfile.mkdtemp(prefix='studio-call-log-api-')
os.environ['STUDIO_KEY_STORE']='memory'
import server as s
from studio.models.call_logs import CallLogs,normalize_usage
class Logs(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();path=Path(self.temp.name)/'calls.db'
  def db():
   conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row;return conn
  self.db=db;self.logs=CallLogs(db,lambda t:str(t).replace('secret-key','[hidden]'))
  self.config={'role':'director','platform':'openai','model':'model','base':'https://api.example/v1'}
 def tearDown(self):self.temp.cleanup()
 def test_usage_normalization_keeps_cache_as_detail(self):
  usage=normalize_usage({'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,'prompt_tokens_details':{'cached_tokens':4}}})
  self.assertEqual(usage,{'input_tokens':10,'output_tokens':5,'total_tokens':15,'cached_tokens':4})
  self.assertEqual(normalize_usage({'usage':{'input_tokens':20,'output_tokens':2,'cached_input_tokens':10}})['total_tokens'],22)
 def test_remote_polls_count_usage_once(self):
  c={**self.config,'role':'animator'}
  for _ in range(3):
   handle=self.logs.start(c,'GET','/contents/generations/tasks/remote-1')
   self.logs.finish(handle,c,'succeeded',{'usage':{'output_tokens':20},'status':'succeeded','duration':5})
  result=self.logs.list(days=0)
  self.assertEqual(result['total'],3);self.assertEqual(result['totals']['total_tokens'],20);self.assertEqual(result['totals']['video_seconds'],5)
 def test_error_is_redacted_and_inputs_are_not_logged(self):
  handle=self.logs.start(self.config,'POST','/images/generations',{'prompt':'private-prompt','image':'private-image','n':1})
  self.logs.finish(handle,self.config,'failed',error='bad secret-key')
  text=json.dumps(self.logs.list(days=0))
  self.assertNotIn('secret-key',text);self.assertNotIn('private-prompt',text);self.assertNotIn('private-image',text)
  self.assertEqual(self.logs.list(days=0)['failed'],1)
 def test_missing_usage_stays_unknown_and_image_count_uses_response(self):
  handle=self.logs.start(self.config,'GET','/models');self.logs.finish(handle,self.config,'succeeded',{})
  self.assertEqual(self.logs.list(days=0)['totals'],{})
  handle=self.logs.start(self.config,'POST','/images/generations',{'n':3})
  self.logs.finish(handle,self.config,'succeeded',{'data':[{'url':'secret-url'}]})
  self.assertEqual(self.logs.list(days=0)['totals']['images'],1)
 def test_pagination_filter_and_restart_persistence(self):
  for i in range(13):
   with self.logs.context(project='p',job='j'):
    h=self.logs.start(self.config,'POST','/responses')
    self.logs.finish(h,self.config,'succeeded',{'usage':{'input_tokens':1,'output_tokens':2}})
  rows=self.logs.list(project='p',page=2,page_size=12,days=0)
  self.assertEqual(len(rows['items']),1);self.assertEqual(rows['totals']['total_tokens'],39)
  h=self.logs.start(self.config,'POST','/responses');other=CallLogs(self.db,lambda t:t)
  self.assertEqual(other.list(status='interrupted',days=0)['total'],1)
  self.assertEqual(other.list(project='p',days=0)['items'][0]['job'],'j')
 def test_transport_records_context_usage_and_request_id(self):
  model='log-'+uuid.uuid4().hex;c={**self.config,'model':model,'protocol':'compatible'}
  s.KEYS['director']='secret-key'
  response=type('Response',(),{'status_code':200,'headers':{'x-request-id':'req-test'},'json':lambda self:{'choices':[{'message':{'content':'private-output'}}],'usage':{'prompt_tokens':7,'completion_tokens':3}}})()
  with patch.object(s,'safe_url',side_effect=lambda u:u),patch.object(s.requests,'request',return_value=response),s.CALL_LOGS.context(project='project-test',job='job-test'):
   s.call(c,'POST','/chat/completions',json={'messages':[{'content':'private-input'}]})
  result=s.CALL_LOGS.list(model=model,days=0);row=result['items'][0]
  self.assertEqual(result['totals']['total_tokens'],10);self.assertEqual(row['project'],'project-test');self.assertEqual(row['job'],'job-test');self.assertEqual(row['request_id'],'req-test')
  self.assertNotIn('private-output',json.dumps(result));self.assertNotIn('private-input',json.dumps(result));self.assertNotIn('secret-key',json.dumps(result))
 def test_failed_transport_is_recorded_without_guessing_usage(self):
  import requests
  model='failure-'+uuid.uuid4().hex;c={**self.config,'model':model,'protocol':'compatible'}
  with patch.object(s,'safe_url',side_effect=lambda u:u),patch.object(s.requests,'request',side_effect=requests.Timeout()):
   with self.assertRaises(s.HTTPException):s.call(c,'POST','/responses')
  result=s.CALL_LOGS.list(model=model,days=0)
  self.assertEqual(result['failed'],1);self.assertEqual(result['totals'],{})
if __name__=='__main__':unittest.main()

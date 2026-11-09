"""Role channel contracts; mock transports so no paid model request occurs."""
import os,tempfile,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['STUDIO_DATA']=tempfile.mkdtemp(prefix='studio-channel-test-')
os.environ['STUDIO_KEY_STORE']='memory'
import server as s
from studio.models import codex_cli

class Channels(unittest.TestCase):
 def setUp(self):self.p=s.create({'name':'渠道测试'})
 def test_codex_cli_configuration_needs_no_api_key(self):
  c=s.save_model('director',{'platform':'openai_codex_cli','model':'gpt-5.3-codex','timeout':600})
  self.assertFalse(c['has_key']);self.assertEqual(s.config('director')['protocol'],'codex_cli')
  with patch.object(codex_cli,'generate_text',return_value='故事正文') as run:
   self.assertEqual(s.llm(self.p,'story','创作'),'故事正文')
  self.assertEqual(run.call_args.args[1:3],('gpt-5.3-codex',600))
 def test_artist_cli_imports_generated_image(self):
  s.save_model('artist',{'platform':'openai_codex_cli','model':'gpt-6.1','custom_model':True})
  content=b'\x89PNG\r\n\x1a\nimage'
  def run(command,**kwargs):
   image=Path(kwargs['cwd'])/'generated.png';image.write_bytes(content)
   Path(command[command.index('--output-last-message')+1]).write_text(json.dumps({'path':str(image)}))
   self.assertIn('image_generation',command)
   return subprocess.CompletedProcess(command,0,'','')
  with patch.object(codex_cli,'cli_path',return_value='/bin/codex'),patch.object(codex_cli.subprocess,'run',side_effect=run):
   self.assertEqual(codex_cli.generate_image('画图','gpt-6.1'),content)
  with patch.object(codex_cli,'generate_image',return_value=content),patch.object(s,'call') as http:
   aid=s.render_image_asset(self.p,s.config('artist'),'style','','水彩')
   self.assertEqual(s.asset(aid)['mime'],'image/png');http.assert_not_called()
 def test_responses_api_uses_correct_endpoint_and_output(self):
  s.save_model('director',{'platform':'openai_codex_api','model':'gpt-5.3-codex','key':'dummy','reasoning':'high'})
  payload={'status':'completed','output':[{'type':'reasoning'},{'type':'message','content':[{'type':'output_text','text':'分镜正文'}]}]}
  with patch.object(s,'call',return_value=payload) as call:
   self.assertEqual(s.llm(self.p,'story','test'),'分镜正文')
  self.assertEqual(call.call_args.args[2],'/responses')
  body=call.call_args.kwargs['json'];self.assertFalse(body['store']);self.assertEqual(body['reasoning'],{'effort':'high'})
 def test_openai_codex_preset_automatically_selects_responses(self):
  c=s.save_model('director',{'platform':'openai','model':'gpt-5.3-codex','key':'dummy'})
  self.assertEqual(c['protocol'],'responses')
 def test_custom_endpoint_keys_are_isolated(self):
  with patch.object(s,'safe_url',side_effect=lambda u:u):
   first=s.save_model('director',{'platform':'custom','model':'my-codex','custom_model':True,'base':'https://one.example/v1','key':'first-key'})
   second=s.save_model('director',{'platform':'custom','model':'other','custom_model':True,'base':'https://two.example/v1','key':'second-key'})
   restored=s.save_model('director',{'platform':'custom','model':'my-codex','custom_model':True,'base':first['base']})
  self.assertEqual(s.KEYS['director'],'first-key');self.assertNotIn('first-key',json.dumps(s.bootstrap()))
  self.assertNotEqual(s.secret_account('director','custom',first['base']),s.secret_account('director','custom',second['base']))
 def test_custom_endpoint_rejects_loopback_before_storing_key(self):
  with patch.object(s.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaises(s.HTTPException):s.save_model('director',{'platform':'custom','model':'my-codex','custom_model':True,'base':'https://localhost/v1','key':'blocked'})
 def test_custom_model_requires_explicit_choice_and_stays_role_bound(self):
  with self.assertRaises(s.HTTPException):s.save_model('director',{'platform':'openai','model':'unlisted'})
  with self.assertRaises(s.HTTPException):s.save_model('artist',{'platform':'openai','model':'unlisted','custom_model':True})
 def test_cli_runs_only_text_in_isolated_readonly_directory(self):
  captured={}
  def run(command,**kwargs):
   captured.update(command=command,kwargs=kwargs)
   Path(command[command.index('--output-last-message')+1]).write_text('最终文本')
   return subprocess.CompletedProcess(command,0,json.dumps({'type':'thread.completed','usage':{'input_tokens':12,'output_tokens':4,'cached_input_tokens':3}}),'')
  with patch.object(codex_cli,'cli_path',return_value='/bin/codex'),patch.object(codex_cli.subprocess,'run',side_effect=run),patch.dict(os.environ,{'CODEX_API_KEY':'should-not-leak'}):
   self.assertEqual(codex_cli.generate_text('主题','gpt-5.3-codex'),'最终文本')
  self.assertEqual(codex_cli.LAST_USAGE.get()['output_tokens'],4)
  command=captured['command'];self.assertIn('--ignore-user-config',command);self.assertIn('read-only',command)
  self.assertIn('shell_tool',command);self.assertIn('--ephemeral',command)
  self.assertNotIn('CODEX_API_KEY',captured['kwargs']['env']);self.assertNotIn('主题',' '.join(command))
 def test_cli_errors_do_not_expose_stderr(self):
  with patch.object(codex_cli,'cli_path',return_value='/bin/codex'),patch.object(codex_cli.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','secret-token')):
   with self.assertRaises(codex_cli.CodexError) as error:codex_cli.generate_text('t','model')
  self.assertNotIn('secret-token',str(error.exception))
 def test_readonly_status_does_not_generate(self):
  state={'installed':True,'connected':True,'models':[{'id':'gpt-5.3-codex'}],'message':'已登录'}
  s.save_model('director',{'platform':'openai_codex_cli','model':'gpt-5.3-codex'})
  with patch.object(codex_cli,'status',return_value=state),patch.object(codex_cli,'generate_text') as generation:
   self.assertTrue(s.test_model('director')['connected']);generation.assert_not_called()
if __name__=='__main__':unittest.main()

import importlib.util,json,os,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
os.environ['STUDIO_KEY_STORE']='memory'
os.environ['STUDIO_DATA']=tempfile.mkdtemp(prefix='studio-tests-')
spec=importlib.util.spec_from_file_location('studio_server',Path(__file__).with_name('server.py'));s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class StudioTests(unittest.TestCase):
 def setUp(self):self.p=s.create({'name':'测试短片','idea':'一封信'})
 def patch(self,**kwargs):self.p=s.update_project(self.p['id'],kwargs);return self.p
 def test_delete_project_cleans_assets(self):
  pid=self.p['id'];other=s.create({'name':'保留'})
  aid=s.add_asset(pid,'style','','图片',b'image','image/png');path=s.MEDIA/s.asset(aid)['path']
  self.assertTrue(s.delete_project(pid)['ok']);self.assertFalse(path.exists())
  with self.assertRaises(s.HTTPException):s.project(pid)
  self.assertEqual(s.project(other['id'])['name'],'保留')
 def test_delete_project_blocks_active_jobs(self):
  for status in ('queued','running','submitted'):
   with s.db() as conn:conn.execute('INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?)',('delete-job',self.p['id'],'video',status,'{}'))
   with self.assertRaises(s.HTTPException) as error:s.delete_project(self.p['id'])
   self.assertEqual(error.exception.status_code,409)
   self.assertEqual(s.project(self.p['id'])['id'],self.p['id'])
  with s.db() as conn:conn.execute("UPDATE jobs SET status='succeeded' WHERE id='delete-job'")
  self.assertTrue(s.delete_project(self.p['id'])['ok'])
 def test_budget_exact_boundary_and_clear_error(self):
  p=dict(self.p,budget=.3,spent=.1,reserved=.1)
  s.check_video_budget(p,.1)
  with self.assertRaises(s.HTTPException) as caught:s.check_video_budget(p,.11)
  self.assertIn('还差 ¥0.01',caught.exception.detail)
 def test_video_settlement_does_not_release_other_jobs_twice(self):
  self.p['reserved']=6;s.put(self.p)
  with s.db() as conn:conn.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('settle-'+self.p['id'],self.p['id'],'video','failed',json.dumps({'quote':4})))
  jid='settle-'+self.p['id']
  with s.LOCK:s.settle_video_reservation(jid,False);s.settle_video_reservation(jid,False)
  self.assertEqual(s.project(self.p['id'])['reserved'],2)
  with self.assertRaises(s.HTTPException):s.release_uncertain(jid,{'resolution':'charged'})
 def test_legacy_rejected_request_releases_reservation(self):
  self.p['reserved']=4;s.put(self.p)
  jid='legacy-'+self.p['id']
  with s.db() as conn:conn.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(jid,self.p['id'],'video','failed',json.dumps({'quote':4,'error':'请求参数被拒绝（HTTP 400）'})))
  s.repair_legacy_video_reservations();s.repair_legacy_video_reservations()
  self.assertEqual(s.project(self.p['id'])['reserved'],0)
  self.assertTrue(s.job(jid)['data']['settled'])
 def test_generation_rejects_unsupported_resolution_before_charging(self):
  self.p.update(confirmed={'4':True},shots=[{'id':'shot','duration':5}]);s.put(self.p)
  c={'platform':'volcengine','model':'doubao-seedance-2-0-mini-260615'}
  with patch.object(s,'config',return_value=c),patch.object(s,'call') as remote:
   with self.assertRaises(s.HTTPException):s.generate_video(self.p['id'],'shot',{'resolution':'1080p','approve':True})
   remote.assert_not_called()
  self.assertEqual(s.project(self.p['id'])['reserved'],0)
 def test_project_persists_and_revision_conflict(self):
  self.patch(story='完整故事',_revision=0)
  self.assertEqual(s.project(self.p['id'])['story'],'完整故事')
  with self.assertRaises(s.HTTPException):s.update_project(self.p['id'],{'story':'覆盖','_revision':0})
 def test_confirm_requires_review_and_order(self):
  self.patch(story='完整故事')
  self.p=s.confirm_step(self.p['id'],0)
  self.assertTrue(self.p['confirmed']['0'])
  with self.assertRaises(s.HTTPException):s.confirm_step(self.p['id'],2)
 def test_downstream_invalidation(self):
  self.p['confirmed']={str(i):True for i in range(8)};self.p['reviews']={'0':{'passed':True}};s.put(self.p)
  self.patch(style='新画风')
  self.assertTrue(self.p['confirmed']['1']);self.assertNotIn('2',self.p['confirmed']);self.assertIn('0',self.p['reviews'])
 def test_selected_video_preserves_submission_review(self):
  aid=s.add_asset(self.p['id'],'video','shot','片段',b'video','video/mp4')
  self.p['shots']=[{'id':'shot','title':'镜头','duration':5,'description':'','prompt':'提示词','review':{'passed':True}}];self.p['confirmed']={str(i):True for i in range(5)};s.put(self.p)
  shots=self.p['shots'];shots[0]['selected']=aid;self.patch(shots=shots)
  self.assertTrue(self.p['confirmed']['4']);self.assertTrue(self.p['shots'][0]['review']['passed'])
 def test_client_cannot_forge_review(self):
  self.patch(shots=[{'id':'x','duration':5,'review':{'passed':True}}]);self.assertNotIn('review',self.p['shots'][0])
 def test_keys_are_not_persisted_or_returned(self):
  with patch.object(s,'safe_url',lambda u:u):
   s.save_model('director',{'platform':'openai','model':'gpt-5.4','key':'test-secret'})
  self.assertNotIn('test-secret',json.dumps(s.bootstrap()))
  self.assertNotIn('key',s.setting('model:director'));self.assertTrue(s.bootstrap()['models']['director']['has_key'])
 def test_platform_automatically_resolves_endpoint(self):
  c=s.save_model('director',{'platform':'anthropic','model':'claude-sonnet-5-5','key':'anthropic-test','base':'https://wrong.example','protocol':'wrong'})
  self.assertEqual(c['base'],'https://api.anthropic.com/v1');self.assertEqual(c['protocol'],'anthropic')
  with self.assertRaises(s.HTTPException):s.save_model('artist',{'platform':'anthropic','model':'claude-sonnet-5-5'})
  restored=s.save_model('director',{'platform':'openai','model':'gpt-5.4'});self.assertTrue(restored['has_key'])
  c=s.save_model('animator',{'platform':'volcengine','model':'doubao-seedance-2-0-mini-260615','key':'video-test'})
  self.assertEqual(c['base'],'https://ark.cn-beijing.volces.com/api/v3')
 def test_expanded_catalog_role_routing(self):
  self.assertGreaterEqual(len(s.CATALOG),10)
  for platform,catalog in s.CATALOG.items():
   for role,models in catalog['models'].items():
    for model in models:
     expected_base='https://custom.example/v1' if platform=='custom' else catalog['base']
     with patch.object(s,'safe_url',side_effect=lambda url:url):result=s.save_model(role,{'platform':platform,'model':model['id'],'key':'test-key','base':expected_base})
     self.assertEqual(result['base'],expected_base);self.assertEqual(result['platform'],platform)
 def test_image_platform_parameters(self):
  p={'ratio':'9:16'}
  ark=s.image_payload({'platform':'volcengine','model':'seedream'},p,'prompt')
  self.assertEqual(ark['size'],'2K');self.assertFalse(ark['watermark'])
  xai=s.image_payload({'platform':'xai','model':'grok'},p,'prompt')
  self.assertEqual(xai['aspect_ratio'],'9:16');self.assertNotIn('size',xai)
 def test_xai_first_last_video_and_poll(self):
  first=s.add_asset(self.p['id'],'first','x','首帧',b'a','image/png');last=s.add_asset(self.p['id'],'last','x','尾帧',b'b','image/png')
  c={'platform':'xai','base':'https://api.x.ai/v1','model':'grok-imagine-video-1.5','role':'animator'}
  path,payload=s.video_payload(c,self.p,{'first':first,'last':last,'duration':5,'prompt':'动作'},'480p')
  self.assertEqual(payload['resolution'],'480p')
  self.assertEqual(path,'/videos/generations');self.assertIn('image',payload);self.assertIn('last_frame',payload)
  with s.db() as conn:conn.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('poll-test',self.p['id'],'video','submitted',json.dumps({'model':c,'remote_id':'remote','shot':'x','quote':2})))
  self.p['reserved']=2;s.put(self.p)
  with patch.object(s,'config',return_value=c),patch.object(s,'call',return_value={'status':'done','video':{'url':'https://example.com/video.mp4'}}),patch.object(s,'download_remote',return_value=b'mp4'):
   result=s.refresh_job('poll-test')
  self.assertEqual(result['status'],'succeeded');self.assertEqual(s.project(self.p['id'])['reserved'],0)
 def test_text_only_model_blocks_image_review(self):
  with patch.object(s,'config',return_value={'platform':'deepseek','model':'deepseek-v4-pro'}),patch.object(s,'call') as remote:
   with self.assertRaises(s.HTTPException):s.llm(self.p,'review','check',images=[{}])
   remote.assert_not_called()
 def test_provider_error_has_reason_and_redacts_credentials(self):
  key='sk-secret-testing-value';s.KEYS['director']=key
  r=type('Response',(),{'status_code':401,'headers':{'x-request-id':'req-123'},'json':lambda self:{'error':{'code':'invalid_api_key','message':'Incorrect API key '+key}}})()
  message=s.provider_error({'platform':'openai','model':'gpt-5.4'},r)
  self.assertIn('invalid_api_key',message);self.assertIn('Incorrect API key',message);self.assertIn('req-123',message);self.assertIn('HTTP 401',message);self.assertNotIn(key,message)
 def test_provider_error_non_json_is_explicitly_unknown(self):
  def bad(self):raise ValueError()
  r=type('Response',(),{'status_code':403,'headers':{},'json':bad})()
  message=s.provider_error({'platform':'google','model':'gemini'},r)
  self.assertIn('未提供',message);self.assertIn('HTTP 403',message)
 def test_provider_error_quota_is_not_wrongly_key_failure(self):
  r=type('Response',(),{'status_code':429,'headers':{},'json':lambda self:{'error':{'type':'insufficient_quota','message':'You exceeded your current quota'}}})()
  message=s.provider_error({'platform':'openai','model':'gpt-5.4'},r)
  self.assertIn('insufficient_quota',message);self.assertIn('current quota',message);self.assertNotIn('API Key 无效',message)
 def test_user_ark_catalog_and_image_generation_params(self):
  models=s.CATALOG['volcengine']['models']
  self.assertEqual(len(models['director']),18)
  self.assertEqual(len(models['modeler']),3)
  self.assertTrue(any(m['name']=='Kimi-K3.1-Pro' for m in models['director']))
  payload=s.image_payload({'platform':'volcengine','model':'doubao-seedream-5-0-pro-260628'},{'ratio':'16:9'},'画图')
  self.assertNotIn('sequential_image_generation',payload)
 def test_first_frame_only_video_omits_last(self):
  first=s.add_asset(self.p['id'],'first','x','首帧',b'a','image/png');last=s.add_asset(self.p['id'],'last','x','尾帧',b'b','image/png')
  c={'platform':'volcengine','model':'doubao-seedance-1-0-pro-fast-251015'}
  path,payload=s.video_payload(c,self.p,{'first':first,'last':last,'duration':5,'prompt':'动作'},'480p')
  self.assertEqual(payload['resolution'],'480p')
  self.assertEqual([x.get('role') for x in payload['content'] if x['type']=='image_url'],['first_frame'])
 def test_3d_generation_and_download_are_real_task_flow(self):
  aid=s.add_asset(self.p['id'],'reference','','参考',b'png','image/png')
  c={'role':'modeler','platform':'volcengine','protocol':'ark','base':'https://ark.cn-beijing.volces.com/api/v3','model':'hyper3d-gen2-260112'}
  with patch.object(s,'config',return_value=c),patch.object(s,'call',return_value={'id':'3d-remote'}):
   task=s.generate_3d(self.p['id'],{'image':aid,'approve':True})
   for _ in range(100):
    j=s.job(task['id'])
    if j['status'] not in ['queued','running']:break
    time.sleep(.02)
  self.assertEqual(j['status'],'submitted')
  with patch.object(s,'config',return_value=c),patch.object(s,'call',return_value={'status':'succeeded','content':{'file_url':'https://example.com/file.zip'}}),patch.object(s,'download_remote',return_value=b'PKmockzip'):
   j=s.refresh_3d(task['id'])
  self.assertEqual(j['status'],'succeeded');self.assertEqual(s.asset(j['data']['asset'])['mime'],'application/zip')
 def wait_job(self,jid):
  for _ in range(200):
   j=s.job(jid)
   if j['status'] not in ['queued','running']:return j
   time.sleep(.01)
  self.fail('job did not finish')
 def test_auto_repair_saves_versions_reviews_and_never_confirms(self):
  self.p['story']='旧故事';self.p['reviews']['0']={'passed':False,'issues':['逻辑错误'],'summary':'不通过'};s.put(self.p)
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',side_effect=['新故事',json.dumps({'passed':True,'issues':[],'summary':'逻辑成立'})]):
   j=self.wait_job(s.auto_repair(self.p['id'],{'step':0,'rounds':2,'approve':True})['id'])
  self.assertEqual(j['status'],'succeeded');self.assertTrue(j['data']['result']['passed']);p=s.project(self.p['id']);self.assertEqual(p['story'],'新故事');self.assertFalse(p['confirmed']);self.assertEqual(len(s.repair_versions(p['id'])),2)
 def test_auto_repair_stops_at_limit_without_faking_pass(self):
  self.p['story']='旧故事';self.p['reviews']['0']={'passed':False,'issues':['问题']};s.put(self.p)
  bad=json.dumps({'passed':False,'issues':['未修复'],'summary':'失败'})
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',side_effect=['改稿1',bad,'改稿2',bad]) as llm:
   j=self.wait_job(s.auto_repair(self.p['id'],{'step':0,'rounds':2,'approve':True})['id'])
  self.assertEqual(llm.call_count,4);self.assertFalse(j['data']['result']['passed']);self.assertFalse(s.project(self.p['id'])['confirmed'])
 def test_auto_repair_wont_overwrite_concurrent_edit(self):
  self.p['story']='旧故事';self.p['reviews']['0']={'passed':False,'issues':['问题']};s.put(self.p)
  def edited(*args,**kw):
   q=s.project(self.p['id']);q['story']='用户修改';q['revision']+=1;s.put(q);return '自动改稿'
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',side_effect=edited):
   j=self.wait_job(s.auto_repair(self.p['id'],{'step':0,'rounds':1,'approve':True})['id'])
  self.assertEqual(j['status'],'failed');self.assertEqual(s.project(self.p['id'])['story'],'用户修改')
 def test_frame_repair_only_plans_no_image_or_video_spending(self):
  self.p['reviews']['3']={'passed':False,'issues':['背景错位']};s.put(self.p)
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',return_value='请对齐背景，改图前确认费用') as llm,patch.object(s,'call') as remote:
   j=self.wait_job(s.auto_repair(self.p['id'],{'step':3,'rounds':3,'approve':True})['id'])
  self.assertEqual(llm.call_count,1);remote.assert_not_called();self.assertEqual(j['kind'],'repair-plan');self.assertEqual(s.project(self.p['id'])['revision'],0)
 def test_saved_keys_survive_memory_reset(self):
  s.save_model('director',{'platform':'volcengine','model':'doubao-seed-2-1-pro-260915','key':'test-persistent-key'})
  s.KEYS.clear();s.restore_keys();self.assertEqual(s.KEYS['director'],'test-persistent-key')
  s.save_model('director',{'platform':'volcengine','model':'doubao-seed-2-1-pro-260915','clear_key':True})
  s.KEYS.clear();s.restore_keys();self.assertNotIn('director',s.KEYS)
 def test_saved_keys_are_isolated_by_platform(self):
  s.save_model('director',{'platform':'openai','model':'gpt-5.4','key':'openai-isolated'})
  s.save_model('director',{'platform':'anthropic','model':'claude-sonnet-5-5','key':'anthropic-isolated'})
  s.save_model('director',{'platform':'openai','model':'gpt-5.4'})
  self.assertEqual(s.KEYS['director'],'openai-isolated')
 def test_keychain_failure_does_not_claim_saved(self):
  before=s.setting('model:director',{})
  with patch.object(s.SECRETS,'set',side_effect=s.SecretStoreError('钥匙串不可用')):
   with self.assertRaises(s.HTTPException):s.save_model('director',{'platform':'openai','model':'gpt-5.4','key':'do-not-save'})
  self.assertEqual(s.setting('model:director',{}),before)
 def test_force_review_preserves_ai_opinion_and_allows_confirmation(self):
  self.p['story']='已人工检查的故事';self.p['reviews']['0']={'passed':False,'issues':['艺术处理问题'],'summary':'AI 不通过'};s.put(self.p)
  p=s.force_review(self.p['id'],{'step':0,'reason':'接受此艺术处理','revision':0})
  self.assertFalse(p['reviews']['0']['passed']);self.assertTrue(s.review_accepted(p['reviews']['0']))
  self.assertEqual(p['reviews']['0']['issues'],['艺术处理问题']);self.assertFalse(p['confirmed'])
  p=s.confirm_step(p['id'],0);self.assertTrue(p['confirmed']['0'])
  p=s.update_project(p['id'],{'story':'重新修改故事'});self.assertFalse(p['reviews'].get('0'))
 def test_force_requires_reason_and_current_revision(self):
  self.p['reviews']['0']={'passed':False};s.put(self.p)
  with self.assertRaises(s.HTTPException):s.force_review(self.p['id'],{'step':0,'reason':'','revision':0})
  with self.assertRaises(s.HTTPException):s.force_review(self.p['id'],{'step':0,'reason':'已检查','revision':99})
 def test_force_shot_cannot_skip_missing_materials(self):
  self.p['confirmed']={'3':True};self.p['shots']=[{'id':'x','duration':5,'title':'镜头','review':{'passed':False,'issues':['缺帧']}}];s.put(self.p)
  p=s.force_review(self.p['id'],{'step':4,'shot':'x','reason':'暂时接受','revision':0})
  self.assertTrue(s.review_accepted(p['shots'][0]['review']))
  with self.assertRaises(s.HTTPException):s.confirm_step(p['id'],4)
 def test_force_stops_auto_repair(self):
  self.p['story']='故事';self.p['reviews']['0']={'passed':False};s.put(self.p)
  with s.db() as c:c.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('force-stop-'+self.p['id'],self.p['id'],'auto-repair','running','{}'))
  s.force_review(self.p['id'],{'step':0,'reason':'已经人工检查','revision':0})
  self.assertTrue(s.job('force-stop-'+self.p['id'])['data']['cancel_requested'])
 def test_frame_planning_keeps_shot_and_existing_media(self):
  self.p['shots']=[{'id':'x','title':'镜头','duration':5,'description':'动作','prompt':'提示词','last':'existing-last'}];self.p['confirmed']={'0':True,'1':True,'2':True};s.put(self.p)
  output=json.dumps([{'id':'x','first_prompt':'首帧构图','last_prompt':'尾帧构图','motion':'物体向右'}])
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',return_value=output):
   j=self.wait_job(s.generate_text(self.p['id'],'frames')['id'])
  self.assertEqual(j['status'],'succeeded');p=s.project(self.p['id']);self.assertEqual(p['shots'][0]['frame_plan']['motion'],'物体向右');self.assertEqual(p['shots'][0]['last'],'existing-last');self.assertTrue(p['confirmed']['2'])
 def test_frame_prompt_isolates_single_shot_and_skips_bad_reference(self):
  import base64
  aid=s.add_asset(self.p['id'],'last','x','错误拼图',b'bad','image/png')
  s.store_setting('asset-warnings:'+self.p['id'],{aid:'多格拼图'})
  self.p.update(style='故事：六镜故事\n预算：30元\n画风：褐黄色调、灰绿柳叶',shots=[{'id':'x','title':'当前镜头','last':aid},{'id':'y','title':'不应传入的第二镜头'}]);s.put(self.p)
  c={'platform':'volcengine','model':'doubao-seedream-5-0-flash-260915','protocol':'ark'}
  with patch.object(s,'call',return_value={'data':[{'b64_json':base64.b64encode(b'png').decode()}]}) as remote:
   s.render_image_asset(self.p,c,'first','x','鲁智深抱树，单个瞬间',reference=aid)
  payload=remote.call_args.kwargs['json'];text=payload['prompt']
  self.assertIn('不分格、不拼贴、不分屏',text);self.assertIn('灰绿柳叶',text)
  for excluded in ['六镜故事','预算：30元','不应传入的第二镜头','先写首帧']:
   self.assertNotIn(excluded,text)
  self.assertNotIn('image',payload)
  self.assertEqual(s.list_assets(self.p['id'])[-1]['warning'],'多格拼图')
 def test_multi_subshot_plan_rejected_before_job_or_provider(self):
  self.p.update(confirmed={'2':True},shots=[{'id':'x','frame_plan':{'first_prompt':'A首帧：近景。B首帧：远景。','last_prompt':'尾帧'}}]);s.put(self.p)
  with patch.object(s,'config',return_value={}),patch.object(s,'new_job') as job,patch.object(s,'call') as remote:
   with self.assertRaises(s.HTTPException) as error:s.generate_frame_pair(self.p['id'],'x',{'approve':True})
   self.assertIn('独立镜头',error.exception.detail);job.assert_not_called();remote.assert_not_called()
 def test_frame_pair_creates_real_assets_after_text_plan(self):
  self.p['confirmed']={'2':True};self.p['shots']=[{'id':'x','title':'镜头','duration':5,'frame_plan':{'last_prompt':'尾帧','first_prompt':'首帧'}}];s.put(self.p)
  import base64
  c={'platform':'volcengine','role':'artist','model':'doubao-seedream-5-0-flash-260915','protocol':'ark'}
  with patch.object(s,'config',return_value=c),patch.object(s,'call',return_value={'data':[{'b64_json':base64.b64encode(b'png-test').decode()}]}) as remote:
   j=self.wait_job(s.generate_frame_pair(self.p['id'],'x',{'approve':True})['id'])
  self.assertEqual(j['status'],'succeeded');self.assertEqual(remote.call_count,2)
  assets=s.list_assets(self.p['id']);self.assertEqual({a['kind'] for a in assets},{'first','last'})
  self.assertEqual(set(j['data']['result']),{'first','last'})
  self.assertIn('image',remote.call_args.kwargs['json'])
  self.assertEqual(s.project(self.p['id'])['shots'][0]['first'],j['data']['result']['first'])
 def test_pair_feedback_only_regenerates_target_shot(self):
  self.p['confirmed']={'2':True};self.p['shots']=[{'id':'x','title':'镜头','duration':5,'frame_plan':{'last_prompt':'尾帧','first_prompt':'首帧'}},{'id':'y','first':'keep-first','last':'keep-last'}];s.put(self.p)
  def image(p,c,kind,sid,text,**kwargs):
   self.assertEqual(sid,'x');self.assertIn('人物坐下',text)
   return s.add_asset(p['id'],kind,sid,'新图',b'image','image/png')
  with patch.object(s,'config',return_value={}),patch.object(s,'render_image_asset',side_effect=image):
   j=self.wait_job(s.generate_frame_pair(self.p['id'],'x',{'approve':True,'feedback':'人物坐下'})['id'])
  self.assertEqual(j['status'],'succeeded');self.assertEqual(j['data']['feedback'],'人物坐下')
  self.assertEqual(s.project(self.p['id'])['shots'][1],self.p['shots'][1])
 def test_failed_review_does_not_block_manual_confirmation(self):
  self.p['story']='人工确认的故事';self.p['reviews']['0']={'passed':False,'issues':['模型建议']};s.put(self.p)
  p=s.confirm_step(self.p['id'],0);self.assertTrue(p['confirmed']['0']);self.assertFalse(p['reviews']['0']['passed'])
 def test_visual_review_never_calls_model(self):
  with patch.object(s,'config') as config,patch.object(s,'llm') as llm:
   for step in [3,7]:
    with self.assertRaises(s.HTTPException):s.review_step(self.p['id'],step)
   config.assert_not_called();llm.assert_not_called()
 def test_shot_text_review_does_not_send_images(self):
  first=s.add_asset(self.p['id'],'first','x','首帧',b'png','image/png');last=s.add_asset(self.p['id'],'last','x','尾帧',b'png','image/png')
  self.p['shots']=[{'id':'x','title':'镜头','duration':5,'first':first,'last':last,'prompt':'文字提示词'}];s.put(self.p)
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',return_value=json.dumps({'passed':True,'issues':[],'summary':'仅检查文字'})) as llm:
   j=self.wait_job(s.review_shot(self.p['id'],'x')['id'])
  self.assertEqual(j['status'],'succeeded');self.assertEqual(llm.call_args.args[-1],[])
 def test_real_person_rejection_identifies_first_frame(self):
  r=type('Response',(),{'status_code':400,'headers':{},'json':lambda self:{'error':{'code':'InputImageSensitiveContentDetected.PrivacyInformation','message':"input image 'content[1]' may contain real person"}}})()
  text=s.provider_error({'platform':'volcengine','model':'seedance'},r)
  self.assertIn('首帧',text);self.assertIn('停止重复提交',text);self.assertNotIn('按服务商错误说明检查模型支持的参数',text)
 def test_generated_frame_does_not_overwrite_concurrent_change(self):
  self.p['shots']=[{'id':'x','duration':5,'first':'original'}];s.put(self.p)
  q=s.project(self.p['id']);q['revision']=1;q['shots'][0]['first']='manual';s.put(q)
  self.assertIsNone(s.select_generated_frame(q['id'],'x','first','generated',0))
  self.assertEqual(s.project(q['id'])['shots'][0]['first'],'manual')
 def test_frame_feedback_updates_only_requested_frame(self):
  first=s.add_asset(self.p['id'],'first','x','首帧',b'png','image/png');last=s.add_asset(self.p['id'],'last','x','尾帧',b'png','image/png')
  self.p['confirmed']={'0':True,'2':True};self.p['shots']=[{'id':'x','duration':5,'first':first,'last':last}];s.put(self.p)
  with patch.object(s,'config',return_value={}),patch.object(s,'render_image_asset',return_value='new-first') as renderer:
   j=self.wait_job(s.generate_image(self.p['id'],{'kind':'first','shot':'x','prompt':'画面','feedback':'向左','reference':first})['id'])
  self.assertEqual(j['status'],'succeeded');self.assertTrue(j['data']['auto_selected'])
  q=s.project(self.p['id']);self.assertEqual(q['shots'][0]['first'],'new-first');self.assertEqual(q['shots'][0]['last'],last)
  self.assertIn('向左',renderer.call_args.args[4]);self.assertEqual(renderer.call_args.args[6],first)
 def test_full_video_sends_one_request_for_all_shots(self):
  first=s.add_asset(self.p['id'],'first','a','首',b'png','image/png');last=s.add_asset(self.p['id'],'last','b','尾',b'png','image/png')
  self.p['confirmed']={'4':True};self.p['shots']=[{'id':'a','duration':5,'first':first},{'id':'b','duration':5,'last':last}];s.put(self.p)
  c={'platform':'volcengine','role':'animator','protocol':'ark','base':'https://ark.cn-beijing.volces.com/api/v3','model':'doubao-seedance-2-5-260628','rate':1}
  with patch.object(s,'config',return_value=c),patch.object(s,'validate_frames'),patch.object(s,'call',return_value={'id':'whole-video-id'}) as remote:
   j=self.wait_job(s.generate_full_video(self.p['id'],{'duration':10,'resolution':'720p','seed':42,'prompt':'完整故事','approve':True,'quote':10})['id'])
  self.assertEqual(j['status'],'submitted');self.assertEqual(remote.call_count,1)
  self.assertEqual(remote.call_args.kwargs['json']['duration'],10);self.assertEqual(remote.call_args.kwargs['json']['seed'],42)
  self.assertTrue(j['data']['full_film'])
  with patch.object(s,'config',return_value=c),patch.object(s,'call',return_value={'status':'succeeded','content':{'video_url':'https://example.com/video.mp4'}}),patch.object(s,'download_remote',return_value=b'video'):
   j=s.refresh_job(j['id'])
  p=s.project(self.p['id']);self.assertEqual(p['final_video'],j['data']['asset']);self.assertEqual(p['stage'],5);self.assertEqual(s.asset(p['final_video'])['kind'],'full-video')
 def test_templates_save_independently(self):
  s.save_prompt('story',{'value':'新故事模板'});s.save_prompt('video',{'value':'视频模板'});s.save_prompt('story',{'value':'第二版'})
  self.assertEqual(s.setting('prompt:video'),'视频模板')
 def test_budget_blocks_before_provider(self):
  first=s.add_asset(self.p['id'],'first','x','首帧',b'png','image/png');last=s.add_asset(self.p['id'],'last','x','尾帧',b'png','image/png')
  self.p.update(budget=1,confirmed={'4':True},shots=[{'id':'x','duration':5,'first':first,'last':last,'prompt':'p','review':{'passed':True}}]);s.put(self.p)
  with patch.object(s,'config',return_value={'rate':1,'model':'m'}),patch.object(s,'call') as remote:
   with self.assertRaises(s.HTTPException):s.generate_video(self.p['id'],'x',{'approve':True,'quote':5})
   remote.assert_not_called()
 def test_missing_key_does_not_fabricate_success(self):
  s.KEYS.pop('artist',None)
  with self.assertRaises(s.HTTPException):s.generate_image(self.p['id'],{'prompt':'图'})
 def test_mocked_text_job_is_saved(self):
  with patch.object(s,'config',return_value={}),patch.object(s,'llm',return_value='真实接口响应测试'):
   j=s.generate_text(self.p['id'],'story')
   for _ in range(100):
    result=s.job(j['id'])
    if result['status'] not in ['queued','running']:break
    time.sleep(.02)
   self.assertEqual(result['status'],'succeeded');self.assertEqual(s.project(self.p['id'])['story'],'真实接口响应测试')
 def test_media_versions_are_retained(self):
  a=s.add_asset(self.p['id'],'first','x','v1',b'a','image/png');b=s.add_asset(self.p['id'],'first','x','v2',b'b','image/png')
  self.assertNotEqual(a,b);self.assertEqual(len(s.list_assets(self.p['id'])),2)
 def test_real_ffmpeg_export_and_sample_frames(self):
  if not s.FFMPEG:self.skipTest('ffmpeg unavailable')
  clip=Path(os.environ['STUDIO_DATA'])/'source.mp4'
  import subprocess
  subprocess.run([s.FFMPEG,'-v','error','-f','lavfi','-i','color=c=blue:s=320x180:d=2','-c:v','libx264','-pix_fmt','yuv420p','-y',str(clip)],check=True,capture_output=True)
  aid=s.add_asset(self.p['id'],'video','x','test clip',clip.read_bytes(),'video/mp4')
  self.p['shots']=[{'id':'x','title':'镜头','duration':2,'selected':aid}];self.p['confirmed']={'5':True};s.put(self.p)
  for resolution,dimensions in [('1080p','1920x1080'),('720p','1280x720')]:
   j=s.export(self.p['id'],{'resolution':resolution})
   for _ in range(1200):
    result=s.job(j['id'])
    if result['status'] not in ['queued','running']:break
    time.sleep(.025)
   self.assertEqual(result['status'],'succeeded',result)
   final=s.asset(result['data']['asset']);self.assertGreater((s.MEDIA/final['path']).stat().st_size,1000)
   probe=subprocess.run([s.FFMPEG,'-hide_banner','-i',str(s.MEDIA/final['path'])],capture_output=True)
   self.assertIn(dimensions,probe.stderr.decode())
   self.assertEqual(s.project(self.p['id'])['export_asset'],final['id'])
  frames=s.sample_video(s.MEDIA/final['path'],self.p['id']);self.assertTrue(frames)
  s.validate_frames(frames[0],frames[0],'16:9')
  cropped=s.crop_image(self.p['id'],frames[0]['id']);self.assertNotEqual(cropped['id'],frames[0]['id']);s.validate_frames(cropped,cropped,'16:9')
if __name__=='__main__':unittest.main()

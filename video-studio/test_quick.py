"""Quick integration contract tests. No remote API calls or production writes."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ['STUDIO_DATA']=tempfile.mkdtemp(prefix='studio-quick-test-')
os.environ['STUDIO_KEY_STORE']='memory'
import server
from fastapi.testclient import TestClient

class QuickTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(server.app)
        self.headers={'X-Studio-Client':'1'}
    def test_start_and_origin_protection(self):
        with patch.object(server.QUICK,'start',return_value={'ready':True,'url':'http://127.0.0.1:8517'}):
            self.assertEqual(self.client.post('/api/quick/start').status_code,403)
            self.assertEqual(self.client.post('/api/quick/start',headers={**self.headers,'Origin':'https://example.com'}).status_code,403)
            self.assertTrue(self.client.post('/api/quick/start',headers=self.headers).json()['ready'])
    def test_output_import_and_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'storage/tasks/demo';folder.mkdir(parents=True)
            (folder/'final-1.mp4').write_bytes(b'test-only-video')
            with patch.object(server,'QUICK_ROOT',root):
                outputs=self.client.get('/api/quick/outputs').json()
                self.assertEqual(outputs[0]['id'],'demo/final-1.mp4')
                r=self.client.post('/api/quick/import',headers=self.headers,json={'id':'demo/final-1.mp4'})
                self.assertEqual(r.status_code,200,r.text)
                self.assertEqual(server.asset(r.json()['asset'])['kind'],'quick-video')
                self.assertEqual(self.client.post('/api/quick/import',headers=self.headers,json={'id':'../../../outside.mp4'}).status_code,404)
    def test_unified_settings_and_validation(self):
        r=self.client.post('/api/quick/settings',headers=self.headers,json={'keys':{'pexels':'test-secret-only'},'subtitle_provider':'whisper'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['keys']['pexels'])
        self.assertNotIn('test-secret-only',r.text)
        self.assertEqual(r.json()['subtitle_provider'],'whisper')
        self.assertEqual(self.client.post('/api/quick/settings',headers=self.headers,json={'subtitle_provider':'bad'}).status_code,400)
        self.assertEqual(self.client.post('/api/quick/generate',headers=self.headers,json={'video_script':'测试','video_source':'local','materials':['../../outside.mp4']}).status_code,400)
        self.assertEqual(self.client.post('/api/quick/archive',headers=self.headers,json={'name':'../../outside.mp4'}).status_code,400)
    def test_quick_script_uses_director_role(self):
        with patch.object(server,'llm',return_value='共用导演文案') as llm:
            result=self.client.post('/api/quick/script',headers=self.headers,json={'topic':'春天','duration':45})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['script'],'共用导演文案')
        self.assertEqual(llm.call_args.args[0]['duration'],45)
        self.assertIn('45 秒',llm.call_args.args[2])
    def test_quick_project_owns_generated_result(self):
        import json,time,types
        p=server.create({'name':'快速测试','mode':'quick'})
        storage=server.QUICK_ROOT/'storage';storage.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=storage) as temp:
            output=Path(temp)/'final.mp4';output.write_bytes(b'test-video')
            uploaded=self.client.post('/api/quick/upload?kind=video',headers={**self.headers,'Content-Type':'video/mp4'},content=b'0000ftyp-test').json()['id']
            response=types.SimpleNamespace(returncode=0,stdout=json.dumps({'result':{'videos':[str(output)]}}))
            with patch('quick_api.subprocess.run',return_value=response) as worker:
                r=self.client.post('/api/quick/generate',headers=self.headers,json={'project':p['id'],'video_script':'测试文案','video_source':'local','materials':[uploaded]})
                self.assertEqual(r.status_code,200,r.text)
                for _ in range(100):
                    j=server.job(r.json()['id'])
                    if j['status'] in ('succeeded','failed'):break
                    time.sleep(.01)
            self.assertEqual(worker.call_args.args[0][:3],[str(server.ROOT/'.venv/bin/python'),'-m','studio.engine.worker'])
            self.assertEqual(j['status'],'succeeded',j)
            self.assertEqual(j['project'],p['id'])
            self.assertEqual(server.project(p['id'])['name'],'测试文案')
            self.assertEqual(server.project(p['id'])['last_video_inputs']['video_script'],'测试文案')
            asset=server.asset(server.project(p['id'])['final_video'])
            self.assertEqual(asset['project'],p['id']);self.assertEqual(asset['kind'],'quick-video')
            self.assertEqual(len(self.client.get('/api/quick/jobs',params={'project':p['id']}).json()),1)
    def test_quick_draft_persists_inputs_without_generation(self):
        p=server.create({'name':'草稿','mode':'quick'})
        fields={'video_subject':'原主题','video_script':'原文案','video_source':'pixabay','video_aspect':'1:1','video_count':2,'voice_rate':1.25,'subtitle_enabled':False,'font_size':48,'target_duration':60}
        with patch('quick_api.subprocess.run') as worker:
            r=self.client.post('/api/projects/'+p['id']+'/quick-draft',headers=self.headers,json=fields)
            self.assertEqual(r.status_code,200,r.text);worker.assert_not_called()
        saved=server.project(p['id'])
        self.assertEqual(saved['quick_inputs'],fields)
        self.assertEqual(saved['name'],'原主题')
        self.assertEqual(saved['story'],'原文案');self.assertEqual(saved['ratio'],'1:1')
    def test_draft_save_does_not_replace_last_generated_state(self):
        p=server.create({'name':'编辑恢复','mode':'quick'})
        snapshot={'video_subject':'生成主题','video_script':'生成文案','voice_rate':1.1,'video_aspect':'9:16'}
        p['last_video_inputs']=snapshot;server.put(p)
        new={**snapshot,'video_script':'尚未用于生成的修改'}
        r=self.client.post('/api/projects/'+p['id']+'/quick-draft',headers=self.headers,json=new)
        self.assertEqual(r.status_code,200)
        saved=server.project(p['id'])
        self.assertEqual(saved['last_video_inputs'],snapshot)
        self.assertEqual(saved['quick_inputs'],new)
    def test_saved_project_name_matches_trimmed_topic(self):
        p=server.create({'name':'原项目名称','mode':'quick'})
        r=self.client.post('/api/projects/'+p['id']+'/quick-draft',headers=self.headers,json={'video_subject':'  新的视频主题  ','video_script':'文案'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['name'],'新的视频主题')
        self.assertEqual(r.json()['quick_inputs']['video_subject'],'新的视频主题')
        r=self.client.post('/api/projects/'+p['id']+'/quick-draft',headers=self.headers,json={'video_subject':'   '})
        self.assertEqual(r.status_code,400)
        self.assertEqual(server.project(p['id'])['name'],'新的视频主题')
    def test_missing_dependencies(self):
        from quick_engine import QuickEngine
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError,'依赖'):QuickEngine(temp).start()

if __name__=='__main__':unittest.main()

"""Isolated HTTP integration; never calls external model services."""
import os,subprocess,tempfile,time,requests
from pathlib import Path
root=Path(__file__).resolve().parent
env={**os.environ,'STUDIO_DATA':tempfile.mkdtemp(prefix='studio-http-'),'PORT':'4174','STUDIO_KEY_STORE':'memory'}
p=subprocess.Popen([str(root/'.venv-api/bin/python'),str(root/'server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
base='http://127.0.0.1:4174';headers={'X-Studio-Client':'1'}
try:
 for _ in range(80):
  try:
   if requests.get(base+'/api/health',timeout=1).ok:break
  except requests.RequestException:pass
  time.sleep(.1)
 else:raise RuntimeError('server unavailable')
 assert requests.get(base+'/',allow_redirects=False).status_code==307
 assert requests.get(base+'/editor',allow_redirects=False).status_code==307
 assert requests.get(base+'/static/app.js').status_code==200
 assert requests.post(base+'/api/projects',json={'name':'blocked'}).status_code==403
 assert requests.post(base+'/api/projects',headers={**headers,'Origin':'https://other.example'},json={'name':'blocked'}).status_code==403
 response=requests.post(base+'/api/projects',headers=headers,json={'name':'HTTP 测试','idea':'测试故事'});assert response.ok,response.text
 project=response.json();pid=project['id']
 response=requests.patch(base+'/api/projects/'+pid,headers=headers,json={'story':'保存后的故事','_revision':0});assert response.ok,response.text
 assert requests.get(base+'/api/projects/'+pid).json()['story']=='保存后的故事'
 assert requests.post(base+'/api/projects/'+pid+'/confirm/0',headers=headers,json={}).status_code==200
 assert requests.post(base+'/api/projects/'+pid+'/generate/story',headers=headers,json={}).status_code==400
 assert requests.post(base+'/api/prompts/story',headers=headers,json={'value':'HTTP 新模板'}).ok
 assert requests.get(base+'/api/bootstrap').json()['prompts']['story']['value']=='HTTP 新模板'
 # New process reads the same SQLite project and prompt data.
 p.terminate();p.wait();p=subprocess.Popen([str(root/'.venv-api/bin/python'),str(root/'server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for _ in range(80):
  try:
   r=requests.get(base+'/api/projects/'+pid,timeout=1)
   if r.ok:break
  except requests.RequestException:pass
  time.sleep(.1)
 assert r.json()['story']=='保存后的故事'
 print('PASS HTTP: page/assets, same-origin protection, project CRUD, review gate, missing key, prompt save, restart persistence')
finally:
 p.terminate();p.wait()

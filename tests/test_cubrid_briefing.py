import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'bin/cubrid-briefing'
FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
p=pathlib.Path(os.environ['FIXTURE']); name=pathlib.Path(sys.argv[0]).name; args=sys.argv[1:]
def read(n): return json.loads((p/n).read_text())
if name == 'watcher':
 if args[0] == 'events':
  for e in read('events'):
   if e['id'] > int(args[2]): print(json.dumps(e))
 else: print(json.dumps({'requests':[read('request')]}))
elif name == 'tracker': print(json.dumps(read('work')))
elif name == 'herdr' and 'get' in args: print(json.dumps({'result':{'agent':read('agent')}}))
else:
 with (p/'calls').open('a') as f: f.write(name+'\\n')
 if name == 'hermes': (p/'message').write_text(pathlib.Path(args[args.index('--file')+1]).read_text())
 if (p/(name+'-fail')).exists(): print('SECRET',file=sys.stderr); sys.exit(1)
 print(json.dumps({'success': True} if name == 'hermes' else {'result':{'type':'agent_prompted'}}))
'''

class BridgeTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.p = Path(self.tmp.name); self.state = self.p/'state'; self.env = dict(os.environ, FIXTURE=str(self.p))
  for n in ('watcher','tracker','herdr','hermes'):
   f=self.p/n; f.write_text(FAKE); f.chmod(0o755)
  self.route={'request_id':1,'work_id':2,'pr':3,'head':'a'*40,'pane_id':'w:p','agent_session':'uuid','cwd':str(self.p)}
  self.write('route',self.route); self.write('request',{'id':1,'pr':3,'head':'a'*40,'phase':'closed','outcome':'failure'})
  self.write('work',{'id':2,'title':'작업','status':'pending','updated_at':'2026-01-01'})
  self.write('agent',{'pane_id':'w:p','agent_session':{'value':'uuid'},'cwd':str(self.p),'agent_status':'idle','interactive_ready':True})
  self.write('events',[self.event(1)])
  cfg={n:str(self.p/n) for n in ('watcher','tracker','herdr','hermes')}
  cfg.update(report_dir=str(self.p/'reports'),report_base='https://example.test/reports',discord_target='1',brief_work_ids=[2])
  self.write('config',cfg); self.runcli('init','--config',str(self.p/'config')); self.runcli('bind','--route',str(self.p/'route'))
 def write(self,n,data): (self.p/n).write_text(json.dumps(data))
 def event(self,n,kind='complete'): return {'schema_version':1,'id':n,'request_id':1,'key':kind,'kind':kind,'occurred_at':'2026-01-01T00:00:00Z','payload':{'outcome':'failure'}}
 def runcli(self,*args):
  r=subprocess.run([str(CLI),'--state-dir',str(self.state),*args],env=self.env,text=True,capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr); return json.loads(r.stdout)
 def add(self): self.write('events',[self.event(1),self.event(2)])
 def states(self): return self.runcli('status')['deliveries']
 def calls(self): return (self.p/'calls').read_text().splitlines() if (self.p/'calls').exists() else []
 def test_bootstrap_and_replay(self):
  self.runcli('tick','--sink','herdr'); self.assertEqual(self.calls(),[])
  self.add(); self.runcli('tick','--sink','herdr'); self.runcli('tick','--sink','herdr'); self.assertEqual(self.calls(),['herdr'])
 def test_failure_is_independent_and_not_retried(self):
  self.add(); (self.p/'hermes-fail').touch(); self.runcli('tick','--sink','discord'); self.runcli('tick','--sink','herdr'); self.runcli('tick','--sink','discord')
  self.assertEqual(self.calls(),['hermes','herdr']); self.assertEqual([x['state'] for x in self.states()],['unknown','sent'])
  self.assertNotIn('SECRET', (self.state/'bridge.sqlite3').read_bytes().decode(errors='ignore'))
 def test_busy_and_missing_readiness_defer(self):
  a=json.loads((self.p/'agent').read_text()); a.pop('interactive_ready'); self.write('agent',a); self.add(); self.runcli('tick','--sink','herdr'); self.assertEqual(self.states()[0]['state'],'deferred'); self.assertEqual(self.calls(),[])
  a['interactive_ready']=True; self.write('agent',a); self.runcli('tick','--sink','herdr'); self.assertEqual(self.calls(),['herdr'])
 def test_identity_and_head_suppressed(self):
  a=json.loads((self.p/'agent').read_text()); a['agent_session']['value']='changed'; self.write('agent',a); self.add(); self.runcli('tick','--sink','herdr'); self.assertEqual(self.states()[0]['state'],'suppressed'); self.assertEqual(self.states()[1]['source'],'notice:event:2')
  req=json.loads((self.p/'request').read_text()); req['head']='b'*40; self.write('request',req); self.runcli('tick','--sink','discord'); self.assertEqual(self.calls(),['hermes'])
 def test_claimed_recovery_never_resends(self):
  self.add(); a=json.loads((self.p/'agent').read_text()); a['agent_status']='working'; self.write('agent',a); self.runcli('tick','--sink','herdr')
  with sqlite3.connect(self.state/'bridge.sqlite3') as db: db.execute("UPDATE delivery SET state='claimed'")
  self.runcli('tick','--sink','herdr'); self.assertEqual(self.states()[0]['state'],'unknown'); self.assertEqual(self.calls(),[])
 def test_terminal_notice_discord_without_herdr(self):
  req=json.loads((self.p/'request').read_text()); req.update(head='b'*40,outcome='head_changed'); self.write('request',req)
  e=self.event(2,'head_changed'); e['payload']={'close':'head_changed','head':'b'*40}; self.write('events',[self.event(1),e])
  self.runcli('tick','--sink','discord'); self.runcli('tick','--sink','discord')
  self.assertEqual(self.calls(),['hermes'])
  message=(self.p/'message').read_text(); self.assertIn('PR 3',message); self.assertIn('a'*40,message); self.assertIn('b'*40,message)
  self.runcli('tick','--sink','herdr'); self.runcli('tick','--sink','discord'); self.assertEqual(self.calls(),['hermes'])
 def test_registry_and_unknown_events_do_not_prompt(self):
  self.write('events',[self.event(1),self.event(2,'registered'),self.event(3,'binding'),self.event(4,'future_kind')])
  self.runcli('tick','--sink','herdr'); self.runcli('tick','--sink','discord')
  self.assertEqual(self.calls(),[]); self.assertEqual(self.states(),[])
  self.assertEqual({x['event_id'] for x in self.runcli('status')['cursors']},{4})
 def test_bind_cannot_replace_route_during_sink_delivery(self):
  a=json.loads((self.p/'agent').read_text()); a['agent_status']='working'; self.write('agent',a); self.add(); self.runcli('tick','--sink','herdr')
  a.update(pane_id='w:new',agent_status='idle'); a['agent_session']['value']='new'; self.write('agent',a)
  route=dict(self.route,pane_id='w:new',agent_session='new'); self.write('route',route)
  with (self.state/'herdr.lock').open('a') as held:
   fcntl.flock(held,fcntl.LOCK_EX | fcntl.LOCK_NB)
   result=subprocess.run([str(CLI),'--state-dir',str(self.state),'bind','--route',str(self.p/'route')],env=self.env,text=True,capture_output=True)
   self.assertNotEqual(result.returncode,0); self.assertIn('already running',result.stderr)
  self.runcli('bind','--route',str(self.p/'route')); self.runcli('tick','--sink','herdr')
  self.assertEqual(self.states()[0]['state'],'suppressed'); self.assertEqual(self.calls(),[])
 def test_brief_preview_and_idempotent_send(self):
  preview=self.runcli('brief','--date','2026-01-01'); self.assertLessEqual(len(preview['summary']),1500); self.assertIn(preview['url'],preview['summary']); self.assertTrue(Path(preview['path']).exists()); self.assertEqual(self.calls(),[])
  self.runcli('brief','--date','2026-01-01','--send'); self.runcli('brief','--date','2026-01-01','--send'); self.assertEqual(self.calls(),['hermes'])

if __name__ == '__main__': unittest.main()

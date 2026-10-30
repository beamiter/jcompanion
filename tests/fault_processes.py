#!/usr/bin/env python3
"""Real local IPC/process faults; mock hosts do NOT establish native pixel removal."""
import os, sys, json, socket, struct, subprocess, tempfile, time, signal, multiprocessing
BIN=sys.argv[1] if len(sys.argv)>1 else 'target/debug/jcompaniond'
os.environ['XDG_SESSION_ID']='eva-fault-test'
os.environ.pop('SSH_CONNECTION',None)
os.environ.pop('SSH_TTY',None)
# /proc/PID/environ reflects process-start environment: launch this test with XDG_SESSION_ID.
assert b'XDG_SESSION_ID=eva-fault-test' in open('/proc/self/environ','rb').read(), 'run with XDG_SESSION_ID=eva-fault-test'
class Host:
 def __init__(self,path,name):
  self.s=socket.socket(socket.AF_UNIX);self.s.connect(path);self.name=name;self.boot='';self.seq=0
  self.send({'type':'hello','host':{'id':name,'incarnation':1,'surface_id':'s','retirement':'native_presented'}})
  self.boot=self.read()['boot_id'];self.read()
 def send(self,b):
  self.seq+=1;e=dict(protocol_version=1,event_id=f'{self.name}-{self.seq}',source_id=self.name,source_seq=self.seq,boot_id=self.boot,session_id='eva-fault-test',body=b);raw=json.dumps(e).encode();self.s.sendall(struct.pack('>I',len(raw))+raw)
 def read(self,timeout=2):
  self.s.settimeout(timeout)
  def exact(n):
   b=b''
   while len(b)<n:
    p=self.s.recv(n-len(b))
    if not p:raise EOFError()
    b+=p
   return b
  return json.loads(exact(struct.unpack('>I',exact(4))[0]))
 def until(self,kind,timeout=2):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   r=self.read(end-time.monotonic())
   if r['type']==kind:return r
  raise AssertionError(kind)
 def geometry(self):
  r=dict(x=0.,y=0.,width=500.,height=500.)
  self.send(dict(type='geometry',revision=1,viewport=r,candidates=[r],exclusions=[]))
 def acquire(self):
  self.geometry();self.send({'type':'recall'});p=self.until('prepare');self.send(dict(type='prepared',epoch=p['epoch']));return self.until('grant')['token']
def child(path,pipe):
 h=Host(path,'old');token=h.acquire();pipe.send(token)
 while True:
  cmd=pipe.recv()
  if cmd=='retire':
   r=h.until('revoke');h.send(dict(type='retired',token=r['token'],presentation_serial=2));pipe.send('retired')
  elif cmd=='close':h.s.close();return

def launch(profile,path):
 env=os.environ.copy();env['EVA_COMPANION_SOCKET']=path;env.pop('EVA_COMPANION_REQUIRE_COMPOSITOR',None);env.pop('EVA_COMPANION_COMPOSITOR_ONLY',None)
 p=subprocess.Popen([BIN,profile],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 for _ in range(200):
  if p.poll() is not None:raise RuntimeError(p.stderr.read().decode())
  if os.path.exists(path):
   try:s=socket.socket(socket.AF_UNIX);s.connect(path);s.close();return p
   except OSError:pass
  time.sleep(.01)
 raise AssertionError('daemon startup')
with tempfile.TemporaryDirectory() as d:
 profile=d+'/profile';path=d+'/eva.sock';os.chmod(d,0o700)
 daemon=launch(profile,path);parent,pipe=multiprocessing.Pipe();old=multiprocessing.Process(target=child,args=(path,pipe));old.start();token=parent.recv()
 try:
  # Exclusive profile lock must reject another daemon, never unlink socket.
  duplicate=subprocess.run([BIN,profile],env={**os.environ,'EVA_COMPANION_SOCKET':path},capture_output=True);assert duplicate.returncode!=0
  os.kill(old.pid,signal.SIGSTOP)
  new=Host(path,'new');new.geometry();new.send({'type':'recall'});p=new.until('prepare');new.send(dict(type='prepared',epoch=p['epoch']))
  deadline=time.monotonic()+.4
  while time.monotonic()<deadline:
   try:assert new.read(.05)['type']!='grant'
   except socket.timeout:pass
  journal=json.load(open(profile+'/residence.json'));assert journal['revoke_intent'] and journal['possible_body']==token
  # No lease expiry or PID responsiveness permits grant.
  os.kill(old.pid,signal.SIGCONT);parent.send('retire');assert parent.recv()=='retired';newtoken=new.until('grant')['token'];assert newtoken['epoch']>token['epoch']
  # Daemon SIGKILL after grant must recover exact old possible-body token.
  daemon.kill();daemon.wait();new.s.close();parent.send('close');old.join(2)
  daemon=launch(profile,path);recovery=Host(path,'new');revoke=recovery.until('revoke');assert revoke['token']==newtoken
  contender=Host(path,'third');contender.geometry();contender.send({'type':'recall'})
  deadline=time.monotonic()+.2
  while time.monotonic()<deadline:
   try: assert contender.read(.03)['type'] not in ('prepare','grant')
   except socket.timeout: pass
  bad=dict(newtoken);bad['boot_id']='forged';recovery.send(dict(type='retired',token=bad,presentation_serial=3));assert recovery.until('operation_error')['reason']=='invalid_retirement_proof'
  recovery.send(dict(type='retired',token=newtoken,presentation_serial=3));time.sleep(.05)
  p=contender.until('prepare');contender.send(dict(type='prepared',epoch=p['epoch']));assert contender.until('grant')['token']['boot_id']!=newtoken['boot_id']
  # Disconnect retains possible body; no autonomous reassignment.
  contender.s.close();time.sleep(.05);assert json.load(open(profile+'/residence.json'))['phase']=='recovery_blocked'
  print('PASS: real IPC, exclusive lock, SIGSTOP block, exact retirement, daemon SIGKILL recovery, stale-proof rejection, disconnect fail-closed')
 finally:
  if old.is_alive():os.kill(old.pid,signal.SIGCONT);old.terminate();old.join()
  daemon.terminate();daemon.wait()

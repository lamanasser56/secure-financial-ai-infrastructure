"""Assessment-only global SDK-dispatch cap. No initialization/reset fallback or request logging.

A trusted setup Job seeds the fresh registered persistent volume once. Reserve is committed and fsynced
before calling the SDK; failed SDK calls consume quota. Untrusted workloads cannot access this volume.
"""
import fcntl
import json
import os
from pathlib import Path
import secrets
import re

RUN=os.environ.get('ASSESSMENT_RUN_ID','')
if not re.fullmatch(r'assess-[0-9a-f]{16}',RUN):
 raise RuntimeError('exact assessment run ID required')
LIMIT=60
class Exhausted(RuntimeError):pass

class Ledger:
 def __init__(self,path):self.path=Path(path)
 def reserve(self):
  with open(str(self.path)+'.lock','a+b') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
   # Missing/corrupt state fails closed, including after a restart or storage loss.
   state=json.loads(self.path.read_text())
   if set(state)!={'run_id','limit','used'} or state['run_id']!=RUN or state['limit']!=LIMIT or type(state['used']) is not int or not 0<=state['used']<LIMIT:
    raise Exhausted('SDP assessment budget unavailable or exhausted')
   state['used']+=1
   temporary=self.path.with_name(self.path.name+'.pending')
   fd=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
   try:
    with os.fdopen(fd,'w') as output:
     json.dump(state,output,sort_keys=True);output.flush();os.fsync(output.fileno())
    os.replace(temporary,self.path)
    directory=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
   finally:
    if temporary.exists():temporary.unlink()
   return state['used']

class CompletedLedger:
 """Durable 20-response ceiling, separate from the 60 SDK-attempt ceiling.

 A reservation is persisted before SDP work, so concurrent requests cannot
 complete a 21st response. A crash leaves its reservation in flight and thus
 consumes capacity until independent reconciliation; it never resets a cap.
 """
 LIMIT=20
 def __init__(self,path):self.path=Path(path)
 def _locked(self,update):
  with open(str(self.path)+'.lock','a+b') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
   state=json.loads(self.path.read_text())
   if (set(state)!={'run_id','limit','completed','inflight'} or state['run_id']!=RUN
       or state['limit']!=self.LIMIT or type(state['completed']) is not int
       or not 0<=state['completed']<=self.LIMIT or type(state['inflight']) is not list
       or any(type(v) is not str or len(v)!=32 or any(c not in '0123456789abcdef' for c in v)
              for v in state['inflight']) or len(set(state['inflight']))!=len(state['inflight'])
       or state['completed']+len(state['inflight'])>self.LIMIT):
    raise Exhausted('completed-redaction ledger unavailable')
   result=update(state)
   temporary=self.path.with_name(self.path.name+'.pending')
   fd=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
   try:
    with os.fdopen(fd,'w') as output:
     json.dump(state,output,sort_keys=True);output.flush();os.fsync(output.fileno())
    os.replace(temporary,self.path)
    directory=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
   finally:
    if temporary.exists():temporary.unlink()
   return result
 def reserve(self):
  token=secrets.token_hex(16)
  def update(state):
   if state['completed']+len(state['inflight'])>=self.LIMIT:
    raise Exhausted('completed-redaction limit exhausted')
   state['inflight'].append(token)
   return token
  return self._locked(update)
 def complete(self,token):
  def update(state):
   if token not in state['inflight'] or state['completed']>=self.LIMIT:
    raise Exhausted('completed-redaction reservation missing')
   state['inflight'].remove(token);state['completed']+=1
   return state['completed']
  return self._locked(update)
 def abort(self,token):
  def update(state):
   if token not in state['inflight']:
    raise Exhausted('completed-redaction reservation missing')
   state['inflight'].remove(token)
  return self._locked(update)

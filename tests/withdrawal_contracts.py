#!/usr/bin/env python3
"""Real private daemon IPC: negotiated admission and exact old-token lifecycle.

Declared presentation serials are protocol fixtures, NOT native/GPU/scene proof.
No GUI, audio device, provider, model, daily profile or external service is used.
The inherited legacy contracts run on the same exact new daemon binary.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import socket
import time
import unittest

import ipc_contracts as legacy

OBSERVATIONS=[]

class ModernPeer(legacy.Peer):
    def __init__(self,path,name):
        self.socket=socket.socket(socket.AF_UNIX);self.socket.settimeout(3);self.socket.connect(str(path))
        self.name,self.boot,self.seq=name,'',0;self.pending=deque();self.epoch=0;self.geometry_revision=0
        try:
            self.send(dict(type='hello_with_features',host=dict(id=name,incarnation=1,surface_id='test-surface',retirement='native_presented'),features=['withdrawal_resume_v1']))
            deadline=time.monotonic()+3
            while True:
                reply=self.read(deadline)
                if reply['type']=='rejected':raise legacy.PeerRejected(reply['reason'])
                if reply['type']=='host_accepted':break
                self.pending.append(reply)
            assert reply['features']==['withdrawal_resume_v1']
            self.boot=reply['boot_id'];self.nonce=reply['connection_nonce']
        except Exception:
            self.socket.close();raise
    def activate(self):
        self.send(dict(type='activate_host',connection_nonce=self.nonce));reply=self.until('host_activated')
        assert reply['connection_nonce']==self.nonce;self.epoch=reply['admission_epoch'];return reply
    def metadata(self,metadata,nonce=None,epoch=None):
        self.send(dict(type='host_metadata',connection_nonce=self.nonce if nonce is None else nonce,
                       admission_epoch=self.epoch if epoch is None else epoch,metadata=metadata))
    def geometry(self,revision=None,safe=True):
        if revision is None:self.geometry_revision+=1;revision=self.geometry_revision
        rect=dict(x=0.,y=0.,width=500.,height=500.)
        self.metadata(dict(type='geometry',revision=revision,viewport=rect,candidates=[rect] if safe else [],exclusions=[]))
    def withdraw(self,intent,previous=None,nonce=None):
        self.send(dict(type='withdraw_intent',connection_nonce=self.nonce if nonce is None else nonce,intent=intent,previous_token=previous))
    def resume(self,intent,nonce=None):
        self.send(dict(type='resume_withdrawal',connection_nonce=self.nonce if nonce is None else nonce,intent=intent))
    def resumed(self,intent):
        reply=self.until('withdrawal_resumed',lambda r:r['intent']==intent and r['connection_nonce']==self.nonce)
        self.epoch=reply['admission_epoch'];return reply
    def ready(self,intent):
        return self.until('withdrawal_ready',lambda r:r['intent']==intent and r['connection_nonce']==self.nonce)
    def retire(self,token,serial=1):
        self.send(dict(type='retired',token=token,presentation_serial=serial))
        return self.until('retirement_accepted',lambda r:r['token']==token)

class WithdrawalContracts(legacy.DaemonContracts):
    def modern(self,name):
        peer=ModernPeer(self.path,name);self.peers.append(peer);return peer
    def reconnect(self,name):
        deadline=time.monotonic()+3
        while True:
            try:return self.modern(name)
            except legacy.PeerRejected as error:
                if str(error)!='host_already_connected' or time.monotonic()>=deadline:raise
                time.sleep(.01)
    def journal(self):return json.loads((self.profile/'residence.json').read_text())
    def error(self,peer,reason):
        reply=peer.until('operation_error',lambda r:r['reason']==reason);self.assertEqual(reply['reason'],reason)
    def test_modern_resume_requires_proof_and_fresh_scoped_metadata(self):
        peer=self.modern('modern');peer.activate();token=peer.acquire();peer.withdraw(1,token)
        peer.resume(1);self.error(peer,'withdrawal_proof_pending')
        self.assertEqual(peer.until('revoke')['token'],token);self.assertEqual(self.journal()['possible_body'],token)
        peer.send(dict(type='retired',token=token,presentation_serial=0));self.error(peer,'invalid_retirement_proof')
        self.assertEqual(self.journal()['possible_body'],token)
        peer.retire(token);ready=peer.ready(1);self.assertEqual(ready['retired_token'],token)
        peer.resume(1);resumed=peer.resumed(1);self.assertEqual(resumed['retired_token'],token);self.assertEqual(peer.epoch,2)
        old=dict(type='geometry',revision=99999,viewport=dict(x=0.,y=0.,width=500.,height=500.),candidates=[],exclusions=[])
        peer.metadata(old,epoch=1);self.error(peer,'stale_host_admission')
        fresh=peer.acquire();self.assertGreater(fresh['epoch'],token['epoch'])
        for field in ['host_id','incarnation','surface_id','companion_id']:self.assertEqual(fresh[field],token[field])
        peer.retire(token,33);self.assertEqual(self.journal()['possible_body'],fresh)
        OBSERVATIONS.append(dict(case='scoped_resume',old_token=token,new_token=fresh,old_metadata_rejected=True,old_retirement_did_not_clear_current=True))
    def test_new_connection_rejects_old_cancel_and_metadata_nonce(self):
        peer=self.modern('reconnect');peer.activate();old=peer.acquire();peer.withdraw(1,old)
        peer.until('revoke');peer.retire(old);peer.ready(1);nonce=peer.nonce;peer.close()
        peer=self.reconnect('reconnect');self.assertNotEqual(peer.nonce,nonce)
        peer.withdraw(2,old);peer.until('revoke');peer.retire(old,2);peer.ready(2)
        peer.resume(1,nonce);self.error(peer,'stale_host_connection')
        peer.metadata(dict(type='focus',focused=True),nonce=nonce,epoch=1);self.error(peer,'stale_host_admission')
        peer.resume(2);peer.resumed(2);fresh=peer.acquire()
        self.assertEqual(fresh['host_id'],old['host_id']);self.assertGreater(fresh['epoch'],old['epoch'])
        OBSERVATIONS.append(dict(case='connection_nonce',same_host=True,old_nonce_rejected=True,old_token=old,new_token=fresh))
    def test_duplicate_resume_preserves_geometry_and_old_cancel_cannot_cancel_new_intent(self):
        peer=self.modern('intents');peer.activate();peer.withdraw(1);peer.ready(1);peer.resume(1);peer.resumed(1)
        peer.geometry();epoch=peer.epoch;peer.resume(1);peer.resumed(1);self.assertEqual(peer.epoch,epoch)
        peer.send(dict(type='recall'));prepare=peer.until('prepare');peer.send(dict(type='prepared',epoch=prepare['epoch']));token=peer.until('grant')['token']
        peer.withdraw(2,token);peer.until('revoke');before=self.journal()['revision']
        peer.withdraw(2,token);peer.resume(1);self.error(peer,'stale_withdrawal_intent')
        self.assertEqual(self.journal()['possible_body'],token);self.assertEqual(self.journal()['revision'],before)
        peer.retire(token);peer.ready(2);peer.resume(2);peer.resumed(2);self.assertGreater(peer.epoch,epoch)
        OBSERVATIONS.append(dict(case='intent_order',duplicate_resume_kept_geometry=True,old_cancel_rejected=True,token=token))
    def test_cache_compaction_and_daemon_restart_preserve_old_token_obligation(self):
        peer=self.modern('compacted');peer.activate();old=peer.acquire();peer.withdraw(1,old);peer.until('revoke');peer.retire(old);peer.ready(1)
        old_boot=peer.boot;peer.close()
        for index in range(70):
            other=self.peer('history-'+str(index));token=other.acquire();other.send(dict(type='withdraw'));other.until('revoke')
            other.send(dict(type='retired',token=token,presentation_serial=index+2));other.until('retirement_accepted',lambda r:r['token']==token);other.until('withdrawal_accepted');other.close()
        before=self.journal();self.assertEqual(len(before['retired_tokens']),64);self.assertNotIn(old,before['retired_tokens'])
        self.stop();self.start();peer=self.reconnect('compacted');self.assertNotEqual(peer.boot,old_boot)
        peer.withdraw(1,old);self.assertEqual(peer.until('revoke')['token'],old);peer.retire(old,1000)
        self.assertEqual(peer.ready(1)['retired_token'],old);peer.resume(1);self.assertEqual(peer.resumed(1)['retired_token'],old)
        fresh=peer.acquire();self.assertEqual(fresh['host_id'],old['host_id']);self.assertGreater(fresh['epoch'],before['epoch'])
        OBSERVATIONS.append(dict(case='compaction_restart',old_token=old,new_token=fresh,retained_exact_tokens=64,old_exact_entry_compacted=True,durable_retirement_watermark=before['retired_tokens'][-1]['epoch'],declared_fixture_serial=1000,native_proof_claimed=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    if os.environ.get('XDG_SESSION_ID')!=legacy.SESSION:parser.error('launch with XDG_SESSION_ID='+legacy.SESSION)
    legacy.BINARY=args.binary.resolve(strict=True)
    result=unittest.main(argv=[__file__],verbosity=2,exit=False).result
    report=dict(schema=1,scope=__doc__,passed=result.wasSuccessful(),tests=result.testsRun,binary_sha256=hashlib.sha256(legacy.BINARY.read_bytes()).hexdigest(),observations=OBSERVATIONS)
    args.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if report['passed'] else 1)

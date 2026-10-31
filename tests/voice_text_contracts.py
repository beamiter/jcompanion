#!/usr/bin/env python3
"""Real private daemon IPC: explicit review of Eva's retained spoken reply.

Fresh offline profiles and private sockets. Eva is a protocol peer that
records a real reference chain (including the reply digest) and answers text
requests; hosts and the desktop observer are real socket peers. No GUI,
audio device, provider, model or daily profile is used.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import time
import unittest

import history_contracts
import ipc_contracts as legacy
from history_contracts import DesktopPeer, HistoryContracts

FEATURES = ['withdrawal_resume_v1', 'dialogue_history_v1', 'voice_text_v1']


def digest(text):
    return hashlib.sha256(json.dumps(text, ensure_ascii=False).encode()).hexdigest()


class VoicePeer(legacy.Peer):
    def __init__(self, path, name, version=3):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(3)
        self.socket.connect(str(path))
        self.name, self.boot, self.seq = name, '', 0
        self.clocked = True
        self.pending = deque()
        self.send(dict(type='eva_hello_dialogue', clock='linux_boottime_ns_v1',
                       dialogue_version=version))
        accepted = self.until('eva_clocked')
        assert accepted['dialogue_version'] == version, accepted
        self.boot = accepted['boot_id']

    def emit(self, event, activation, turn):
        self.send(dict(type='voice_dialogue', voice_session_id=activation, turn_id=turn,
                       observed_at_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME), event=event))

    def spoken_turn(self, activation, turn, reply):
        self.send(dict(type='voice_acquire', session_id=activation))
        assert self.until('voice_permit')['granted']
        self.send(dict(type='audio', turn_id=turn, state='thinking', generated_samples=0,
                       played_samples=None, interrupted=False))
        for event in [dict(kind='input_committed', item_id='input-' + turn),
                      dict(kind='response_completed', response_id='plan-' + turn,
                           phase='plan', status='completed'),
                      dict(kind='response_completed', response_id='feedback-' + turn,
                           phase='feedback', status='completed'),
                      dict(kind='reply_generated', response_id='feedback-' + turn,
                           content_digest=digest(reply))]:
            self.emit(event, activation, turn)
        self.send(dict(type='voice_release', session_id=activation))
        self.until('voice_released')

    def answer(self, body):
        self.send(body)


class VoiceTextContracts(HistoryContracts):
    def voice(self, name='eva-voice', version=3):
        peer = VoicePeer(self.path, name, version)
        self.peers.append(peer)
        return peer

    def text_host(self, name, features=FEATURES):
        return self.host(name, features)

    def request(self, host, context, scope=None, kind='voice_text_review'):
        host.request_id += 1
        body: dict = dict(type=kind, request_id=host.request_id, context=context)
        if kind == 'voice_text_review':
            body['scope'] = scope or dict(kind='global')
        host.send(body)
        return host.request_id

    def status(self, host, request_id, timeout=3):
        return host.until('voice_text', lambda r: r['request_id'] == request_id and
                          r['status'] != 'voice_text_requested', timeout)['status']

    def entries(self):
        path = self.profile / 'memory.sqlite'
        with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
            return [dict(zip(('scope', 'key', 'value', 'source'), row)) for row in
                    db.execute('SELECT scope,key,value,source FROM entries ORDER BY id')]

    def test_verified_reply_becomes_an_explicitly_approved_memory_with_voice_source(self):
        eva = self.voice()
        self.assertEqual(eva.until('voice_text_retention')['enabled'], True)
        reply = '好的，窗口已经移到右边。'
        eva.spoken_turn('activation-1', 'turn-1', reply)
        host = self.text_host('forge-voice')
        self.assertEqual(host.features, FEATURES)
        context = host.context(project='p')
        request_id = self.request(host, context)
        asked = eva.until('voice_text_request')
        self.assertEqual((asked['voice_session_id'], asked['turn_id']), ('activation-1', 'turn-1'))
        eva.answer(dict(type='voice_text_offer', request_id=asked['request_id'],
                        voice_session_id='activation-1', turn_id='turn-1', reply=reply,
                        caption='把窗口移到右边'))
        review = host.until('memory_review')['review']
        self.assertEqual(self.status(host, request_id), 'voice_text_review_ready')
        change = review['change']
        self.assertEqual(change['source_event_id'], 'voice:activation-1:turn-1')
        self.assertIn('Eva: ' + reply, change['value'])
        self.assertIn('把窗口移到右边', change['value'])
        self.assertFalse((self.profile / 'memory.sqlite').exists() and self.entries(),
                         'a review alone must not write memory')
        host.send(dict(type='memory_approve', context=context, review_id=review['id'],
                       digest=review['digest']))
        self.assertEqual(host.until('memory_result')['status'], 'committed')
        saved = self.entries()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['source'], 'voice:activation-1:turn-1')
        for ledger in ('dialogue-index.json', 'dialogue-events.json'):
            self.assertNotIn(reply, (self.profile / ledger).read_text())
        self.record('save', source=saved[0]['source'], scope=saved[0]['scope'])

    def test_unrequested_mismatched_or_wrong_turn_text_is_never_proposed(self):
        eva = self.voice()
        eva.until('voice_text_retention')
        eva.spoken_turn('activation-1', 'turn-1', 'The real reply.')
        eva.answer(dict(type='voice_text_offer', request_id=1, voice_session_id='activation-1',
                        turn_id='turn-1', reply='The real reply.', caption=None))
        self.assertEqual(eva.until('operation_error')['reason'], 'voice_text_not_requested')
        host = self.text_host('ember-voice')
        context = host.context(project='p')
        outcomes = []
        for reply, turn in [('A forged reply.', 'turn-1'), ('The real reply.', 'turn-9')]:
            request_id = self.request(host, context)
            asked = eva.until('voice_text_request')
            eva.answer(dict(type='voice_text_offer', request_id=asked['request_id'],
                            voice_session_id='activation-1', turn_id=turn, reply=reply,
                            caption=None))
            outcomes.append(self.status(host, request_id))
        self.assertEqual(outcomes, ['voice_text_digest_mismatch', 'voice_text_wrong_turn'])
        self.assertFalse([r for r in host.pending if r['type'] == 'memory_review'])
        self.assertFalse((self.profile / 'memory.sqlite').exists() and self.entries())
        self.record('mismatch', outcomes=outcomes)

    def test_pause_and_lock_disable_retention_and_refuse_review(self):
        eva = self.voice()
        self.assertTrue(eva.until('voice_text_retention')['enabled'])
        eva.spoken_turn('activation-1', 'turn-1', 'Reply.')
        host = self.text_host('frost-voice')
        context = host.context(project='p')
        host.send(dict(type='memory_pause', paused=True))
        host.until('memory_result')
        self.assertFalse(eva.until('voice_text_retention')['enabled'])
        self.assertEqual(self.status(host, self.request(host, context)), 'memory_paused')
        host.send(dict(type='memory_pause', paused=False))
        host.until('memory_result')
        self.assertTrue(eva.until('voice_text_retention')['enabled'])
        desktop = DesktopPeer(self.path, 'desktop')
        self.peers.append(desktop)
        desktop.lock(True)
        self.assertFalse(eva.until('voice_text_retention')['enabled'])
        self.assertEqual(self.status(host, self.request(host, context)),
                         'desktop_locked_or_unknown')
        desktop.lock(False)
        self.assertTrue(eva.until('voice_text_retention')['enabled'])
        self.record('retention', paused=False, locked=False)

    def test_forget_unavailable_and_timeout_are_relayed_truthfully(self):
        eva = self.voice()
        eva.until('voice_text_retention')
        eva.spoken_turn('activation-1', 'turn-1', 'Reply.')
        host = self.text_host('anvil-voice')
        context = host.context(project='p')
        request_id = self.request(host, context, kind='voice_text_forget')
        asked = eva.until('voice_text_forget')
        eva.answer(dict(type='voice_text_forgotten', request_id=asked['request_id'], count=1))
        self.assertEqual(self.status(host, request_id), 'voice_text_forgotten')
        request_id = self.request(host, context)
        asked = eva.until('voice_text_request')
        eva.answer(dict(type='voice_text_unavailable', request_id=asked['request_id'],
                        reason='not_retained'))
        self.assertEqual(self.status(host, request_id), 'voice_text_not_retained')
        request_id = self.request(host, context)
        eva.until('voice_text_request')
        self.assertEqual(self.status(host, request_id, timeout=8), 'voice_text_timeout')
        request_id = self.request(host, context)
        eva.until('voice_text_request')
        eva.close()
        self.peers.remove(eva)
        self.assertEqual(self.status(host, request_id), 'voice_text_eva_unavailable')
        self.record('relay', forget=True, timeout=True)

    def test_older_eva_and_hosts_keep_working_without_text(self):
        eva = self.voice('old-eva', version=2)
        eva.spoken_turn('activation-1', 'turn-1', 'Reply.')
        host = self.text_host('forge-new')
        context = host.context(project='p')
        self.assertEqual(self.status(host, self.request(host, context)),
                         'voice_text_eva_unavailable')
        self.assertFalse([r for r in eva.pending if r['type'].startswith('voice_text')])
        older = self.host('forge-old', FEATURES[:2])
        self.assertEqual(older.features, FEATURES[:2])
        old_context = older.context(project='p')
        self.assertEqual(self.status(older, self.request(older, old_context)),
                         'voice_text_not_negotiated')
        self.record('compatibility', old_eva='no text', old_host='not negotiated')


def own_tests():
    names = sorted(n for n in VoiceTextContracts.__dict__ if n.startswith('test_'))
    return unittest.TestSuite(VoiceTextContracts(name) for name in names)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('XDG_SESSION_ID') != legacy.SESSION:
        parser.error('launch with XDG_SESSION_ID=' + legacy.SESSION)
    legacy.BINARY = args.binary.resolve(strict=True)
    result = unittest.TextTestRunner(verbosity=2).run(own_tests())
    report = dict(schema=1, scope=(__doc__ or '').strip(), passed=result.wasSuccessful(),
                  tests=result.testsRun,
                  failures=[str(t) for t, _ in result.failures + result.errors],
                  binary_sha256=hashlib.sha256(legacy.BINARY.read_bytes()).hexdigest(),
                  observations=history_contracts.OBSERVATIONS)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if report['passed'] else 1)

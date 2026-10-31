#!/usr/bin/env python3
"""Real private daemon IPC: negotiated, scope-bound dialogue history pages.

A fresh offline profile and a private socket per test. Hosts are real socket
peers; the desktop observer is this Python executable, explicitly authorized
through EVA_COMPANION_DESKTOP_EXE. No GUI, audio, provider or daily profile.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import unittest

import ipc_contracts as legacy

BASE = ['withdrawal_resume_v1']
EXTENDED = ['withdrawal_resume_v1', 'dialogue_history_v1']
OBSERVATIONS = []


class HistoryPeer(legacy.Peer):
    def __init__(self, path, name, features=EXTENDED):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(3)
        self.socket.connect(str(path))
        self.name, self.boot, self.seq = name, '', 0
        self.clocked = False
        self.pending = deque()
        self.request_id = 0
        try:
            self.send(dict(type='hello_with_features', host=dict(
                id=name, incarnation=1, surface_id='test-surface',
                retirement='native_presented'), features=features))
            deadline = time.monotonic() + 3
            while True:
                reply = self.read(deadline)
                if reply['type'] == 'rejected':
                    raise legacy.PeerRejected(reply['reason'])
                if reply['type'] == 'host_accepted':
                    break
                self.pending.append(reply)
            self.features = reply['features']
            self.boot, self.nonce = reply['boot_id'], reply['connection_nonce']
            self.send(dict(type='activate_host', connection_nonce=self.nonce))
            self.epoch = self.until('host_activated')['admission_epoch']
        except Exception:
            self.socket.close()
            raise

    def context(self, task=None, project=None, revision=1, pane='pane-a'):
        context = dict(host_id=self.name, pane_id=pane, task_id=task,
                       project_id=project, revision=revision)
        self.send(dict(type='host_metadata', connection_nonce=self.nonce,
                       admission_epoch=self.epoch,
                       metadata=dict(type='context_observed', context=context)))
        return context

    def say(self, turn, context, text=None):
        self.send(dict(type='dialogue_start', turn_id=turn, context=context,
                       text=text or f'question {turn}', approved_selection=None))
        reply = self.until('dialogue', lambda r: r['turn_id'] == turn)
        assert reply['status'] == 'offline', reply
        return reply

    def history(self, context, scope, before=None):
        self.request_id += 1
        request_id = self.request_id
        self.send(dict(type='dialogue_history', request_id=request_id,
                       context=context, scope=scope, before=before))
        reply = self.until('dialogue_history', lambda r: r['request_id'] == request_id)
        assert reply['context'] == context and reply['scope'] == scope
        assert len(json.dumps(reply)) <= legacy.MAX_FRAME
        return reply


class DesktopPeer(legacy.Peer):
    def __init__(self, path, name):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(3)
        self.socket.connect(str(path))
        self.name, self.boot, self.seq = name, '', 0
        self.clocked = False
        self.pending = deque()
        self.send(dict(type='desktop_hello'))
        self.boot = self.until('accepted')['boot_id']

    def lock(self, locked):
        self.send(dict(type='session_lock', locked=locked))


def ids(reply):
    return [e['turn_id'] for e in reply['entries']]


class HistoryContracts(legacy.DaemonContracts):
    def start(self):
        self.env['EVA_COMPANION_DESKTOP_EXE'] = os.path.realpath(sys.executable)
        super().start()

    def host(self, name, features=EXTENDED):
        deadline = time.monotonic() + 3
        while True:
            try:
                peer = HistoryPeer(self.path, name, features)
                break
            except legacy.PeerRejected as error:
                if str(error) != 'host_already_connected' or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)
        self.peers.append(peer)
        return peer

    def record(self, name, **facts):
        OBSERVATIONS.append(dict(test=self._testMethodName, check=name, **facts))

    def test_history_is_negotiated_and_echoed_exactly(self):
        modern = self.host('modern-extended')
        self.assertEqual(modern.features, EXTENDED)
        base = self.host('modern-base', BASE)
        self.assertEqual(base.features, BASE)
        context = base.context(project='p')
        base.say('base-turn', context)
        base.request_id += 1
        base.send(dict(type='dialogue_history', request_id=1, context=context,
                       scope='context', before=None))
        error = base.until('operation_error', lambda r: r['operation'] == 'dialogue_history')
        self.assertEqual(error['reason'], 'history_not_negotiated')
        for features in (['dialogue_history_v1'], EXTENDED[::-1], EXTENDED + EXTENDED[1:]):
            with self.assertRaises(legacy.PeerRejected) as rejected:
                HistoryPeer(self.path, 'invalid-' + str(len(features)), features)
            self.assertEqual(str(rejected.exception), 'invalid_host_features')
        self.record('negotiation', extended=modern.features, base=base.features)

    def test_scopes_isolate_projects_tasks_and_panes_across_real_hosts(self):
        ember, forge, frost = self.host('ember-a'), self.host('forge-b'), self.host('frost-c')
        a = ember.context(task='task-1', project='project-a', pane='ember-pane')
        b = forge.context(task='task-9', project='project-b', pane='forge-pane')
        # Another host cannot adopt task-1 without the existing share review.
        c = frost.context(task='task-2', project='project-a', pane='frost-pane')
        ember.say('a1', a)
        forge.say('b1', b, 'secret for project b only')
        frost.say('c1', c)
        ember.say('a2', a)
        self.assertEqual(ids(ember.history(a, 'context')), ['a2', 'a1'])
        self.assertEqual(ids(ember.history(a, 'project')), ['a2', 'c1', 'a1'])
        self.assertEqual(ids(ember.history(a, 'task')), ['a2', 'a1'])
        self.assertEqual(ids(frost.history(c, 'task')), ['c1'])
        project_b = forge.history(b, 'project')
        self.assertEqual(ids(project_b), ['b1'])
        self.assertEqual(project_b['entries'][0]['input'], 'secret for project b only')
        for reply in (ember.history(a, 'project'), frost.history(c, 'project')):
            self.assertNotIn('secret for project b only', json.dumps(reply))
        shared = frost.history(c, 'project')['entries'][0]
        self.assertEqual(shared['source']['host_id'], 'ember-a')
        self.assertEqual(shared['text'], 'shown')
        # A context other than the host's current one is refused, never served.
        stale = dict(a, project_id='project-b')
        self.assertEqual(ember.history(stale, 'project')['status'], 'stale_context')
        foreign = dict(b)
        ember.send(dict(type='dialogue_history', request_id=99, context=foreign,
                        scope='project', before=None))
        reply = ember.until('dialogue_history', lambda r: r['request_id'] == 99)
        self.assertEqual((reply['status'], reply['entries']), ('stale_context', []))
        bare = ember.context(pane='scratch')
        self.assertEqual(ember.history(bare, 'project')['status'], 'scope_unavailable')
        self.assertEqual(ember.history(bare, 'voice')['entries'], [])
        self.record('isolation', project_a=ids(ember.history(a, 'project')),
                    project_b=ids(forge.history(b, 'project')))

    def test_lock_and_unknown_desktop_withdraw_and_refuse_pages(self):
        legacy_host = legacy.Peer(self.path, 'legacy-host')
        self.peers.append(legacy_host)
        legacy_host.context(project='p')
        host = self.host('locked-host')
        context = host.context(project='p')
        host.say('t1', context)
        self.assertEqual(host.history(context, 'context')['status'], 'ok')
        desktop = DesktopPeer(self.path, 'desktop')
        self.peers.append(desktop)
        desktop.lock(True)
        withdrawn = host.until('dialogue_history_withdrawn')
        self.assertEqual(withdrawn['reason'], 'desktop_locked_or_unknown')
        locked = host.history(context, 'context')
        self.assertEqual((locked['status'], locked['entries']), ('desktop_locked_or_unknown', []))
        desktop.lock(False)
        deadline = time.monotonic() + 3
        while host.history(context, 'context')['status'] != 'ok':
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.02)
        desktop.close()
        self.peers.remove(desktop)
        host.until('dialogue_history_withdrawn')
        unknown = host.history(context, 'context')
        self.assertEqual((unknown['status'], unknown['entries']), ('desktop_locked_or_unknown', []))
        seen = list(legacy_host.pending)
        deadline = time.monotonic() + .3
        while True:
            try:
                seen.append(legacy_host.read(deadline))
            except socket.timeout:
                break
        self.assertTrue(seen, 'legacy host kept receiving its normal replies')
        self.assertFalse([r for r in seen if r['type'].startswith('dialogue_history')])
        self.record('lock', withdrawn=withdrawn['reason'], locked=locked['status'],
                    unknown=unknown['status'])

    def test_pages_are_bounded_newest_first_and_stale_cursors_refused(self):
        host = self.host('pager')
        context = host.context(project='p')
        turns = [f'turn-{n:02}' for n in range(11)]
        for turn in turns:
            host.say(turn, context)
        first = host.history(context, 'context')
        self.assertEqual(ids(first), turns[::-1][:8])
        self.assertEqual(first['next_before'], first['entries'][-1]['cursor'])
        host.say('late', context)
        second = host.history(context, 'context', first['next_before'])
        self.assertEqual(ids(second), turns[::-1][8:])
        self.assertIsNone(second['next_before'])
        unknown = host.history(context, 'context', '0' * 64)
        self.assertEqual((unknown['status'], unknown['entries']), ('history_cursor_stale', []))
        host.send(dict(type='dialogue_history', request_id=50, context=context,
                       scope='context', before='../etc'))
        self.assertEqual(host.until('operation_error')['reason'], 'invalid_history_request')
        host.send(dict(type='dialogue_history', request_id=0, context=context,
                       scope='context', before=None))
        self.assertEqual(host.until('operation_error')['reason'], 'invalid_history_request')
        self.record('paging', first=len(first['entries']), second=len(second['entries']))

    def test_restart_keeps_metadata_but_no_text_and_no_new_authority(self):
        host = self.host('restart-host')
        context = host.context(project='p')
        secret = 'session-only-dialogue-text'
        host.say('before-restart', context, secret)
        page = host.history(context, 'context')
        self.assertEqual(page['entries'][0]['input'], secret)
        self.assertNotIn(secret, (self.profile / 'dialogue-index.json').read_text())
        host.close()
        self.peers.remove(host)
        self.stop()
        self.start()
        host = self.host('restart-host')
        context = host.context(project='p')
        page = host.history(context, 'context')
        entry = page['entries'][0]
        self.assertEqual((entry['turn_id'], entry['text']), ('before-restart', 'earlier_session'))
        self.assertIsNone(entry['input'])
        self.assertIsNone(entry['reply'])
        self.assertNotIn(secret, json.dumps(page))
        self.record('restart', text=entry['text'], generated=entry['generated'])


def own_tests():
    names = sorted(n for n in HistoryContracts.__dict__ if n.startswith('test_'))
    return unittest.TestSuite(HistoryContracts(name) for name in names)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('XDG_SESSION_ID') != legacy.SESSION:
        parser.error('launch with XDG_SESSION_ID=' + legacy.SESSION)
    legacy.BINARY = args.binary.resolve(strict=True)
    result = unittest.TextTestRunner(verbosity=2).run(own_tests())
    report = dict(schema=1, scope=__doc__, passed=result.wasSuccessful(),
                  tests=result.testsRun,
                  failures=[str(t) for t, _ in result.failures + result.errors],
                  binary_sha256=hashlib.sha256(legacy.BINARY.read_bytes()).hexdigest(),
                  observations=OBSERVATIONS)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if report['passed'] else 1)

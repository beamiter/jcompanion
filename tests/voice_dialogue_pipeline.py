#!/usr/bin/env python3
"""Production Eva planning/feedback and observer into a real private daemon.

The Realtime server is loopback scripted data. The default case is noop;
--delayed executes the actual serial executor against an IPC stand-in only;
--voice-text keeps the real Eva process alive while this harness, as a real
host peer, asks for its retained spoken reply, reviews and approves it.
No audio device, API credential, external provider or real desktop action is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_voice_text(root, profile, socket):
    """Real host peer: request, inspect, approve. Returns observed facts."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ipc_contracts
    from history_contracts import HistoryPeer
    ipc_contracts.SESSION = 'eva-dialogue-pipeline'
    events = profile / 'dialogue-events.json'
    deadline = time.monotonic() + 20
    while not (events.exists() and 'reply_generated' in events.read_text()):
        if time.monotonic() > deadline:
            raise RuntimeError('Eva did not record a reply')
        time.sleep(.02)
    host = HistoryPeer(socket, 'forge-pipeline-host',
                       ['withdrawal_resume_v1', 'dialogue_history_v1', 'voice_text_v1'])
    try:
        context = host.context(project='pipeline')
        host.send(dict(type='voice_text_review', request_id=1, context=context,
                       scope=dict(kind='global')))
        review = host.until('memory_review', timeout=8)['review']
        status = host.until('voice_text', lambda r: r['status'] != 'voice_text_requested')
        assert status['status'] == 'voice_text_review_ready', status
        change = review['change']
        turn = json.loads(events.read_text())['turns'][0]
        assert change['source_event_id'] == 'voice:%s:%s' % (turn['voice_session_id'], turn['turn_id'])
        assert 'Eva: The operation result is not confirmed yet.' in change['value'], change
        assert 'not transcribed' in change['value']
        assert not (profile / 'memory.sqlite').exists() or not sqlite3.connect(
            'file:%s?mode=ro' % (profile / 'memory.sqlite'), uri=True).execute(
            'SELECT count(*) FROM entries').fetchone()[0]
        host.send(dict(type='memory_approve', context=context, review_id=review['id'],
                       digest=review['digest']))
        assert host.until('memory_result')['status'] == 'committed'
        with sqlite3.connect('file:%s?mode=ro' % (profile / 'memory.sqlite'), uri=True) as db:
            rows = db.execute('SELECT scope,value,source FROM entries').fetchall()
        assert len(rows) == 1 and rows[0][2] == change['source_event_id'], rows
        host.send(dict(type='voice_text_forget', request_id=2, context=context))
        forgotten = host.until('voice_text', lambda r: r['request_id'] == 2 and
                               r['status'] != 'voice_text_requested')
        assert forgotten['status'] == 'voice_text_forgotten', forgotten
        host.send(dict(type='voice_text_review', request_id=3, context=context,
                       scope=dict(kind='global')))
        after = host.until('voice_text', lambda r: r['request_id'] == 3 and
                           r['status'] != 'voice_text_requested')
        assert after['status'] == 'voice_text_not_retained', after
        for ledger in ('dialogue-index.json', 'dialogue-events.json'):
            assert 'The operation result is not confirmed yet.' not in (profile / ledger).read_text()
        return dict(review='ready', approved_source=rows[0][2], scope=rows[0][0],
                    forget='voice_text_forgotten', after_forget=after['status'])
    finally:
        host.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--eva-test', type=Path, required=True)
    parser.add_argument('--delayed', action='store_true')
    parser.add_argument('--voice-text', action='store_true')
    args = parser.parse_args()
    if args.voice_text and os.environ.get('XDG_SESSION_ID') != 'eva-dialogue-pipeline':
        parser.error('--voice-text: launch with XDG_SESSION_ID=eva-dialogue-pipeline')
    daemon = args.daemon.resolve(strict=True)
    eva = args.eva_test.resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix='eva-dialogue-pipeline-'))
    profile, socket = root / 'profile', root / 'eva.sock'
    env = {key: value for key, value in os.environ.items() if not (
        key.startswith(('EVA_COMPANION_', 'JWM_EVA_'))
        or key in ('OPENAI_API_KEY', 'SSH_CONNECTION', 'SSH_TTY'))}
    env.update(XDG_SESSION_ID='eva-dialogue-pipeline', EVA_COMPANION_SOCKET=str(socket),
               JWM_EVA_COMPANION='1', JWM_EVA_DIALOGUE_PIPELINE_TEST='1',
               JWM_EVA_DIALOGUE_PROFILE=str(profile), JWM_SOCKET=str(root/'native.sock'),
               JWM_EVA_VOICE_TEXT_DONE=str(root/'voice-text-done'))
    report = dict(scope=__doc__, root=str(root), daemon_sha256=sha(daemon),
                  eva_test_sha256=sha(eva), physical_audio=False,
                  external_provider=False, desktop_actions=False, passed=False)
    process = None
    try:
        with (root / 'daemon.log').open('w') as log:
            process = subprocess.Popen([str(daemon), str(profile)], env=env, stdout=log, stderr=log)
            deadline = time.monotonic() + 5
            while not socket.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('private daemon did not start')
                time.sleep(.01)
            with (root / 'pipeline.log').open('w') as output:
                test = ('companion_delayed_receipt_to_original_dialogue' if args.delayed else
                        'companion_voice_text_review_from_private_daemon' if args.voice_text else
                        'companion_dialogue_pipeline_to_private_daemon')
                child = subprocess.Popen([str(eva), 'session::tests::'+test,
                                          '--exact', '--ignored', '--nocapture'], env=env,
                                         stdout=output, stderr=subprocess.STDOUT)
                try:
                    if args.voice_text:
                        report['voice_text'] = review_voice_text(root, profile, socket)
                        (root / 'voice-text-done').touch()
                    returncode = child.wait(timeout=30)
                finally:
                    (root / 'voice-text-done').touch()
                    if child.poll() is None:
                        child.kill()
                        child.wait()
            if returncode != 0:
                raise RuntimeError('pipeline failed; see pipeline.log')
            text = (root / 'pipeline.log').read_text()
            assert '1 passed; 0 failed; 0 ignored' in text
            journal = json.loads((profile / 'dialogue-events.json').read_text())
            history = json.loads((profile / 'dialogue-index.json').read_text())
            events = journal['turns'][0]['events']
            if args.delayed:
                assert len(events) == 12
                assert events[6]['event']['kind'] == 'operation_registered'
                assert events[7]['event']['outcome'] == 'unknown'
                assert events[8]['event']['kind'] == 'tool_result' and events[8]['event']['outcome'] == 'unknown'
                assert events[-1]['event']['kind'] == 'operation_settled' and events[-1]['event']['outcome'] == 'succeeded'
                assert events[6]['event']['request_digest'] == events[-1]['event']['request_digest']
                assert events[6]['event']['operation_id'] == events[-1]['event']['operation_id']
                assert all(e['event']['kind'] == 'input_committed' for e in journal['turns'][1]['events'])
                execution = json.loads((root/'execution-probe.json').read_text())
                assert execution['dispatches'] == 1 and execution['status_queries'] == 2
                report['execution'] = execution
            else:
                assert [e['event']['kind'] for e in events] == [
                    'input_committed', 'response_completed', 'tool_call', 'tool_result',
                    'response_completed', 'tool_call', 'tool_result', 'response_completed', 'reply_generated']
                assert events[6]['event']['outcome'] == 'noop'
                assert events[6]['event']['operations'] == []
                assert events[7]['event']['phase'] == 'feedback'
            assert events[3]['event']['outcome'] == 'described'
            assert len({e['voice_session_id'] for e in events}) == 1
            assert len({e['turn_id'] for e in events}) == 1
            entry = history['turns'][0]['entry']
            assert entry['generated'] and entry['finished'] and not entry['displayed']
            assert entry['audio']['confirmed_played_samples'] == 0
            serialized = json.dumps(journal)
            assert 'No desktop changes were made.' not in serialized
            assert 'The operation result is not confirmed yet.' not in serialized
            assert '当前测试输入' not in serialized
            if args.voice_text:
                assert 'The operation result is not confirmed yet.' not in serialized
            report.update(passed=True, reference_events=len(events), tool_calls=2,
                          final_outcome='settled_original_operation' if args.delayed else 'noop', feedback_generated=True,
                          feedback_audibly_played=False)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))


if __name__ == '__main__':
    main()

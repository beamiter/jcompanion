"""Real Eva observation worker and private daemon ledger/IPC regression.

PlaybackHistory supplies fixture metadata. No microphone, speaker, provider or
physical timing evidence is claimed. Run with XDG_SESSION_ID=eva-c07-worker-probe.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import importlib.util
import select
import socket
import struct
import subprocess
import tempfile
import threading
import time
import traceback

REPO = Path(__file__).resolve().parents[1]
SESSION = 'eva-c07-worker-probe'


class Proxy:
    def __init__(self, path, target, log):
        self.path, self.target, self.log = path, target, log
        self.messages = []
        self.cv = threading.Condition()
        self.stop = threading.Event()
        self.cut = threading.Event()
        self.drop_kind = None
        self.hold_audio = threading.Event()
        self.flush_audio = threading.Event()
        self.held = []
        self.failure = None
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(path))
        path.chmod(0o600)
        self.listener.listen(1)
        self.listener.settimeout(0.1)
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def record(self, side, body, dropped=False):
        row = dict(side=side, body=body, dropped=dropped,
                   observed_ns=time.monotonic_ns())
        with self.cv:
            self.messages.append(row)
            self.log.write(json.dumps(row) + '\n')
            self.log.flush()
            self.cv.notify_all()

    def wait(self, side, predicate, after=0, timeout=10):
        end = time.monotonic() + timeout
        with self.cv:
            while True:
                for row in self.messages[after:]:
                    if row['side'] == side and predicate(row['body']):
                        return row
                if self.failure:
                    raise AssertionError(self.failure)
                if time.monotonic() >= end:
                    raise AssertionError(f'wire event missing: {side}; after={after}')
                self.cv.wait(0.05)

    def mark(self):
        with self.cv:
            return len(self.messages)

    def run(self):
        try:
            while not self.stop.is_set():
                try:
                    client, _ = self.listener.accept()
                except socket.timeout:
                    continue
                server = socket.socket(socket.AF_UNIX)
                try:
                    server.connect(str(self.target))
                    peers = {client: (server, 'client'), server: (client, 'server')}
                    buffers = {client: bytearray(), server: bytearray()}
                    for peer in peers:
                        peer.settimeout(1)
                    while not self.stop.is_set():
                        if self.flush_audio.is_set():
                            self.flush_audio.clear()
                            for frame in self.held:
                                server.sendall(frame)
                            self.held.clear()
                        if self.cut.is_set():
                            self.cut.clear()
                            break
                        ready, _, _ = select.select(list(peers), [], [], 0.05)
                        ended = False
                        for peer in ready:
                            chunk = peer.recv(65536)
                            if not chunk:
                                ended = True
                                break
                            buffers[peer].extend(chunk)
                            buffer = buffers[peer]
                            while len(buffer) >= 4:
                                size = struct.unpack('>I', buffer[:4])[0]
                                assert 0 < size <= 65536
                                if len(buffer) < size + 4:
                                    break
                                frame = bytes(buffer[:size + 4])
                                del buffer[:size + 4]
                                body = json.loads(frame[4:])
                                destination, side = peers[peer]
                                dropped = side == 'server' and body.get('type') == self.drop_kind
                                self.record(side, body, dropped)
                                if dropped:
                                    self.drop_kind = None
                                    ended = True
                                    break
                                if side == 'client' and body.get('body', {}).get('type') == 'audio_clocked' and self.hold_audio.is_set():
                                    self.held.append(frame)
                                else:
                                    destination.sendall(frame)
                            if ended:
                                break
                        if ended:
                            break
                except (ConnectionResetError, BrokenPipeError):
                    pass
                finally:
                    client.close()
                    server.close()
        except Exception as error:
            self.failure = repr(error)
            with self.cv:
                self.cv.notify_all()

    def close(self):
        self.stop.set()
        self.thread.join(3)
        self.listener.close()
        assert not self.thread.is_alive()
        assert not self.failure, self.failure


def kind(name):
    return lambda body: body.get('type') in ({'accepted', 'eva_clocked'} if name == 'accepted' else {name})


def request(name, **fields):
    return lambda envelope: (envelope.get('body', {}).get('type') in ({'audio', 'audio_clocked'} if name == 'audio' else {name})
                             and all(envelope['body'].get(k) == v for k, v in fields.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--eva-source', type=Path, required=True,
                        help='Actual jwm/eva/src/companion.rs to compile unchanged')
    args = parser.parse_args()
    daemon_path = args.daemon.resolve(strict=True)
    source = args.eva_source.resolve(strict=True)
    assert f'XDG_SESSION_ID={SESSION}'.encode() in Path('/proc/self/environ').read_bytes().split(b'\0')
    root = Path(tempfile.mkdtemp(prefix='eva-c07-worker-case-'))
    fixture = root / 'fixture'
    (fixture/'src').mkdir(parents=True)
    (fixture/'src/main.rs').write_bytes((REPO/'tests/fixtures/voice_worker.rs').read_bytes())
    (fixture/'src/production_companion.rs').write_bytes(source.read_bytes())
    (fixture/'src/companion').mkdir()
    (fixture/'src/companion/operations.rs').write_bytes((source.parent/'companion/operations.rs').read_bytes())
    (fixture/'Cargo.toml').write_text(
        '[package]\nname = "eva-c07-worker-probe"\nversion = "0.0.0"\nedition = "2024"\npublish = false\n'
        '[workspace]\n[dependencies]\n'
        + 'companion-client = { path = ' + json.dumps(str(REPO/'crates/companion-client')) + ' }\n'
        + 'companion-protocol = { path = ' + json.dumps(str(REPO/'crates/companion-protocol')) + ' }\n'
        + 'companion-voice = { path = ' + json.dumps(str(REPO/'crates/companion-voice')) + ' }\n'
        + 'serde_json = "1"\ntokio = { version = "1", features = ["rt", "sync", "time"] }\n')
    with (root/'build.log').open('w') as log:
        subprocess.run(['cargo', 'build', '--offline', '--manifest-path', str(fixture/'Cargo.toml')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    worker_path = fixture/'target/debug/eva-c07-worker-probe'
    for name in ['home', 'runtime', 'config', 'state', 'data']:
        (root / name).mkdir(mode=0o700)
    env = dict(PATH=os.environ['PATH'], HOME=str(root/'home'),
               XDG_SESSION_ID=SESSION, XDG_RUNTIME_DIR=str(root/'runtime'),
               XDG_CONFIG_HOME=str(root/'config'), XDG_STATE_HOME=str(root/'state'),
               XDG_DATA_HOME=str(root/'data'), EVA_COMPANION_SOCKET=str(root/'authority.sock'), EVA_COMPANION_DEBUG_VOICE='1')
    result = dict(passed=False, root=str(root), scope=__doc__,
                  daemon_sha256=hashlib.sha256(daemon_path.read_bytes()).hexdigest(),
                  worker_sha256=hashlib.sha256(worker_path.read_bytes()).hexdigest(),
                  exact_companion_source_sha256=hashlib.sha256((fixture/'src/production_companion.rs').read_bytes()).hexdigest(),
                  exact_operations_source_sha256=hashlib.sha256((fixture/'src/companion/operations.rs').read_bytes()).hexdigest(),
                  audio_device_opened=False, provider_called=False, checks=[])
    daemon = worker = proxy = viewer = None
    logs = []
    try:
        daemon_log = (root/'daemon.log').open('wb'); logs.append(daemon_log)
        daemon = subprocess.Popen([str(daemon_path), str(root/'profile')], env=env,
                                  stdout=daemon_log, stderr=subprocess.STDOUT)
        end = time.monotonic() + 5
        while not (root/'authority.sock').exists():
            assert daemon.poll() is None
            assert time.monotonic() < end
            time.sleep(0.01)
        wire_log = (root/'wire.jsonl').open('w'); logs.append(wire_log)
        proxy = Proxy(root/'bridge.sock', root/'authority.sock', wire_log)
        worker_log = (root/'worker.stderr').open('wb'); logs.append(worker_log)
        result['daemon_pid'] = daemon.pid
        worker = subprocess.Popen([str(worker_path)],
                                  env=dict(env, EVA_COMPANION_SOCKET=str(root/'bridge.sock'), JWM_EVA_COMPANION='1'),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=worker_log, text=True, bufsize=1)

        result['worker_pid'] = worker.pid

        def read():
            assert select.select([worker.stdout], [], [], 6)[0], 'worker response timeout'
            line = worker.stdout.readline()
            assert line, f'worker exited {worker.poll()}'
            return json.loads(line)

        def call(command, **arguments):
            worker.stdin.write(json.dumps(dict(command=command, **arguments)) + '\n')
            worker.stdin.flush()
            return read()

        def acquire_ready(generation):
            deadline = time.monotonic() + 6
            while True:
                value = call('acquire', generation=generation)
                if value['acquired']:
                    return value
                assert time.monotonic() < deadline, value
                time.sleep(.03)

        def ledger_record(predicate, timeout=5):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                lines = (root/'daemon.log').read_text().splitlines()
                for line in reversed(lines):
                    if line.startswith('EVA voice ledger '):
                        value = json.loads(line.removeprefix('EVA voice ledger '))
                        if predicate(value):
                            return value
                time.sleep(0.02)
            raise AssertionError('matching actual daemon ledger observation missing')

        result['ledger_observations'] = []
        assert read()['ready']
        accepted = proxy.wait('server', kind('accepted'))
        assert accepted['body']['type'] == 'eva_clocked'
        spec = importlib.util.spec_from_file_location('voice_contracts', REPO/'tests/ipc_contracts.py')
        contracts = importlib.util.module_from_spec(spec); spec.loader.exec_module(contracts)
        contracts.SESSION = SESSION
        viewer = contracts.Peer(root/'authority.sock', 'voice-viewer', retirement='none')
        acquired = acquire_ready(1)
        assert acquired['acquired']
        context = call('context')['context']
        assert context['companion_id'] and context['global_memory'] == []
        labels = dict(generation=1, session_epoch=1, turn_id=1)
        call('milestone', stage='activation', labels=labels)
        call('playback', labels=labels, generated=48000, played=480, drained=False)
        proxy.wait('client', request('audio', turn_id='eva-1-1-1', state='speaking'))
        ledger_record(lambda value: value['turn_id'] == 'eva-1-1-1' and value['confirmed_played_samples'] == 480)
        call('progress', generated=48000, played=None, drained=False)
        unknown = ledger_record(lambda value: value['turn_id'] == 'eva-1-1-1'
                                and value['reported_played_samples'] is None
                                and value['confirmed_played_samples'] == 480)
        assert unknown['generated'] and not unknown['displayed'] and not unknown['finished']
        assert unknown['companion_id'] == context['companion_id']
        result['ledger_observations'].append(unknown)
        call('progress', generated=48000, played=960, drained=False)
        ledger_record(lambda value: value['turn_id'] == 'eva-1-1-1' and value['confirmed_played_samples'] == 960)
        def await_pose(expected, timeout=4):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                pose = viewer.reply_pose()
                if (pose == expected) if isinstance(expected, str) else expected(pose):
                    return pose
            raise AssertionError(f'pose did not reach {expected}')

        assert await_pose('speak') == 'speak'
        time.sleep(.45)
        assert await_pose('speak') == 'speak', 'live unchanged data did not refresh'
        worker_fd = os.pidfd_open(worker.pid)
        try:
            signal.pidfd_send_signal(worker_fd, signal.SIGSTOP)
            time.sleep(.4)
            stopped_pose = await_pose(lambda pose: pose not in ('speak', 'listen'))
            blocked_context = viewer.context()
            viewer.send(dict(type='dialogue_start', turn_id='blocked-while-voice-paused', context=blocked_context, text='synthetic route exclusion check', approved_selection=None))
            assert viewer.until('dialogue')['status'] == 'eva_voice_route_active_or_recovery_blocked'
            assert ledger_record(lambda value: value['turn_id'] == 'eva-1-1-1' and value['confirmed_played_samples'] == 960)['finished'] is False
            signal.pidfd_send_signal(worker_fd, signal.SIGCONT)
            assert await_pose('speak') == 'speak'
            # Hold actual producer frames unchanged, then release them while the
            # producer is stopped. Buffered packets must not renew current pose.
            proxy.hold_audio.set()
            time.sleep(.5)
            signal.pidfd_send_signal(worker_fd, signal.SIGSTOP)
            time.sleep(.3)
            held_count = len(proxy.held)
            assert held_count >= 2, held_count
            proxy.hold_audio.clear(); proxy.flush_audio.set()
            time.sleep(.15)
            assert await_pose(lambda pose: pose not in ('speak', 'listen'))
            proxy.wait('server', lambda value: value.get('type') == 'operation_error' and value.get('reason') == 'audio_observation_stale_or_future')
            signal.pidfd_send_signal(worker_fd, signal.SIGCONT)
            assert await_pose('speak') == 'speak'
        finally:
            signal.pidfd_send_signal(worker_fd, signal.SIGCONT)
            os.close(worker_fd)
        result['checks'].append('stopped but connected producer and delayed original frames cannot keep speaking alive; fresh observations restore the same turn')
        result['checks'].append('stale audio pose does not release the durable voice route or allow text generation')
        result['freshness'] = dict(stopped_pose=stopped_pose, original_frames_delayed=held_count, timeout_is_device_release=False)
        connections_before = sum(row['side']=='client' and row['body'].get('body',{}).get('type')in ('eva_hello_clocked', 'eva_hello_dialogue') for row in proxy.messages)
        call('progress', generated=48000, played=960, drained=False, observed_at_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME)-1_000_000_000)
        time.sleep(.4)
        assert await_pose(lambda pose: pose not in ('listen','speak'))
        call('progress', generated=48000, played=960, drained=False)
        assert await_pose('speak')=='speak'
        connections_after = sum(row['side']=='client' and row['body'].get('body',{}).get('type')in ('eva_hello_clocked', 'eva_hello_dialogue') for row in proxy.messages)
        assert connections_after==connections_before, 'discarding an expired observation disconnected the healthy voice turn'
        result['checks'].append('a locally expired source observation is discarded without disconnecting or closing the current turn')
        call('end_playback', labels=labels, generated=48000, played=1440, interrupted=True)
        proxy.wait('client', request('audio', turn_id='eva-1-1-1', state='cancelling', interrupted=True))
        interrupted = ledger_record(lambda value: value['turn_id'] == 'eva-1-1-1' and value['end'] == 'interrupted')
        assert interrupted['confirmed_played_samples'] == 1440
        assert interrupted['generated_samples'] == 48000 and interrupted['finished']
        result['ledger_observations'].append(interrupted)
        marker = proxy.mark()
        call('progress', generated=48000, played=2400, drained=False)
        time.sleep(0.2)
        assert not any(request('audio', turn_id='eva-1-1-1')(row['body']) for row in proxy.messages[marker:])
        call('release')
        proxy.wait('server', lambda body: body.get('type') == 'voice_released' and body['session_id'] == acquired['session_id'])
        result['checks'].append('real worker connects, acquires, refreshes identity, closes interrupted turn and releases exact lease')

        marker = proxy.mark()
        proxy.drop_kind = 'voice_permit'
        deadline = time.monotonic() + 6
        while True:
            attempt = proxy.mark()
            assert call('acquire', generation=1)['acquired'] is False
            if any(row['side'] == 'client' and request('voice_acquire')(row['body']) for row in proxy.messages[attempt:]):
                break
            assert time.monotonic() < deadline
            time.sleep(.03)
        sent = proxy.wait('client', request('voice_acquire'), after=marker)['body']['body']
        assert sent['session_id'] != acquired['session_id'], 'new activation reused a prior lease identity'
        dropped = proxy.wait('server', kind('voice_permit'), after=marker)
        assert dropped['dropped'] and dropped['body']['granted']
        proxy.wait('client', request('voice_release', session_id=sent['session_id']), after=marker)
        proxy.wait('server', lambda body: body.get('type') == 'voice_released' and body['session_id'] == sent['session_id'], after=marker)
        result['checks'].append('lost accepted grant is released by the real acquire guard after reconnect')

        acquired = acquire_ready(3)
        assert acquired['acquired']
        labels = dict(generation=3, session_epoch=3, turn_id=1)
        call('milestone', stage='activation', labels=labels)
        call('playback', labels=labels, generated=24000, played=480, drained=False)
        proxy.wait('client', request('audio', turn_id='eva-3-3-1', state='speaking'))
        marker = proxy.mark(); proxy.cut.set()
        proxy.wait('server', kind('accepted'), after=marker)
        lost = ledger_record(lambda value: value['turn_id'] == 'eva-3-3-1' and value['end'] == 'observation_lost')
        assert lost['reported_played_samples'] is None and lost['confirmed_played_samples'] == 480
        assert not lost['interrupted'] and lost['finished']
        result['ledger_observations'].append(lost)
        marker = proxy.mark()
        call('progress', generated=24000, played=960, drained=False)
        time.sleep(0.2)
        assert not any(request('audio', turn_id='eva-3-3-1')(row['body']) for row in proxy.messages[marker:])
        labels['turn_id'] = 2
        call('milestone', stage='activation', labels=labels)
        call('playback', labels=labels, generated=24000, played=480, drained=False)
        proxy.wait('client', request('audio', turn_id='eva-3-3-2', state='speaking'), after=marker)
        result['checks'].append('transport loss prevents old audio-turn replay and a fresh local turn restores observation')

        marker = proxy.mark(); proxy.drop_kind = 'voice_released'
        call('release')
        proxy.wait('server', lambda body: body.get('type') == 'voice_released' and body['session_id'] == acquired['session_id'], after=marker)
        end = time.monotonic() + 10
        while True:
            releases = [row for row in proxy.messages[marker:] if row['side'] == 'server' and row['body'].get('type') == 'voice_released']
            if len(releases) >= 2:
                break
            assert time.monotonic() < end
            time.sleep(0.05)
        released = ledger_record(lambda value: value['turn_id'] == 'eva-3-3-2' and value['end'] == 'resources_released')
        assert released['confirmed_played_samples'] == 480 and released['finished']
        result['ledger_observations'].append(released)
        assert releases[0]['dropped'] and not releases[1]['dropped']
        assert all(row['body']['session_id'] == acquired['session_id'] for row in releases)
        acquired = acquire_ready(4)
        assert acquired['acquired']
        call('milestone', stage='activation', labels=dict(generation=4, session_epoch=4, turn_id=1))
        call('capture', active=True)
        assert await_pose('listen') == 'listen'
        time.sleep(.45)
        assert await_pose('listen') == 'listen'
        capture_fd = os.pidfd_open(worker.pid)
        try:
            signal.pidfd_send_signal(capture_fd, signal.SIGSTOP)
            time.sleep(.4)
            assert await_pose(lambda pose: pose not in ('listen', 'speak'))
            signal.pidfd_send_signal(capture_fd, signal.SIGCONT)
            assert await_pose('listen') == 'listen'
        finally:
            signal.pidfd_send_signal(capture_fd, signal.SIGCONT)
            os.close(capture_fd)
        call('capture', active=False)
        assert await_pose(lambda pose: pose not in ('listen', 'speak'))
        result['checks'].append('fresh capture pulses maintain listening; process pause and capture stop expire it without inventing played audio')
        call('release')
        proxy.wait('server', lambda body: body.get('type') == 'voice_released' and body['session_id'] == acquired['session_id'])
        result['checks'].append('lost release receipt retries the exact original lease and permits the next activation only after recovery')
        acquired = acquire_ready(5)
        labels = dict(generation=5, session_epoch=5, turn_id=1)
        call('milestone', stage='activation', labels=labels)
        proxy.wait('client', request('audio', turn_id='eva-5-5-1', state='connecting'))
        call('dialogue', session_id=acquired['session_id'], labels=labels,
             event=dict(kind='input_committed', item_id='owned-input'))
        proxy.wait('client', request('voice_dialogue', turn_id='eva-5-5-1'))
        call('dialogue', session_id=acquired['session_id'], labels=labels,
             event=dict(kind='tool_result', call_id='never-called', result_digest='a' * 64,
                        outcome='unknown', operations=[]))
        proxy.wait('server', lambda body: body.get('type') == 'operation_error'
                   and body.get('operation') == 'voice_dialogue')
        ledger_record(lambda value: value['turn_id'] == 'eva-5-5-1'
                      and value['end'] == 'observation_lost')
        call('release')
        assert not call('acquire', generation=6)['acquired']
        result['checks'].append('rejected tool references close the real observer; later acquisition cannot silently claim complete history')
        sources = {row['body']['source_id'] for row in proxy.messages if row['side'] == 'client'}
        assert len(sources) == 1
        result['stable_source_identity_across_reconnects'] = next(iter(sources))
        for row in proxy.messages:
            if row['side'] == 'client' and request('audio')(row['body']):
                assert set(row['body']['body']) == {'type','turn_id','state','generated_samples','played_samples','interrupted','observed_at_ns'}
        expected_fields = {'route', 'companion_id', 'source_id', 'session_id', 'turn_id',
                           'generated', 'displayed', 'generated_samples', 'reported_played_samples',
                           'confirmed_played_samples', 'interrupted', 'finished', 'end', 'observed_at_ns'}
        assert all(set(value) == expected_fields for value in result['ledger_observations'])
        result['checks'].append('actual shared ledger keeps unknown/current and confirmed/lower-bound playback separate, with distinct interruption, disconnect and release outcomes')
        result['dependency_scope'] = 'Exact copied Eva companion.rs with the current working-tree client/protocol and saved fixture Cargo.lock; not a production Eva binary or device test.'
        result['passed'] = True
    except Exception as error:
        result['error'] = repr(error)
        result['traceback'] = traceback.format_exc()
    finally:
        cleanup_errors = []
        if worker is not None and worker.poll() is None:
            try:
                worker.stdin.write('{"command":"exit"}\n'); worker.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            try:
                worker.wait(3)
            except subprocess.TimeoutExpired:
                worker.kill(); worker.wait()
        if viewer is not None:
            viewer.close()
        if proxy is not None:
            try:
                proxy.close()
            except Exception as error:
                cleanup_errors.append(repr(error))
        if daemon is not None and daemon.poll() is None:
            daemon.terminate()
            try:
                daemon.wait(3)
            except subprocess.TimeoutExpired:
                daemon.kill(); daemon.wait()
        for log in logs:
            log.close()
        result['cleanup'] = dict(worker_exited=worker is None or worker.poll() is not None,
                                 daemon_exited=daemon is None or daemon.poll() is not None,
                                 errors=cleanup_errors)
        if cleanup_errors:
            result['passed'] = False
        (root/'report.json').write_text(json.dumps(result, indent=2)+'\n')

    print(json.dumps(result))
    assert result['passed'], result


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Native >64 retirement compaction and lost-ack recovery in one private profile.

Three real same-frontend GUIs, actual native focus/body frames and JWM scene
receipts. A byte-preserving relay drops only the source's first exact retirement
ack; two other GUIs perform at least 70 verified handoffs. After daemon SIGKILL
and genuine reconnect, the same original GUI must obtain a new native clearance
for its compacted old token and a newly generated daemon ack. No host, task,
grant, serial or native proof is fabricated or replayed. Screenshots sample
default-Cat bodies, not physical/continuous uniqueness, audio/API or performance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

from native_close_intent import CloseIntentSession
from native_windows import host
from native_window_use import stat


class CompactionSession(CloseIntentSession):
    def __init__(self, args):
        super().__init__(args)
        self.cycler = self.frontend + '-3'
        self.instances[self.cycler] = self.frontend
        self.transitions = []
        self.recovery = {}
        for name in [Path(__file__).name, 'native_retirement_proxy.py']:
            shutil.copy2(Path(__file__).with_name(name), self.root / 'harness' / name)

    def launch(self, name, argv, **kwargs):
        if name in getattr(self, 'instances', {}):
            self.env['RUST_LOG'] += ',eva_native_host=debug'
        if name == 'daemon' and self.cycler not in self.windows:
            # All GUIs must exist before first authority. Launching the third
            # later would retire the source during setup and consume the fault.
            self.launch_host(0, self.cycler)
            for i, label in enumerate(self.instances):
                self.command('xdotool', 'windowsize', '--sync', self.windows[label], '1344', '1100')
                self.command('xdotool', 'windowmove', '--sync', self.windows[label], str(20 + i*1400), '50')
            self.focus(self.source)
        if name not in getattr(self, 'instances', {}):
            return super().launch(name, argv, **kwargs)
        old = self.env['EVA_COMPANION_SOCKET']
        self.env['EVA_COMPANION_SOCKET'] = str(self.root / ('relay-' + name + '.sock'))
        try:
            return super().launch(name, argv, **kwargs)
        finally:
            self.env['EVA_COMPANION_SOCKET'] = old

    def relay_events(self):
        path = self.root / 'relay-events.jsonl'
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines(keepends=True) if line.endswith('\n')]

    def residence(self):
        return json.loads((self.root / 'profile/residence.json').read_text())

    def wait_event(self, predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.relay.poll() is not None:
                raise AssertionError('private frame relay exited')
            events = self.relay_events()
            if any(e.get('action') == 'error' for e in events):
                raise AssertionError('relay failed: ' + str(events[-1]))
            matches = [e for e in events if predicate(e)]
            if matches:
                return matches[-1]
            time.sleep(.05)
        raise AssertionError('expected original relay event did not arrive')

    def native_proof(self, label, token, after_index=0):
        event = self.wait_event(lambda e: e['index'] > after_index and e.get('label') == label
                                and e.get('direction') == 'client' and e.get('kind') == 'retired'
                                and e.get('token') == token)
        serial = event['presentation_serial']
        text = (self.root / (label + '.log')).read_text(errors='replace')
        published = re.findall(r'producer frame published window=(\d+) counter=(\d+) pass=(\d+)', text)
        accepted = re.findall(r'compositor scene receipt accepted counter=(\d+) pass=(\d+)', text)
        pairs = {(int(counter), int(frame)) for counter, frame in accepted}
        native_passes = {serial}
        bridge = []
        if self.frontend == 'frost':
            bridge = [(int(native), int(tree), int(body)) for native, tree, body in re.findall(
                r'native host receipt native_pass=(\d+) cleared_frame=(\d+) body_frame=(\d+) accepted=true', text)
                if int(tree) == serial]
            native_passes = {native for native, _, _ in bridge}
        matching = [(int(window), int(counter), int(frame)) for window, counter, frame in published
                    if int(frame) in native_passes and (int(counter), int(frame)) in pairs]
        if not serial or not matching or any(window != int(self.windows[label]) for window, _, _ in matching):
            raise AssertionError('Retired request lacks its actual original native publication/scene serial')
        return dict(token=token, relay_event=event, native_serial=serial,
                    native_pass_to_captured_tree=bridge, matching_window_counter_pass=matching)

    def handoff(self, previous, target, original):
        before = self.proof_counts(previous)
        index = self.relay_events()[-1]['index']
        self.focus(target)
        if not self.wait_visible(target):
            raise AssertionError('actual native body failed to settle on ' + target)
        state = self.residence()
        current = state['possible_body']
        if original not in state['retired_tokens'] or current['epoch'] <= original['epoch']:
            raise AssertionError('native handoff lacks exact durable retirement/increasing epoch')
        if len(state['retired_tokens']) > 64:
            raise AssertionError('exact retirement cache grew beyond its bound')
        proof = self.native_proof(previous, original, index)
        if self.proof_counts(previous)['accepted'] <= before['accepted']:
            raise AssertionError('handoff reused an old native clearance')
        item = dict(source=previous, target=target, previous_token=original, current_token=current,
                    retained_exact_tokens=len(state['retired_tokens']), proof=proof)
        self.transitions.append(item)
        (self.root / 'compaction-progress.json').write_text(json.dumps(dict(
            native_handoffs=len(self.transitions), last=item), indent=2) + '\n')
        return current

    def run(self):
        self.relay = self.launch('relay', [sys.executable, str(Path(__file__).with_name('native_retirement_proxy.py')),
            '--root', str(self.root), '--source', self.source,
            *[v for label in self.instances for v in ['--label', label]]])
        deadline = time.monotonic() + 8
        while not (self.root / 'relay-ready').exists():
            if self.relay.poll() is not None or time.monotonic() >= deadline:
                raise AssertionError('private relay did not become ready')
            time.sleep(.05)
        self.startup()
        self.focus(self.source)
        if not self.wait_visible(self.source):
            raise AssertionError('source body was not actually visible before lost acknowledgement')
        gui = self.host_processes[self.source]
        window = self.windows[self.source]
        shell = self.wait_shells(self.source, 1)[0]
        shell_identity = stat(shell['pid'])
        original = self.residence()['possible_body']
        old_boot = original['boot_id']
        # Only this naturally generated first clearance acknowledgement is lost.
        current = self.handoff(self.source, self.target, original)
        first = self.transitions[-1]['proof']
        dropped = self.wait_event(lambda e: e.get('action') == 'drop' and e.get('token') == original)
        self.record('real-original-clearance-accepted-ack-dropped', original_token=original,
                    proof=first, dropped_ack=dropped)
        previous = self.target
        for _ in range(self.args.cycles):
            target = self.cycler if previous == self.target else self.target
            current = self.handoff(previous, target, current)
            previous = target
        compacted = self.residence()
        if len(compacted['retired_tokens']) != 64 or original in compacted['retired_tokens']:
            raise AssertionError('single-profile native retirements did not compact the exact original entry')
        if any(e.get('direction') == 'server' and e.get('action') == 'forward'
               and e.get('kind') == 'retirement_accepted' and e.get('token') == original
               for e in self.relay_events()):
            raise AssertionError('old source received its missing acknowledgement before compaction')
        source_grants = [e for e in self.relay_events() if e.get('label') == self.source
                         and e.get('kind') == 'grant' and e.get('index', 0) > dropped['index']]
        if source_grants:
            raise AssertionError('held-ack source was granted another token before recovery')
        (self.root / 'compacted-before-restart.json').write_text(json.dumps(compacted, indent=2) + '\n')
        self.record('single-profile-native-exact-cache-compacted', native_retirements=len(self.transitions),
                    original_token=original, retained_exact_tokens=64)
        # A real transport/daemon restart, not delivery of an old cached reply.
        (self.root / 'hold-source-reconnect').write_text('hold original source only\n')
        self.daemon.kill()
        self.daemon.wait(5)
        self.daemon = self.launch('daemon-restarted', [str(self.binaries['jcompaniond']), str(self.root / 'profile')])
        self.focus(previous)
        if not self.wait_visible(previous):
            raise AssertionError('genuine current owner did not recover across daemon restart')
        after_restart = self.residence()
        if after_restart['boot_id'] == old_boot or original in after_restart['retired_tokens']:
            raise AssertionError('restart did not preserve compaction and change boot')
        # This body must survive the old-token re-ack; no cached old reply is sent.
        current_after_restart = after_restart['possible_body']
        release_index = self.relay_events()[-1]['index']
        (self.root / 'release-acks').write_text('forward future exact daemon replies only\n')
        (self.root / 'hold-source-reconnect').unlink()
        new_hello = self.wait_event(lambda e: e['index'] > release_index and e.get('label') == self.source
                                   and e.get('kind') == 'host_accepted' and e.get('boot_id') != old_boot)
        renewed = self.native_proof(self.source, original, new_hello['index'])
        ack = self.wait_event(lambda e: e['index'] > renewed['relay_event']['index']
                             and e.get('label') == self.source and e.get('action') == 'forward'
                             and e.get('kind') == 'retirement_accepted' and e.get('token') == original)
        if renewed['native_serial'] <= first['native_serial']:
            raise AssertionError('reconnect reused the old native frame serial')
        if self.residence()['possible_body'] != current_after_restart:
            raise AssertionError('old compacted retirement re-ack cleared the newer current body')
        self.focus(self.source)
        if not self.wait_visible(self.source):
            raise AssertionError('same original native GUI did not regain a body after real old-token recovery')
        recovered = self.residence()['possible_body']
        for key in ['host_id', 'incarnation', 'surface_id', 'companion_id']:
            if recovered[key] != original[key]:
                raise AssertionError('compaction recovery replaced original host identity: ' + key)
        if recovered['epoch'] <= compacted['epoch'] or gui.poll() is not None or self.windows[self.source] != window:
            raise AssertionError('native source GUI/window/epoch was not preserved')
        if stat(shell['pid'])['start_ticks'] != shell_identity['start_ticks']:
            raise AssertionError('original shell incarnation was replaced')
        marker = self.root / 'compaction-original-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + str(marker))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if marker.exists() and marker.read_text().endswith('\n'):
                break
            time.sleep(.05)
        if not marker.exists() or marker.read_text().strip() != str(shell['pid']):
            raise AssertionError('recovered GUI did not consume real input in the exact original shell')
        self.key('Return')
        if not self.wait_visible(self.source):
            raise AssertionError('recovered body lost eligibility after native input')
        self.recovery = dict(original_token=original, first_native_proof=first, compacted_state=compacted,
            current_body_untouched_by_old_ack=current_after_restart, reconnect_hello=new_hello,
            renewed_native_proof=renewed, generated_ack=ack, recovered_token=recovered,
            original_gui_pid=gui.pid, native_window=window, original_shell=shell_identity,
            confirmed_shell_pid=int(marker.read_text()))
        token = self.residence()['possible_body']
        counts = self.proof_counts(self.source)
        self.native_close()
        self.wait_source_exit(token, counts)
        return dict(passed=True, native_handoffs=len(self.transitions), retained_exact_tokens=64,
                    original_exact_entry_compacted=True, real_daemon_restart=True,
                    old_native_clearance_reproved=True, newly_generated_old_ack=True,
                    old_ack_preserved_current_newer_body=True, same_original_gui_host_and_shell=True,
                    fresh_close_with_native_retirement=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--wm', type=Path, required=True)
    parser.add_argument('--shell', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=70)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True, freeze_owner=False,
                        restart_daemon=False, desktop_shell=False, components=True, task_canvas=False,
                        screen='4200x1200')
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['ember', 'frost'] or args.cycles < 70:
        parser.error('one real Ember/Frost and at least 70 native handoffs required')
    args.task_canvas = args.host[0][0] == 'ember'
    args.daemon, args.wm, args.shell = [p.resolve(strict=True) for p in [args.daemon, args.wm, args.shell]]
    session = CompactionSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try:
            session.capture('failed-retirement-compaction')
        except Exception as error:
            result['capture_error'] = str(error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, frontend=session.frontend,
            binary_sha256=session.binary_hashes, events=session.events, samples=session.samples,
            native_backing_samples=session.native_samples, transitions=session.transitions,
            recovery=session.recovery, native_host_ids=session.host_ids,
            gui_processes={name: process.pid for name, process in session.host_processes.items()})
        report = session.root / 'retirement-compaction-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

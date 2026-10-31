#!/usr/bin/env python3
"""Native GTK withdrawal cancellation/resumption, with real Block and VTE.

Uses actual jsh, native WM/key/button input, original GUI/window/PTY identities,
connection socket inodes, exact durable retirement and complete GDK timings.
Bodyless offline closes require no fabricated retirement or withdrawal ACK.
Pauses only owned private daemon/compositor actors. The late-work case starts a
real trap after clearance is pending, then pauses the original private shell
while its controlled raw-input foreground job reads Escape; that isolates the
fixture's shell-reader race, not normal shell job-control UX. No host, grant,
geometry, task or presentation proof is injected. Full-size sampled Cat pixels
are not continuous/physical uniqueness, trusted C11, API or performance proof.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import signal
import time

from native_gtk_jobs import GtkJobsSession
from native_withdrawal_resume import ResumeSession
from native_window_use import stat
from native_windows import host


class GtkResumeSession(GtkJobsSession):
    server_connections = ResumeSession.server_connections
    residence = ResumeSession.residence
    stop_actor = ResumeSession.stop_actor
    wait_pid_marker = ResumeSession.wait_pid_marker

    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)
        shutil.copy2(Path(__file__).with_name('native_withdrawal_resume.py'), self.root / 'harness/native_withdrawal_resume.py')
        self.resume_observation = {}
        self.paused_shell = None

    def proof_counts(self, name):
        text = (self.root / (name + '.log')).read_text(errors='replace')
        return dict(published=text.count('GTK clearance submitted'),
                    pending=text.count('GTK retirement awaiting native presentation'),
                    accepted=sum('GTK presentation receipt' in line and 'retirement=true' in line
                                 for line in text.splitlines()))

    def begin_close(self):
        self.confirmed_close = False
        # A harmless native comment draft makes admission explicit in both
        # backends. It is unverified input, not a running job. The real native
        # confirmation must accept it before any withdrawal begins.
        self.key('ctrl+u')
        self.text('# EVA_CLOSE_INTENT')
        time.sleep(.2)
        self.native_close()
        self.confirm_dialog()
        time.sleep(.25)

    def wait_source_exit(self, token, initial_counts):
        # begin_close handled VTE's admission before its native withdrawal.
        return super(GtkJobsSession, self).wait_source_exit(token, initial_counts)

    def wait_pending(self, token, before):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            self.assert_gui_stays(.05)
            now = self.proof_counts(self.source)
            if self.held(token) and now['pending'] > before['pending'] and now['accepted'] == before['accepted']:
                self.record('actual-gtk-retirement-awaiting-native-presentation', token=token, proof_counts=now,
                            submission_already_observed=now['published'] > before['published'])
                return
        raise AssertionError('close never reached actual GTK clearance awaiting native timing')

    def keep_button(self):
        # Actual native GTK close strip, fixed full-size private window. The
        # backing PNG is retained for visual QA of this pointer target.
        self.capture_native('before-native-keep-window-open')
        g = self.geometry(self.source)
        point = [g['WIDTH']//2 + 184, 18 if self.frontend == 'forge' else 60]
        self.command('xdotool', 'mousemove', '--window', self.windows[self.source],
                     str(point[0]), str(point[1]), 'click', '1')
        self.record('native-keep-window-open-pointer', client_point=point)

    def identities(self):
        shell = self.wait_shells(self.source, 1)[0]
        return dict(token=self.journal()['possible_body'], proof_counts=self.proof_counts(self.source),
                    shell=shell, shell_start=stat(shell['pid'])['start_ticks'],
                    window=self.windows[self.source], gui_pid=self.host_processes[self.source].pid,
                    connections=self.server_connections())

    def verify_resumed(self, original):
        self.assert_gui_stays(1)
        self.key('Return')
        old = original['token']
        deadline = time.monotonic() + 20
        while True:
            visible = self.wait_visible(self.source)
            self.assert_gui_stays(.05)
            resumed = self.journal()['possible_body']
            if visible and resumed and resumed['epoch'] > old['epoch']: break
            assert time.monotonic() < deadline, 'kept-open GTK window did not resume a newer native body'
            time.sleep(.1)
        for key in ['companion_id', 'host_id', 'incarnation', 'surface_id']:
            assert resumed[key] == old[key], 'resumption replaced identity: ' + key
        assert resumed['epoch'] > old['epoch'], 'resumption reused old body token'
        assert old in self.residence()['retired_tokens'], 'cancellation discarded original retirement obligation'
        assert self.proof_counts(self.source)['accepted'] > original['proof_counts']['accepted'], 'missing real GTK removal timing'
        assert self.windows[self.source] == original['window']
        assert self.host_processes[self.source].pid == original['gui_pid']
        if self.args.case != 'restart-during-cancel':
            assert self.server_connections() == original['connections'], 'ordinary cancellation reconnected IPC'
        assert stat(original['shell']['pid'])['start_ticks'] == original['shell_start']
        marker = self.root / 'resumed-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        assert self.wait_pid_marker(marker) == original['shell']['pid'], 'native input missed original shell'
        self.assert_gui_stays(.5)
        self.key('Return')
        assert self.wait_visible(self.source)
        self.resume_observation = dict(original=original, resumed_token=resumed,
            connections_after=self.server_connections(), final_shell=stat(original['shell']['pid']),
            proof_counts_after=self.proof_counts(self.source))
        self.record('same-window-shell-host-resumed', **self.resume_observation)
        current, counts = self.journal()['possible_body'], self.proof_counts(self.source)
        self.begin_close()
        self.wait_source_exit(current, counts)

    def cancellation(self):
        original = self.identities()
        scene = self.args.case == 'pending-scene-escape'
        actor = self.old_wm if scene else self.daemon
        # GTK's real confirmation can be a separate native surface. Let the
        # private WM map/focus it before withholding scene timing. The paused
        # daemon holds withdrawal until that admission step has completed.
        self.stop_actor(self.daemon, 'private-daemon-paused-before-confirmation')
        self.begin_close()
        if scene:
            self.stop_actor(self.old_wm, 'private-compositor-paused-after-confirmation')
            os.kill(self.daemon.pid, signal.SIGCONT)
            self.wait_pending(original['token'], original['proof_counts'])
        self.capture('before-close-cancellation')
        self.capture_native('before-close-cancellation')
        if self.args.case == 'pre-revoke-button':
            self.keep_button()
        elif self.args.case == 'held-escape-blur':
            self.command('xdotool', 'keydown', 'Escape')
            self.focus(self.target)
            self.focus(self.source)
            self.command('xdotool', 'keydown', 'Escape')
            self.command('xdotool', 'keyup', 'Escape')
        else:
            self.key('Escape')
        self.assert_gui_stays(.5)
        assert original['token'] not in self.residence()['retired_tokens'], 'cancellation fabricated native proof'
        if self.args.case == 'reclose-before-resume':
            self.begin_close()
            self.assert_gui_stays(.5)
            os.kill(actor.pid, signal.SIGCONT)
            self.wait_source_exit(original['token'], original['proof_counts'])
            return dict(passed=True, cancel_then_fresh_close_before_resume=True, exact_native_retirement=True)
        if self.args.case == 'restart-during-cancel':
            self.daemon.kill(); self.daemon.wait(3)
            self.daemon = self.launch('daemon-restarted', [str(self.binaries['jcompaniond']), str(self.root/'profile')])
        else:
            os.kill(actor.pid, signal.SIGCONT)
        self.verify_resumed(original)
        return dict(passed=True, same_host_window_shell_resumed=True,
                    same_connection=self.args.case != 'restart-during-cancel', exact_native_retirement=True)

    def late_work(self):
        shell = self.wait_shells(self.source, 1)[0]
        script = self.root / 'late-gtk-work.py'
        script.write_text('''import json,os,select,signal,sys,termios,tty
from pathlib import Path
root=Path(__file__).parent
shell=os.getsid(0)
original=None
signal.signal(signal.SIGTTOU,signal.SIG_IGN)
def finish(number,frame):
 if original is not None:termios.tcsetattr(0,termios.TCSANOW,original)
 os.tcsetpgrp(0,shell)
 (root/'late-gtk-done.json').write_text(json.dumps({'pid':os.getpid(),'signal':number}))
 sys.exit(128+number)
for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,finish)
os.tcsetpgrp(0,os.getpgrp())
original=termios.tcgetattr(0);tty.setraw(0)
(root/'late-gtk-started.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp()}))
received=b''
while True:
 if select.select([0],[],[],.1)[0]:
  received+=os.read(0,64)
  (root/'late-gtk-input.hex').write_text(received.hex())
''')
        armed = self.root / 'trap-armed.pid'
        self.send_command('trap ' + shlex.quote('/usr/bin/python3 ' + shlex.quote(str(script))) +
                          ' USR1; printf \'%s\\n\' "$$" > ' + shlex.quote(str(armed)))
        assert int(self.wait_line(armed)) == shell['pid']
        self.wait_shell_foreground(shell['pid'])
        self.key('Return')
        assert self.wait_visible(self.source)
        original = self.identities()
        self.stop_actor(self.daemon, 'private-daemon-paused-before-confirmation')
        self.begin_close()
        self.stop_actor(self.old_wm, 'private-compositor-paused-after-confirmation')
        os.kill(self.daemon.pid, signal.SIGCONT)
        self.wait_pending(original['token'], original['proof_counts'])
        assert stat(shell['pid'])['start_ticks'] == original['shell_start']
        os.kill(shell['pid'], signal.SIGUSR1)
        os.kill(shell['pid'], signal.SIGINT)
        started = self.wait_json(self.root / 'late-gtk-started.json')
        self.register_work(started['pid'], shell)
        # Isolate the already-existing shell-reader race in this trap fixture.
        os.kill(shell['pid'], signal.SIGSTOP)
        self.paused_shell = (shell['pid'], original['shell_start'])
        os.kill(self.old_wm.pid, signal.SIGCONT)
        deadline = time.monotonic() + 12
        while original['token'] not in self.residence()['retired_tokens']:
            self.assert_gui_stays(.05, job=True)
            assert time.monotonic() < deadline, 'new work cancelled original clearance obligation'
        self.assert_gui_stays(1, job=True)
        self.key('Escape')
        received = self.root / 'late-gtk-input.hex'
        deadline = time.monotonic() + 5
        while not received.exists() and time.monotonic() < deadline:
            self.assert_gui_stays(.05, job=True)
        assert received.exists() and received.read_text() == '1b', 'close captured Escape from actual new work'
        self.capture('new-work-alive-after-original-retirement')
        self.capture_native('new-work-alive-after-original-retirement')
        self.record('new-work-preserved-and-escape-forwarded', work=stat(self.work['pid']), received_hex=received.read_text())
        os.kill(self.work['pid'], signal.SIGTERM)
        assert self.wait_json(self.root/'late-gtk-done.json') == dict(pid=self.work['pid'], signal=int(signal.SIGTERM))
        os.kill(shell['pid'], signal.SIGCONT); self.paused_shell = None
        self.wait_shell_foreground(shell['pid'])
        self.assert_gui_stays(2)
        self.verify_resumed(original)
        return dict(passed=True, new_work_during_native_clearance=True, work_escape_preserved=True,
                    no_auto_close_after_work=True, same_host_window_shell_resumed=True,
                    original_shell_paused_for_fixture_stdin=True)

    def no_daemon(self):
        self.startup(start_coordinator=False)
        shell = self.wait_shells(self.source, 1)[0]
        marker = self.root / 'no-daemon-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        assert int(self.wait_line(marker)) == shell['pid']
        assert not (self.root/'eva.sock').exists()
        assert not (self.root/'profile/residence.json').exists()
        assert not self.capture('never-admitted-before-close')['visible_body_windows']
        self.begin_close()
        process = self.host_processes[self.source]
        deadline = time.monotonic() + 8
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert process.poll() == 0, 'never-admitted window could not close without a coordinator'
        self.closed_windows[self.source] = self.windows.pop(self.source)
        assert self.host_processes[self.target].poll() is None
        assert not self.capture('never-admitted-close-finished')['visible_body_windows']
        self.record('never-admitted-window-closed-without-fabricating-proof', exit_code=process.returncode,
                    coordinator_socket_exists=(self.root/'eva.sock').exists(), journal_exists=(self.root/'profile/residence.json').exists())
        return dict(passed=True, never_admitted_close=True, no_coordinator=True, no_shared_or_legacy_body=True,
                    surviving_gui_preserved=True, original_shell=shell)

    def nonowner_daemon_loss(self):
        self.startup()
        original = self.journal()['possible_body']
        self.focus(self.target); assert self.wait_visible(self.target)
        other = self.journal()['possible_body']
        assert other['host_id'] != original['host_id']
        assert original in self.residence()['retired_tokens']
        deadline = time.monotonic()+8
        while True:
            text = (self.root/(self.source+'.log')).read_text(errors='replace')
            if any('GTK retirement acknowledged' in line and all(
                    (key+': "'+value+'"') in line if isinstance(value, str)
                    else re.search(r'\b'+re.escape(key)+': '+str(value)+r'(?=[, }])', line)
                    for key, value in original.items()) for line in text.splitlines()): break
            assert time.monotonic()<deadline, 'nonowner lacks observed GUI retirement acknowledgement'
            time.sleep(.05)
        residence = (self.root/'profile/residence.json').read_bytes()
        self.daemon.kill(); self.daemon.wait(3)
        self.focus(self.source)
        shell = self.wait_shells(self.source, 1)[0]
        marker = self.root/'nonowner-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        assert int(self.wait_line(marker)) == shell['pid']
        self.begin_close()
        process = self.host_processes[self.source]
        deadline = time.monotonic()+8
        while process.poll() is None and time.monotonic()<deadline: time.sleep(.05)
        assert process.poll() == 0, 'bodyless nonowner could not close after coordinator loss'
        self.closed_windows[self.source] = self.windows.pop(self.source)
        assert self.host_processes[self.target].poll() is None
        assert (self.root/'profile/residence.json').read_bytes() == residence, 'offline close fabricated durable retirement'
        self.record('bodyless-nonowner-closed-after-coordinator-loss', original_token=original, other_possible_body=other,
                    exit_code=process.returncode, residence_unchanged=True)
        return dict(passed=True, bodyless_nonowner_close=True, no_retirement_of_other_host_fabricated=True,
                    surviving_gui_preserved=True, original_shell=shell)

    def owner_daemon_loss(self):
        self.startup()
        shell = self.wait_shells(self.source, 1)[0]
        shell_start = stat(shell['pid'])['start_ticks']
        original = self.journal()['possible_body']
        self.daemon.kill(); self.daemon.wait(3)
        self.begin_close()
        self.assert_gui_stays(1.5)
        assert stat(shell['pid'])['start_ticks'] == shell_start
        assert original not in self.residence()['retired_tokens']
        assert self.journal()['possible_body'] == original
        self.record('owner-close-retains-possible-body-with-coordinator-offline', token=original, shell=stat(shell['pid']))
        before_reconnect = self.proof_counts(self.source)
        self.daemon = self.launch('daemon-restarted', [str(self.binaries['jcompaniond']), str(self.root/'profile')])
        self.wait_source_exit(original, before_reconnect)
        return dict(passed=True, possible_body_blocks_offline_close=True,
                    original_shell_retained_until_native_retirement=True, fresh_reconnect_native_retirement=True)

    def run(self):
        if self.args.case == 'no-daemon': return self.no_daemon()
        if self.args.case == 'owner-daemon-loss': return self.owner_daemon_loss()
        if self.args.case == 'nonowner-daemon-loss': return self.nonowner_daemon_loss()
        self.startup()
        self.focus(self.target); assert self.wait_visible(self.target)
        self.focus(self.source); assert self.wait_visible(self.source)
        # A first launch prompt is deliberately not a verified Block prompt.
        # Establish a genuine completed semantic command through native input.
        shell = self.wait_shells(self.source, 1)[0]
        ready = self.root / 'original-ready-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(ready)))
        assert int(self.wait_line(ready)) == shell['pid']
        self.wait_editor_idle(shell)
        self.key('Return'); assert self.wait_visible(self.source)
        return self.late_work() if self.args.case == 'late-work' else self.cancellation()

    def close(self):
        if self.paused_shell:
            pid, start = self.paused_shell
            try:
                if stat(pid)['start_ticks'] == start: os.kill(pid, signal.SIGCONT)
            except (ProcessLookupError, FileNotFoundError): pass
        super().close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['daemon', 'wm', 'shell']:
        parser.add_argument('--'+option, type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--backend', choices=['block', 'vte'], required=True)
    parser.add_argument('--case', choices=['pre-revoke-escape', 'pre-revoke-button', 'pending-scene-escape',
        'reclose-before-resume', 'restart-during-cancel', 'held-escape-blur', 'late-work', 'no-daemon', 'nonowner-daemon-loss', 'owner-daemon-loss'], required=True)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True, freeze_owner=False,
                        restart_daemon=False, desktop_shell=False, components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['forge','anvil']:
        parser.error('one actual Forge or Anvil binary required')
    args.daemon, args.wm, args.shell = [p.resolve(strict=True) for p in [args.daemon,args.wm,args.shell]]
    session = GtkResumeSession(args); result = dict(passed=False)
    try: result = session.run()
    except Exception as error:
        result['error'] = str(error)
        for name, process in session.host_processes.items():
            if process.poll() is not None and name in session.windows:
                session.closed_windows[name] = session.windows.pop(name)
        try: session.capture('failed-gtk-withdrawal-resume')
        except Exception as capture_error: result['capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, frontend=session.frontend, backend=args.backend, case=args.case,
            binary_sha256=session.binary_hashes, events=session.events, samples=session.samples,
            native_samples=session.native_samples, resume_observation=session.resume_observation,
            backend_observation=session.backend_observation,
            work_observation=session.work_observation, native_host_ids=session.host_ids,
            gui_processes={name:p.pid for name,p in session.host_processes.items()})
        report = session.root / 'gtk-resume-report.json'
        report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],report=str(report),error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

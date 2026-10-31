#!/usr/bin/env python3
"""Real PTY background jobs, wait/loop builtins and natural parent exit.

Native input launches every command. Ordinary whole-window close must preserve
attached work, including a separate background process group at an empty prompt.
Explicit shell exit ends its attached PTY session before publishing final exit.
No task/grant/geometry/presentation messages or proofs are injected. Sampled
Cat PNGs are not continuous/physical, provider, remote or performance evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import time

from native_shell_lifecycle import ShellLifecycleSession
from native_windows import host


class ShellJobsSession(ShellLifecycleSession):
    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)
        self.control = self.root / 'finish-job'

    def wait_command_editor(self, shell):
        """Backend fixtures may observe their actual editor before new input."""
        pass

    def start_job(self, shell):
        helper = self.root / 'background-job.py'
        helper.write_text('''import json,os,signal,time
from pathlib import Path
root=Path(__file__).parent
def observed(number,frame):
 with (root/'job-signals.jsonl').open('a') as stream:
  stream.write(json.dumps({'pid':os.getpid(),'signal':number})+'\\n')
for number in [signal.SIGHUP,signal.SIGTERM]:signal.signal(number,observed)
(root/'job-started.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'sid':os.getsid(0),'tty':os.ttyname(1)}))
while not (root/'finish-job').exists():time.sleep(.02)
(root/'job-finished.json').write_text(json.dumps({'pid':os.getpid(),'completed':True}))
''')
        self.send_command('/usr/bin/python3 ' + shlex.quote(str(helper)) + ' &')
        started = self.wait_json(self.root / 'job-started.json')
        work = self.process(started['pid'])
        root = self.process(shell['pid'])
        assert work['session_id'] == root['session_id'] == shell['pid']
        assert work['pgid'] != shell['pid'] and work['tty_number'] == root['tty_number']
        assert root['foreground_pgid'] == shell['pid']
        self.work = work
        self.work_observation.update(original_shell=root, background_job=work)
        self.record('real-background-job-in-separate-group', shell=root, work=work)

    def guard(self):
        self.native_close()
        until = time.monotonic() + 2
        while time.monotonic() < until:
            assert self.host_processes[self.source].poll() is None, 'ordinary window close destroyed a GUI with attached shell work'
            assert self.work_alive(), 'ordinary window close terminated attached shell work'
            assert not (self.root / 'job-signals.jsonl').exists(), 'ordinary window close signaled the background job'
            time.sleep(.05)
        self.capture('attached-shell-work-preserved')
        self.record('ordinary-window-close-refused-for-attached-work', work=self.process(self.work['pid']))

    def run(self):
        self.startup()
        shell = self.wait_shells(self.source, 1)[0]
        original = self.process(shell['pid'])
        if self.args.case == 'loop':
            marker = self.root / 'loop-started.pid'
            done = self.root / 'loop-finished.pid'
            self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)) +
                '; while read eva_job_line; do if [ "$eva_job_line" = EVA_LOOP_DONE ]; then break; fi; done; ' +
                "printf '%s\\n' \"$$\" > " + shlex.quote(str(done)))
            assert int(self.wait_line(marker)) == shell['pid']
            self.work = original
            self.guard()
            self.send_command('EVA_LOOP_DONE')
            assert int(self.wait_line(done)) == shell['pid']
        else:
            self.start_job(shell)
            if self.args.case == 'stopped':
                self.send_command('kill -STOP ' + str(self.work['pid']))
                deadline = time.monotonic() + 5
                while self.process(self.work['pid'])['state'] not in ['T', 't']:
                    assert time.monotonic() < deadline, 'background job did not stop'
                    time.sleep(.05)
                self.record('native-shell-stopped-background-job', work=self.process(self.work['pid']))
            if self.args.case == 'parent-exit':
                self.key('Return')
                assert self.wait_visible(self.source), 'original body did not settle before explicit shell exit'
                token = self.journal()['possible_body']
                counts = self.proof_counts(self.source)
                self.send_command('exit')
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        state = self.process(shell['pid'])
                    except FileNotFoundError:
                        break
                    if state['state'] == 'Z':
                        break
                    time.sleep(.05)
                else:
                    raise AssertionError('explicit shell exit did not reach natural parent exit')
                deadline = time.monotonic() + 5
                while self.work_alive() and time.monotonic() < deadline:
                    time.sleep(.05)
                assert not self.work_alive(), 'natural shell exit left its separate-group PTY job alive'
                self.record('explicit-parent-exit-drained-attached-job', original_shell=original, job=self.work)
                self.wait_source_exit(token, counts)
                return dict(passed=True, separate_background_group=True, natural_parent_exit_drained=True,
                            native_retirement_after_explicit_exit=True)
            if self.args.case == 'wait':
                started = self.root / 'wait-started.pid'
                finished = self.root / 'wait-finished.pid'
                self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(started)) +
                                  '; wait ' + str(self.work['pid']) + "; printf '%s\\n' \"$$\" > " + shlex.quote(str(finished)))
                assert int(self.wait_line(started)) == shell['pid']
                assert not finished.exists()
                assert self.process(shell['pid'])['foreground_pgid'] == shell['pid']
            if self.args.case == 'background-inactive':
                self.key('ctrl+shift+t')
                self.wait_shells(self.source, 2)
                marker = self.root / 'idle-tab.pid'
                self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
                assert int(self.wait_line(marker)) != shell['pid']
            self.guard()
            if self.args.case == 'background-inactive' and self.frontend == 'ember':
                self.key('ctrl+shift+Tab')
            if self.args.case == 'wait':
                self.key('ctrl+c')
                # A shell may abort the rest of this compound list on SIGINT.
                # The following native command proves return to the shell;
                # executing printf after the interrupted wait is not required.
                self.work_observation['post_wait_sequence_ran'] = finished.exists()
                assert self.work_alive(), 'interrupting shell wait killed its background job'
                self.wait_command_editor(shell)
            if self.args.case == 'stopped':
                self.send_command('kill -CONT ' + str(self.work['pid']))
                self.wait_command_editor(shell)
            self.send_command('touch ' + shlex.quote(str(self.control)) + '; wait ' + str(self.work['pid']))
            assert self.wait_json(self.root / 'job-finished.json')['pid'] == self.work['pid']
            deadline = time.monotonic() + 8
            while self.work_alive() and time.monotonic() < deadline:
                time.sleep(.05)
            assert not self.work_alive(), 'background job did not complete through native shell input'
        self.assert_gui_stays(.5)
        self.wait_command_editor(shell)
        marker = self.root / 'shell-after-work.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        assert int(self.wait_line(marker)) == shell['pid']
        assert self.process(shell['pid'])['start_ticks'] == original['start_ticks']
        self.key('Return')
        assert self.wait_visible(self.source)
        token = self.journal()['possible_body']
        counts = self.proof_counts(self.source)
        self.native_close()
        self.wait_source_exit(token, counts)
        return dict(passed=True, ordinary_close_preserved_work=True, original_shell_preserved=True,
                    native_input_completed_work=True, fresh_close_with_native_retirement=True)

    def close(self):
        if self.work and self.args.case != 'loop' and self.work_alive():
            # Cleanup, never a successful completion or presentation proof.
            os.kill(self.work['pid'], signal.SIGKILL)
        super().close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--wm', type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--shell', type=Path, required=True)
    parser.add_argument('--case', choices=['background', 'background-inactive', 'stopped', 'wait', 'loop', 'parent-exit'], required=True)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True, freeze_owner=False,
                        restart_daemon=False, desktop_shell=False, components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['ember', 'frost']:
        parser.error('one real Ember/Frost binary required')
    args.task_canvas = args.host[0][0] == 'ember'
    args.daemon, args.wm, args.shell = [path.resolve(strict=True) for path in [args.daemon, args.wm, args.shell]]
    session = ShellJobsSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        for label, process in session.host_processes.items():
            if process.poll() is not None and label in session.windows:
                session.closed_windows[label] = session.windows.pop(label)
        try:
            session.capture('failed-shell-jobs')
        except Exception as capture_error:
            result['capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, case=args.case, frontend=session.frontend,
                      binary_sha256=session.binary_hashes, events=session.events, samples=session.samples,
                      native_samples=session.native_samples, work_observation=session.work_observation,
                      native_host_ids=session.host_ids, gui_processes={name: process.pid for name, process in session.host_processes.items()})
        report = session.root / 'shell-jobs-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

#!/usr/bin/env python3
"""Real shell exec/builtin close checks in two private X11 GUI processes.

Commands are typed through native keys into the actual shell. Kernel PID,
start time, executable, session, foreground group and TTY establish whether
work replaced the shell or is a builtin in it. No provider, host, task fact,
geometry, grant or retirement receipt is injected. Completion uses native
input; a fresh ordinary close must retire its exact token with a native scene
receipt before the surviving GUI acquires. This is not physical scanout,
remote/provider, general descendant, audio/API or performance acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import time

from native_close_intent import CloseIntentSession
from native_window_use import stat
from native_windows import host


class ShellLifecycleSession(CloseIntentSession):
    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)

    def process(self, pid):
        value = stat(pid)
        value['executable'] = os.readlink(f'/proc/{pid}/exe')
        value['argv'] = Path(f'/proc/{pid}/cmdline').read_bytes().decode().strip('\0').split('\0')
        return value

    def wait_line(self, path, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('source GUI exited before native input completed')
            try:
                value = path.read_text()
                if value.endswith('\n') and value.strip():
                    return value.strip()
            except FileNotFoundError:
                pass
            time.sleep(.05)
        raise AssertionError('native input marker missing: ' + path.name)

    def start_exec(self, shell):
        original = self.process(shell['pid'])
        (self.root / 'original-shell.json').write_text(json.dumps(original))
        helper = self.root / 'exec-work.py'
        helper.write_text('''import json,os,signal,sys,termios
from pathlib import Path
root=Path(__file__).parent
def finish(number,frame):
 (root/'unexpected-work-signal.json').write_text(json.dumps({'pid':os.getpid(),'signal':number}))
 sys.exit(128+number)
for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,finish)
mode=termios.tcgetattr(0)
mode[3] |= termios.ICANON | termios.ECHO | termios.ISIG
termios.tcsetattr(0,termios.TCSANOW,mode)
(root/'exec-started.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'tty':os.ttyname(0)}))
print('CONTROLLED EXEC WORK: awaiting native input',flush=True)
line=sys.stdin.readline()
(root/'work-input.json').write_text(json.dumps({'pid':os.getpid(),'input':line}))
if line != 'EVA_SHELL_WORK_INPUT\\n':sys.exit(3)
original=json.loads((root/'original-shell.json').read_text())
os.execv(original['executable'],original['argv'])
''')
        self.send_command('exec /usr/bin/python3 ' + shlex.quote(str(helper)))
        marker = self.wait_json(self.root / 'exec-started.json')
        current = self.process(marker['pid'])
        for key in ['pid', 'start_ticks', 'pgid', 'session_id', 'tty_number', 'foreground_pgid']:
            if current[key] != original[key]:
                raise AssertionError('exec did not preserve actual shell identity field: ' + key)
        if current['executable'] == original['executable']:
            raise AssertionError('exec fixture did not replace the actual shell executable')
        self.work = current
        self.work_observation.update(original_shell=original, work=current, launch_marker=marker)
        self.record('same-pid-shell-exec-is-live-work', original=original, work=current)

    def start_builtin(self, shell):
        original = self.process(shell['pid'])
        started = self.root / 'builtin-started.pid'
        done = self.root / 'builtin-input.txt'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(started)) +
                          "; read eva_lifecycle_input; printf '%s:%s\\n' \"$$\" \"$eva_lifecycle_input\" > " +
                          shlex.quote(str(done)))
        if int(self.wait_line(started)) != shell['pid']:
            raise AssertionError('builtin is not running in the original actual shell')
        time.sleep(.3)
        current = self.process(shell['pid'])
        for key in ['pid', 'start_ticks', 'pgid', 'session_id', 'tty_number', 'foreground_pgid', 'executable']:
            if current[key] != original[key]:
                raise AssertionError('builtin changed actual shell identity field: ' + key)
        if done.exists():
            raise AssertionError('builtin finished before native input')
        self.work = current
        self.work_observation.update(original_shell=original, work=current)
        self.record('same-image-shell-builtin-awaits-native-input', original=original, work=current)

    def start_same_image_exec(self, shell):
        original = self.process(shell['pid'])
        started = self.root / 'same-image-started.pid'
        done = self.root / 'same-image-input.txt'
        back = ' '.join(shlex.quote(x) for x in [original['executable'], *original['argv'][1:]])
        command = ("printf '%s\\n' \"$$\" > " + shlex.quote(str(started)) +
                   "; read eva_lifecycle_input; printf '%s:%s\\n' \"$$\" \"$eva_lifecycle_input\" > " +
                   shlex.quote(str(done)) + '; exec ' + back)
        self.send_command('exec ' + shlex.quote(original['executable']) + ' -c ' + shlex.quote(command))
        if int(self.wait_line(started)) != shell['pid']:
            raise AssertionError('same-image exec did not preserve the actual root PID')
        current = self.process(shell['pid'])
        for key in ['pid', 'start_ticks', 'pgid', 'session_id', 'tty_number', 'foreground_pgid', 'executable']:
            if current[key] != original[key]:
                raise AssertionError('same-image exec changed identity field: ' + key)
        if '-c' not in current['argv'][1:] or done.exists():
            raise AssertionError('actual noninteractive same-image exec is not waiting for input')
        self.work = current
        self.work_observation.update(original_shell=original, work=current)
        self.record('same-image-exec-awaits-native-input', original=original, work=current)

    def run(self):
        self.startup()
        shell = self.wait_shells(self.source, 1)[0]
        original_host = self.journal()['possible_body']['host_id']
        if self.args.case.startswith('exec-same-image'):
            self.start_same_image_exec(shell)
        elif self.args.case.startswith('exec'):
            self.start_exec(shell)
        else:
            self.start_builtin(shell)
        if self.args.case.endswith('background'):
            self.key('ctrl+shift+t')
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                panes = self.shells(self.source)
                others = [p for p in panes if p['pid'] != shell['pid']]
                uses_jsh = self.shell_programs[self.frontend] == str(self.binaries.get('jsh'))
                if others and (not uses_jsh or others[0]['editor_raw']):
                    break
                time.sleep(.05)
            else:
                raise AssertionError('a second native shell tab did not become ready')
            time.sleep(.4)
            marker = self.root / 'active-idle-shell.pid'
            self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
            active = int(self.wait_line(marker))
            if active == shell['pid'] or active not in [p['pid'] for p in others]:
                raise AssertionError('native input did not select a distinct idle shell tab')
            self.work_observation['active_idle_shell'] = self.process(active)
        self.refuse_busy_close()
        self.capture_native('ordinary-close-preserved-same-root-work')
        if self.frontend == 'frost':
            # Existing per-tab termination remains an explicit user decision.
            # Cancel while the actual builtin/exec is still waiting for input.
            # Frost's refused whole-window close already focuses its busy
            # session. Toggling tabs here would target the unrelated idle tab.
            self.key('ctrl+shift+w')
            self.assert_gui_stays(.5, job=True)
            if self.args.case.endswith('background'):
                idle = self.work_observation['active_idle_shell']
                current = self.process(idle['pid'])
                if current['start_ticks'] != idle['start_ticks'] or current['state'] == 'Z':
                    raise AssertionError('tab confirmation closed the unrelated idle shell')
            self.capture_native('work-tab-explicit-confirmation')
            self.key('Escape')
            self.assert_gui_stays(.5, job=True)
            self.record('explicit-work-tab-close-cancelled', work=self.process(shell['pid']))
        elif self.args.case.endswith('background'):
            self.key('ctrl+shift+Tab')
        self.send_command('EVA_SHELL_WORK_INPUT')
        if self.args.case.startswith('exec-same-image'):
            if self.wait_line(self.root / 'same-image-input.txt') != str(shell['pid']) + ':EVA_SHELL_WORK_INPUT':
                raise AssertionError('native input did not complete the same-image exec')
            deadline = time.monotonic() + 12
            while '-c' in self.process(shell['pid'])['argv'][1:]:
                if time.monotonic() >= deadline:
                    raise AssertionError('same-image exec did not return to the interactive shell')
                time.sleep(.05)
            self.wait_shells(self.source, 2 if self.args.case.endswith('background') else 1)
        elif self.args.case.startswith('exec'):
            received = self.wait_json(self.root / 'work-input.json')
            if received != {'pid': shell['pid'], 'input': 'EVA_SHELL_WORK_INPUT\n'}:
                raise AssertionError('native input did not reach the exact exec process')
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                current = self.process(shell['pid'])
                if current['executable'] == shell['executable']:
                    break
                time.sleep(.05)
            else:
                raise AssertionError('exec work did not return to the original shell executable')
            self.wait_shells(self.source, 2 if self.args.case.endswith('background') else 1)
        else:
            if self.wait_line(self.root / 'builtin-input.txt') != str(shell['pid']) + ':EVA_SHELL_WORK_INPUT':
                raise AssertionError('native input did not complete the actual builtin')
        self.assert_gui_stays(1)
        marker = self.root / 'original-shell-after-work.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        if int(self.wait_line(marker)) != shell['pid']:
            raise AssertionError('native shell input crossed process/session after work')
        self.key('Return')
        if not self.wait_visible(self.source):
            raise AssertionError('fresh original shell prompt did not regain a visible body')
        token = self.journal()['possible_body']
        if token['host_id'] != original_host:
            raise AssertionError('work completion replaced the GUI host identity')
        counts = self.proof_counts(self.source)
        self.record('native-work-completed-original-shell-and-host-preserved', shell=self.process(shell['pid']))
        self.native_close()
        if self.frontend == 'frost' and not self.args.shell:
            # A plain sh does not report semantic command boundaries. An idle
            # executable/PGID alone cannot distinguish its prompt from read.
            # Require the actual existing per-tab confirmation, even now.
            self.assert_gui_stays(.5)
            for _ in range(2 if self.args.case.endswith('background') else 1):
                self.key('ctrl+shift+w')
                self.assert_gui_stays(.3)
                self.key('Return')
                time.sleep(.2)
            self.record('uninstrumented-shell-explicit-tab-termination-confirmed')
        self.wait_source_exit(token, counts)
        return dict(passed=True, same_root_work_preserved=True, native_input_completed_work=True,
                    original_shell_pid_preserved=True, fresh_close_with_exact_native_retirement=True,
                    uninstrumented_shell_requires_explicit_termination=self.frontend == 'frost' and not self.args.shell)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--wm', type=Path, required=True)
    parser.add_argument('--shell', type=Path)
    parser.add_argument('--case', choices=['exec', 'builtin', 'exec-background', 'builtin-background',
                                         'exec-same-image', 'exec-same-image-background'], required=True)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True, freeze_owner=False,
                        restart_daemon=False, desktop_shell=False, components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['ember', 'frost']:
        parser.error('one Ember or Frost binary required; two real GUI processes are opened')
    args.task_canvas = args.host[0][0] == 'ember'
    if args.task_canvas and not args.shell:
        parser.error('Ember requires the real jsh')
    args.daemon, args.wm = [p.resolve(strict=True) for p in [args.daemon, args.wm]]
    if args.shell:
        args.shell = args.shell.resolve(strict=True)
    session = ShellLifecycleSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        for name, process in session.host_processes.items():
            if process.poll() is not None and name in session.windows:
                session.closed_windows[name] = session.windows.pop(name)
        try:
            session.capture('failed-shell-lifecycle')
        except Exception as error:
            result['failure_capture_error'] = str(error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, case=args.case, frontend=session.frontend,
                      binary_sha256=session.binary_hashes, events=session.events, samples=session.samples,
                      native_samples=session.native_samples, work_observation=session.work_observation,
                      shell_programs=session.shell_programs,
                      native_host_ids=session.host_ids, gui_processes={n: p.pid for n, p in session.host_processes.items()})
        report = session.root / 'shell-lifecycle-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

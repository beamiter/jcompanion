#!/usr/bin/env python3
"""Native GTK last-tab cancellation and confirmed cleanup in Block/VTE.

Real jsh input starts a separate-group job that ignores HUP and TERM. The
application's actual Ctrl+Shift+W and confirmation dialog must retain work
until explicit confirmation, then drain it before process exit. Real GDK
timing plus exact-token retirement and a surviving GUI are required. No
host/task/frame proof is injected; this is not trusted/physical acceptance.
"""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import time

from native_gtk_jobs import GtkJobsSession
from native_windows import host


class GtkCloseSession(GtkJobsSession):
    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)
        self.close_chord = 'ctrl+shift+w'
        self.split_input = False
        for name, _ in args.host:
            path = self.root / 'config' / name / 'config.toml'
            path.write_text(path.read_text() + '\n[keybindings]\nclose_tab = "Ctrl+Shift+F4"\n')

    def send_command(self, text):
        if not self.split_input:
            return super().send_command(text)
        # Keep the actual active split's keyboard focus. The whole-window
        # footer coordinate used by the one-pane fixture is ambiguous here.
        self.text(text)
        time.sleep(.2)
        self.key('Return')

    def native_close(self):
        if self.close_chord == 'palette:Close tab':
            # Safe mode intentionally ignores configured shortcuts. Exercise
            # its actual whole-tab action through the native command palette.
            self.key('ctrl+shift+p')
            time.sleep(.3)
            self.text('> Close tab')
            time.sleep(.3)
            self.capture('native-whole-tab-command-palette')
            self.key('Return')
        else:
            self.key(self.close_chord)
        self.record('native-close-action-requested', native_window=self.windows[self.source], chord=self.close_chord)

    def whole_tab_action(self):
        return 'palette:Close tab' if self.args.backend == 'vte' else 'ctrl+shift+F4'

    def start_split_job(self):
        self.startup()
        original = self.wait_shells(self.source, 1)[0]
        self.key('ctrl+shift+e')
        shells = self.wait_shells(self.source, 2)
        time.sleep(.5)
        self.split_input = True
        marker = self.root / 'active-split.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        pid = int(self.wait_line(marker))
        shell = next(p for p in shells if p['pid'] == pid)
        assert pid != original['pid'], 'split did not select its new actual shell'
        self.wait_editor_idle(shell)
        self.start_job(shell)
        self.work_observation['split_shells'] = [self.process(p['pid']) for p in shells]
        self.work_observation['original_survivor'] = original['pid']
        return shell

    def complete_job(self, shell):
        marker = self.root / 'split-work-completed.pid'
        self.send_command('touch ' + shlex.quote(str(self.control)) + '; wait ' + str(self.work['pid']) +
                          "; printf '%s\\n' \"$$\" > " + shlex.quote(str(marker)))
        assert int(self.wait_line(marker)) == shell['pid']
        assert self.wait_json(self.root / 'job-finished.json')['pid'] == self.work['pid']
        deadline = time.monotonic() + 5
        while self.work_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        assert not self.work_alive(), 'native shell completion did not finish split job'

    def guard(self):
        self.native_close()
        self.assert_gui_stays(2, job=True)
        assert not (self.root / 'job-signals.jsonl').exists(), 'last-tab close signaled work before confirmation'
        self.capture('native-last-tab-awaiting-confirmation')
        self.key('Escape')
        self.assert_gui_stays(.5, job=True)
        assert not (self.root / 'job-signals.jsonl').exists(), 'cancelling last-tab close signaled work'
        self.record('native-last-tab-close-cancelled-with-work-intact', work=self.process(self.work['pid']))

    def run(self):
        if self.args.case == 'last-tab-cancel':
            result = super().run()
            result.update(close_action='last-tab', cancellation_preserved_work=True)
            return result
        if self.args.case.startswith('split-'):
            shell = self.start_split_job()
        else:
            self.startup()
            shell = self.wait_shells(self.source, 1)[0]
            self.start_job(shell)
        if self.args.case == 'split-pane-cancel':
            self.guard()
            self.complete_job(shell)
            self.record('split-pane-cancel-preserved-original-input', shell=self.process(shell['pid']))
            self.close_chord = self.whole_tab_action()
            self.key('Return')
            assert self.wait_visible(self.source)
            token, counts = self.journal()['possible_body'], self.proof_counts(self.source)
            self.native_close()
            self.wait_source_exit(token, counts)
            return dict(passed=True, close_action='split-pane', cancellation_preserved_work=True,
                        original_split_input_preserved=True, exact_native_retirement=True)
        if self.args.case.startswith('split-'):
            self.close_chord = self.whole_tab_action()
        self.key('Return')
        assert self.wait_visible(self.source)
        token, counts = self.journal()['possible_body'], self.proof_counts(self.source)
        self.native_close()
        self.assert_gui_stays(.5, job=True)
        assert not (self.root / 'job-signals.jsonl').exists(), 'last-tab close signaled work before confirmation'
        self.capture('native-last-tab-awaiting-confirmation')
        self.confirm_dialog()
        self.record('native-last-tab-close-confirmed-with-attached-work')
        self.wait_source_exit(token, counts)
        deadline = time.monotonic() + 5
        while self.work_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        assert not self.work_alive(), 'confirmed last-tab close left an attached job alive'
        return dict(passed=True, close_action='split-tab' if self.args.case.startswith('split-') else 'last-tab',
                    confirmed_close_drained_attached_job=True,
                    exact_native_retirement=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['daemon', 'wm', 'shell']:
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--backend', choices=['block', 'vte'], required=True)
    parser.add_argument('--case', choices=['last-tab-cancel', 'last-tab-confirm', 'split-pane-cancel', 'split-tab-confirm'], required=True)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True,
                        freeze_owner=False, restart_daemon=False, desktop_shell=False,
                        components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['forge', 'anvil']:
        parser.error('one actual Forge or Anvil binary required')
    args.daemon, args.wm, args.shell = [p.resolve(strict=True) for p in [args.daemon, args.wm, args.shell]]
    session = GtkCloseSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        for name, process in session.host_processes.items():
            if process.poll() is not None and name in session.windows:
                session.closed_windows[name] = session.windows.pop(name)
        try:
            session.capture('failed-gtk-close')
        except Exception as error:
            result['capture_error'] = str(error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, frontend=session.frontend, backend=args.backend, case=args.case,
                      binary_sha256=session.binary_hashes, events=session.events, samples=session.samples,
                      native_samples=session.native_samples, work_observation=session.work_observation,
                      backend_observation=session.backend_observation,
                      native_host_ids=session.host_ids,
                      gui_processes={name: process.pid for name, process in session.host_processes.items()})
        report = session.root / 'gtk-close-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

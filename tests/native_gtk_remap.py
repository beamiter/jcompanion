#!/usr/bin/env python3
"""Actual GTK terminal remap while its original native clearance is pending.

Uses real Block/VTE, original GUI/PTY identities, native X11 unmap/remap and
positive GDK timings. No host, geometry, task, frame or retirement messages are
injected. This is same-XID functional recovery, not physical/trusted C11 proof.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import time

from native_gtk_resume import GtkResumeSession
from native_window_use import stat
from native_windows import host


class GtkRemapSession(GtkResumeSession):
    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)
        self.remap_observation = {}

    def run(self):
        self.startup()
        token = self.journal()['possible_body']
        before = self.proof_counts(self.source)
        geometry = self.geometry(self.source)
        original_window = self.windows[self.source]
        gui = stat(self.host_processes[self.source].pid)
        shell = self.wait_shells(self.source, 1)[0]
        shell_before = stat(shell['pid'])
        wm_before = stat(self.old_wm.pid)
        descriptor = os.pidfd_open(self.old_wm.pid)
        try:
            signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
            deadline = time.monotonic() + 2
            while stat(self.old_wm.pid)['state'] not in ['T', 't']:
                assert time.monotonic() < deadline, 'private WM did not stop'
                time.sleep(.01)
            assert stat(self.old_wm.pid)['start_ticks'] == wm_before['start_ticks']
            self.direct_focus(self.target)
            deadline = time.monotonic() + 12
            while True:
                counts = self.proof_counts(self.source)
                if self.held(token) and counts['pending'] > before['pending'] and counts['accepted'] == before['accepted']:
                    break
                assert time.monotonic() < deadline, 'no actual pending native clearance'
                assert self.host_processes[self.source].poll() is None
                time.sleep(.05)
            self.record('actual-gtk-clearance-pending-before-unmap', token=token, proof_counts=counts)
            self.command('xdotool', 'windowunmap', '--sync', original_window)
            assert self.map_state(self.source) == 'IsUnMapped'
            self.capture('native-gtk-window-unmapped')
            assert self.held(token) and self.proof_counts(self.source)['accepted'] == before['accepted'], 'unmap supplied a fake retirement'
            self.record('unmapped-original-gtk-window', window=original_window, token=token)
        finally:
            signal.pidfd_send_signal(descriptor, signal.SIGCONT)
            os.close(descriptor)
        deadline = time.monotonic() + 5
        while self.managed(self.source) is not None:
            assert time.monotonic() < deadline, 'WM did not remove unmapped client'
            time.sleep(.05)
        self.command('xdotool', 'windowmap', '--sync', original_window)
        deadline = time.monotonic() + 5
        while self.managed(self.source) is None:
            assert time.monotonic() < deadline, 'WM did not remanage original client'
            time.sleep(.05)
        assert self.map_state(self.source) == 'IsViewable'
        after_geometry = self.geometry(self.source)
        assert (geometry['WIDTH'], geometry['HEIGHT']) == (after_geometry['WIDTH'], after_geometry['HEIGHT'])
        self.focus(self.target)
        assert self.wait_visible(self.target), 'remapped source did not complete actual clearance'
        assert self.proof_counts(self.source)['accepted'] > before['accepted']
        self.focus(self.source)
        assert self.wait_visible(self.source), 'original GTK window did not admit a fresh body'
        current = self.journal()['possible_body']
        assert current['host_id'] == token['host_id'] and current['epoch'] > token['epoch']
        assert stat(gui['pid'])['start_ticks'] == gui['start_ticks']
        assert stat(shell['pid'])['start_ticks'] == shell_before['start_ticks']
        marker = self.root / 'remapped-original-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > " + str(marker))
        assert self.wait_pid_marker(marker) == shell['pid']
        self.key('Return')
        assert self.wait_visible(self.source)
        self.remap_observation = dict(original_token=token, resumed_token=current,
            original_window=original_window, original_gui=gui, original_shell=shell_before,
            original_geometry=geometry, remapped_geometry=after_geometry,
            native_input_shell_pid=int(marker.read_text()), proof_counts=self.proof_counts(self.source))
        self.record('original-gtk-window-and-shell-resumed', **self.remap_observation)
        return dict(passed=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['daemon', 'wm', 'shell']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--backend', choices=['block', 'vte'], required=True)
    parser.set_defaults(case='native-remap', renderer='cairo', compositor='xrender', frame_sync=True,
                        freeze_owner=False, restart_daemon=False, desktop_shell=False,
                        components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['forge', 'anvil']:
        parser.error('one GTK frontend is required')
    for name in ['daemon', 'wm', 'shell']:
        setattr(args, name, getattr(args, name).resolve(strict=True))
    session = GtkRemapSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try:
            session.capture('failed-gtk-remap')
        except Exception as capture_error:
            result['capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, frontend=session.frontend, backend=args.backend,
                      binary_sha256=session.binary_hashes, backend_observation=session.backend_observation,
                      remap_observation=session.remap_observation, events=session.events,
                      samples=session.samples)
        report = session.root / 'gtk-remap-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], error=result.get('error'), report=str(report))))
    raise SystemExit(0 if result['passed'] else 1)

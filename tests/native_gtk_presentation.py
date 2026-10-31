#!/usr/bin/env python3
"""Real GTK handoff while only the private compositor is intermittently stopped.

Exercises actual GDK frame timings and original native windows/PTYs. No host,
geometry, frame or retirement messages are fabricated. This is a functional
ordering stress case, not performance, physical scanout or trusted C11 proof.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import threading
import time

from native_gtk_jobs import GtkJobsSession
from native_window_use import stat
from native_windows import host


class PresentationSession(GtkJobsSession):
    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)
        self.stop_pulses = threading.Event()
        self.pulse_thread = None
        self.pulse_count = 0
        self.stops_observed = 0
        self.pulse_error = None
        self.handoffs = []

    def start_pulses(self):
        compositor = self.old_wm
        original = stat(compositor.pid)
        fd = os.pidfd_open(compositor.pid)

        def pulse():
            try:
                while not self.stop_pulses.is_set():
                    signal.pidfd_send_signal(fd, signal.SIGSTOP)
                    self.stop_pulses.wait(.01)
                    current = stat(compositor.pid)
                    if current['start_ticks'] != original['start_ticks']:
                        raise AssertionError('private compositor identity changed')
                    self.stops_observed += current['state'] in ['T', 't']
                    self.stop_pulses.wait(.07)
                    signal.pidfd_send_signal(fd, signal.SIGCONT)
                    self.pulse_count += 1
                    self.stop_pulses.wait(.03)
            except Exception as error:
                self.pulse_error = repr(error)
            finally:
                try:
                    signal.pidfd_send_signal(fd, signal.SIGCONT)
                except ProcessLookupError:
                    pass
                os.close(fd)

        self.pulse_thread = threading.Thread(target=pulse, daemon=True)
        self.pulse_thread.start()
        time.sleep(.35)
        assert self.pulse_error is None, self.pulse_error
        self.record('private-compositor-frame-feedback-delayed', compositor=original,
                    stop_ms=80, continue_ms=30)

    def finish_pulses(self):
        self.stop_pulses.set()
        if self.pulse_thread:
            self.pulse_thread.join(3)
            assert not self.pulse_thread.is_alive(), 'private compositor pulse did not stop'
            self.pulse_thread = None

    def run(self):
        self.startup()
        self.focus(self.target)
        assert self.wait_visible(self.target), 'warm target did not become active'
        original = {name: stat(process.pid) for name, process in self.host_processes.items()}
        token = self.journal()['possible_body']
        self.start_pulses()
        try:
            for name in [self.source, self.target, self.source]:
                self.focus(name)
                active = self.wait_visible(name, seconds=20)
                self.capture('delayed-native-presentation-' + name)
                assert self.pulse_error is None, self.pulse_error
                assert active, 'visible GTK body never became active under delayed native feedback: ' + name
                current = self.journal()['possible_body']
                assert current['epoch'] > token['epoch'] and current['companion_id'] == token['companion_id']
                assert stat(self.host_processes[name].pid)['start_ticks'] == original[name]['start_ticks']
                self.handoffs.append(dict(window=name, token=current, compositor_cycles=self.pulse_count))
                token = current
            assert self.stops_observed >= 3
        finally:
            self.finish_pulses()
        self.record('native-presentation-progressed-under-delayed-feedback', handoffs=self.handoffs,
                    compositor_cycles=self.pulse_count, actual_stop_observations=self.stops_observed)
        return dict(passed=True, native_handoffs=len(self.handoffs),
                    compositor_cycles=self.pulse_count, actual_stop_observations=self.stops_observed)

    def close(self):
        self.finish_pulses()
        super().close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['daemon', 'wm', 'shell']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--backend', choices=['block', 'vte'], required=True)
    parser.set_defaults(case='delayed-presentation', renderer='cairo', compositor='xrender',
                        frame_sync=True, freeze_owner=False, restart_daemon=False,
                        desktop_shell=False, components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['forge', 'anvil']:
        parser.error('one actual GTK frontend is required')
    for name in ['daemon', 'wm', 'shell']:
        setattr(args, name, getattr(args, name).resolve(strict=True))
    session = PresentationSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try:
            session.capture('failed-delayed-presentation')
        except Exception as capture_error:
            result['capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, frontend=session.frontend, backend=args.backend,
                      binary_sha256=session.binary_hashes, backend_observation=session.backend_observation,
                      events=session.events, samples=session.samples, handoffs=session.handoffs,
                      compositor_cycles=session.pulse_count, actual_stop_observations=session.stops_observed,
                      pulse_error=session.pulse_error)
        report = session.root / 'gtk-presentation-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], error=result.get('error'), report=str(report))))
    raise SystemExit(0 if result['passed'] else 1)

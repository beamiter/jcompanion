#!/usr/bin/env python3
"""Real native clock recreation using each frontend's production GTK adapter.

An ignored test binary owns two real windows in one process. The driver only
requests ordinary hide/unrealize/present operations. Actual coordinator state,
GDK timings, object identities and PNGs prove the observed result. This does not
claim full terminal multiwindow, physical scanout or trusted destruction.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import time

from native_gtk_jobs import GtkJobsSession
from native_surface_lifecycle import SurfaceSession
from native_windows import host


class ClockSession(SurfaceSession):
    capture = GtkJobsSession.capture

    def __init__(self, args):
        super().__init__(args)
        self.body_regions = {}
        self.control = self.root / 'clock-control.json'
        self.status_path = self.root / 'clock-status.json'
        self.nonce = 0
        self.clock_observations = []
        self.harness = None
        for source in Path(__file__).parent.glob('native_*.py'):
            shutil.copy2(source, self.root / 'harness' / source.name)

    def status(self, predicate=lambda state: True, seconds=10, allow_exit=False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert allow_exit or self.harness.poll() is None, 'native GTK fixture exited'
            try:
                value = json.loads(self.status_path.read_text())
                if predicate(value):
                    return value
            except (OSError, ValueError):
                pass
            time.sleep(.03)
        raise AssertionError('native clock observation did not arrive')

    def action(self, action):
        self.nonce += 1
        pending = self.control.with_suffix('.next')
        pending.write_text(json.dumps(dict(nonce=self.nonce, action=action)))
        pending.replace(self.control)
        value = self.status(lambda state: state['nonce'] == self.nonce, allow_exit=action == 'finish')
        self.clock_observations.append(dict(action=action, observed=value))
        return value

    def find_window(self, name):
        title = self.frontend.capitalize() + ' clock ' + ('primary' if name == self.source else 'secondary')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            found = self.command('xdotool', 'search', '--all', '--onlyvisible', '--pid',
                                 str(self.harness.pid), '--name', '^' + title + '$', check=False)
            if found.returncode == 0:
                windows = found.stdout.splitlines()
                assert len(windows) == 1, 'ambiguous native fixture window'
                self.windows[name] = windows[0]
                return windows[0]
            time.sleep(.05)
        raise AssertionError('real native fixture window did not map: ' + name)

    def position(self, name):
        index = 0 if name == self.source else 1
        self.command('xdotool', 'windowsize', '--sync', self.windows[name], '1344', '1100')
        self.command('xdotool', 'windowmove', '--sync', self.windows[name], str(20 + 1500 * index), '50')

    def startup(self):
        self.start_display()
        for config in (self.root / 'config/jwm').glob('config_*.toml'):
            text = config.read_text()
            rule = dict(name=self.frontend.capitalize() + ' clock', tags=0,
                        is_floating=True, monitor=-1, instance='')
            rule['class'] = ''
            inline = ', '.join(key + ' = ' + json.dumps(value) for key, value in rule.items())
            text, count = re.subn(r'(?m)^rules = \[\]$', 'rules = [{' + inline + '}]', text, count=1)
            assert count == 1, 'private floating rules missing'
            config.write_text(text)
        self.wm(command='reload_config')
        self.env.update(EVA_GTK_CLOCK_CONTROL=str(self.control),
                        EVA_GTK_CLOCK_STATUS=str(self.status_path),
                        EVA_GTK_CLOCK_FRONTEND=self.frontend)
        self.env['RUST_LOG'] += ',eva_native_host=debug'
        self.harness = self.launch('gtk-clock-fixture', [str(self.binaries[self.frontend]),
            '--exact', 'eva_companion::clock_fixture::native_clock_recreation_uses_exact_adapter',
            '--ignored', '--nocapture', '--test-threads=1'])
        self.host_processes = {self.source: self.harness, self.target: self.harness}
        for name in [self.source, self.target]:
            self.find_window(name)
            self.position(name)
        self.status(lambda state: state['primary']['mapped'] and state['secondary']['mapped'])
        self.focus(self.source)
        assert self.capture('before-authority')['visible_body_windows'] == []
        self.daemon = self.launch('daemon', [str(self.binaries['jcompaniond']), str(self.root / 'profile')])
        assert self.wait_visible(self.source), 'initial native body did not become active'
        self.status(lambda state: state['primary']['frame'] >= 80)
        self.record('two-native-windows-one-process-active', pid=self.harness.pid,
                    native_windows=dict(self.windows), clock_status=self.status())

    def receipt(self, token, retirement, after=0):
        text = (self.root / 'gtk-clock-fixture.log').read_text(errors='replace')
        rows = []
        for index, line in enumerate(text.splitlines()):
            if index < after or 'GTK presentation receipt' not in line:
                continue
            if ('host_id: "' + token['host_id'] + '"') not in line or ('epoch: ' + str(token['epoch']) + ',') not in line:
                continue
            match = re.search(r'frame=(\d+) presentation_time=(\d+) retirement=(true|false) serial=(\d+) native_generation=(\d+)', line)
            if match and (match[3] == 'true') == retirement:
                rows.append(dict(line=index, frame=int(match[1]), presentation_time=int(match[2]),
                                 serial=int(match[4]), native_generation=int(match[5])))
        return rows

    def run(self):
        self.startup()
        original = self.journal()['possible_body']
        old_window = self.windows[self.source]
        if self.args.case == 'retired-rebuild':
            self.focus(self.target)
            assert self.wait_visible(self.target), 'old native surface did not retire before rebuild'
            assert self.receipt(original, True), 'old surface has no actual clearance receipt'
        self.capture('before-native-surface-rebuild')
        log_offset = len((self.root / 'gtk-clock-fixture.log').read_text().splitlines())
        hidden = self.action('rebuild-primary')
        assert hidden['primary']['surface'] is None and not hidden['primary']['realized']
        assert hidden['old_surface_destroyed'] is True
        self.windows.pop(self.source)
        self.capture('native-primary-unrealized')
        self.action('show-primary')
        self.find_window(self.source)
        self.position(self.source)
        rebuilt = self.status(lambda state: state['primary']['mapped'] and state['primary']['surface'] is not None)
        assert rebuilt['primary']['surface'] != rebuilt['replaced']['surface']
        assert rebuilt['primary']['clock'] != rebuilt['replaced']['clock']
        assert self.windows[self.source] != old_window
        assert rebuilt['pid'] == self.harness.pid
        self.record('native-surface-and-clock-replaced', before=hidden, after=rebuilt,
                    old_xid=old_window, new_xid=self.windows[self.source])
        if self.args.case == 'retired-rebuild':
            self.focus(self.source)
            assert self.wait_visible(self.source), 'rebuilt native surface did not accept a new body'
            new_token = self.journal()['possible_body']
            assert new_token['host_id'] == original['host_id'] and new_token['epoch'] > original['epoch']
            self.focus(self.target)
            assert self.wait_visible(self.target), 'new low-counter clock could not retire its body'
            receipts = self.receipt(new_token, True, log_offset)
            assert receipts and all(row['presentation_time'] > 0 for row in receipts)
            assert any(row['frame'] < hidden['replaced']['frame'] for row in receipts), 'counter reset was not exercised'
            old_receipts = self.receipt(original, True)
            assert min(row['serial'] for row in receipts) > max(row['serial'] for row in old_receipts)
            self.record('new-clock-retired-below-old-native-counter', old=old_receipts, new=receipts)
        else:
            self.focus(self.target)
            for _ in range(8):
                sample = self.capture('unproved-old-surface-still-blocks')
                assert sample['visible_body_windows'] == [], 'new surface repainted an unretired body'
                state = self.journal()
                assert state['possible_body'] == original
                assert state['phase'] in ['awaiting_removal_proof', 'recovery_blocked']
                assert not self.receipt(original, True, log_offset), 'new surface fabricated old clearance'
                time.sleep(.15)
            self.record('destroyed-surface-is-not-trusted-retirement', token=original)
        self.capture('final-native-clock-state')
        assert len(self.host_ids) == (2 if self.args.case == 'retired-rebuild' else 1)
        self.action('finish')
        assert self.harness.wait(timeout=5) == 0
        return dict(passed=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['daemon', 'wm']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True,
                        help='frontend=its compiled ignored-test executable')
    parser.add_argument('--case', choices=['retired-rebuild', 'unproved-rebuild'], required=True)
    parser.set_defaults(shell=None, renderer='cairo', compositor='xrender', frame_sync=True,
                        freeze_owner=False, restart_daemon=False, desktop_shell=False,
                        components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['forge', 'anvil']:
        parser.error('one actual GTK frontend test executable is required')
    for name in ['daemon', 'wm']:
        setattr(args, name, getattr(args, name).resolve(strict=True))
    session = ClockSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try:
            session.capture('failed-native-clock')
        except Exception as capture_error:
            result['capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, case=args.case, frontend=session.frontend,
                      binary_sha256=session.binary_hashes, clock_observations=session.clock_observations,
                      events=session.events, samples=session.samples, native_host_ids=session.host_ids)
        report = session.root / 'gtk-clock-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], error=result.get('error'), report=str(report))))
    raise SystemExit(0 if result['passed'] else 1)

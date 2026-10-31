#!/usr/bin/env python3
"""Native compositor authority loss and restart in an isolated X11 session.

Runs two real WGPU GUI processes. A stopped private JWM withholds scene feedback;
the fixture then clears the actual X-server compositor selection. No coordinator
host, grant, retirement or frame acknowledgement is injected. Native keyboard
input must resume without a resize/new input, and a real replacement JWM must
establish new ownership before normal body handoffs work again.

PNG sampling is not continuous/physical uniqueness evidence. Marker execution
checks GUI input consumption, not transfer latency, IME, audio/API or performance.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import time

from PIL import Image, ImageChops

from native_windows import NativeSession, host
from native_matrix import MatrixSession


class XAuthority:
    def __init__(self, display):
        self.lib = C.CDLL('libX11.so.6')
        self.lib.XOpenDisplay.argtypes = [C.c_char_p]
        self.lib.XOpenDisplay.restype = C.c_void_p
        self.lib.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
        self.lib.XInternAtom.restype = C.c_ulong
        self.lib.XGetSelectionOwner.argtypes = [C.c_void_p, C.c_ulong]
        self.lib.XGetSelectionOwner.restype = C.c_ulong
        self.lib.XSetSelectionOwner.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong]
        self.lib.XSync.argtypes = [C.c_void_p, C.c_int]
        self.lib.XCloseDisplay.argtypes = [C.c_void_p]
        self.display = self.lib.XOpenDisplay(display.encode())
        if not self.display:
            raise RuntimeError('private X11 authority connection failed')
        self.selection = self.lib.XInternAtom(self.display, b'_NET_WM_CM_S0', 0)

    def owner(self):
        return int(self.lib.XGetSelectionOwner(self.display, self.selection))

    def clear(self):
        self.lib.XSetSelectionOwner(self.display, self.selection, 0, 0)
        self.lib.XSync(self.display, 0)
        if self.owner() != 0:
            raise AssertionError('private compositor selection was not cleared')

    def close(self):
        self.lib.XCloseDisplay(self.display)


class LifecycleSession(NativeSession):
    wait_visible = MatrixSession.wait_visible
    wm = MatrixSession.wm

    def __init__(self, args):
        super().__init__(args)
        self.frontend = args.host[0][0]
        self.source = self.frontend + '-1'
        self.target = self.frontend + '-2'
        self.instances = {self.source: self.frontend, self.target: self.frontend}
        self.host_ids, self.companion_id = {}, None
        self.events = []
        self.authority = None
        self.old_wm = None
        self.input_observation = {}
        self.native_samples = []
        (self.root/'harness').mkdir()
        for filename in ['native_lifecycle.py', 'native_windows.py', 'native_matrix.py']:
            shutil.copyfile(Path(__file__).with_name(filename), self.root/'harness'/filename)

    def record(self, action, **data):
        self.events.append(dict(action=action, elapsed_ms=round((time.monotonic()-self.started)*1000, 2),
                                journal=self.journal(), **data))

    def proof_counts(self, name):
        text = (self.root/(name+'.log')).read_text(errors='replace')
        return {'published': text.count('producer frame published'),
                'accepted': text.count('compositor scene receipt accepted'),
                'vulkan_completed': text.count('Vulkan publication completed'),
                'authority_events': text.count('compositor authority changed; native proof invalidated')}

    def capture(self, label):
        sample = super().capture(label)
        sample['actual_input_focus'] = self.command('xdotool', 'getwindowfocus', check=False).stdout.strip()
        return sample

    def capture_native(self, label):
        # Read the redirected client backing, not the frozen compositor root.
        # Compare decoded pixels; PNG metadata/hash changes alone prove nothing.
        path = self.root/(f'native-{len(self.native_samples):03}-'+label+'.png')
        self.command('import', '-window', self.windows[self.source], str(path))
        with Image.open(path) as image:
            pixels = image.convert('RGB')
        self.native_samples.append(dict(label=label, screenshot=path.name, size=pixels.size,
                                        pixel_sha256=hashlib.sha256(pixels.tobytes()).hexdigest()))
        return pixels

    def focus(self, name):
        # The replacement WM rearranges existing clients. Put the actual pointer
        # in the requested window as well, so a late EnterNotify cannot select
        # the window under the old pointer after XSetInputFocus succeeds.
        self.command('xdotool', 'mousemove', '--window', self.windows[name], '100', '100')
        super().focus(name)

    def direct_focus(self, name):
        self.command('xdotool', 'windowfocus', '--sync', self.windows[name])
        actual = self.command('xdotool', 'getwindowfocus').stdout.strip()
        if actual != self.windows[name]:
            raise AssertionError('actual X11 input focus did not reach '+name)

    def queue_marker(self, name, marker):
        self.direct_focus(name)
        result = self.command('xdotool', 'getwindowgeometry', '--shell', self.windows[name])
        geometry = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        self.command('xdotool', 'mousemove', '--window', self.windows[name],
                     str(int(geometry['WIDTH'])//2), str(int(geometry['HEIGHT'])-80), 'click', '1')
        command = "printf 'EVA_OWNER_CHANGE_OK\\n' > " + shlex.quote(str(marker))
        self.command('xdotool', 'type', '--clearmodifiers', '--delay', '4', '--', command)
        self.command('xdotool', 'key', '--clearmodifiers', 'Return')

    def wait_marker(self, marker, seconds):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            if marker.exists():
                if marker.read_text() != 'EVA_OWNER_CHANGE_OK\n':
                    raise AssertionError('wrong real shell marker')
                return True
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('source GUI exited during authority loss')
            time.sleep(.05)
        return False

    def held(self, token):
        state = self.journal()
        return state and state['possible_body'] == token and state['phase'] == 'awaiting_removal_proof'

    def run(self):
        self.start_display()
        self.old_wm = next(p for p in self.processes if p.args[0] == str(self.binaries['jwm']))
        self.authority = XAuthority(self.env['DISPLAY'])
        old_owner = self.authority.owner()
        if not old_owner:
            raise AssertionError('private JWM did not own the compositor selection')
        self.launch_host(0, self.source)
        self.launch_host(0, self.target)
        self.focus(self.source)
        if self.capture('before-authority')['visible_body_windows']:
            raise AssertionError('body appeared before coordinator authority')
        self.daemon = self.launch('daemon', [str(self.binaries['jcompaniond']), str(self.root/'profile')])
        if not self.wait_visible(self.source):
            raise AssertionError('source native body did not become active')
        token = self.journal()['possible_body']
        before = self.proof_counts(self.source)
        os.kill(self.old_wm.pid, signal.SIGSTOP)
        deadline = time.monotonic()+2
        while True:
            state = next(line for line in Path(f'/proc/{self.old_wm.pid}/status').read_text().splitlines() if line.startswith('State:'))
            if '\tT' in state:
                break
            if time.monotonic() >= deadline:
                raise AssertionError('private WM stop was not observed')
            time.sleep(.01)
        self.record('wm-stopped', pid=self.old_wm.pid, kernel_state=state, owner=old_owner)
        self.direct_focus(self.target)
        deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            counts = self.proof_counts(self.source)
            if self.held(token) and counts['published'] > before['published'] and counts['accepted'] == before['accepted']:
                break
            time.sleep(.05)
        else:
            raise AssertionError('a genuine published clearance frame did not wait for stopped compositor')
        self.record('clearance-published-scene-pending', proof_counts=counts, token=token)
        self.capture('stopped-compositor-holds-owner')
        time.sleep(2)
        marker = self.root/'owner-change-input.txt'
        self.queue_marker(self.source, marker)
        before_loss = self.wait_marker(marker, .4)
        if self.frontend == 'ember' and before_loss:
            raise AssertionError('Ember consumed input while its evidence frame was still deferred')
        self.input_observation['executed_before_owner_loss'] = before_loss
        if not self.held(token):
            raise AssertionError('stopped compositor allowed replacement or retirement')
        before_loss_counts = self.proof_counts(self.source)
        before_loss_pixels = self.capture_native('before-owner-loss')
        self.authority.clear()
        self.record('compositor-selection-cleared', owner=self.authority.owner(), proof_counts=before_loss_counts)
        resumed = self.wait_marker(marker, self.args.recovery_seconds)
        self.input_observation['executed_after_owner_loss_without_new_input'] = resumed
        self.input_observation['marker'] = str(marker)
        self.record('queued-input-observed', resumed=resumed, proof_counts=self.proof_counts(self.source))
        if not resumed:
            raise AssertionError('queued native GUI input did not resume after compositor authority disappeared')
        # iced can consume keyboard/model updates while native drawing is paced.
        # The already executed shell marker cannot prove native draw recovery.
        # Check real client backing pixels in both frontends; Frost additionally
        # retains its pending evidence request, so its exact producer wait is
        # observed too. Eframe can draw input without requesting that wait.
        deadline = time.monotonic()+self.args.recovery_seconds
        while time.monotonic() < deadline:
            after_loss_counts = self.proof_counts(self.source)
            after_loss_pixels = self.capture_native('after-owner-loss')
            if after_loss_pixels.size != before_loss_pixels.size:
                raise AssertionError('native geometry changed during owner-loss-only recovery')
            changed = ImageChops.difference(before_loss_pixels, after_loss_pixels).convert('L')
            changed_pixels = sum(n for n, value in changed.getcolors(changed.width*changed.height) if value)
            if (changed_pixels >= 100
                    and after_loss_counts['authority_events'] > before_loss_counts['authority_events']
                    and (self.frontend != 'frost' or after_loss_counts['vulkan_completed'] > before_loss_counts['vulkan_completed'])):
                break
            time.sleep(.05)
        else:
            raise AssertionError('native drawing did not resume after compositor authority disappeared')
        self.record('native-draw-resumed-without-new-input', proof_counts=after_loss_counts,
                    changed_native_pixels=changed_pixels)
        if not self.held(token) or self.proof_counts(self.source)['accepted'] != before['accepted']:
            raise AssertionError('authority loss fabricated a scene/retirement receipt')
        self.capture('ownerless-compositor-holds-old-owner')
        os.killpg(self.old_wm.pid, signal.SIGCONT)
        os.killpg(self.old_wm.pid, signal.SIGTERM)
        self.old_wm.wait(5)
        replacement = self.launch('jwm-restarted', [str(self.binaries['jwm']), '--backend', 'x11rb'])
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            owner = self.authority.owner()
            marker_property = self.command('xprop', '-root', '_JWM_FRAME_SYNC_OWNER', check=False).stdout
            marker_values = re.findall(r'0x[0-9a-fA-F]+', marker_property)
            marker_owner = int(marker_values[-1], 16) if marker_values else 0
            if owner and marker_owner == owner:
                break
            if replacement.poll() is not None:
                raise AssertionError('replacement private JWM exited')
            time.sleep(.05)
        else:
            raise AssertionError('replacement compositor did not establish a new owner')
        self.record('replacement-compositor-owner', pid=replacement.pid, owner=owner,
                    old_owner=old_owner, owner_xid_reused=owner == old_owner)
        # Selection ownership is established before the replacement WM scans
        # existing clients. Wait for its real event loop to report both PIDs;
        # this is startup readiness, never body or retirement evidence.
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            try:
                managed = self.wm(query='get_windows')
                pids = {window.get('pid') for window in managed}
                if {p.pid for p in self.host_processes.values()} <= pids:
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(.05)
        else:
            raise AssertionError('replacement WM did not finish managing both native clients')
        self.record('replacement-wm-clients-ready', windows=managed)
        self.focus(self.target)
        if not self.wait_visible(self.target):
            raise AssertionError('native handoff did not recover with the replacement compositor')
        self.focus(self.source)
        if not self.wait_visible(self.source):
            raise AssertionError('native reverse handoff did not recover after compositor replacement')
        return dict(passed=True, real_owner_loss_recovered=True, no_synthetic_retirement=True,
                    native_drawing_resumed=True, compositor_restart_round_trip=True)

    def close(self):
        if self.authority:
            self.authority.close()
        super().close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--wm', type=Path, required=True)
    parser.add_argument('--shell', type=Path)
    parser.add_argument('--recovery-seconds', type=float, default=5)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True,
                        freeze_owner=False, restart_daemon=False, desktop_shell=False,
                        components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['ember','frost']:
        parser.error('one Ember or Frost binary is required; two native processes are launched')
    args.task_canvas = args.host[0][0] == 'ember'
    if args.task_canvas and not args.shell:
        parser.error('Ember lifecycle needs the real jsh task fixture')
    args.daemon = args.daemon.resolve(strict=True)
    args.wm = args.wm.resolve(strict=True)
    if args.shell:
        args.shell = args.shell.resolve(strict=True)
    session = LifecycleSession(args)
    result = {'passed':False}
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try:
            session.capture('failed-lifecycle')
        except Exception as capture_error:
            result['failure_capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, binary_sha256=session.binary_hashes,
                      frontend=session.frontend, gui_processes={name:p.pid for name,p in session.host_processes.items()},
                      native_host_ids=session.host_ids, events=session.events,
                      input_observation=session.input_observation, samples=session.samples,
                      native_backing_samples=session.native_samples)
        report = session.root/'lifecycle-report.json'
        report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'report':str(report),'error':result.get('error')}))
    raise SystemExit(0 if result['passed'] else 1)

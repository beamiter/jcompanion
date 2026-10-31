#!/usr/bin/env python3
"""Real X11 matrix: two GUI processes per frontend, four native PTYs per GUI.

Uses actual input, shells, screenshots and the residence journal, with no
injected coordinator hosts, geometry, grants, task facts or retirement proofs.
Default-Cat image grouping checks both cross-window and separated within-window
body pixels. Samples do not certify continuous uniqueness/physical scanout,
other skins/Compact, IME, audio/API, suspend or performance. The private JWM's
existing shortcut passthrough is enabled for each focused test window so its
Ctrl+Alt pane navigation reaches the application.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import threading
import time
import termios

from native_windows import NativeSession, SESSION, host


class MatrixSession(NativeSession):
    def __init__(self, args):
        super().__init__(args)
        self.frontends = {name: i for i, (name, _) in enumerate(args.host)}
        self.instances = {f'{name}-{i}': name for name in self.frontends for i in (1, 2)}
        self.focused = None
        self.host_ids = {}
        self.panes = {}
        self.focus_events = []
        self.companion_id = None
        self.marker_seq = 0
        self.companion_connections = []
        self.resume_observation = None
        (self.root / 'harness').mkdir()
        for filename in ('native_matrix.py', 'native_windows.py'):
            shutil.copyfile(Path(__file__).with_name(filename), self.root / 'harness' / filename)

    def launch(self, name, argv, **kwargs):
        if getattr(self.args, 'native_host_debug', False) and name in getattr(self, 'instances', {}):
            self.env['RUST_LOG'] += ',eva_native_host=debug'
        return super().launch(name, argv, **kwargs)

    def wm(self, command=None, query=None, args=None):
        request = {'command': command} if command else {'query': query}
        if args is not None:
            request['args'] = args
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(5)
            peer.connect(str(self.root / 'jwm-ipc.sock'))
            peer.sendall(json.dumps(request).encode() + b'\n')
            with peer.makefile('rb') as stream:
                raw = stream.readline(1_048_577)
        if len(raw) > 1_048_576 or not raw.endswith(b'\n'):
            raise RuntimeError('invalid private JWM reply')
        reply = json.loads(raw)
        if not reply.get('success'):
            raise RuntimeError('private JWM rejected fixture control: ' + str(reply))
        return reply.get('data')

    def focus(self, name):
        previous = self.focused
        super().focus(name)
        if previous != name:
            time.sleep(.1)
            self.wm(command='toggle_shortcut_passthrough')
        self.focused = name

    def key(self, chord, delay=60):
        self.command('xdotool', 'key', '--clearmodifiers', '--delay', str(delay), chord)

    def shells(self, name):
        """Kernel descendants, executable identity and unique live PTY fds."""
        process = self.host_processes[name]
        if process.poll() is not None:
            raise RuntimeError(name + ' GUI exited')
        parents, sessions = {}, {}
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / 'stat').read_text()
                fields = stat[stat.rfind(')') + 2:].split()
                parents[int(entry.name)] = int(fields[1])
                sessions[int(entry.name)] = int(fields[3])
            except (OSError, ValueError, IndexError):
                continue
        descendants, frontier = set(), {process.pid}
        while frontier:
            children = {pid for pid, parent in parents.items() if parent in frontier} - descendants
            descendants.update(children)
            frontier = children
        expected = Path(self.shell_programs[self.instances[name]]).resolve()
        found = []
        for pid in sorted(descendants):
            try:
                exe = Path(f'/proc/{pid}/exe').resolve(strict=True)
                tty = os.readlink(f'/proc/{pid}/fd/0')
                # jsh can briefly fork helpers which inherit its executable
                # and stdin. Only the PTY session leader is a shell pane.
                if exe == expected and tty.startswith('/dev/pts/') and sessions[pid] == pid:
                    fd = os.open(tty, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC)
                    try:
                        local_flags = termios.tcgetattr(fd)[3]
                    finally:
                        os.close(fd)
                    found.append(dict(pid=pid, session_id=sessions[pid], tty=tty, executable=str(exe),
                                      editor_raw=not bool(local_flags & (termios.ICANON | termios.ECHO))))
            except (OSError, RuntimeError):
                continue
        return found

    def wait_shells(self, name, count):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            shells = self.shells(name)
            if len(shells) == count:
                if len({shell['tty'] for shell in shells}) != count:
                    raise AssertionError(name + ' PTYs are not distinct')
                # A spawned jsh process is not yet a ready line editor. Wait
                # for observed kernel raw/no-echo mode before diagnostic input.
                uses_jsh = self.shell_programs[self.instances[name]] == str(self.binaries.get('jsh'))
                if not uses_jsh or all(shell['editor_raw'] for shell in shells):
                    return shells
            if len(shells) > count:
                raise AssertionError(f'{name}: expected {count} shell panes, got {len(shells)}')
            time.sleep(.1)
        raise AssertionError(f'{name}: native split did not create {count} real shell panes')

    def mark_pane(self, name):
        if self.instances[name] == 'ember':
            self.wait_shells(name, len(self.shells(name)))
        self.marker_seq += 1
        marker = self.root / f'pane-{name}-{self.marker_seq}.pid'
        # Fixed local diagnostic input; the shell itself supplies its PID.
        command = "printf '%s\\n' \"$$\" > " + shlex.quote(str(marker))
        self.command('xdotool', 'type', '--clearmodifiers', '--delay', '4', '--', command)
        time.sleep(.2)
        self.key('Return')
        deadline = time.monotonic() + 10
        while True:
            try:
                value = marker.read_text()
            except FileNotFoundError:
                value = ''
            # Shell redirection creates the file before printf writes it.
            # Existence is not evidence that its complete PID has arrived.
            if value.endswith('\n'):
                pid = int(value.strip())
                break
            if time.monotonic() >= deadline:
                self.capture('pane-command-not-executed-' + name)
                raise AssertionError(name + ' did not execute the native pane diagnostic')
            time.sleep(.05)
        if pid not in {shell['pid'] for shell in self.shells(name)}:
            raise AssertionError(name + ' marker did not identify its own live PTY shell')
        return pid

    def four_panes(self, name):
        self.wait_shells(name, 1)
        time.sleep(.4)
        first = self.mark_pane(name)
        self.key('ctrl+shift+e')
        self.wait_shells(name, 2)
        # A fork/exec-ready child can precede GTK's next pane allocation.
        # This is input pacing only; the following real PID marker remains
        # the routing check and no native frame/geometry proof is supplied.
        time.sleep(.5)
        second = self.mark_pane(name)
        self.key('ctrl+shift+d')
        self.wait_shells(name, 3)
        time.sleep(.5)
        third = self.mark_pane(name)
        self.key('ctrl+alt+Left')
        time.sleep(.2)
        if self.mark_pane(name) != first:
            raise AssertionError(name + ' native pane-left routing did not return to the original shell')
        self.key('ctrl+shift+d')
        shells = self.wait_shells(name, 4)
        time.sleep(.5)
        fourth = self.mark_pane(name)
        if len({first, second, third, fourth}) != 4:
            raise AssertionError(name + ' four native pane inputs did not reach four distinct shells')
        # Visit all four quadrants through the applications' real spatial keys.
        for chord, expected in [('ctrl+alt+Up', first), ('ctrl+alt+Right', second),
                                ('ctrl+alt+Down', third), ('ctrl+alt+Left', fourth)]:
            self.key(chord)
            time.sleep(.5)
            if self.mark_pane(name) != expected:
                raise AssertionError(name + ' spatial pane routing changed the target shell')
        self.panes[name] = dict(shells=shells, native_input_pids=[first, second, third, fourth])

    def wait_visible(self, name, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            sample = self.capture('waiting-' + name)
            state = sample['journal']
            token = state and state['possible_body']
            if (token and state['phase'] == 'active' and
                    token['host_id'].startswith(self.instances[name] + '-') and
                    sample['visible_body_windows'] == [name] and
                    len(sample['body_components'][name]) == 1):
                known = self.host_ids.get(name)
                if known and known != token['host_id']:
                    raise AssertionError(name + ' changed live GUI host identity')
                if not known and token['host_id'] in self.host_ids.values():
                    raise AssertionError('two distinct GUI processes reused one companion host identity')
                self.host_ids[name] = token['host_id']
                if self.companion_id and self.companion_id != token['companion_id']:
                    raise AssertionError('native handoff created a different companion identity')
                self.companion_id = token['companion_id']
                return True
            time.sleep(.1)
        return False

    def observe_companion_connections(self):
        inodes = set()
        for fd in Path(f'/proc/{self.daemon.pid}/fd').iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith('socket:['):
                    inodes.add(target[8:-1])
            except OSError:
                continue
        sockets = []
        for line in Path('/proc/net/unix').read_text().splitlines()[1:]:
            fields = line.split()
            if (len(fields) == 8 and fields[7] == str(self.root / 'eva.sock')
                    and fields[5] == '03' and fields[6] in inodes):
                sockets.append(dict(inode=fields[6], state=fields[5]))
        self.companion_connections = sockets
        if len(sockets) != 8:
            raise AssertionError(f'expected eight actual companion connections, observed {len(sockets)}')

    def burst(self, names, rounds):
        stopped = threading.Event()

        def camera():
            while not stopped.is_set():
                self.capture('rapid-focus')
                stopped.wait(.05)

        with ThreadPoolExecutor(max_workers=1) as executor:
            sample_job = executor.submit(camera)
            try:
                for _ in range(rounds):
                    for name in names:
                        self.focus(name)
                        self.key('ctrl+alt+Right', delay=1)
                        active = self.command('xdotool', 'getactivewindow').stdout.strip()
                        if active != self.windows[name]:
                            raise AssertionError('native focus did not reach ' + name)
                        self.focus_events.append(dict(instance=name, window=active,
                                                      elapsed_ms=round((time.monotonic() - self.started) * 1000, 2),
                                                      journal=self.journal()))
                        if sample_job.done():
                            sample_job.result()
            finally:
                stopped.set()
                sample_job.result(timeout=20)

    def run(self):
        self.start_display()
        self.wm(command='set_layout', args={'layout': 'grid'})
        names = list(self.instances)
        for name in names:
            super().launch_host(self.frontends[self.instances[name]], instance=name)
            self.four_panes(name)
        if self.capture('eight-windows-daemon-absent')['visible_body_windows']:
            raise AssertionError('body appeared before coordinator authority')
        barrier = getattr(self.args, 'startup_barrier', None)
        if barrier:
            # Orchestration only: make concurrent load begin after all native
            # pane-input preconditions passed, before any body can be granted.
            # These files never provide host, frame or retirement evidence.
            ready = barrier.with_suffix('.ready.json')
            ready.write_text(json.dumps(dict(root=str(self.root), panes=self.panes,
                gui_pids={name: process.pid for name, process in self.host_processes.items()})))
            deadline = time.monotonic() + 60
            while not barrier.with_suffix('.release').exists():
                if time.monotonic() >= deadline:
                    raise AssertionError('matrix startup orchestration barrier expired')
                time.sleep(.05)
        self.focus(names[0])
        self.daemon = self.launch('daemon', [str(self.binaries['jcompaniond']), str(self.root / 'profile')])
        if not self.wait_visible(names[0]):
            raise AssertionError('first eight-window native body did not become visible/active')
        old_token = self.journal()['possible_body']
        owner = self.host_processes[names[0]]
        os.kill(owner.pid, signal.SIGSTOP)
        deadline = time.monotonic() + 2
        while '\tT' not in next(line for line in Path(f'/proc/{owner.pid}/status').read_text().splitlines() if line.startswith('State:')):
            if time.monotonic() >= deadline:
                raise AssertionError('matrix owner did not stop')
            time.sleep(.01)
        blocked = False
        try:
            self.focus(names[1])
            began = time.monotonic()
            while time.monotonic() - began < 4:
                sample = self.capture('frozen-four-pane-owner')
                if sample['journal']['possible_body'] != old_token or names[1] in sample['visible_body_windows']:
                    raise AssertionError('matrix granted a replacement while native owner was stopped')
                blocked |= sample['journal']['phase'] == 'awaiting_removal_proof'
        finally:
            os.kill(owner.pid, signal.SIGCONT)
        deadline = time.monotonic() + 2
        while True:
            state = next(line for line in Path(f'/proc/{owner.pid}/status').read_text().splitlines() if line.startswith('State:'))
            if '\tT' not in state:
                self.resume_observation = dict(pid=owner.pid, state=state, elapsed_ms=round((time.monotonic() - self.started) * 1000, 2))
                break
            if time.monotonic() >= deadline:
                raise AssertionError('matrix owner did not resume after SIGCONT')
            time.sleep(.01)
        if not blocked:
            raise AssertionError('matrix did not observe exact retirement blocking')
        for name in names[1:]:
            self.focus(name)
            if not self.wait_visible(name):
                raise AssertionError('native matrix handoff failed at ' + name)
        self.burst(names, self.args.rounds)
        if not self.wait_visible(names[-1]):
            raise AssertionError('rapid native focus did not settle on the final host')
        for name in reversed(names):
            self.focus(name)
            if not self.wait_visible(name):
                raise AssertionError('reverse native matrix handoff failed at ' + name)
            self.wait_shells(name, 4)
        if len(self.host_ids) != 8 or len({pid for record in self.panes.values() for pid in record['native_input_pids']}) != 32:
            raise AssertionError('incomplete native process/pane coverage')
        self.observe_companion_connections()
        return dict(passed=True, stopped_owner_blocked=blocked, distinct_native_hosts=8,
                    distinct_shell_panes=32, settled_round_trips=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--wm', type=Path, required=True)
    parser.add_argument('--shell', type=Path, required=True, help='Existing jsh for actual Ember canvas tasks')
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--rounds', type=int, default=3, choices=range(1, 9))
    parser.add_argument('--native-host-debug', action='store_true', help='Record real host submission/receipt order after display setup')
    parser.add_argument('--startup-barrier', type=Path, help='Optional private-file barrier before authority, after native pane input checks')
    parser.add_argument('--screen', default='4000x4800', choices=['4000x4800', '4800x4800'])
    parser.add_argument('--desktop-shell', action='store_true', help='Also exercise JWM desktop-shell load in the private display')
    args = parser.parse_args()
    if len(args.host) != 4 or {name for name, _ in args.host} != {'forge', 'anvil', 'ember', 'frost'}:
        parser.error('provide each of forge/anvil/ember/frost exactly once')
    if f'XDG_SESSION_ID={SESSION}'.encode() not in Path('/proc/self/environ').read_bytes().split(b'\0'):
        parser.error(f'launch with XDG_SESSION_ID={SESSION}')
    for attr in ('daemon', 'wm', 'shell'):
        setattr(args, attr, getattr(args, attr).resolve(strict=True))
    args.renderer, args.compositor, args.frame_sync = 'cairo', 'glx', True
    args.task_canvas, args.components = True, True
    session = MatrixSession(args)
    result = {'passed': False}
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try:
            session.capture('failed-matrix')
        except Exception as capture_error:
            result['failure_capture_error'] = str(capture_error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, screen=args.screen,
                      started_unix=session.started_unix, ended_unix=time.time(),
                      desktop_shell=args.desktop_shell, native_host_debug=args.native_host_debug,
                      binary_sha256=session.binary_hashes, native_host_ids=session.host_ids,
                      gui_processes={name: dict(pid=process.pid, window=session.windows.get(name), frontend=session.instances[name]) for name, process in session.host_processes.items()},
                      companion_id=session.companion_id, panes=session.panes,
                      companion_connections=session.companion_connections,
                      owner_resume=session.resume_observation,
                      focus_events=session.focus_events, samples=session.samples)
        (session.root / 'matrix-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'report': str(session.root / 'matrix-report.json'),
                      'error': result.get('error')}))
    raise SystemExit(0 if result['passed'] else 1)

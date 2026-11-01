#!/usr/bin/env python3
"""Real JWM default coordinator startup and default-enabled four-host handoff.

No explicit shared-mode flag, coordinator launch, fake host, grant or receipt.
Private HOME/XDG/DBus/Xvfb; screenshots and the real authority journal are sampled.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import time

from native_windows import NativeSession, host

parser = argparse.ArgumentParser(description=__doc__)
for name in ('daemon', 'wm', 'shell'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--host', type=host, action='append', required=True)
parser.add_argument('--restart', action='store_true', help='Also require body resumption after a WM restart; separate lifecycle probe')
args = parser.parse_args()
if {n for n, _ in args.host} != {'anvil', 'forge', 'ember', 'frost'} or len(args.host) != 4:
    parser.error('provide all four frontends exactly once')
args.renderer, args.compositor, args.frame_sync = 'cairo', 'glx', True
args.task_canvas, args.components, args.screen = True, True, '6000x1200'


class DefaultSession(NativeSession):
    def launch(self, name, argv, **kwargs):
        if name == 'jwm':
            self.env.pop('JWM_X11_FRAME_SYNC', None)
        return super().launch(name, argv, **kwargs)

    def journal(self):
        try:
            state = json.loads((self.root / 'state/jcompanion-eva/residence.json').read_text())
            return {k: state[k] for k in ('phase', 'possible_body', 'revoke_intent', 'target')}
        except FileNotFoundError:
            return None


session = DefaultSession(args)
session.env.pop('EVA_COMPANION_SOCKET', None)
session.env.pop('EVA_COMPANION_MODE', None)
session.env['JWM_COMPANION_DAEMON'] = str(session.binaries['jcompaniond'])
for app, _ in args.host:
    p = session.root / 'config' / app / 'config.toml'
    text = '\n'.join(line for line in p.read_text().splitlines()
                     if not line.startswith(('eva_companion_enabled', 'ascii_organism_enabled')))
    p.write_text(text.replace('shell = "/bin/sh"', 'shell = ' + json.dumps(str(session.binaries['jsh']))) + '\n')


def ipc(command):
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(5)
        peer.connect(str(session.root / 'jwm-ipc.sock'))
        key = 'query' if command.startswith('get_') else 'command'
        peer.sendall(json.dumps({key: command, 'args': {}}).encode() + b'\n')
        with peer.makefile('rb') as stream:
            reply = json.loads(stream.readline())
    if not reply.get('success'):
        raise RuntimeError(reply)
    return reply.get('data')


def daemon_pids():
    found = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            argv = (p / 'cmdline').read_bytes().split(b'\0')
            if argv[0] == str(session.binaries['jcompaniond']).encode():
                found.append(int(p.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return found


def wait_observer(timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data = ipc('get_companion_desktop_state')
            if data and data.get('desktop_observer_connected'):
                return data
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise AssertionError('default JWM observer did not connect')


result = dict(passed=False, scope=__doc__, restart_probe=args.restart)
try:
    session.start_display()
    result['desktop_before_hosts'] = wait_observer()
    result['daemon_pids_before'] = daemon_pids()
    if len(result['daemon_pids_before']) != 1:
        raise AssertionError('JWM did not start exactly one coordinator')
    identity = None
    for i, (app, _) in enumerate(args.host):
        session.launch_host(i)
        ipc('toggle_floating')
        session.command('xdotool', 'windowsize', session.windows[app], '1400', '1000')
        session.command('xdotool', 'windowmove', session.windows[app], str(10 + i * 1450), '40')
        if not session.wait_for(app, 15):
            raise AssertionError('default-enabled body did not settle on ' + app)
        current = session.journal()['possible_body']['companion_id']
        if identity is not None and identity != current:
            raise AssertionError('identity changed')
        identity = current
        session.capture('default-' + app)
    for app, _ in reversed(args.host[:-1]):
        session.focus(app)
        if not session.wait_for(app, 15):
            raise AssertionError('default return did not settle on ' + app)
        session.capture('returned-' + app)
    if args.restart:
        ipc('restart')
        result['desktop_after_restart'] = wait_observer()
        result['daemon_pids_after'] = daemon_pids()
        if result['daemon_pids_before'] != result['daemon_pids_after']:
            raise AssertionError('JWM restart replaced or duplicated the coordinator')
        owner = args.host[0][0]
        session.focus(owner)
        if not session.wait_for(owner, 15):
            raise AssertionError('body did not resume after JWM restart')
        if session.journal()['possible_body']['companion_id'] != identity:
            raise AssertionError('JWM restart changed companion identity')
        session.capture('after-jwm-restart')
    result.update(passed=True, companion_id=identity, settled_stops=7)
except Exception as error:
    result['error'] = str(error)
    try:
        session.capture('failed-default-startup')
    except Exception:
        pass
finally:
    result.update(binary_sha256=session.binary_hashes, samples=session.samples,
                  archive=str(session.root), ended_unix=time.time())
    report = session.root / 'default-startup-report.json'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    session.close()
    for pid in daemon_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
raise SystemExit(0 if result['passed'] else 1)

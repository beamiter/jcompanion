#!/usr/bin/env python3
"""Sample one real shared body across all four native X11 frontends.

No synthetic hosts, grants, task states, geometry or presentation receipts.
Raw screenshots and the real residence journal must agree at each settled stop.
This visual check does not certify continuous scanout, IME or audio behavior.
"""
import argparse
import json
import socket
from pathlib import Path
import time

from native_windows import NativeSession, host

parser = argparse.ArgumentParser(description=__doc__)
for name in ('daemon', 'wm', 'shell'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--host', type=host, action='append', required=True)
args = parser.parse_args()
if {name for name, _ in args.host} != {'anvil', 'forge', 'ember', 'frost'} or len(args.host) != 4:
    parser.error('provide all four native frontends exactly once')
args.renderer, args.compositor, args.frame_sync = 'cairo', 'glx', True
args.task_canvas, args.components, args.screen = True, True, '6000x1200'
session = NativeSession(args)
# A plain /bin/sh owns a full raw viewport and supplies no proven blank Block
# canvas. Use the actual reporting shell on GTK too; keep the absence oracle.
for app in ('anvil', 'forge'):
    config = session.root / 'config' / app / 'config.toml'
    config.write_text(config.read_text().replace('shell = "/bin/sh"',
        'shell = ' + json.dumps(str(session.binaries['jsh']))))

def floating(index):
    name = args.host[index][0]
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(5)
        peer.connect(str(session.root / 'jwm-ipc.sock'))
        peer.sendall(b'{"command":"toggle_floating","args":{}}\n')
        with peer.makefile('rb') as stream:
            if not json.loads(stream.readline()).get('success'):
                raise RuntimeError('private WM did not float the native window')
    session.command('xdotool','windowsize',session.windows[name],'1400','1000')
    session.command('xdotool','windowmove',session.windows[name],str(index*1450+10),'40')
result = dict(passed=False, scope=__doc__)
try:
    session.start_display()
    session.launch_host(0)
    floating(0)
    if session.capture('before-coordinator')['visible_body_windows']:
        raise AssertionError('body painted before coordinator authority')
    session.daemon = session.launch('daemon', [str(session.binaries['jcompaniond']), str(session.root / 'profile')])
    identity = None
    for index, (name, _) in enumerate(args.host):
        if index:
            session.launch_host(index)
            floating(index)
        if not session.wait_for(name, 12):
            raise AssertionError('native body did not settle on ' + name)
        current = session.journal()['possible_body']['companion_id']
        if identity is not None and current != identity:
            raise AssertionError('companion identity changed during native handoff')
        identity = current
        session.capture('settled-' + name)
    for name, _ in reversed(args.host[:-1]):
        session.focus(name)
        if not session.wait_for(name, 12):
            raise AssertionError('native return did not settle on ' + name)
        if session.journal()['possible_body']['companion_id'] != identity:
            raise AssertionError('return changed companion identity')
        session.capture('returned-' + name)
    result.update(passed=True, companion_id=identity, settled_stops=7)
except Exception as error:
    result['error'] = str(error)
    try:
        session.capture('failed-visual-handoff')
    except Exception as capture_error:
        result['capture_error'] = str(capture_error)
finally:
    result.update(binary_sha256=session.binary_hashes, samples=session.samples,
                  started_unix=session.started_unix, ended_unix=time.time())
    report = session.root / 'visual-handoff-report.json'
    report.write_text(json.dumps(result, indent=2) + '\n')
    session.close()
print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
raise SystemExit(0 if result['passed'] else 1)

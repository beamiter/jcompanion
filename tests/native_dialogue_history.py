#!/usr/bin/env python3
"""Native history viewer fixture: private Xvfb/metacity/DBus/HOME/profile, no provider.

Real mouse/keyboard input drives one frontend window. This driver process is
also the explicitly authorized desktop observer (EVA_COMPANION_DESKTOP_EXE),
so lock/unlock and observer loss are real coordinator inputs, not UI mocks.
Screenshots are evidence for review; they are not OCR assertions.
"""
from pathlib import Path
import argparse, hashlib, json, os, sys, time
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ipc_contracts
from native_windows import NativeSession, SESSION
from history_contracts import DesktopPeer

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', choices=['forge', 'anvil', 'ember', 'frost'], required=True)
parser.add_argument('--daemon', type=Path, required=True)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--commands', type=Path, required=True,
                    help='JSON lines appended by the operator; read incrementally')
parser.add_argument('--events', type=Path, required=True)
args = parser.parse_args()
if f'XDG_SESSION_ID={SESSION}'.encode() not in Path('/proc/self/environ').read_bytes().split(b'\0'):
    parser.error(f'launch with XDG_SESSION_ID={SESSION}')
ipc_contracts.SESSION = SESSION

session = NativeSession(SimpleNamespace(
    host=[(args.app, args.binary)], daemon=args.daemon, wm=None, shell=None,
    renderer='cairo', compositor='xrender', screen='1600x1200',
    frame_sync=False, task_canvas=False))
session.env['EVA_COMPANION_DESKTOP_EXE'] = os.path.realpath(sys.executable)
stages, observer = [], None


def emit(record):
    with args.events.open('a') as out:
        out.write(json.dumps(record, ensure_ascii=False) + '\n')


def turns():
    path = session.root / 'profile/dialogue-index.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [dict(turn_id=t['turn_id'], generated=t['entry']['generated'],
                 displayed=t['entry']['displayed'], route=t['entry']['route'],
                 project=(t['entry']['origin']['value'] or {}).get('project_id')
                 if t['entry']['origin']['kind'] == 'text' else None)
            for t in data['turns']]


def capture(label):
    path = session.root / (label + '.png')
    session.command('import', '-window', 'root', str(path))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


try:
    session.start_display()
    session.daemon = session.launch('daemon', [str(session.binaries['jcompaniond']),
                                               str(session.root / 'profile')])
    session.launch_host(0)
    time.sleep(1)
    emit(dict(ready=True, root=str(session.root), display=session.env['DISPLAY'],
              window=session.windows[args.app], capture=capture('initial')))
    offset = 0
    while True:
        data = args.commands.read_text() if args.commands.exists() else ''
        lines = data[offset:].split('\n')
        if len(lines) < 2:
            time.sleep(.1)
            continue
        offset += len(lines[0]) + 1
        command = json.loads(lines[0])
        with (session.root / 'driver-commands.jsonl').open('a') as log:
            log.write(json.dumps(command, ensure_ascii=False) + '\n')
        action = command['action']
        facts = {}
        if action == 'click':
            session.command('xdotool', 'mousemove', str(command['x']), str(command['y']), 'click', '1')
        elif action == 'type':
            session.command('xdotool', 'type', '--clearmodifiers', '--delay', '2', '--', command['text'])
        elif action == 'key':
            session.command('xdotool', 'key', '--clearmodifiers', command['key'])
        elif action == 'scroll':
            session.command('xdotool', 'mousemove', str(command['x']), str(command['y']),
                            'click', '--delay', '20', '--repeat', str(command.get('count', 5)),
                            command.get('button', '5'))
        elif action == 'lock':
            if observer is None:
                observer = DesktopPeer(session.root / 'eva.sock', 'native-desktop-observer')
            observer.lock(bool(command['locked']))
            facts['observer'] = 'locked' if command['locked'] else 'unlocked'
        elif action == 'observer_close':
            if observer is not None:
                observer.close()
            observer = None
            facts['observer'] = 'disconnected'
        elif action == 'end':
            break
        elif action != 'capture':
            raise ValueError(action)
        time.sleep(command.get('settle', .5))
        facts['turns'] = turns()
        shot = capture(command.get('label', 'current'))
        if 'label' in command:
            stages.append(dict(label=command['label'], note=command.get('note'), **facts, capture=shot))
        emit(dict(action=action, **facts, capture=shot))
finally:
    if observer is not None:
        observer.close()
    session.close()
    report = dict(schema=1, app=args.app, root=str(session.root),
                  binary_sha256=session.binary_hashes, stages=stages,
                  scope=(__doc__ or '').strip(),
                  review='Stage captures require visual review; this report records inputs and ledger facts only.')
    (session.root / 'history-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    emit(dict(done=True, report=str(session.root / 'history-report.json')))

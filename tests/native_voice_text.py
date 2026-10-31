#!/usr/bin/env python3
"""Native spoken-reply review fixture: private Xvfb/metacity/DBus/HOME/profile.

Real mouse/keyboard input drives one frontend window. This driver process is
also a protocol-level Eva (dialogue version 3): it records one voice turn with
the digest of its reply and answers the coordinator's text requests from
memory, like jwm-eva does. No audio device, provider or model is used.
Screenshots are evidence for review; memory rows are read from SQLite.
"""
from pathlib import Path
import argparse, hashlib, json, select, sqlite3, sys, time
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ipc_contracts
from native_windows import NativeSession, SESSION
from voice_text_contracts import VoicePeer

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', choices=['forge', 'anvil', 'ember', 'frost'], required=True)
parser.add_argument('--daemon', type=Path, required=True)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--commands', type=Path, required=True)
parser.add_argument('--events', type=Path, required=True)
args = parser.parse_args()
if f'XDG_SESSION_ID={SESSION}'.encode() not in Path('/proc/self/environ').read_bytes().split(b'\0'):
    parser.error(f'launch with XDG_SESSION_ID={SESSION}')
ipc_contracts.SESSION = SESSION

session = NativeSession(SimpleNamespace(
    host=[(args.app, args.binary)], daemon=args.daemon, wm=None, shell=None,
    renderer='cairo', compositor='xrender', screen='1600x1200',
    frame_sync=False, task_canvas=False))
stages, eva, retained, retention, answers = [], None, {}, False, []


def emit(record):
    with args.events.open('a') as out:
        out.write(json.dumps(record, ensure_ascii=False) + '\n')


def entries():
    path = session.root / 'profile/memory.sqlite'
    if not path.exists():
        return []
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        return [dict(zip(('scope', 'key', 'value', 'source'), row)) for row in
                db.execute('SELECT scope,key,value,source FROM entries ORDER BY id')]


def capture(label):
    path = session.root / (label + '.png')
    session.command('import', '-window', 'root', str(path))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def serve_eva():
    """Answer coordinator pushes from memory, exactly like the Eva retention."""
    global retention
    if eva is None:
        return
    queued = [r for r in eva.pending if r['type'].startswith('voice_text_')]
    for reply in queued:
        eva.pending.remove(reply)
    while queued or select.select([eva.socket], [], [], 0)[0]:
        push = queued.pop(0) if queued else eva.read(time.monotonic() + 2)
        kind = push['type']
        if kind == 'voice_text_retention':
            retention = push['enabled']
            if not retention:
                retained.clear()
        elif kind == 'voice_text_forget':
            count = len(retained)
            retained.clear()
            eva.answer(dict(type='voice_text_forgotten', request_id=push['request_id'], count=count))
        elif kind == 'voice_text_request':
            key = (push['voice_session_id'], push['turn_id'])
            if retention and key in retained:
                eva.answer(dict(type='voice_text_offer', request_id=push['request_id'],
                                voice_session_id=key[0], turn_id=key[1], reply=retained[key],
                                caption=None))
            else:
                eva.answer(dict(type='voice_text_unavailable', request_id=push['request_id'],
                                reason='not_retained' if retention else 'retention_paused'))
        else:
            continue
        answers.append(dict(push=kind, retained=len(retained)))


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
        serve_eva()
        data = args.commands.read_text() if args.commands.exists() else ''
        lines = data[offset:].split('\n')
        if len(lines) < 2:
            time.sleep(.05)
            continue
        offset += len(lines[0]) + 1
        command = json.loads(lines[0])
        with (session.root / 'driver-commands.jsonl').open('a') as log:
            log.write(json.dumps(command, ensure_ascii=False) + '\n')
        action = command['action']
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
        elif action == 'eva_turn':
            if eva is None:
                eva = VoicePeer(session.root / 'eva.sock', 'native-eva')
                deadline = time.monotonic() + 3
                while not retention and time.monotonic() < deadline:
                    push = eva.until('voice_text_retention')
                    retention = push['enabled']
            eva.spoken_turn(command['activation'], command['turn'], command['reply'])
            retained[(command['activation'], command['turn'])] = command['reply']
        elif action == 'end':
            break
        elif action != 'capture':
            raise ValueError(action)
        deadline = time.monotonic() + command.get('settle', .5)
        while time.monotonic() < deadline:
            serve_eva()
            time.sleep(.05)
        facts = dict(entries=entries(), retained=len(retained), retention=retention,
                     answers=list(answers))
        shot = capture(command.get('label', 'current'))
        if 'label' in command:
            stages.append(dict(label=command['label'], note=command.get('note'), **facts, capture=shot))
        emit(dict(action=action, **facts, capture=shot))
finally:
    if eva is not None:
        eva.close()
    session.close()
    report = dict(schema=1, app=args.app, root=str(session.root),
                  binary_sha256=session.binary_hashes, stages=stages,
                  scope=(__doc__ or '').strip(),
                  review='Stage captures require visual review; memory rows come from SQLite.')
    (session.root / 'voice-text-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    emit(dict(done=True, report=str(session.root / 'voice-text-report.json')))

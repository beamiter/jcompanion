#!/usr/bin/env python3
"""Operate isolated production windows; preserve raw captures and inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import socket
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_windows import NativeSession

parser = argparse.ArgumentParser()
parser.add_argument('--app', choices=['anvil','forge','ember','frost'], required=True)
parser.add_argument('--mode', choices=['block','chat'], default='block')
parser.add_argument('--binary', type=Path)
parser.add_argument('--scale', type=float, default=1.0)
parser.add_argument('--commands', type=Path, required=True)
parser.add_argument('--events', type=Path, required=True)
parser.add_argument('--daemon', type=Path, required=True)
parser.add_argument('--wm', type=Path, required=True)
parser.add_argument('--shell', type=Path, required=True)
args = parser.parse_args()

class VisualSession(NativeSession):
    def launch(self, name, argv, **kwargs):
        if name == args.app and '--mode' in argv:
            argv[argv.index('--mode') + 1] = args.mode
        return super().launch(name, argv, **kwargs)

session = VisualSession(SimpleNamespace(
    host=[(args.app, args.binary or Path.home() / '.local/bin' / args.app)],
    daemon=args.daemon, wm=args.wm,
    shell=args.shell, renderer='cairo', compositor='glx',
    frame_sync=True, task_canvas=False, screen='2200x1600', components=True))
config = session.root / 'config' / args.app / 'config.toml'
if args.app in ('anvil', 'forge'):
    config.write_text(config.read_text() + '\nterminal_mode = "' + args.mode + '"\nascii_organism_enabled = false\n')
else:
    config.write_text(config.read_text() + f'\nterminal_mode = "{args.mode}"\nui_scale = {args.scale}\ninitial_width = 1356\ninitial_height = 704\n')
# All modes use the same real, isolated shell with command-boundary reporting.
text = config.read_text().replace('shell = "/bin/sh"', 'shell = ' + json.dumps(str(session.binaries['jsh'])))
config.write_text(text)
session.env.update(WINIT_X11_SCALE_FACTOR='1', GDK_SCALE=str(int(args.scale)) if args.app in ('anvil','forge') else '1', GDK_DPI_SCALE='1')

fixture = session.root / 'visual-fixture.sh'
fixture.write_text("#!/bin/bash\nprintf 'VISUAL_READY — native fixture\\n'\nprintf '\\033[32mSuccess\\033[0m · \\033[31mFailure\\033[0m · \\033[36mUnknown\\033[0m\\n'\nprintf '中文界面 · selection / composer / history\\n'\nprintf 'ONCE\\n' >> " + shlex.quote(str(session.root / 'pty-once.txt')) + "\n")

history = session.root / 'history-fixture.sh'
history.write_text("for i in $(seq 1 100); do printf 'HISTORY_ROW_%03d\\n' \"$i\"; done\n")

def emit(record):
    with args.events.open('a') as out:
        out.write(json.dumps(record, ensure_ascii=False) + '\n')

def wm(command, arguments=None):
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(5)
        peer.connect(str(session.root / 'jwm-ipc.sock'))
        peer.sendall(json.dumps(dict(command=command, args=arguments or {})).encode() + b'\n')
        with peer.makefile('rb') as stream:
            reply=json.loads(stream.readline())
    if not reply.get('success'):
        raise RuntimeError(reply)

def capture(label):
    path=session.root / (label+'.png')
    session.command('import','-window',session.windows[args.app],str(path))
    root_path=session.root / (label+'-root.png')
    session.command('import','-window','root',str(root_path))
    geom=session.command('xdotool','getwindowgeometry','--shell',session.windows[args.app]).stdout
    return dict(root_path=str(root_path), root_sha256=hashlib.sha256(root_path.read_bytes()).hexdigest(), path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), geometry=geom,
                journal=session.journal())

stages=[]
try:
    session.start_display()
    session.daemon=session.launch('daemon',[str(session.binaries['jcompaniond']),str(session.root/'profile')])
    session.launch_host(0)
    wm('toggle_floating')
    wm('toggle_shortcut_passthrough')
    window=session.windows[args.app]
    session.command('xdotool','windowsize','--sync',window,'1672','1000')
    session.command('xdotool','windowmove',window,'20','30')
    session.command('xdotool','mousemove','2100','1500')
    time.sleep(2)
    emit(dict(ready=True, app=args.app, mode=args.mode, root=str(session.root), display=session.env['DISPLAY'],
              window=window, binary_sha256=session.binary_hashes, capture=capture('initial')))
    offset=0
    while True:
        data=args.commands.read_text() if args.commands.exists() else ''
        lines=data[offset:].split('\n')
        if len(lines)<2:
            time.sleep(.1)
            continue
        offset+=len(lines[0])+1
        command=json.loads(lines[0])
        action=command['action']
        with (session.root/'commands.jsonl').open('a') as log:
            log.write(json.dumps(command,ensure_ascii=False)+'\n')
        if action=='end':
            break
        if action in ('fixture', 'history'):
            source = fixture if action == 'fixture' else history
            session.command('xdotool','type','--clearmodifiers','--delay',str(command.get('delay_ms', 20)),'--','bash '+shlex.quote(str(source)))
            session.command('xdotool','key','--clearmodifiers','Return')
        elif action=='key':
            session.command('xdotool','key','--clearmodifiers',command['key'])
        elif action=='type':
            session.command('xdotool','type','--clearmodifiers','--delay','3','--',command['text'])
        elif action=='click':
            session.command('xdotool','mousemove','--window',window,str(command['x']),str(command['y']),'click','1')
        elif action=='move':
            session.command('xdotool','mousemove','--window',window,str(command['x']),str(command['y']))
        elif action=='drag':
            session.command('xdotool','mousemove','--window',window,str(command['x1']),str(command['y1']))
            time.sleep(.15)
            session.command('xdotool','mousedown','1')
            time.sleep(.15)
            session.command('xdotool','mousemove','--sync','--window',window,str(command['x2']),str(command['y2']))
            time.sleep(.2)
            session.command('xdotool','mouseup','1')
        elif action=='resize':
            session.command('xdotool','windowsize','--sync',window,str(command['width']),str(command['height']))
        elif action=='scroll':
            session.command('xdotool','mousemove','--window',window,str(command['x']),str(command['y']),
                            'click','--repeat',str(command.get('count',5)),'--delay','40',str(command.get('button',4)))
        elif action!='capture':
            raise ValueError(action)
        time.sleep(command.get('settle',.5))
        shot=capture(command.get('label','current'))
        if 'label' in command:
            stages.append(dict(label=command['label'],action=action,capture=shot))
        emit(dict(action=action,capture=shot))
finally:
    report=dict(pty_once=(session.root/'pty-once.txt').read_text() if (session.root/'pty-once.txt').exists() else None, app=args.app,mode=args.mode,scale=args.scale,root=str(session.root),binary_sha256=session.binary_hashes,stages=stages)
    (session.root/'visual-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    session.close()
    emit(dict(done=True,report=str(session.root/'visual-report.json')))

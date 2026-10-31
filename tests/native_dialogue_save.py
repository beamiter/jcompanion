#!/usr/bin/env python3
"""Native mouse/keyboard review fixture. Private display/profile, no provider."""
from pathlib import Path
import argparse, hashlib, json, os, sqlite3, sys, time
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_windows import NativeSession

parser = argparse.ArgumentParser()
parser.add_argument('--app', choices=['forge','anvil','ember','frost'], required=True)
parser.add_argument('--daemon', type=Path, required=True)
parser.add_argument('--binary', type=Path, required=True)
args = parser.parse_args()
session = NativeSession(SimpleNamespace(
    host=[(args.app, args.binary)],
    daemon=args.daemon,
    wm=None, shell=None, renderer='cairo', compositor='xrender', screen='1600x1200',
    frame_sync=False, task_canvas=False,
))
stages = []
def entries():
    path = session.root/'profile/memory.sqlite'
    if not path.exists(): return []
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        return [dict(zip(('scope','key','value','source'), row)) for row in db.execute('SELECT scope,key,value,source FROM entries ORDER BY id')]
def capture(label):
    path = session.root/(label+'.png')
    session.command('import','-window','root',str(path))
    return str(path)
try:
    session.start_display()
    session.daemon = session.launch('daemon', [str(session.binaries['jcompaniond']),str(session.root/'profile')])
    session.launch_host(0)
    time.sleep(1)
    print(json.dumps({'ready':True,'root':str(session.root),'display':session.env['DISPLAY'],
                      'window':session.windows[args.app], 'capture':capture('initial')}),flush=True)
    for line in sys.stdin:
        command = json.loads(line)
        with (session.root/'driver-commands.jsonl').open('a') as log:
            log.write(json.dumps(command)+'\n')
        action = command['action']
        if action == 'click':
            session.command('xdotool','mousemove',str(command['x']),str(command['y']),'click','1')
        elif action == 'type':
            session.command('xdotool','type','--clearmodifiers','--delay','2','--',command['text'])
        elif action == 'key':
            session.command('xdotool','key','--clearmodifiers',command['key'])
        elif action == 'scroll':
            session.command('xdotool','mousemove',str(command['x']),str(command['y']),
                            'click','--delay','20','--repeat',str(command.get('count',5)),command.get('button','5'))
        elif action == 'assert':
            observed = entries()
            if command['state'] == 'empty': assert not observed, observed
            else:
                assert len(observed) == 1, observed
                entry = observed[0]
                assert entry['scope'] == 'global', entry
                assert entry['source'] == entry['key'], entry
                assert entry['value'].startswith('User:\n'+command['prompt']+'\n\nEva:\n'), entry
                assert '离线陪伴模式' in entry['value'], entry
            stages.append({'label':command['label'],'state':command['state'],'entries':observed,'capture':capture(command['label'])})
        elif action == 'end':
            break
        elif action != 'capture':
            raise ValueError(action)
        time.sleep(.3)
        print(json.dumps({'action':action,'entries':entries(),'capture':capture(command.get('label','current'))}),flush=True)
finally:
    session.close()
    report = {'app':args.app,'root':str(session.root),'binary_sha256':session.binary_hashes,
              'stages':stages,'passed': [s['label'] for s in stages] == ['before-save','review-only','committed','deleted'],
              'scope':__doc__}
    (session.root/'review-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)

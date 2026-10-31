#!/usr/bin/env python3
"""Private native command-owned PTY close admission, not provider acceptance.

A controlled Python executable occupies the existing coding-CLI launch path. It
does not implement or call a provider, create model/task outcomes, or inject host,
residence or frame proof. Kernel PID/parent/session/TTY/foreground ownership are
observed directly. GUI commands and a private cloned Git project are real.
The Ember probe is UI exploration only and deliberately is not a passing gate.
No daily app/config/repository, microphone or paid API is used.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import time

from native_close_intent import CloseIntentSession
from native_window_use import stat
from native_windows import host


class CommandRoleSession(CloseIntentSession):
    def __init__(self,args):
        super().__init__(args)
        shutil.copy2(__file__,self.root/'harness'/Path(__file__).name)
        self.project=self.root/'project'
        subprocess.run(['git','clone','--quiet','--local','--no-hardlinks',
                        str(Path(__file__).resolve().parents[1]),str(self.project)],
                       check=True,capture_output=True)
        helper=self.root/'fixture-cli.py'
        helper.write_text('''import json,os,signal,sys
from pathlib import Path
root=Path(__file__).parent
if '--version' in sys.argv:
 print('controlled CLI fixture 0.0');sys.exit(0)
def finish(number,frame):
 try:
  with (root/'command-role-done.json').open('x') as output:json.dump({'pid':os.getpid(),'signal':number},output)
 except FileExistsError:pass
 sys.exit(128+number)
for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,finish)
(root/'command-role-started.json').write_text(json.dumps({'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'sid':os.getsid(0),'tty':os.ttyname(0),'argv':sys.argv}))
print('CONTROLLED COMMAND FIXTURE: no provider or model is running',flush=True)
while True:signal.pause()
''')
        commands=self.root/'command-bin';commands.mkdir(mode=0o700)
        for name in ['codex','opencode']:
            path=commands/name
            path.write_text('#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(helper))+' "$@"\n')
            path.chmod(0o700)
        self.env['PATH']=str(commands)+os.pathsep+self.env['PATH']
        if self.frontend=='ember':
            config=self.root/'config/ember/config.toml'
            value=config.read_text()
            # Only the private profile enables the existing task-start gate.
            # Its entire CLI PATH is controlled; no real provider is invoked.
            for name in ['ai_enabled','ai_share_command_context']:
                if re.search(r'^'+name+r'\s*=.*$',value,re.M):
                    value=re.sub(r'^'+name+r'\s*=.*$',name+' = true',value,flags=re.M)
                else:value+='\n'+name+' = true\n'
            value+='experimental_task_sidebar = true\npreferred_fix_provider = "opencode"\n'
            config.write_text(value)

    def launch(self,name,argv,**kwargs):
        if name in [self.source,self.target]:kwargs['cwd']=self.project
        return super().launch(name,argv,**kwargs)

    def palette(self,text):
        self.focus(self.source)
        self.key('ctrl+shift+p');time.sleep(.2)
        self.text(text);self.key('Return')

    def click_source(self,x,y):
        geometry=self.command('xdotool','getwindowgeometry','--shell',self.windows[self.source]).stdout
        origin=dict(line.split('=',1) for line in geometry.splitlines() if '=' in line)
        self.command('xdotool','mousemove',str(int(origin['X'])+x),str(int(origin['Y'])+y))
        time.sleep(.1)
        self.command('xdotool','mousedown','1');time.sleep(.1)
        self.command('xdotool','mouseup','1');time.sleep(.2)

    def launch_ember_command(self):
        self.focus(self.source);self.key('ctrl+alt+shift+t');time.sleep(.4)
        # Native clicks in the fixture's fixed 1344x1100 source window, using
        # the existing Tasks composer and isolated-worktree start action.
        self.click_source(1096,110)
        self.click_source(200,158);self.text('Controlled PTY role check')
        self.click_source(200,250)
        self.text('Run the local controlled CLI fixture only; verify terminal ownership and safe close. No model calls.')
        self.capture('actual-task-composer-before-create')
        self.click_source(98,479)
        path=self.root/'data/ember/agent-tasks/.creation-recovery/journal.json'
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:records=json.loads(path.read_text())['records']
            except (FileNotFoundError,json.JSONDecodeError):records=[]
            registered=[r for r in records if r['stage']=='registered']
            if registered:break
            if self.host_processes[self.source].poll() is not None:raise AssertionError('GUI exited during task creation')
            time.sleep(.1)
        else:raise AssertionError('native task composer did not create/register its real isolated worktree')
        if len(registered)!=1 or registered[0]['repository']!=str(self.project) or registered[0]['provider']!='open_code':
            raise AssertionError('native task registration is not the exact private project/provider')
        self.work_observation['actual_task_registration']=registered[0]
        time.sleep(.5)
        self.command('xdotool','mousemove','200','1015','click','--repeat','3','--delay','100','5')
        time.sleep(.4)
        self.capture('actual-task-before-controlled-cli-start')
        self.click_source(105,935)

    def owned_command(self):
        shell=self.wait_shells(self.source,1)[0]
        if self.frontend=='frost':self.palette('Open Codex in new tab')
        else:self.launch_ember_command()
        marker=self.wait_json(self.root/'command-role-started.json',15)
        state=stat(marker['pid']);self.work=state
        if not (state['pid']==state['pgid']==state['session_id']==state['foreground_pgid']):
            raise AssertionError('the actual command does not itself own its PTY foreground group')
        if state['ppid']!=self.host_processes[self.source].pid or marker['tty']==shell['tty']:
            raise AssertionError('command was not spawned by the actual source GUI on a distinct PTY')
        self.work_observation.update(command=state,origin_shell=shell,launch_marker=marker)
        self.record('actual-command-root-is-foreground',command=state,origin_shell=shell)
        self.capture('command-owned-pty-live')
        if self.args.case=='owned-command-background':
            self.key('ctrl+shift+Tab');time.sleep(.3)
            active=self.root/'command-background-shell.pid'
            self.send_command("printf '%s\\n' \"$$\" > "+shlex.quote(str(active)))
            deadline=time.monotonic()+8
            while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
            if not active.exists() or int(active.read_text())!=shell['pid']:
                raise AssertionError('native tab switch did not execute input in the exact original shell')
            shell_state=stat(shell['pid'])
            if shell_state['foreground_pgid']!=shell['pid'] or not self.work_alive():
                raise AssertionError('original active shell is not idle while the command remains live')
            self.work_observation['active_original_shell']=shell_state
            self.record('native-original-shell-tab-selected-with-command-still-live',
                        command=stat(self.work['pid']),active_shell=shell_state)
        self.refuse_busy_close()
        if self.args.case=='owned-command-tab':
            self.key('ctrl+shift+w');time.sleep(.3)
            self.assert_gui_stays(1,job=True)
            self.capture('command-tab-awaiting-user-confirmation')
            self.key('Escape');self.assert_gui_stays(.5,job=True)
            self.record('command-tab-close-cancelled-with-work-preserved',command=stat(self.work['pid']))
            self.key('ctrl+shift+w');time.sleep(.2)
            self.record('explicit-command-tab-termination-confirmed',command=stat(self.work['pid']))
            self.key('Return')
        else:os.kill(self.work['pid'],signal.SIGTERM)
        done=self.wait_json(self.root/'command-role-done.json')
        if done['pid']!=self.work['pid'] or (self.args.case!='owned-command-tab' and done['signal']!=int(signal.SIGTERM)):
            raise AssertionError('controlled command did not finish by exact fixture completion')
        self.work_observation['fixture_completion']=done
        self.assert_gui_stays(1)
        if self.args.case not in ['owned-command-background','owned-command-tab']:self.key('ctrl+shift+Tab')
        time.sleep(.2)
        self.key('Return')
        if not self.wait_visible(self.source):raise AssertionError('original shell/body did not recover after the command ended')
        token=self.journal()['possible_body'];counts=self.proof_counts(self.source)
        self.native_close();self.wait_source_exit(token,counts)
        return dict(passed=True,command_root_equals_foreground=True,ordinary_close_refused=True,
                    command_completion_keeps_gui=True,fresh_close_with_exact_retirement=True)

    def probe_ember(self):
        self.focus(self.source)
        self.key('ctrl+alt+shift+t')
        time.sleep(.5)
        self.capture('ember-task-launcher-probe')
        (self.root/'probe-ready.json').write_text(json.dumps(dict(display=self.env['DISPLAY'],
             source_window=self.windows[self.source],root=str(self.root),case=self.args.case)))
        print(json.dumps(dict(probe_ready=str(self.root/'probe-ready.json'))),flush=True)
        deadline=time.monotonic()+240
        while time.monotonic()<deadline and not (self.root/'finish-probe').exists():
            if self.host_processes[self.source].poll() is not None:break
            time.sleep(.1)
        self.capture('ember-task-launcher-probe-finished')
        return dict(passed=False,exploratory_probe=True,acceptance_claimed=False)

    def run(self):
        self.startup()
        return self.probe_ember() if self.args.case=='ember-probe' else self.owned_command()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon',type=Path,required=True)
    parser.add_argument('--host',type=host,action='append',required=True)
    parser.add_argument('--wm',type=Path,required=True)
    parser.add_argument('--shell',type=Path)
    parser.add_argument('--case',choices=['owned-command','owned-command-background','owned-command-tab','ember-probe'],required=True)
    parser.set_defaults(renderer='cairo',compositor='xrender',frame_sync=True,freeze_owner=False,
                        restart_daemon=False,desktop_shell=False,components=True,task_canvas=False)
    args=parser.parse_args()
    if len(args.host)!=1 or args.host[0][0] not in ['ember','frost']:parser.error('one Ember or Frost required')
    args.task_canvas=args.host[0][0]=='ember'
    if args.task_canvas and not args.shell:parser.error('Ember requires the real jsh')
    if args.case=='ember-probe' and not args.task_canvas:parser.error('probe requires Ember')
    if args.case=='owned-command-tab' and args.task_canvas:parser.error('tab confirmation requires Frost')
    args.daemon,args.wm=[p.resolve(strict=True) for p in [args.daemon,args.wm]]
    if args.shell:args.shell=args.shell.resolve(strict=True)
    session=CommandRoleSession(args);result=dict(passed=False)
    try:result=session.run()
    except Exception as error:
        result['error']=str(error)
        for name,process in session.host_processes.items():
            if process.poll() is not None and name in session.windows:
                session.closed_windows[name]=session.windows.pop(name)
        try:session.capture('failed-command-role')
        except Exception as error:result['failure_capture_error']=str(error)
    finally:
        session.close()
        result.update(schema=1,scope=__doc__,case=args.case,frontend=session.frontend,binary_sha256=session.binary_hashes,
             events=session.events,samples=session.samples,work_observation=session.work_observation,
             native_host_ids=session.host_ids,gui_processes={name:p.pid for name,p in session.host_processes.items()})
        report=session.root/'command-role-report.json';report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],report=str(report),error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

#!/usr/bin/env python3
"""Native delayed-close intent and embedded Vim9 acceptance in private X11.

Uses two actual GUI processes, actual native keys, real Vim bridge state written
by Vim itself, and original native retirement evidence. No host/task/frame proof
is injected. Native input arms a real shell trap; signals start its job only
after close publishes its clearance while JWM withholds scene feedback.
Fixture SIGTERM completes that work without a new close click.
This tests close intent, not normal job-control UX or physical scanout.
Embedded Vim9 is exercised in Ember; the delayed-close case also supports Frost.
Embedded Vim9 is distinct from an external alternate-screen Vim. No daily desktop,
microphone, model provider, performance or same-process multiwindow is exercised.
"""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import time

from native_lifecycle import XAuthority
from native_window_use import WindowUseSession, stat
from native_windows import host


class ClientData(C.Union):
    _fields_=[('b',C.c_char*20),('s',C.c_short*10),('l',C.c_long*5)]


class ClientMessage(C.Structure):
    _fields_=[('type',C.c_int),('serial',C.c_ulong),('send_event',C.c_int),
              ('display',C.c_void_p),('window',C.c_ulong),('message_type',C.c_ulong),
              ('format',C.c_int),('data',ClientData)]


class Event(C.Union):
    _fields_=[('client',ClientMessage),('pad',C.c_long*24)]


class CloseIntentSession(WindowUseSession):
    def __init__(self,args):
        super().__init__(args)
        shutil.copy2(__file__,self.root/'harness'/Path(__file__).name)

    def launch(self,name,argv,**kwargs):
        if name.startswith('frost') and 'RUST_LOG' in self.env:
            self.env['RUST_LOG']+=',terminal_close=debug'
        return super().launch(name,argv,**kwargs)

    def wait_shell_pid_marker(self,path,expected,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                value=path.read_text()
                if value.endswith('\n'):
                    if value.strip()!=str(expected):raise AssertionError('native input selected a different shell')
                    return
            except FileNotFoundError:pass
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('source GUI exited before native shell marker')
            time.sleep(.05)
        raise AssertionError('native shell PID marker missing')

    def native_close(self):
        window=self.windows[self.source]
        protocols=self.command('xprop','-id',window,'WM_PROTOCOLS').stdout
        if 'WM_DELETE_WINDOW' not in protocols:
            raise AssertionError('normal native close protocol missing')
        connection=XAuthority(self.env['DISPLAY'])
        try:
            event=Event()
            event.client.type=33
            event.client.display=connection.display
            event.client.window=int(window)
            event.client.message_type=connection.lib.XInternAtom(connection.display,b'WM_PROTOCOLS',0)
            event.client.format=32
            event.client.data.l[0]=connection.lib.XInternAtom(connection.display,b'WM_DELETE_WINDOW',0)
            connection.lib.XSendEvent.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_long,C.POINTER(Event)]
            connection.lib.XSendEvent.restype=C.c_int
            if not connection.lib.XSendEvent(connection.display,int(window),0,0,C.byref(event)):
                raise AssertionError('native WM_DELETE_WINDOW delivery failed')
            connection.lib.XSync(connection.display,0)
        finally:connection.close()
        self.record('native-window-close-requested',native_window=window)

    def wait_shell_foreground(self,pid,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('GUI exited before a fresh close request')
            s=stat(pid)
            if s['foreground_pgid']==pid:return s
            time.sleep(.05)
        raise AssertionError('native shell did not regain actual PTY foreground')

    def assert_gui_stays(self,seconds,job=False):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('pending close exited GUI while new foreground work was live' if job else
                                     'pending close auto-closed GUI after work ended without a fresh request')
            if job and not self.work_alive():
                raise AssertionError('window close terminated actual pending work')
            time.sleep(.05)

    def wait_source_exit(self,token,initial_counts):
        process=self.host_processes[self.source]
        deadline=time.monotonic()+15
        while process.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        if process.poll() is None:raise AssertionError('explicit healthy close did not finish')
        if process.returncode!=0:raise AssertionError('healthy close did not exit normally')
        self.closed_windows[self.source]=self.windows.pop(self.source)
        journal=json.loads((self.root/'profile/residence.json').read_text())
        counts=self.proof_counts(self.source)
        if token not in journal['retired_tokens'] or counts['accepted']<=initial_counts['accepted']:
            raise AssertionError('close lacks exact old-token retirement and actual new native scene feedback')
        self.record('explicit-close-completed-with-native-retirement',token=token,exit_code=process.returncode,proof_counts=counts)
        self.focus(self.target)
        if not self.wait_visible(self.target):raise AssertionError('surviving GUI did not acquire')

    def late_job(self,final_tab=False):
        shell=self.wait_shells(self.source,1)[0]
        shell_start=stat(shell['pid'])['start_ticks']
        job=self.root/'late_foreground_job.py'
        job.write_text('''import json,os,signal,sys,time
from pathlib import Path
root=Path(__file__).parent
shell=os.getsid(0)
signal.signal(signal.SIGTTOU,signal.SIG_IGN)
def finish(number,frame):
 try:
  with (root/'late-job-done.json').open('x') as output:json.dump({'pid':os.getpid(),'signal':number},output)
 except FileExistsError:pass
 try:os.tcsetpgrp(0,shell)
 except OSError:pass
 sys.exit(128+number)
for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,finish)
(root/'late-job-armed.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'tty':os.ttyname(0)}))
while not (root/'take-foreground').exists():time.sleep(.01)
os.tcsetpgrp(0,os.getpgrp())
(root/'late-job-started.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'tty':os.ttyname(0)}))
while True:signal.pause()
''')
        marker=self.root/'late-trap-ready.pid'
        self.send_command('trap '+shlex.quote('python3 '+shlex.quote(str(job)))+
                          ' USR1; printf \'%s\\n\' "$$" > '+shlex.quote(str(marker)))
        self.wait_shell_pid_marker(marker,shell['pid'])
        self.wait_shells(self.source,1)
        self.wait_shell_foreground(shell['pid'])
        time.sleep(.2)
        self.key('Return')
        if not self.wait_visible(self.source):raise AssertionError('idle source did not have an actual body before close')
        time.sleep(.2)
        token=self.journal()['possible_body'];counts=self.proof_counts(self.source)
        self.focus(self.source)
        os.kill(self.old_wm.pid,signal.SIGSTOP)
        deadline=time.monotonic()+2
        while '\tT' not in Path(f'/proc/{self.old_wm.pid}/status').read_text():
            if time.monotonic()>deadline:raise AssertionError('private WM stop not observed')
            time.sleep(.01)
        self.native_close()
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            now=self.proof_counts(self.source)
            if self.held(token) and now['published']>counts['published'] and now['accepted']==counts['accepted']:break
            time.sleep(.05)
        else:raise AssertionError('normal close did not reach a genuine published clearance with scene feedback withheld')
        self.record('native-close-clearance-pending',token=token,proof_counts=now)
        # No worker exists before close. A real trap starts it afterwards; INT
        # wakes the idle line editor so the pending USR1 trap can run. No host,
        # task or presentation messages are injected, and no shell is paused.
        if stat(shell['pid'])['start_ticks']!=shell_start:raise AssertionError('trap target shell changed')
        (self.root/'take-foreground').write_text('fixture trigger\n')
        os.kill(shell['pid'],signal.SIGUSR1)
        os.kill(shell['pid'],signal.SIGINT)
        started=self.wait_json(self.root/'late-job-started.json')
        self.register_work(started['pid'],shell)
        os.kill(self.old_wm.pid,signal.SIGCONT)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if not self.work_alive() or self.host_processes[self.source].poll() is not None:
                raise AssertionError('close killed work that entered the PTY during native withdrawal')
            journal=json.loads((self.root/'profile/residence.json').read_text())
            now=self.proof_counts(self.source)
            if token in journal['retired_tokens'] and now['accepted']>counts['accepted']:break
            time.sleep(.05)
        else:raise AssertionError('actual retirement did not complete while new foreground work kept GUI open')
        self.record('native-retirement-completed-with-new-work-alive',token=token,work=stat(self.work['pid']),proof_counts=now)
        self.assert_gui_stays(2,job=True)
        self.capture('late-work-window-kept-open')
        self.native_close()
        self.assert_gui_stays(1,job=True)
        self.record('repeated-close-with-new-work-refused',work=stat(self.work['pid']))
        if final_tab:
            # The user's per-process confirmation is a separate explicit
            # decision from the earlier refused whole-window close request.
            self.key('ctrl+shift+w')
            self.assert_gui_stays(1,job=True)
            self.capture('last-tab-awaiting-user-confirmation')
            self.record('last-tab-close-awaits-explicit-confirmation',work=stat(self.work['pid']))
            self.key('Return')
            self.record('native-user-confirmed-last-tab-close')
            self.wait_source_exit(token,counts)
            deadline=time.monotonic()+5
            while self.work_alive() and time.monotonic()<deadline:time.sleep(.05)
            if self.work_alive():raise AssertionError('confirmed final-tab close left the actual foreground job running')
            return dict(passed=True,real_foreground_work_during_native_withdrawal=True,
                        original_retirement_completed=True,explicit_final_tab_confirmation=True)
        os.kill(self.work['pid'],signal.SIGTERM)
        done=self.wait_json(self.root/'late-job-done.json')
        if done!=dict(pid=self.work['pid'],signal=int(signal.SIGTERM)):
            raise AssertionError('fixture completion did not end the exact real foreground job')
        self.work_observation['fixture_completion']=done
        self.wait_shell_foreground(shell['pid'])
        self.assert_gui_stays(2)
        self.record('new-work-finished-window-still-open',shell=stat(shell['pid']))
        marker=self.root/'paused-window-input.txt'
        self.queue_marker(self.source,marker)
        if not self.wait_marker(marker,5):raise AssertionError('kept-open GUI did not consume real terminal input')
        self.assert_gui_stays(1)
        self.record('kept-open-window-native-input-confirmed',marker=marker.name)
        self.native_close()
        self.wait_source_exit(token,counts)
        return dict(passed=True,real_foreground_work_during_native_withdrawal=True,
                    original_retirement_completed=True,fresh_close_required=True)

    def vim_marker_command(self,path,modified=False):
        items="'pid':getpid(), 'loaded':get(g:,'jterm_vim9_bridge_loaded',0), 'connected':get(g:,'jterm_vim9_connected',0)"
        if modified:items+=", 'modified':&modified"
        return 'call writefile([json_encode({'+items+'})], '+repr(str(path))+')'

    def vim_command(self,command):
        self.key('Escape');self.text(':'+command);self.key('Return')

    def embedded_vim(self,window_close):
        shell=self.wait_shells(self.source,1)[0]
        token=self.journal()['possible_body'];counts=self.proof_counts(self.source)
        original='EVA_EMBEDDED_ORIGINAL\n'
        target=self.root/'embedded-buffer.txt';target.write_text(original)
        started=self.root/'embedded-started.json'
        command=['vim','-Nu','NONE','-i','NONE','-n','-N',str(target),'-c',self.vim_marker_command(started)]
        self.send_command(shlex.join(command))
        marker=self.wait_json(started,15)
        if not marker['loaded']:raise AssertionError('native command opened external Vim instead of the embedded bridge')
        state=stat(marker['pid']);tty=os.readlink(f'/proc/{marker["pid"]}/fd/0')
        if (state['session_id']!=state['pid'] or tty==shell['tty']
                or state['ppid']!=self.host_processes[self.source].pid):
            raise AssertionError('embedded editor did not own a distinct real PTY')
        self.work=state
        self.work_observation.update(editor=state,editor_tty=tty,origin_shell=shell,initial_bridge=marker)
        time.sleep(1)
        connected=self.root/'embedded-connected.json'
        self.vim_command(self.vim_marker_command(connected))
        state=self.wait_json(connected,12)
        if not state['loaded'] or not state['connected'] or state['pid']!=self.work['pid']:
            raise AssertionError('actual embedded Vim bridge is not connected to the GUI')
        self.work_observation['connected_bridge']=state
        self.key('Escape');self.text('iEVA_NATIVE_UNSAVED_');self.key('Escape')
        modified=self.root/'embedded-modified.json'
        self.vim_command(self.vim_marker_command(modified,True))
        state=self.wait_json(modified)
        if not state['connected'] or state['modified']!=1 or target.read_text()!=original:
            raise AssertionError('embedded Vim lacks a genuine unsaved buffer')
        self.work_observation['modified_bridge']=state
        self.record('embedded-vim-connected-with-unsaved-buffer',editor=stat(self.work['pid']),bridge=state)
        self.capture('embedded-unsaved-buffer')
        if window_close:
            self.refuse_busy_close()
            if target.read_text()!=original:raise AssertionError('refused editor close wrote the unsaved buffer')
        self.vim_command('w')
        expected='EVA_NATIVE_UNSAVED_'+original
        deadline=time.monotonic()+8
        while target.read_text()!=expected and time.monotonic()<deadline:time.sleep(.05)
        if target.read_text()!=expected:raise AssertionError('embedded native :w did not save exact edited bytes')
        self.assert_gui_stays(1,job=True)
        self.record('embedded-native-write-kept-editor-and-window',saved_fixture_text=target.read_text())
        self.vim_command('q')
        if window_close:
            self.wait_source_exit(token,counts)
        else:
            deadline=time.monotonic()+8
            while self.work_alive() and time.monotonic()<deadline:time.sleep(.05)
            if self.work_alive():raise AssertionError('native :q did not finish the actual embedded editor')
            self.wait_shell_foreground(shell['pid'])
            self.assert_gui_stays(2)
            self.key('Return')
            if not self.wait_visible(self.source):raise AssertionError('original GUI did not recover its body after editor exit')
            self.native_close();self.wait_source_exit(token,counts)
        return dict(passed=True,embedded_vim_modified_buffer_preserved=True,exact_native_save=True,
                    explicit_editor_quit_completes_window_intent=window_close,
                    editor_quit_alone_keeps_gui_open=not window_close)

    def run(self):
        self.startup()
        if self.args.case=='late-job':return self.late_job()
        if self.args.case=='late-final-tab':return self.late_job(final_tab=True)
        return self.embedded_vim(window_close=self.args.case=='embedded-save')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon',type=Path,required=True)
    parser.add_argument('--host',type=host,action='append',required=True)
    parser.add_argument('--wm',type=Path,required=True)
    parser.add_argument('--shell',type=Path)
    parser.add_argument('--case',choices=['late-job','late-final-tab','embedded-save','embedded-editor-exit'],required=True)
    parser.set_defaults(renderer='cairo',compositor='xrender',frame_sync=True,freeze_owner=False,
                        restart_daemon=False,desktop_shell=False,components=True,task_canvas=True)
    args=parser.parse_args()
    if len(args.host)!=1 or args.host[0][0] not in ['ember','frost']:parser.error('one actual Ember or Frost binary required')
    args.task_canvas=args.host[0][0]=='ember'
    if args.task_canvas and not args.shell:parser.error('Ember requires a real jsh')
    if not args.task_canvas and args.case not in ['late-job','late-final-tab']:parser.error('embedded Vim9 cases currently exercise Ember')
    if args.task_canvas and args.case=='late-final-tab':parser.error('the final-tab confirmation case currently exercises Frost')
    args.daemon,args.wm=[p.resolve(strict=True) for p in [args.daemon,args.wm]]
    if args.shell:args.shell=args.shell.resolve(strict=True)
    session=CloseIntentSession(args);result=dict(passed=False)
    try:result=session.run()
    except Exception as error:
        result['error']=str(error)
        for name,process in session.host_processes.items():
            if process.poll() is not None and name in session.windows:
                session.closed_windows[name]=session.windows.pop(name)
        try:session.capture('failed-close-intent')
        except Exception as error:result['failure_capture_error']=str(error)
    finally:
        session.close()
        result.update(schema=1,scope=__doc__,case=args.case,frontend=session.frontend,binary_sha256=session.binary_hashes,
                      events=session.events,samples=session.samples,work_observation=session.work_observation,
                      native_host_ids=session.host_ids,gui_processes={name:p.pid for name,p in session.host_processes.items()})
        report=session.root/'close-intent-report.json';report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],report=str(report),error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

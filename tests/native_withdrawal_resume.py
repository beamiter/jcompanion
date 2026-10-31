#!/usr/bin/env python3
"""Private real GUI cancellation and same-host resumption in supported X11.

Only native close/key/pointer input and pauses of owned private actors are used.
No host, retirement, presentation, task or provider messages are injected.
Actual native scene receipts, old/new tokens, GUI/window/shell identities, IPC
socket inodes and real shell input are checked separately from sampled pixels.
This is not physical/continuous uniqueness, real voice/API or full acceptance.
The late-work case can stop the original private shell after the fixture takes
the PTY foreground, so a previously blocked shell read cannot steal its input.
That shell is resumed after work completion; this is controlled fixture setup,
not normal shell fg, orphan-descendant or shell-exit lifecycle acceptance.
"""
import argparse
import array
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import termios
import time

from native_close_intent import CloseIntentSession
from native_window_use import stat
from native_windows import host

class ResumeSession(CloseIntentSession):
    def __init__(self,args):
        super().__init__(args);shutil.copy2(__file__,self.root/'harness'/Path(__file__).name)
        self.resume_observation={}
    def server_connections(self):
        descriptors=set()
        for fd in Path(f'/proc/{self.daemon.pid}/fd').iterdir():
            try:value=fd.readlink().as_posix()
            except FileNotFoundError:continue
            if value.startswith('socket:['):descriptors.add(value[8:-1])
        return sorted(fields[6] for line in Path('/proc/net/unix').read_text().splitlines()[1:]
                      if len(fields:=line.split())>=8 and fields[6] in descriptors and fields[5]=='03'
                      and fields[-1]==str(self.root/'eva.sock'))
    def residence(self):return json.loads((self.root/'profile/residence.json').read_text())
    def wait_pid_marker(self,path,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:value=path.read_text()
            except FileNotFoundError:value=''
            # The shell opens/truncates before printf writes. An existing empty
            # file is not a completed native command or a failed PID assertion.
            if value:
                if not value.endswith('\n') or not value.strip().isdigit():raise AssertionError('invalid completed native shell PID marker')
                return int(value)
            if self.host_processes[self.source].poll() is not None:raise AssertionError('GUI exited before native PID marker completed')
            time.sleep(.02)
        raise AssertionError('native shell PID marker did not complete')
    def pty_input_state(self,pid):
        fd=os.open(f'/proc/{pid}/fd/0',os.O_RDONLY|os.O_NONBLOCK|os.O_NOCTTY)
        try:
            flags=termios.tcgetattr(fd);pending=array.array('i',[0]);fcntl.ioctl(fd,termios.FIONREAD,pending,True)
            return dict(canonical=bool(flags[3]&termios.ICANON),echo=bool(flags[3]&termios.ECHO),
                        pending_bytes=pending[0],foreground_pgid=stat(pid)['foreground_pgid'])
        finally:os.close(fd)
    def stop_actor(self,actor,label):
        if actor.poll() is not None:raise AssertionError('owned actor already exited')
        identity=stat(actor.pid);os.kill(actor.pid,signal.SIGSTOP)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            current=stat(actor.pid)
            if current['start_ticks']!=identity['start_ticks']:raise AssertionError('owned actor PID identity changed')
            if current['state']=='T':break
            time.sleep(.01)
        else:raise AssertionError('owned actor stop was not observed')
        self.record(label,actor=current)
    def native_keep_open(self):
        if self.args.case=='pre-revoke-button':
            x,y=self.button_point('keep')
            self.command('xdotool','mousemove','--window',self.windows[self.source],str(x),str(y),'click','1')
            self.record('native-pointer-keep-window-open',client_point=[x,y])
        elif self.args.case=='held-escape-blur':
            self.command('xdotool','keydown','Escape')
            self.record('native-cancelling-escape-held')
        else:
            # --clearmodifiers also releases held mouse buttons. In the stale
            # pointer test that would click Force before Escape even arrives.
            self.command('xdotool','key','Escape')
            self.record('native-escape-cancelled-window-exit')
    def button_point(self,which):
        # Coordinates are client-local, from the captured actual native backing
        # at the fixture's fixed 1344x1100 size. Each is checked visually in QA.
        if self.frontend=='ember':return (100,67 if which in ['keep','work-keep'] else 163)
        if which=='work-keep':return (920,76)
        return (480,575 if which=='keep' else 619)
    def late_work_cancel(self):
        shell=self.wait_shells(self.source,1)[0]
        shell_start=stat(shell['pid'])['start_ticks']
        script=self.root/'cancel_foreground_job.py'
        script.write_text('''import json,os,select,signal,sys,termios,time,tty
from pathlib import Path
root=Path(__file__).parent
shell=os.getsid(0)
original=None
signal.signal(signal.SIGTTOU,signal.SIG_IGN)
def finish(number,frame):
 if original is not None:termios.tcsetattr(0,termios.TCSANOW,original)
 os.tcsetpgrp(0,shell)
 (root/'cancel-work-done.json').write_text(json.dumps({'pid':os.getpid(),'signal':number}))
 sys.exit(128+number)
for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,finish)
(root/'cancel-work-armed.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp()}))
while not (root/'take-foreground').exists():time.sleep(.01)
os.tcsetpgrp(0,os.getpgrp())
original=termios.tcgetattr(0);tty.setraw(0)
(root/'cancel-work-started.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp()}))
received=b''
while True:
 if select.select([0],[],[],.1)[0]:
  received+=os.read(0,64)
  (root/'cancel-work-input.hex').write_text(received.hex())
''')
        marker=self.root/'late-trap-ready.pid'
        self.send_command('trap '+shlex.quote('python3 '+shlex.quote(str(script)))+
                          ' USR1; printf \'%s\\n\' "$$" > '+shlex.quote(str(marker)))
        self.wait_shell_pid_marker(marker,shell['pid'])
        self.wait_shells(self.source,1)
        time.sleep(.2)
        self.wait_shell_foreground(shell['pid']);self.key('Return')
        if not self.wait_visible(self.source):raise AssertionError('source lacks native body before late work')
        time.sleep(.2)
        original=self.journal()['possible_body'];before=self.proof_counts(self.source)
        connections=self.server_connections();window=self.windows[self.source];gui=self.host_processes[self.source]
        self.stop_actor(self.old_wm,'private-compositor-stopped-before-late-work')
        self.native_close()
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            counts=self.proof_counts(self.source)
            if self.held(original) and counts['published']>before['published'] and counts['accepted']==before['accepted']:break
            time.sleep(.05)
        else:raise AssertionError('late work lacks actual pending native clearance')
        if stat(shell['pid'])['start_ticks']!=shell_start:raise AssertionError('trap target shell changed')
        (self.root/'take-foreground').write_text('fixture trigger\n')
        os.kill(shell['pid'],signal.SIGUSR1)
        os.kill(shell['pid'],signal.SIGINT)
        started=self.wait_json(self.root/'cancel-work-started.json');self.register_work(started['pid'],shell)
        os.kill(self.old_wm.pid,signal.SIGCONT)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if original in self.residence()['retired_tokens'] and self.proof_counts(self.source)['accepted']>before['accepted']:break
            if not self.work_alive() or gui.poll() is not None:raise AssertionError('pending close killed actual new work')
            time.sleep(.05)
        else:raise AssertionError('late work did not retain exact native retirement')
        self.assert_gui_stays(2,job=True)
        self.capture('paused-close-before-explicit-keep');self.capture_native('paused-close-before-explicit-keep')
        if self.args.stop_fixture_shell:
            if stat(shell['pid'])['start_ticks']!=self.work_observation['shell_kernel_state']['start_ticks']:
                raise AssertionError('original shell identity changed')
            os.kill(shell['pid'],signal.SIGSTOP)
            self.record('original-private-shell-stopped-for-input-diagnosis',shell=stat(shell['pid']))
        self.record('foreground-before-escape',pty_input=self.pty_input_state(self.work['pid']),shell=stat(shell['pid']))
        self.key('Escape')
        deadline=time.monotonic()+5;received=self.root/'cancel-work-input.hex'
        while time.monotonic()<deadline and (not received.exists() or '1b' not in received.read_text()):time.sleep(.05)
        self.record('foreground-after-escape',pty_input=self.pty_input_state(self.work['pid']),shell=stat(shell['pid']),
                    received=received.read_text() if received.exists() else None)
        if not received.exists() or received.read_text()!='1b':raise AssertionError('paused close took Escape away from actual foreground work')
        x,y=self.button_point('work-keep')
        self.command('xdotool','mousemove','--window',window,str(x),str(y),'click','1')
        self.record('explicit-pointer-kept-window-open-with-work-alive',client_point=[x,y],received_work_bytes=received.read_text())
        self.assert_gui_stays(1,job=True)
        self.capture_native('after-explicit-keep-with-work-alive')
        os.kill(self.work['pid'],signal.SIGTERM)
        done=self.wait_json(self.root/'cancel-work-done.json')
        if self.args.stop_fixture_shell:os.kill(shell['pid'],signal.SIGCONT)
        if done!=dict(pid=self.work['pid'],signal=int(signal.SIGTERM)):raise AssertionError('wrong actual work completion')
        self.wait_shell_foreground(shell['pid']);self.assert_gui_stays(2);self.key('Return')
        if not self.wait_visible(self.source):raise AssertionError('kept-open host did not re-admit after actual work')
        resumed=self.journal()['possible_body'];after=self.proof_counts(self.source)
        if any(resumed[k]!=original[k] for k in ['companion_id','host_id','incarnation','surface_id']) or resumed['epoch']<=original['epoch']:
            raise AssertionError('late-work cancellation did not resume exact original host with a newer token')
        if self.server_connections()!=connections or self.windows[self.source]!=window or gui.poll() is not None:
            raise AssertionError('late-work cancellation replaced GUI/window/connection')
        marker=self.root/'resumed-window-shell.pid'
        self.send_command("printf '%s\\n' \"$$\" > "+shlex.quote(str(marker)))
        if self.wait_pid_marker(marker)!=shell['pid']:raise AssertionError('late-work resumed input missed original shell')
        self.key('Return')
        if not self.wait_visible(self.source):raise AssertionError('late-work resumed body lost eligibility')
        self.resume_observation=dict(original_token=original,resumed_token=resumed,original_gui_pid=gui.pid,native_window=window,
             original_shell=shell,confirmed_shell_pid=int(marker.read_text()),server_connection_inodes_before=connections,
             server_connection_inodes_after=self.server_connections(),proof_counts_before=before,proof_counts_after=after,
             actual_work=self.work_observation,fixture_completion=done,foreground_escape_bytes=received.read_text())
        self.record('late-work-ended-same-window-resumed',**self.resume_observation)
        current=self.journal()['possible_body'];counts=self.proof_counts(self.source)
        self.native_close();self.wait_source_exit(current,counts)
        return dict(passed=True,real_foreground_work_during_native_withdrawal=True,paused_escape_reaches_actual_work=True,
                    explicit_pointer_cancel=True,original_token_retired=True,same_host_resumed=True,native_shell_input=True,
                    fresh_close_with_new_retirement=True,original_shell_paused_for_fixture_stdin=self.args.stop_fixture_shell)
    def pre_revoke(self):
        original=self.journal()['possible_body'];before=self.proof_counts(self.source)
        process=self.host_processes[self.source];window=self.windows[self.source]
        shell=self.wait_shells(self.source,1)[0];connections=self.server_connections()
        if len(connections)!=2:raise AssertionError('expected two actual GUI IPC connections before cancellation')
        pending_scene=self.args.case=='pending-scene-escape'
        actor=self.old_wm if pending_scene else self.daemon
        self.stop_actor(actor,'private-compositor-stopped' if pending_scene else 'private-daemon-stopped-before-withdrawal')
        if self.args.case=='focused-control-escape':
            self.command('xdotool','mousemove','--window',window,'1180','466','click','1')
            # Exercise focus/ownership, not input throughput. Allow the private
            # software-rendered UI to apply each edit before the next key.
            self.command('xdotool','type','--clearmodifiers','--delay','35','--','EVA_CANCEL_FOCUS')
            time.sleep(.4)
            self.capture_native('local-eva-draft-before-native-close')
            self.record('local-eva-text-input-focused-before-native-close',local_draft='EVA_CANCEL_FOCUS',
                        draft_visual_qa_required=True,clipboard_accepted=False)
        self.native_close();time.sleep(.5)
        if pending_scene:
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                now=self.proof_counts(self.source)
                if self.held(original) and now['published']>before['published'] and now['accepted']==before['accepted']:break
                time.sleep(.05)
            else:raise AssertionError('close did not reach actual published clearance awaiting native scene')
            self.record('original-clearance-published-scene-pending',token=original,proof_counts=now)
        self.capture('close-progress-before-native-cancel');self.capture_native('close-progress-before-native-cancel')
        if self.journal()['possible_body']!=original or original in self.residence()['retired_tokens']:
            raise AssertionError('paused authority did not retain the exact original possible body')
        stale_force=self.args.case=='stale-force-release'
        if stale_force:
            x,y=self.button_point('force')
            self.command('xdotool','mousemove','--window',window,str(x),str(y),'mousedown','1')
            time.sleep(.2);self.record('native-force-button-held-in-old-close',client_point=[x,y])
        if self.args.case=='held-enter':
            self.command('xdotool','keydown','Return');self.record('dialog-enter-held')
        self.native_keep_open();self.assert_gui_stays(1)
        if self.args.case=='held-escape-blur':
            self.command('xdotool','keydown','Escape');self.focus(self.target);self.focus(self.source)
            self.command('xdotool','keydown','Escape');self.command('xdotool','keyup','Escape')
            self.record('cancelling-escape-repeat-blur-refocus-and-real-release')
        if self.args.case=='focused-control-escape':
            g=self.geometry(self.source)
            self.command('xdotool','mousemove','--window',window,str(g['WIDTH']//2),str(g['HEIGHT']-80),'click','1')
            self.record('native-terminal-focus-restored-after-captured-escape')
        self.capture('window-kept-open-authority-still-paused')
        if original in self.residence()['retired_tokens']:
            raise AssertionError('user cancellation fabricated old-token retirement')
        if self.args.case in ['reclose-before-resume','stale-force-release']:
            self.native_close();time.sleep(.5)
            if stale_force:
                self.capture_native('fresh-close-before-old-force-release')
                self.command('xdotool','mouseup','1');self.record('old-force-button-release-in-fresh-close')
            self.assert_gui_stays(2)
            if self.journal()['possible_body']!=original:raise AssertionError('fresh close manufactured retirement while authority paused')
            os.kill(actor.pid,signal.SIGCONT);self.wait_source_exit(original,before)
            return dict(passed=True,cancel_then_fresh_close_before_resume=True,old_force_release_ignored=stale_force,
                        original_token_retired_with_native_scene=True)
        restarted=self.args.case=='restart-during-cancel'
        if restarted:
            # Kill only the already-identified private daemon; the real GUI,
            # native window, shell and persistent residence journal stay put.
            self.daemon.kill();self.daemon.wait(3)
            self.daemon=self.launch('daemon-restarted',[str(self.binaries['jcompaniond']),str(self.root/'profile')])
            self.record('private-daemon-restarted-during-cancel',daemon_pid=self.daemon.pid)
        else:os.kill(actor.pid,signal.SIGCONT)
        marker=self.root/'resumed-window-shell.pid'
        if self.args.case=='held-enter':
            # Ember deliberately keeps the companion hidden while a physical
            # key remains held. Prove input ownership before requiring a new
            # visible body; waiting for that body first would deadlock this test.
            deadline=time.monotonic()+12
            while original not in self.residence()['retired_tokens'] and time.monotonic()<deadline:
                self.assert_gui_stays(.1)
            if original not in self.residence()['retired_tokens']:raise AssertionError('held dialog Enter prevented actual old-token retirement')
            self.text("printf '%s\\n' \"$$\" > "+shlex.quote(str(marker)))
            for _ in range(4):
                self.command('xdotool','keydown','Return');time.sleep(.15)
            if marker.exists():raise AssertionError('held dialog Enter escaped into the resumed shell')
            self.command('xdotool','keyup','Return');time.sleep(.2);self.key('Return')
            self.wait_pid_marker(marker)
            self.key('Return')
            self.record('held-dialog-enter-repeats-suppressed-fresh-press-admitted')
        try:visible=self.wait_visible(self.source)
        except Exception:
            if process.poll() is not None:raise AssertionError('GUI exited after native cancellation when withdrawal completed')
            raise
        if not visible:raise AssertionError('same kept-open GUI did not recover its actual body')
        resumed=self.journal()['possible_body'];after=self.proof_counts(self.source)
        if resumed['host_id']!=original['host_id'] or resumed['incarnation']!=original['incarnation'] or resumed['surface_id']!=original['surface_id']:
            raise AssertionError('cancellation replaced the actual host identity')
        if resumed['companion_id']!=original['companion_id'] or resumed['epoch']<=original['epoch']:
            raise AssertionError('resumption reused the old token or companion identity changed')
        if original not in self.residence()['retired_tokens'] or after['accepted']<before['accepted']+2:
            raise AssertionError('resumption lacks original retirement and actual clear/new-body native receipts')
        if process.pid!=self.host_processes[self.source].pid or process.poll() is not None or self.windows[self.source]!=window:
            raise AssertionError('resumption replaced or exited the real GUI/native window')
        if not restarted and self.server_connections()!=connections:raise AssertionError('ordinary cancellation forced an IPC reconnect')
        self.assert_gui_stays(1)
        if self.args.case!='held-enter':
            self.send_command("printf '%s\\n' \"$$\" > "+shlex.quote(str(marker)))
        if self.wait_pid_marker(marker)!=shell['pid']:
            raise AssertionError('resumed real window did not execute native input in its original shell')
        self.key('Return')
        if not self.wait_visible(self.source):raise AssertionError('resumed body did not remain eligible after native input')
        self.resume_observation=dict(original_token=original,resumed_token=resumed,original_gui_pid=process.pid,
             native_window=window,original_shell=shell,confirmed_shell_pid=int(marker.read_text()),
             server_connection_inodes_before=connections,server_connection_inodes_after=self.server_connections(),
             proof_counts_before=before,proof_counts_after=after)
        self.record('same-window-host-and-connection-resumed',**self.resume_observation)
        # A fresh close must retire the current body, not use the original ack.
        current=self.journal()['possible_body'];counts=self.proof_counts(self.source)
        self.native_close();self.wait_source_exit(current,counts)
        return dict(passed=True,explicit_cancel_before_retirement=True,same_gui_window_and_host=True,
                    same_connection=not restarted,daemon_restart=restarted,pending_native_scene=pending_scene,
                    local_draft_did_not_modify_shell=self.args.case=='focused-control-escape',
                    exact_old_token_retired=True,new_token_actually_presented=True,native_shell_input=True,fresh_close_with_new_retirement=True)
    def run(self):
        self.startup();self.focus(self.target)
        if not self.wait_visible(self.target):raise AssertionError('actual target did not establish its native host')
        self.focus(self.source)
        if not self.wait_visible(self.source):raise AssertionError('actual source did not recover before cancellation')
        return self.late_work_cancel() if self.args.case=='late-work-button' else self.pre_revoke()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--daemon',type=Path,required=True)
    parser.add_argument('--host',type=host,action='append',required=True);parser.add_argument('--wm',type=Path,required=True)
    parser.add_argument('--shell',type=Path);parser.add_argument('--case',choices=['pre-revoke-escape','pre-revoke-button',
        'pending-scene-escape','reclose-before-resume','stale-force-release','restart-during-cancel','held-enter','late-work-button',
        'held-escape-blur','focused-control-escape'],required=True)
    parser.add_argument('--stop-fixture-shell',action='store_true',help='diagnose only the controlled foreground fixture stdin race')
    parser.set_defaults(renderer='cairo',compositor='xrender',frame_sync=True,freeze_owner=False,restart_daemon=False,
                        desktop_shell=False,components=True,task_canvas=False)
    args=parser.parse_args()
    if len(args.host)!=1 or args.host[0][0] not in ['ember','frost']:parser.error('one Ember or Frost required')
    args.task_canvas=args.host[0][0]=='ember'
    if args.task_canvas and args.case=='focused-control-escape':parser.error('focused Eva control case currently exercises Frost')
    if args.task_canvas and not args.shell:parser.error('Ember requires the real jsh')
    args.daemon,args.wm=[p.resolve(strict=True) for p in [args.daemon,args.wm]]
    if args.shell:args.shell=args.shell.resolve(strict=True)
    session=ResumeSession(args);result=dict(passed=False)
    try:result=session.run()
    except Exception as error:
        result['error']=str(error)
        for name,process in session.host_processes.items():
            if process.poll() is not None and name in session.windows:session.closed_windows[name]=session.windows.pop(name)
        try:session.capture('failed-withdrawal-resume')
        except Exception as capture_error:result['failure_capture_error']=str(capture_error)
    finally:
        session.close();result.update(schema=1,scope=__doc__,case=args.case,frontend=session.frontend,
             binary_sha256=session.binary_hashes,events=session.events,samples=session.samples,
             native_backing_samples=session.native_samples,resume_observation=session.resume_observation,
             manual_visual_checks_required=['local-eva-draft'] if args.case=='focused-control-escape' else [],
             native_host_ids=session.host_ids,gui_processes={name:p.pid for name,p in session.host_processes.items()})
        report=session.root/'withdrawal-resume-report.json';report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],report=str(report),error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

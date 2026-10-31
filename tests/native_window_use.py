#!/usr/bin/env python3
"""Actual native busy-window, external Vim and mapped-resize acceptance.

Runs two real GUI processes in private Xvfb/DBus/home. Native keys start a held
foreground Python job or an actual external Vim with modified buffer. Ordinary
WM close must preserve GUI and work; native Ctrl+C or :wq ends work, then a fresh
empty shell prompt restores eligible canvas and a fresh close must obtain native
retirement. An idle foreground group alone is not safe-geometry evidence.
No fake host, task or frame proofs are used.
Mapped-resize exercises viewable windows without unmap/remap or host replacement.
External Vim is distinct from the embedded Vim9 IDE. Samples are not physical
scanout/continuous uniqueness, IME, API/audio or performance acceptance.
Requires xwininfo, xdotool, ImageMagick import, Python/Pillow, Xvfb, DBus and Vim.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import time

from native_surface_lifecycle import SurfaceSession
from native_matrix import MatrixSession
from native_windows import host


def stat(pid):
    raw=Path(f'/proc/{pid}/stat').read_text()
    fields=raw[raw.rfind(')')+2:].split()
    return dict(pid=pid,state=fields[0],ppid=int(fields[1]),pgid=int(fields[2]),
                session_id=int(fields[3]),tty_number=int(fields[4]),
                foreground_pgid=int(fields[5]),start_ticks=int(fields[19]))


class WindowUseSession(SurfaceSession):
    shells=MatrixSession.shells
    wait_shells=MatrixSession.wait_shells

    def __init__(self,args):
        super().__init__(args)
        shutil.copy2(__file__,self.root/'harness'/Path(__file__).name)
        self.work=None
        self.work_observation={}
        self.focused=None

    def focus(self,name):
        previous=self.focused
        super().focus(name)
        if previous!=name:
            time.sleep(.1)
            self.wm(command='toggle_shortcut_passthrough')
        self.focused=name

    def send_command(self,text):
        self.focus(self.source)
        g=self.geometry(self.source)
        self.command('xdotool','mousemove','--window',self.windows[self.source],
                     str(g['WIDTH']//2),str(g['HEIGHT']-80),'click','1')
        self.command('xdotool','type','--clearmodifiers','--delay','4','--',text)
        # Let native widgets/readline consume the typed batch before Return.
        # These are lifecycle checks, not an input throughput/latency claim.
        time.sleep(.2)
        self.command('xdotool','key','--clearmodifiers','Return')

    def key(self,chord):
        self.command('xdotool','key','--clearmodifiers',chord)

    def text(self,text):
        self.command('xdotool','type','--clearmodifiers','--delay','6','--',text)

    def wait_json(self,path,seconds=8):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('source GUI exited while starting native work')
            try:return json.loads(path.read_text())
            except (FileNotFoundError,json.JSONDecodeError):pass
            time.sleep(.05)
        raise AssertionError('actual native work marker did not arrive: '+path.name)

    def register_work(self,pid,shell):
        s=stat(pid)
        shell_state=stat(shell['pid'])
        if s['session_id']!=shell['pid'] or s['tty_number']!=shell_state['tty_number']:
            raise AssertionError('work does not belong to the actual native PTY shell')
        if shell_state['foreground_pgid']!=s['pgid'] or s['pgid']==shell['pid']:
            raise AssertionError('work is not the genuine non-shell foreground group')
        self.work=s
        self.work_observation.update(work=s,shell=shell,shell_kernel_state=shell_state)
        self.record('actual-pty-foreground-work-started',work=s,shell=shell_state)

    def work_alive(self):
        try:
            current=stat(self.work['pid'])
            return current['start_ticks']==self.work['start_ticks'] and current['state']!='Z'
        except FileNotFoundError:return False

    def refuse_busy_close(self):
        self.focus(self.source)
        protocols=self.command('xprop','-id',self.windows[self.source],'WM_PROTOCOLS').stdout
        if 'WM_DELETE_WINDOW' not in protocols:
            raise AssertionError('busy close must use the normal native close protocol')
        self.wm(command='kill_client')
        self.record('normal-wm-close-with-live-work',work=self.work)
        began=time.monotonic()
        while time.monotonic()-began<4:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('ordinary window close terminated the GUI while real foreground work was live')
            if not self.work_alive():
                raise AssertionError('ordinary window close terminated actual foreground work')
            self.capture('busy-close-preserves-window-and-work')
            time.sleep(.15)
        self.record('busy-close-refused-with-work-preserved',work=stat(self.work['pid']))

    def wait_idle(self,shell):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('refused close was left armed and later closed the GUI')
            if not self.work_alive() and stat(shell['pid'])['foreground_pgid']==shell['pid']:
                break
            time.sleep(.05)
        else:raise AssertionError('actual native shell did not regain foreground')
        # Refusing a close must not leave a deferred auto-close armed.
        until=time.monotonic()+1
        while time.monotonic()<until:
            if self.host_processes[self.source].poll() is not None:
                raise AssertionError('GUI auto-closed after work ended without a fresh close request')
            time.sleep(.05)
        self.record('work-ended-native-shell-idle',shell=stat(shell['pid']))
        self.focus(self.source)
        # An interrupt or TUI can leave the next native prompt on a shared
        # terminal row. That is deliberately ineligible for canvas padding.
        # Request a fresh empty prompt through the real shell; never infer a
        # safe drawable region solely from the foreground group being idle.
        self.key('Return')
        self.record('native-empty-prompt-requested-after-work')
        if not self.wait_visible(self.source):
            raise AssertionError('shared body did not recover after a fresh native prompt')

    def busy(self,background=False):
        shell=self.wait_shells(self.source,1)[0]
        job=self.root/'held_native_job.py'
        started=self.root/'held-job-started.json'
        done=self.root/'held-job-done.json'
        job.write_text('''import json,os,signal,sys
from pathlib import Path
root=Path(__file__).parent
def finish(number,frame):
 (root/'held-job-done.json').write_text(json.dumps({'signal':number,'pid':os.getpid()}))
 sys.exit(128+number)
for number in [signal.SIGINT,signal.SIGTERM,signal.SIGHUP]:signal.signal(number,finish)
(root/'held-job-started.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'tty':os.ttyname(0)}))
while True:signal.pause()
''')
        self.send_command('python3 '+shlex.quote(str(job)))
        marker=self.wait_json(started)
        self.register_work(marker['pid'],shell)
        if background:
            self.key('ctrl+shift+e')
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                panes=self.shells(self.source)
                ready=[p for p in panes if p['pid']!=shell['pid']]
                if len(panes)==2 and len({p['tty'] for p in panes})==2 and ready and (
                        self.shell_programs[self.frontend]!=str(self.binaries.get('jsh')) or ready[0]['editor_raw']):break
                time.sleep(.05)
            else:raise AssertionError('new idle pane did not become ready beside the real busy job')
            active=self.root/'active-idle-pane.pid'
            self.text("printf '%s\\n' \"$$\" > "+shlex.quote(str(active)))
            self.key('Return')
            deadline=time.monotonic()+8
            while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
            if not active.exists():raise AssertionError('new pane did not execute native input')
            active_pid=int(active.read_text())
            if active_pid==shell['pid'] or active_pid not in {p['pid'] for p in panes}:
                raise AssertionError('foreground work was not moved to an inactive pane')
            if stat(active_pid)['foreground_pgid']!=active_pid or not self.work_alive():
                raise AssertionError('new active pane is not idle while the original work runs')
            self.work_observation['active_idle_pane']=stat(active_pid)
            self.work_observation['native_panes']=panes
            self.record('busy-job-in-inactive-pane',active_idle_pane=stat(active_pid),work=stat(self.work['pid']))
        self.refuse_busy_close()
        self.focus(self.source)
        if background:self.key('ctrl+alt+Left')
        self.key('ctrl+c')
        ended=self.wait_json(done)
        if ended!={'signal':int(signal.SIGINT),'pid':self.work['pid']}:
            raise AssertionError('native Ctrl+C did not interrupt the exact held foreground process')
        self.work_observation['native_interrupt']=ended
        self.wait_idle(shell)
        result=self.healthy_close()
        result.update(busy_close_refused=True,native_ctrl_c_exact_foreground=True,
                      fresh_close_required=True,inactive_pane_work=background)
        return result

    def external_vim(self):
        shell=self.wait_shells(self.source,1)[0]
        original='EVA_ORIGINAL\n'
        target=self.root/'vim-buffer.txt'
        target.write_text(original)
        started=self.root/'vim-started.json'
        modified=self.root/'vim-modified.json'
        def write_marker(path,items):
            return 'call writefile([json_encode({'+items+'})], '+repr(str(path))+')'
        start_command=write_marker(started,"'pid':getpid(), 'modified':&modified")
        argv=['env','VIMINIT=','EXINIT=','/usr/bin/vim','-Nu','NONE','-i','NONE','-n','-N',str(target),'-c',start_command]
        self.send_command(shlex.join(argv))
        marker=self.wait_json(started)
        self.register_work(marker['pid'],shell)
        # A real modified Vim buffer, not a process-name or an injected job fact.
        self.key('Escape')
        self.text('iEVA_NATIVE_UNSAVED_')
        self.key('Escape')
        self.text(':'+write_marker(modified,"'pid':getpid(), 'modified':&modified"))
        self.key('Return')
        evidence=self.wait_json(modified)
        if evidence!={'pid':self.work['pid'],'modified':1} or target.read_text()!=original:
            raise AssertionError('actual Vim did not hold an unsaved native buffer')
        self.work_observation['modified_buffer']=evidence
        self.refuse_busy_close()
        if target.read_text()!=original:
            raise AssertionError('refused close unexpectedly wrote the Vim buffer')
        self.focus(self.source)
        self.key('Escape')
        self.text(':wq')
        self.key('Return')
        self.wait_idle(shell)
        if target.read_text()!='EVA_NATIVE_UNSAVED_'+original:
            raise AssertionError('native Vim :wq did not preserve the exact edited text')
        self.work_observation['saved_fixture_text']=target.read_text()
        result=self.healthy_close()
        result.update(external_vim_modified_buffer_preserved=True,native_save_and_exit=True,fresh_close_required=True)
        return result

    def mapped_resize(self):
        window=self.windows[self.source]
        for width,height in [(1184,940),(1304,1060),(1344,1100)]:
            if self.map_state(self.source)!='IsViewable':
                raise AssertionError('mapped resize started with an unmapped window')
            self.command('xdotool','windowsize','--sync',window,str(width),str(height))
            g=self.geometry(self.source)
            if (g['WIDTH'],g['HEIGHT'])!=(width,height) or self.map_state(self.source)!='IsViewable':
                raise AssertionError('actual mapped native size did not match the request')
            if not self.wait_visible(self.source):
                raise AssertionError('visible body did not converge after mapped resize')
            self.record('mapped-size-visible-body',native_window=window,geometry=g)
        self.focus(self.target)
        if not self.wait_visible(self.target):raise AssertionError('mapped resize broke transfer')
        self.focus(self.source)
        if not self.wait_visible(self.source):raise AssertionError('mapped resize broke reverse transfer')
        marker=self.root/'mapped-resize-input.txt'
        self.queue_marker(self.source,marker)
        if not self.wait_marker(marker,5):raise AssertionError('mapped resize broke native terminal input')
        return dict(passed=True,mapped_sizes=3,body_converged=True,native_round_trip=True,native_input=True)

    def run(self):
        self.startup()
        if self.args.case=='busy':return self.busy()
        if self.args.case=='busy-background':return self.busy(background=True)
        if self.args.case=='external-vim':return self.external_vim()
        return self.mapped_resize()

    def close(self):
        if self.work and self.work_alive():
            # The child is our fixture and its start identity was observed from
            # the private native PTY. Cleanup is not a successful test action.
            try:os.kill(self.work['pid'],signal.SIGTERM)
            except ProcessLookupError:pass
        super().close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon',type=Path,required=True)
    parser.add_argument('--host',type=host,action='append',required=True)
    parser.add_argument('--wm',type=Path,required=True)
    parser.add_argument('--shell',type=Path)
    parser.add_argument('--case',choices=['busy','busy-background','external-vim','mapped-resize'],required=True)
    parser.set_defaults(renderer='cairo',compositor='xrender',frame_sync=True,freeze_owner=False,
                        restart_daemon=False,desktop_shell=False,components=True,task_canvas=False)
    args=parser.parse_args()
    if len(args.host)!=1 or args.host[0][0] not in ['ember','frost']:
        parser.error('one Ember or Frost binary is required; two actual GUIs are opened')
    args.task_canvas=args.host[0][0]=='ember'
    if args.task_canvas and not args.shell:parser.error('Ember requires a real jsh')
    args.daemon,args.wm=args.daemon.resolve(strict=True),args.wm.resolve(strict=True)
    if args.shell:args.shell=args.shell.resolve(strict=True)
    session=WindowUseSession(args)
    result=dict(passed=False)
    try:result=session.run()
    except Exception as error:
        result['error']=str(error)
        try:session.capture('failed-window-use')
        except Exception as error:result['failure_capture_error']=str(error)
    finally:
        session.close()
        result.update(schema=1,scope=__doc__,case=args.case,frontend=session.frontend,
                      binary_sha256=session.binary_hashes,events=session.events,samples=session.samples,
                      work_observation=session.work_observation,native_host_ids=session.host_ids,
                      gui_processes={name:p.pid for name,p in session.host_processes.items()})
        report=session.root/'window-use-report.json'
        report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],report=str(report),error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

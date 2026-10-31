#!/usr/bin/env python3
"""Real GTK pre-exec window close under private strace syscall delays.

The native window must retain unresolved launch ownership until its actual
child is drained. No host, task, geometry, frame or retirement messages are
injected. Trace delays are functional stress, not performance measurements.
Final fixture cleanup never supplies acceptance proof.
"""
from pathlib import Path
import argparse,json,os,re,select,shutil,signal,sys,time
from native_gtk_jobs import GtkJobsSession
from native_windows import NativeSession,sha,host
from native_window_use import stat

class PendingSession(GtkJobsSession):
    def __init__(self,args):
        super().__init__(args)
        source=Path('/usr/bin/strace');target=self.root/'bin/strace';shutil.copy2(source,target);target.chmod(0o700)
        self.exec_delay_seconds = 3 if args.case.startswith('split-') else 8
        self.instrumentation=dict(strace_sha256=sha(target),exec_delay_seconds=self.exec_delay_seconds,signal_delay_seconds=8,scope='Delay real execve and kill syscalls of owned private GUI tracees; no fake host/task/frame or retirement messages.')
        if args.case.startswith('split-'):
            # The pending pane is the subject of this stress case. Avoid
            # inheriting the developer's Conda startup integration or Git cwd
            # before the original, real jsh has reached its first prompt.
            removed = [key for key in self.env if key.startswith('CONDA_') or key in ('_CE_CONDA', '_CE_M')]
            for key in removed:
                self.env.pop(key)
            self.env['PATH'] = str(self.root / 'bin') + ':/usr/local/bin:/usr/bin:/bin'
            self.instrumentation['initial_shell_isolation'] = dict(
                removed_environment_names=sorted(removed), private_cwd=str(self.root),
                shell='byte-identical real jsh; supported safe-mode PATH entry')
        self.tool=target;self.pending_observation={};self.launch_settles_before=0
        shutil.copy2(__file__,self.root/'harness/native_gtk_launch.py')
    def launch(self,name,argv,**kwargs):
        if name in getattr(self,'instances',{}):
            if self.args.case.startswith('split-'):
                kwargs['cwd'] = str(self.root)
            self.env['RUST_LOG']+=',eva_native_host=debug,forge::terminal=debug,anvil::terminal::vte=debug'
            argv=[str(self.tool),'-D','-f','--kill-on-exit','-qq','-ttt','-o',str(self.root/(name+'-strace.log')),
                '-e','trace=execve,clone,clone3,fork,vfork,wait4,waitid,kill,pidfd_send_signal',
                '-e',f'inject=execve:delay_enter={self.exec_delay_seconds}s','-e','inject=kill,pidfd_send_signal:delay_enter=8s',argv[0],'--safe-mode']
            return super(GtkJobsSession,self).launch(name,argv,**kwargs)
        return super().launch(name,argv,**kwargs)
    def launch_host(self,index,instance=None):
        return NativeSession.launch_host(self,index,instance)
    def pending(self):
        path=self.root/(self.source+'-strace.log');deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            text=path.read_text(errors='replace') if path.exists() else ''
            for match in re.finditer(r'(?m)^(\d+)\s+[^\n]*execve\("'+re.escape(str(self.root/'bin/sh'))+r'"[^\n]*',text):
                pid=int(match[1]);s=stat(pid)
                if s['state'] not in ['Z','X','x'] and os.readlink(f'/proc/{pid}/exe')!=str(self.binaries['jsh']):
                    self.pending_observation=dict(child=s,executable_before_exec=os.readlink(f'/proc/{pid}/exe'),
                            tty=os.readlink(f'/proc/{pid}/fd/0'),gui_pid=self.host_processes[self.source].pid,
                            trace_line=match[0],source_launch_callback_seen=(self.launch_callbacks() > self.launch_settles_before))
                    assert s['ppid']==self.host_processes[self.source].pid
                    return pid
            time.sleep(.02)
        raise AssertionError('no real shell exec held before native launch completion')
    def launch_callbacks(self):
        text=(self.root/(self.source+'.log')).read_text(errors='replace')
        return text.count('spawn_async: ')+text.count('GTK VTE launch settled')
    def confirm(self):
        time.sleep(.25);self.capture('pending-native-close-confirmation');self.key('Tab');self.key('Return')
    def live(self,pid):
        try:return stat(pid)['state'] not in ['Z','X','x']
        except FileNotFoundError:return False
    def run(self):
        self.start_display();self.launch_host(0,self.source)
        assert sha(Path(f'/proc/{self.host_processes[self.source].pid}/exe'))==self.binary_hashes[self.frontend]
        original=None
        split=self.args.case.startswith('split-')
        if split:
            original=self.wait_shells(self.source,1)[0];self.wait_editor_idle(original)
            self.launch_settles_before=self.launch_callbacks()
            self.key('ctrl+shift+e')
        pid=self.pending();assert not self.pending_observation['source_launch_callback_seen']
        self.capture('real-native-spawn-pending-before-close')
        if self.args.case=='window':self.native_close()
        elif self.args.case=='split-tab-confirm':
            self.key('ctrl+shift+p');time.sleep(.3);self.text('> Close tab');time.sleep(.3);self.key('Return')
        else:self.key('ctrl+shift+w')
        if self.args.case=='split-pane-cancel':
            time.sleep(.25);self.capture('pending-pane-confirmation-cancelled');self.key('Escape')
            deadline=time.monotonic()+20
            while self.launch_callbacks()<=self.launch_settles_before and time.monotonic()<deadline:time.sleep(.05)
            assert self.launch_callbacks()>self.launch_settles_before,'cancelled pane launch never completed'
            assert self.live(pid) and self.live(original['pid']),'cancellation signaled the pending pane or original shell'
            self.wait_editor_idle(self.process(pid))
            marker=self.root/'cancelled-pending-pane-input.pid'
            self.text("printf '%s\\n' \"$$\" > "+str(marker));self.key('Return')
            assert int(self.wait_line(marker))==pid,'cancelled pending pane lost its actual native input'
            self.record('pending-pane-cancel-kept-real-child-and-native-input',original=original,pending_child=stat(pid))
            self.native_close();self.confirm()
        else:
            self.confirm()
            if self.args.case=='split-pane-confirm':
                # Close the window while its removed pane still owns unresolved launch
                # work. The empty/mutated model must not lose that retained ticket.
                assert self.host_processes[self.source].poll() is None and self.live(original['pid'])
                self.capture('removed-pending-pane-before-window-close');self.native_close();self.confirm()
        self.record('confirmed-native-close-with-real-unresolved-child',**self.pending_observation)
        deadline=time.monotonic()+70
        while self.host_processes[self.source].poll() is None and time.monotonic()<deadline:time.sleep(.05)
        process=self.host_processes[self.source]
        callback_seen=self.launch_callbacks()>self.launch_settles_before
        try:child=stat(pid)
        except FileNotFoundError:child=None
        live=self.live(pid)
        self.pending_observation.update(gui_exit_code=process.poll(),callback_seen_before_gui_exit=callback_seen,child_after_exit=child,child_live_after_gui_exit=live,original_shell=original)
        if process.poll() is not None:self.closed_windows[self.source]=self.windows.pop(self.source)
        self.capture('after-pending-native-close')
        assert process.poll()==0,'GUI did not finish pending-launch close'
        assert callback_seen,'GUI exited before observing the actual native spawn outcome'
        assert not live,'GUI exit left a live child from its unresolved launch'
        assert original is None or not self.live(original['pid']),'GUI exit left its original shell alive'
        return dict(passed=True,native_spawn_settled_before_gui_exit=True,pending_close_case=self.args.case)
    def close(self):
        # Explicit final cleanup of our trace controller; EXITKILL applies only to
        # its own tracees. This is never an acceptance/retirement proof.
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if os.readlink(proc/'exe')!=str(self.tool):continue
                fd=os.pidfd_open(int(proc.name))
                try:signal.pidfd_send_signal(fd,signal.SIGTERM)
                finally:os.close(fd)
            except (FileNotFoundError,ProcessLookupError,PermissionError):pass
        super().close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for option in ['daemon','wm','shell']:p.add_argument('--'+option,type=Path,required=True)
    p.add_argument('--host',type=host,action='append',required=True)
    p.add_argument('--case',choices=['window','last-tab','split-pane-cancel','split-pane-confirm','split-tab-confirm'],default='window')
    p.set_defaults(backend='vte',renderer='cairo',compositor='xrender',frame_sync=True,freeze_owner=False,restart_daemon=False,desktop_shell=False,components=True,task_canvas=False)
    a=p.parse_args()
    if len(a.host)!=1 or a.host[0][0] not in ['forge','anvil']:p.error('one actual Forge or Anvil binary required')
    for option in ['daemon','wm','shell']:setattr(a,option,getattr(a,option).resolve(strict=True))
    s=PendingSession(a);r=dict(passed=False)
    try:r=s.run()
    except Exception as error:r['error']=str(error)
    finally:
        s.close();r.update(schema=1,scope='Private native pre-exec launch/close race under strace syscall delays; no coordinator/body proof or performance claim.',frontend=a.host[0][0],case=a.case,binary_sha256=s.binary_hashes,instrumentation=s.instrumentation,pending_observation=s.pending_observation,events=s.events,samples=s.samples)
        report=s.root/'pending-launch-report.json';report.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(dict(passed=r['passed'],error=r.get('error'),report=str(report))))
    raise SystemExit(0 if r['passed'] else 1)


if __name__ == "__main__":
    main()

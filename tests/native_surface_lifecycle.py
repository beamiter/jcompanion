#!/usr/bin/env python3
"""Real native window remap/resize/healthy-close/crash acceptance in private X11.

Two actual GUI processes, native publication/scene feedback and shell input are
used. Private JWM floating rules preserve sizes across remap, so a ConfigureNotify
cannot accidentally rescue the same-size case. No host/proof/retirement protocol
messages are injected. A crash is expected to remain recovery_blocked without a
trusted destruction certificate; that negative case is not automatic recovery.
PNG sampling/default-Cat classification is not physical or continuous uniqueness,
latency, IME, voice/API or full proposal acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import time

from native_lifecycle import LifecycleSession
from native_windows import host


class SurfaceSession(LifecycleSession):
    def __init__(self, args):
        super().__init__(args)
        shutil.copy2(__file__, self.root/'harness'/Path(__file__).name)
        self.closed_windows = {}

    def geometry(self, name):
        output = self.command('xdotool','getwindowgeometry','--shell',self.windows[name]).stdout
        return {k:int(v) for k,v in (line.split('=',1) for line in output.splitlines() if '=' in line)
                if k in ['X','Y','WIDTH','HEIGHT']}

    def map_state(self, name):
        output = self.command('xwininfo','-id',self.windows[name]).stdout
        match = re.search(r'Map State:\s*(\S+)', output)
        if not match:
            raise AssertionError('actual native map state unavailable')
        return match[1]

    def managed(self, name):
        pid = self.host_processes[name].pid
        return next((w for w in self.wm(query='get_windows') if w.get('pid')==pid), None)

    def startup(self, start_coordinator=True):
        self.start_display()
        self.old_wm = next(p for p in self.processes if p.args[0]==str(self.binaries['jwm']))
        for config in (self.root/'config/jwm').glob('config_*.toml'):
            text = config.read_text()
            rule = dict(name=self.frontend.capitalize(),class_='',instance='',tags=0,is_floating=True,monitor=-1)
            rule['class'] = rule.pop('class_')
            inline = ', '.join(k+' = '+json.dumps(v) for k,v in rule.items())
            text, count = re.subn(r'(?m)^rules = \[\]$', 'rules = [{'+inline+'}]', text, count=1)
            if count!=1:
                raise AssertionError('unexpected private WM fixture rules')
            config.write_text(text)
        self.wm(command='reload_config')
        self.launch_host(0,self.source)
        self.launch_host(0,self.target)
        for index,name in enumerate([self.source,self.target]):
            self.command('xdotool','windowsize','--sync',self.windows[name],'1344','1100')
            self.command('xdotool','windowmove','--sync',self.windows[name],str(20+index*1500),'50')
            if not self.managed(name)['is_floating']:
                raise AssertionError('native fixture window is not floating')
        self.focus(self.source)
        if self.capture('before-authority')['visible_body_windows']:
            raise AssertionError('body appeared before coordinator authority')
        if not start_coordinator:
            self.record('two-native-windows-without-coordinator', geometries={n:self.geometry(n) for n in self.windows})
            return
        self.daemon = self.launch('daemon',[str(self.binaries['jcompaniond']),str(self.root/'profile')])
        if not self.wait_visible(self.source):
            raise AssertionError('actual source body did not become active')
        self.record('two-native-windows-active', geometries={n:self.geometry(n) for n in self.windows})

    def pending_clearance(self):
        token = self.journal()['possible_body']
        before = self.proof_counts(self.source)
        os.kill(self.old_wm.pid,signal.SIGSTOP)
        deadline = time.monotonic()+2
        while True:
            state = next(line for line in Path(f'/proc/{self.old_wm.pid}/status').read_text().splitlines() if line.startswith('State:'))
            if '\tT' in state:
                break
            if time.monotonic()>=deadline:
                raise AssertionError('private WM stop was not observed')
            time.sleep(.01)
        self.direct_focus(self.target)
        deadline = time.monotonic()+12
        while time.monotonic()<deadline:
            counts = self.proof_counts(self.source)
            if self.held(token) and counts['published']>before['published'] and counts['accepted']==before['accepted']:
                text = (self.root/(self.source+'.log')).read_text(errors='replace')
                published = re.findall(r'producer frame published[^\n]*counter=(\d+)[^\n]*pass=(\d+)',text)
                if not published:
                    raise AssertionError('native pending counter was not recorded')
                counter,serial = map(int,published[-1])
                self.record('clearance-published-scene-pending',token=token,proof_counts=counts,kernel_state=state,
                            pending_counter=counter,original_pass=serial)
                return token,counts,counter
            time.sleep(.05)
        raise AssertionError('no genuine published clearance waiting for scene feedback')

    def remap(self, resize=False):
        original = self.geometry(self.source)
        token,counts,counter = self.pending_clearance()
        self.command('xdotool','windowunmap','--sync',self.windows[self.source])
        if self.map_state(self.source)!='IsUnMapped':
            raise AssertionError('actual source window did not unmap')
        self.record('source-unmapped',native_map_state=self.map_state(self.source),geometry=self.geometry(self.source))
        if not self.held(token) or self.proof_counts(self.source)['accepted']!=counts['accepted']:
            raise AssertionError('unmap fabricated a native clearance/retirement receipt')
        os.kill(self.old_wm.pid,signal.SIGCONT)
        deadline = time.monotonic()+5
        while self.managed(self.source) is not None:
            if time.monotonic()>=deadline:
                raise AssertionError('private WM did not remove unmapped client')
            time.sleep(.05)
        if resize:
            self.command('xdotool','windowsize','--sync',self.windows[self.source],
                         str(original['WIDTH']-120),str(original['HEIGHT']-100))
            smaller = self.geometry(self.source)
            if smaller['WIDTH']>=original['WIDTH'] or smaller['HEIGHT']>=original['HEIGHT']:
                raise AssertionError('actual native backing did not resize while unmapped')
            self.record('unmapped-native-backing-resized',geometry=smaller)
            self.command('xdotool','windowsize','--sync',self.windows[self.source],
                         str(original['WIDTH']),str(original['HEIGHT']))
            self.record('unmapped-native-backing-restored',geometry=self.geometry(self.source))
        self.command('xdotool','windowmap','--sync',self.windows[self.source])
        deadline = time.monotonic()+5
        while self.managed(self.source) is None:
            if time.monotonic()>=deadline:
                raise AssertionError('private WM did not remanage the same native client')
            time.sleep(.05)
        current = self.geometry(self.source)
        if (current['WIDTH'],current['HEIGHT'])!=(original['WIDTH'],original['HEIGHT']):
            raise AssertionError('same-size remap was accidentally rescued by a different native size')
        self.record('same-window-remapped',native_map_state=self.map_state(self.source),
                    original_geometry=original,current_geometry=current,proof_counts=self.proof_counts(self.source))
        self.assert_old_counter_rejected(counter)
        self.focus(self.target)
        if not self.wait_visible(self.target):
            raise AssertionError('native transfer did not recover after same-window remap')
        self.focus(self.source)
        if not self.wait_visible(self.source):
            raise AssertionError('same GUI host could not reacquire after remap')
        self.assert_old_counter_rejected(counter)
        marker = self.root/'surface-remap-input.txt'
        self.queue_marker(self.source,marker)
        if not self.wait_marker(marker,5):
            raise AssertionError('real GUI shell input failed after remap')
        return dict(passed=True,same_native_window_and_gui_host=True,native_round_trip=True,
                    unmap_did_not_prove_retirement=True,resize_aba_exercised=resize)

    def assert_old_counter_rejected(self, counter):
        text = (self.root/(self.source+'.log')).read_text(errors='replace')
        if re.search(r'compositor scene receipt accepted counter='+str(counter)+r'\b',text):
            raise AssertionError('pre-unmap native scene receipt was accepted across a mapping generation')

    def healthy_close(self):
        token = self.journal()['possible_body']
        counts = self.proof_counts(self.source)
        protocols = self.command('xprop','-id',self.windows[self.source],'WM_PROTOCOLS').stdout
        if 'WM_DELETE_WINDOW' not in protocols:
            raise AssertionError('normal WM close protocol is missing')
        self.focus(self.source)
        self.wm(command='kill_client')
        self.record('healthy-close-requested',token=token,proof_counts=counts)
        process = self.host_processes[self.source]
        deadline = time.monotonic()+15
        while process.poll() is None and time.monotonic()<deadline:
            time.sleep(.1)
        if process.poll() is None:
            raise AssertionError('healthy native close did not finish')
        if process.returncode!=0:
            raise AssertionError('normal close did not exit cleanly')
        self.closed_windows[self.source] = self.windows.pop(self.source)
        state = json.loads((self.root/'profile/residence.json').read_text())
        if token not in state['retired_tokens'] or self.proof_counts(self.source)['accepted']<=counts['accepted']:
            raise AssertionError('healthy close lacks exact retirement and a new native scene receipt')
        self.record('healthy-source-closed',exit_code=process.returncode,retired_token=token,
                    proof_counts=self.proof_counts(self.source))
        self.focus(self.target)
        if not self.wait_visible(self.target):
            raise AssertionError('surviving native GUI did not acquire after healthy close')
        return dict(passed=True,healthy_close_with_exact_native_retirement=True,surviving_gui_acquired=True)

    def crash(self):
        token = self.journal()['possible_body']
        process = self.host_processes[self.source]
        os.kill(process.pid,signal.SIGKILL)
        process.wait(5)
        self.closed_windows[self.source] = self.windows.pop(self.source)
        self.focus(self.target)
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            state = self.journal()
            if state['phase']=='recovery_blocked':
                break
            time.sleep(.05)
        else:
            raise AssertionError('crashed owner did not enter explicit blocked recovery')
        began = time.monotonic()
        while time.monotonic()-began<4:
            sample = self.capture('crashed-owner-exact-token-held')
            if sample['journal']['possible_body']!=token or sample['journal']['phase']!='recovery_blocked':
                raise AssertionError('crash/time/absence granted a replacement body')
            time.sleep(.15)
        self.record('crashed-native-owner-stays-blocked',killed_pid=process.pid,exact_token=token)
        return dict(passed=True,expected_negative=True,exact_crashed_owner_retained=True,
                    automatic_recovery=False,reason='trusted_surface_destruction_certificate_unavailable')

    def run(self):
        self.startup()
        if self.args.case in ['remap','resize']:
            return self.remap(self.args.case=='resize')
        if self.args.case=='close':
            return self.healthy_close()
        return self.crash()


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon',type=Path,required=True)
    parser.add_argument('--host',type=host,action='append',required=True)
    parser.add_argument('--wm',type=Path,required=True)
    parser.add_argument('--shell',type=Path)
    parser.add_argument('--case',choices=['remap','resize','close','crash'],required=True)
    parser.set_defaults(renderer='cairo',compositor='xrender',frame_sync=True,freeze_owner=False,
                        restart_daemon=False,desktop_shell=False,components=True,task_canvas=False)
    args = parser.parse_args()
    if len(args.host)!=1 or args.host[0][0] not in ['ember','frost']:
        parser.error('one Ember or Frost binary is required; two native processes are launched')
    args.task_canvas = args.host[0][0]=='ember'
    if args.task_canvas and not args.shell:
        parser.error('Ember requires the real jsh task fixture')
    args.daemon,args.wm = args.daemon.resolve(strict=True),args.wm.resolve(strict=True)
    if args.shell: args.shell = args.shell.resolve(strict=True)
    session = SurfaceSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        try: session.capture('failed-surface-lifecycle')
        except Exception as error: result['failure_capture_error']=str(error)
    finally:
        session.close()
        result.update(schema=1,scope=__doc__,case=args.case,frontend=session.frontend,
                      binary_sha256=session.binary_hashes,native_host_ids=session.host_ids,
                      gui_processes={name:p.pid for name,p in session.host_processes.items()},
                      native_windows=session.windows,closed_windows=session.closed_windows,
                      events=session.events,samples=session.samples)
        report = session.root/'surface-report.json'
        report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],report=str(report),error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

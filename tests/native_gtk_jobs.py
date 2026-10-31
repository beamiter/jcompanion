#!/usr/bin/env python3
"""Native Forge/Anvil shell-job lifecycle in explicit Block or VTE backends.

Same real commands and kernel PID/session checks as native_shell_jobs. GTK's
running-work confirmation is cancelled through native Escape; final retirement
requires actual GDK presentation receipts and the exact durable token. No host,
task, frame or retirement proofs are injected. Not physical/continuous or API
acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import termios
import time
from PIL import Image

from native_shell_jobs import ShellJobsSession
from native_windows import host, sha, cat_components, cat_ink


class GtkJobsSession(ShellJobsSession):
    def __init__(self, args):
        super().__init__(args)
        # The general matrix deliberately uses /bin/sh for GTK terminals.
        # These shell-lifecycle cases need the same real integrated jsh that
        # their WGPU equivalents use, with its native prompt evidence.
        for name, _ in args.host:
            path = self.root / 'config' / name / 'config.toml'
            path.write_text(path.read_text().replace('shell = "/bin/sh"',
                'shell = ' + json.dumps(str(self.binaries['jsh']))) + '\ntheme = "solarized-dark"\n')
            self.shell_programs[name] = str(self.binaries['jsh'])
        # Solarized's UI success/cyan colors are outside the fixed mint Cat
        # mask. The default theme's Completed badge overlaps that mask; the
        # body detector itself, thresholds and authored Cat palette stay fixed.
        self.env['NO_COLOR'] = '1'
        shutil.copy2(__file__, self.root / 'harness' / Path(__file__).name)
        self.confirmed_close = False
        self.body_regions = {}
        self.backend_observation = {}
        if args.backend == 'vte':
            # --mode vte is a public Block alias in both applications. Their
            # supported safe mode retains the conventional VTE backend and
            # chooses "sh" from PATH. Resolve that name to the byte-identical
            # real jsh in this private fixture, not a shim or fake shell.
            (self.root / 'bin/sh').symlink_to(self.binaries['jsh'])
            self.env['PATH'] = str(self.root / 'bin') + os.pathsep + self.env['PATH']

    def capture(self, label):
        """Full-size Cat samples in fixed 1344x1100 GTK windows.

        GTK's Completed badge shares the Cat's mint palette. Retain all palette
        groups as diagnostics, but a positive full Cat must span 48x48 pixels.
        Once a body was seen, even a small mint residue in that exact region
        still counts as visible. This is not a compact/resized-body oracle.
        """
        path = self.root / f'{len(self.samples):03}-{label}.png'
        self.command('import', '-window', 'root', str(path))
        counts, components, all_groups, geometries = {}, {}, {}, {}
        with Image.open(path) as source:
            pixels = source.convert('RGB')
            for name, window in self.windows.items():
                geometry = self.command('xdotool', 'getwindowgeometry', '--shell', window)
                info = dict(line.split('=', 1) for line in geometry.stdout.splitlines() if '=' in line)
                x, y, w, h = (int(info[key]) for key in ('X', 'Y', 'WIDTH', 'HEIGHT'))
                geometries[name] = dict(x=x, y=y, width=w, height=h)
                area = pixels.crop((x, y, x+w, y+h))
                counts[name] = sum(n for n, color in area.getcolors(w*h) if cat_ink(color))
                groups = cat_components(area)
                all_groups[name] = groups
                full = [g for g in groups if g['bounds'][2]-g['bounds'][0] >= 48 and
                        g['bounds'][3]-g['bounds'][1] >= 48]
                if full:
                    self.body_regions[name] = [g['bounds'] for g in full]
                else:
                    for box in self.body_regions.get(name, []):
                        region = area.crop(box)
                        ink = sum(n for n, color in region.getcolors(region.width*region.height)
                                  if cat_ink(color))
                        if ink >= 20:
                            full.append(dict(bounds=box, ink_pixels_approx=ink, retained_region_residue=True))
                components[name] = full
        bodies = [name for name, groups in components.items() if groups]
        sample = dict(label=label, elapsed_ms=round((time.monotonic()-self.started)*1000, 2),
                      screenshot=path.name, sha256=sha(path), palette_pixels=counts,
                      visible_body_windows=bodies, window_geometries=geometries,
                      body_components=components, all_palette_components=all_groups,
                      body_oracle='full-size mint Cat >=48x48, plus retained-region residue >=20 pixels',
                      journal=self.journal())
        self.samples.append(sample)
        assert len(bodies) <= 1, 'sample contains full-size Cat/residue in multiple native windows'
        assert all(len(groups) <= 1 for groups in components.values()), 'sample contains multiple full-size Cat groups'
        return sample

    def launch(self, name, argv, **kwargs):
        if name in getattr(self, 'instances', {}):
            argv = ([argv[0], '--safe-mode'] if self.args.backend == 'vte' else list(argv))
            if self.args.backend == 'block':
                assert argv[argv.index('--mode') + 1] == 'block'
            self.env['RUST_LOG'] += ',eva_native_host=debug'
        return super().launch(name, argv, **kwargs)

    def launch_host(self, index, instance=None):
        super().launch_host(index, instance)
        name = instance or self.args.host[index][0]
        process = self.host_processes[name]
        shell = self.wait_shells(name, 1)[0]
        threads = []
        for entry in sorted(Path(f'/proc/{process.pid}/task').iterdir()):
            try:
                threads.append(dict(tid=int(entry.name), comm=(entry / 'comm').read_text().strip()))
            except FileNotFoundError:
                pass
        # This application-owned reaper is installed only for the conventional
        # VTE pane. Block's shadow VTE never owns/watches the actual shell.
        reapers = [t for t in threads if t['comm'] == 'vte-session-rea']
        assert bool(reapers) == (self.args.backend == 'vte'), 'actual kernel backend differs from requested case'
        assert sha(Path(f"/proc/{shell['pid']}/exe")) == self.binary_hashes['jsh'], 'actual pane did not run the recorded jsh bytes'
        observed = dict(requested=self.args.backend, actual='vte' if reapers else 'block',
                        launch_argv=process.args, gui_pid=process.pid, threads=threads,
                        vte_session_reapers=reapers, shell=shell, shell_sha256=self.binary_hashes['jsh'],
                        entry_point='--safe-mode; private PATH sh -> real jsh' if reapers else '--mode block',
                        proof_scope='Kernel thread identity from the application-owned conventional VTE reaper, plus actual shell executable bytes; not CLI-label inference.')
        self.backend_observation[name] = observed
        self.record('actual-native-backend-observed', **observed)

    def wait_editor_idle(self, shell):
        """Observe the real jsh prompt after a command's completion marker.

        File output precedes the next line editor. Require its raw/no-echo PTY
        mode to remain stable before another native diagnostic command, rather
        than typing directly on the first marker write.
        """
        deadline, stable = time.monotonic() + 8, None
        while time.monotonic() < deadline:
            current = self.process(shell['pid'])
            fd = os.open(f"/proc/{shell['pid']}/fd/0", os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC)
            try:
                flags = termios.tcgetattr(fd)[3]
            finally:
                os.close(fd)
            raw = not flags & (termios.ICANON | termios.ECHO)
            if raw and current['foreground_pgid'] == shell['pid']:
                stable = stable or time.monotonic()
                if time.monotonic() - stable >= .25:
                    self.record('real-jsh-editor-ready-after-command', shell=current, local_flags=flags,
                                raw_no_echo=True, stable_observation_ms=250)
                    return
            else:
                stable = None
            time.sleep(.05)
        raise AssertionError('original jsh did not return to a stable real line editor')

    def start_job(self, shell):
        super().start_job(shell)
        self.wait_editor_idle(shell)

    def wait_command_editor(self, shell):
        self.wait_editor_idle(shell)

    def guard(self):
        super().guard()
        self.key('Escape')
        self.assert_gui_stays(.25, job=True)
        if self.args.case == 'background-inactive':
            self.key('ctrl+Page_Up')
            time.sleep(.2)

    def proof_counts(self, name):
        log = (self.root / (name + '.log')).read_text(errors='replace')
        count = log.count('GTK presentation receipt')
        return dict(published=count, accepted=count)

    def wait_source_exit(self, token, initial_counts):
        if self.args.case != 'parent-exit' and not self.confirmed_close:
            time.sleep(.5)
            journal = self.journal()
            if (self.host_processes[self.source].poll() is None and
                    journal.get('phase') == 'active' and not journal.get('revoke_intent')):
                # VTE has no verified prompt; Block can also conservatively
                # refuse an unproven prompt. Preserve that policy and exercise
                # the actual dialog after native input has finished the work.
                self.confirm_dialog()
                self.record('native-final-close-confirmed-after-work-completed')
        super().wait_source_exit(token, initial_counts)

    def confirm_dialog(self):
        time.sleep(.5)
        self.capture('native-final-close-confirmation')
        self.key('Tab')
        self.key('Return')
        self.confirmed_close = True

    def run(self):
        if self.args.case != 'confirm':
            return super().run()
        self.startup()
        shell = self.wait_shells(self.source, 1)[0]
        self.start_job(shell)
        self.key('Return')
        assert self.wait_visible(self.source)
        token = self.journal()['possible_body']
        counts = self.proof_counts(self.source)
        self.native_close()
        self.assert_gui_stays(.3, job=True)
        self.confirm_dialog()
        self.wait_source_exit(token, counts)
        deadline = time.monotonic() + 5
        while self.work_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        assert not self.work_alive(), 'confirmed close left an attached job alive'
        return dict(passed=True, confirmed_close_drained_attached_job=True,
                    fresh_close_with_native_retirement=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', type=Path, required=True)
    parser.add_argument('--wm', type=Path, required=True)
    parser.add_argument('--host', type=host, action='append', required=True)
    parser.add_argument('--shell', type=Path, required=True)
    parser.add_argument('--backend', choices=['block', 'vte'], required=True)
    parser.add_argument('--case', choices=['background', 'background-inactive', 'stopped', 'wait', 'loop', 'parent-exit', 'confirm'], required=True)
    parser.set_defaults(renderer='cairo', compositor='xrender', frame_sync=True,
                        freeze_owner=False, restart_daemon=False, desktop_shell=False,
                        components=True, task_canvas=False)
    args = parser.parse_args()
    if len(args.host) != 1 or args.host[0][0] not in ['forge', 'anvil']:
        parser.error('one actual Forge or Anvil binary required')
    args.daemon, args.wm, args.shell = [p.resolve(strict=True) for p in [args.daemon, args.wm, args.shell]]
    session = GtkJobsSession(args)
    result = dict(passed=False)
    try:
        result = session.run()
    except Exception as error:
        result['error'] = str(error)
        for label, process in session.host_processes.items():
            if process.poll() is not None and label in session.windows:
                session.closed_windows[label] = session.windows.pop(label)
        try:
            session.capture('failed-gtk-shell-jobs')
        except Exception as error:
            result['capture_error'] = str(error)
    finally:
        session.close()
        result.update(schema=1, scope=__doc__, frontend=session.frontend, backend=args.backend, case=args.case,
                      binary_sha256=session.binary_hashes, events=session.events, samples=session.samples,
                      native_samples=session.native_samples, work_observation=session.work_observation,
                      backend_observation=session.backend_observation,
                      native_host_ids=session.host_ids,
                      gui_processes={name: process.pid for name, process in session.host_processes.items()})
        report = session.root / 'gtk-shell-jobs-report.json'
        report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], report=str(report), error=result.get('error'))))
    raise SystemExit(0 if result['passed'] else 1)

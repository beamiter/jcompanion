#!/usr/bin/env python3
"""Sample actual X11 frontend windows in an isolated Xvfb/DBus session.

Requires Xvfb, metacity, dbus-daemon, xdotool, ImageMagick import and Pillow.
Exit 0 requires visible body pixels AND successful native-host handoffs. A
missing retirement/presentation proof is a failed acceptance gate, not a skip.
Screenshots sample frames; this does not certify physical scanout, GPU timing,
Wayland, IME, audio, arbitrary frozen-frame uniqueness or performance budgets.
The default-cat mint-ink detector tolerates native opacity/color conversion but
does not classify compact text, other skins or high-contrast presentations.
Absence of a match is not proof of body absence;
review screenshots as well. A positive run is only this scoped native smoke.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from xml.sax.saxutils import escape

from PIL import Image, ImageChops

SESSION = "eva-native-test"


def cat_ink(color):
    r, g, b = color
    # The default outline remains mint when dimmed over the native dark canvas.
    # Blue controls, neutral text and the shell's green cursor are excluded.
    # Outline/Accent have (G-B)/(G-R) >= .2; authored Dim effects are near .1.
    # An AA/opacity margin at .15 prevents a detached cloud being another body.
    return (r >= 60 and g >= 110 and b >= 100 and g - r >= 20 and g - b >= 4
            and 20 * (g - b) >= 3 * (g - r))


def cat_components(area):
    """Locate separated default-Cat ink groups, including within one window.

    This deliberately only classifies the fixture's mint skin. Coarse spatial
    grouping joins nearby glyphs; weak isolated controls/specks and palette Dim
    effects are excluded. Join distance and minimum ink strength stay fixed.
    It is a sampled image diagnostic, not a universal body/absence classifier.
    """
    red, green, blue = area.convert('RGB').split()
    mask = Image.new('L', area.size, 255)
    for channel, threshold in [(red, 60), (green, 110), (blue, 100),
                               (ImageChops.subtract(green, red), 20),
                               (ImageChops.subtract(green, blue), 4)]:
        mask = ImageChops.multiply(mask, channel.point([255 if v >= threshold else 0 for v in range(256)]))
    # dg >= ceil(3*dr/20). Subtract required-1 and test >0, so equality is
    # included without clipped negative differences accidentally matching.
    required_minus_one = ImageChops.subtract(green, red).point(
        [max(0, (3*v+19)//20-1) for v in range(256)])
    body_hue = ImageChops.subtract(ImageChops.subtract(green, blue), required_minus_one)
    mask = ImageChops.multiply(mask, body_hue.point([0]+[255]*255))
    width, height = area.size
    cols, rows = (width + 5) // 6, (height + 5) // 6
    coarse = mask.resize((cols, rows), Image.Resampling.BOX)
    occupied = {i: value for i, value in enumerate(coarse.getdata()) if value}
    groups = []
    while occupied:
        first, value = occupied.popitem()
        pending, points, strength = [first], [first], value
        while pending:
            cell = pending.pop()
            x, y = cell % cols, cell // cols
            for ny in range(max(0, y - 3), min(rows, y + 4)):
                for nx in range(max(0, x - 3), min(cols, x + 4)):
                    neighbor = ny * cols + nx
                    value = occupied.pop(neighbor, 0)
                    if value:
                        strength += value
                        points.append(neighbor)
                        pending.append(neighbor)
        count = strength * width * height / (cols * rows * 255)
        if count >= 60:
            xs, ys = [p % cols for p in points], [p // cols for p in points]
            groups.append(dict(ink_pixels_approx=round(count),
                               bounds=[round(min(xs) * width / cols), round(min(ys) * height / rows),
                                       round((max(xs) + 1) * width / cols), round((max(ys) + 1) * height / rows)]))
    return sorted(groups, key=lambda group: group['bounds'])


def edit_setting(text, section, key, value):
    import re
    pattern = r'(?ms)(^\[' + re.escape(section) + r'\]\s*\n)(.*?)(?=^\[|\Z)'
    match = re.search(pattern, text)
    if not match:
        raise ValueError('missing test configuration section ' + section)
    body = match.group(2)
    changed, count = re.subn(r'(?m)^' + re.escape(key) + r'\s*=.*$', key + ' = ' + value, body)
    if not count:
        raise ValueError('missing test configuration key ' + section + '.' + key)
    return text[:match.start(2)] + changed + text[match.end(2):]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NativeSession:
    def __init__(self, args):
        self.args = args
        self.root = Path(tempfile.mkdtemp(prefix="eva-native-"))
        # Use private immutable copies: a simultaneous caller build must not
        # change the executable or the checksum halfway through acceptance.
        (self.root / "bin").mkdir(mode=0o700)
        self.binaries, self.binary_hashes = {}, {}
        for name, source in [("jcompaniond", args.daemon), *args.host,
                             *([("jwm", args.wm)] if args.wm else []),
                             *([("jsh", args.shell)] if args.shell else [])]:
            path = self.root / "bin" / name
            shutil.copyfile(source, path)
            path.chmod(0o700)
            self.binaries[name] = path
            self.binary_hashes[name] = sha(path)
        self.processes, self.logs, self.windows, self.samples = [], [], {}, []
        self.host_processes = {}
        self.task_canvas_completed = False
        self.shell_programs = {}
        self.started = time.monotonic()
        self.started_unix = time.time()
        self.env = {k: v for k, v in os.environ.items() if not (
            k.startswith(("EVA_COMPANION_", "JWM_", "OPENAI_", "EMBER_", "FORGE_", "ANVIL_", "FROST_")) or k in (
                "SSH_CONNECTION", "SSH_TTY", "WAYLAND_DISPLAY", "OPENAI_API_KEY"))}
        self.env.update(XDG_SESSION_ID=SESSION, GDK_BACKEND="x11", GTK_A11Y="none",
                        GTK_USE_PORTAL="0", GIO_USE_VFS="local", GSETTINGS_BACKEND="memory",
                        GSK_RENDERER=args.renderer, SHELL="/bin/sh",
                        XDG_RUNTIME_DIR=str(self.root), EVA_COMPANION_MODE="shared",
                        EVA_COMPANION_SOCKET=str(self.root / "eva.sock"))
        for key, name in [("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                          ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state")]:
            path = self.root / name
            path.mkdir(mode=0o700)
            self.env[key] = str(path)
        # Interactive shells keep history/session files outside XDG as well.
        # Give these child applications a real private home for the test.
        test_home = self.root / 'user'
        test_home.mkdir(mode=0o700)
        self.env['HOME'] = str(test_home)
        self.env.pop('JSH_REAL_HOME', None)
        for name, _ in args.host:
            path = self.root / "config" / name
            path.mkdir(mode=0o700)
            config = 'shell = "/bin/sh"\njsh_update_check = "never"\neva_companion_enabled = true\n'
            if name in ('ember', 'frost') and args.shell:
                config = 'shell = ' + json.dumps(str(self.binaries['jsh'])) + '\njsh_update_check = "never"\neva_companion_enabled = true\n'
            self.shell_programs[name] = str(self.binaries['jsh']) if name in ('ember', 'frost') and args.shell else '/bin/sh'
            if name in ("ember", "frost"):
                config += 'restore_session = false\nascii_organism_enabled = false\n'
            config_path = path / "config.toml"
            config_path.write_text(config)
            config_path.chmod(0o600)

    def launch(self, name, argv, **kwargs):
        log = open(self.root / f"{name}.log", "wb")
        self.logs.append(log)
        process = subprocess.Popen(argv, env=self.env, stdout=log, stderr=log,
                                   start_new_session=True, **kwargs)
        self.processes.append(process)
        return process

    def command(self, *argv, check=True):
        return subprocess.run(argv, env=self.env, capture_output=True, text=True,
                              timeout=5, check=check)

    def start_display(self):
        rd, wr = os.pipe()
        try:
            self.launch("xvfb", ["Xvfb", "-displayfd", str(wr), "-screen", "0",
                                 getattr(self.args, 'screen', '3000x1200') + 'x24',
                                 "-nolisten", "tcp"], pass_fds=[wr])
        finally:
            os.close(wr)
        with os.fdopen(rd) as stream:
            if not select.select([stream], [], [], 5)[0]:
                raise RuntimeError("Xvfb startup deadline")
            display = stream.readline().strip()
            if not display.isdigit():
                raise RuntimeError("Xvfb did not return a display number")
            self.env["DISPLAY"] = ":" + display
        config = self.root / "bus.conf"
        config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' +
                          escape(str(self.root)) + '</listen><auth>EXTERNAL</auth>'
                          '<policy context="default"><allow send_destination="*"/>'
                          '<allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
        # No activation/service directories: desktop portals and account services
        # from the real user session cannot be started by this test bus.
        log = open(self.root / "dbus.log", "wb")
        self.logs.append(log)
        bus = subprocess.Popen(["dbus-daemon", "--nofork", "--config-file=" + str(config),
                                "--print-address=1"], stdout=subprocess.PIPE, stderr=log,
                               start_new_session=True)
        self.processes.append(bus)
        if not select.select([bus.stdout], [], [], 5)[0]:
            raise RuntimeError("private DBus startup deadline")
        self.env["DBUS_SESSION_BUS_ADDRESS"] = bus.stdout.readline().decode().strip()
        bus.stdout.close()
        if self.args.wm:
            self.env.update(JWM_COMPOSITOR="1", JWM_COMPOSITOR_API="glx",
                            JWM_X11_FRAME_SYNC="1" if self.args.frame_sync else "0",
                            LIBGL_ALWAYS_SOFTWARE="1", RUST_LOG="info,jwm::backend::x11::compositor::frame_sync=debug,eva_native_publication=debug")
            (self.root / 'config' / 'jwm').mkdir(mode=0o700)
            self.command(str(self.binaries['jwm']), '--backend', 'x11rb', '--gen-config')
            configs = list((self.root / 'config' / 'jwm').glob('config_*.toml'))
            if not configs:
                raise RuntimeError('JWM did not generate its private configuration')
            for config in configs:
                text = config.read_text()
                text = edit_setting(text, 'status_bar', 'show_bar', 'false')
                shell_enabled = 'true' if getattr(self.args, 'desktop_shell', False) else 'false'
                if '[desktop_shell]' in text:
                    text = edit_setting(text, 'desktop_shell', 'enabled', shell_enabled)
                else:
                    # Generated defaults may omit this optional section while
                    # enabling the shell through defaults/legacy migration.
                    text += '\n[desktop_shell]\nenabled = ' + shell_enabled + '\n'
                text = edit_setting(text, 'behavior', 'compositor', 'true')
                config.write_text(text)
            wm = self.launch('jwm', [str(self.binaries['jwm']), '--backend', 'x11rb'])
            deadline = time.monotonic() + 30
            while not (self.root / 'jwm-ipc.sock').exists():
                if wm.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('JWM startup failed; inspect jwm.log')
                time.sleep(.05)
        else:
            self.launch("metacity", ["metacity", "--sm-disable", "--compositor=" + self.args.compositor])
        time.sleep(0.3)

    def launch_host(self, index, instance=None):
        frontend, _ = self.args.host[index]
        name = instance or frontend
        argv = [str(self.binaries[frontend])]
        if frontend in ("forge", "anvil"):
            argv += ["--no-restore", "--mode", "block"]
        process = self.launch(name, argv)
        self.host_processes[name] = process
        deadline = time.monotonic() + 30
        window = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited {process.returncode}; inspect {name}.log")
            found = self.command("xdotool", "search", "--onlyvisible", "--pid",
                                 str(process.pid), check=False)
            if found.returncode == 0:
                for candidate in found.stdout.splitlines():
                    size = self.command("xdotool", "getwindowgeometry", "--shell", candidate)
                    values = dict(line.split("=", 1) for line in size.stdout.splitlines() if "=" in line)
                    if int(values.get("WIDTH", 0)) > 200 and int(values.get("HEIGHT", 0)) > 200:
                        window = candidate
                        break
            if window:
                break
            time.sleep(0.05)
        if window is None:
            raise RuntimeError(f"{name} did not map a window")
        self.command("xdotool", "windowsize", window, "1400", "1000")
        self.command("xdotool", "windowmove", window, str(index * 1450), "0")
        self.windows[name] = window
        self.focus(name)
        if frontend == 'ember' and self.args.task_canvas:
            deadline = time.monotonic() + 20
            while 'Shell session started successfully' not in (self.root / (name + '.log')).read_text(errors='replace'):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Ember task fixture shell did not become ready')
                time.sleep(.05)
            time.sleep(.4)
            geometry = self.command('xdotool', 'getwindowgeometry', '--shell', window)
            info = dict(line.split('=', 1) for line in geometry.stdout.splitlines() if '=' in line)
            x, y = int(info['WIDTH']) // 2, int(info['HEIGHT']) - 80
            self.command('xdotool', 'mousemove', '--window', window, str(x), str(y), 'click', '1')
            # A real harmless local command builds an actual completed task
            # canvas. Its private marker verifies execution; no coordinator
            # task facts or retirement events are injected.
            marker = self.root / ('task-canvas-' + name + '-complete')
            command = "printf 'EVA_NATIVE_CANVAS_OK\\n' > " + shlex.quote(str(marker)) + "; printf 'EVA_NATIVE_CANVAS_OK\\n'"
            self.command('xdotool', 'type', '--clearmodifiers', '--delay', '5', '--', command)
            time.sleep(.2)
            self.command('xdotool', 'key', '--clearmodifiers', 'Return')
            deadline = time.monotonic() + 10
            while not marker.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.capture('task-canvas-not-executed')
                    raise RuntimeError('real Ember task command was not executed')
                time.sleep(.05)
            self.task_canvas_completed = marker.read_text() == 'EVA_NATIVE_CANVAS_OK\n'
            if not self.task_canvas_completed:
                raise RuntimeError('unexpected real Ember task result')
            time.sleep(2)

    def focus(self, name):
        self.command("xdotool", "windowactivate", "--sync", self.windows[name])
        self.command("xdotool", "windowfocus", "--sync", self.windows[name])

    def journal(self):
        try:
            state = json.loads((self.root / "profile" / "residence.json").read_text())
            return {k: state[k] for k in ("phase", "possible_body", "revoke_intent", "target")}
        except FileNotFoundError:
            return None

    def capture(self, label):
        path = self.root / f"{len(self.samples):03}-{label}.png"
        self.command("import", "-window", "root", str(path))
        with Image.open(path) as source:
            pixels = source.convert("RGB")
            counts, components, geometries = {}, {}, {}
            for name, window in self.windows.items():
                geometry = self.command("xdotool", "getwindowgeometry", "--shell", window)
                info = dict(line.split("=", 1) for line in geometry.stdout.splitlines() if "=" in line)
                x, y, w, h = (int(info[key]) for key in ("X", "Y", "WIDTH", "HEIGHT"))
                geometries[name] = dict(x=x, y=y, width=w, height=h)
                area = pixels.crop((x, y, x + w, y + h))
                counts[name] = sum(n for n, color in area.getcolors(w * h) if cat_ink(color))
                if getattr(self.args, 'components', False):
                    components[name] = cat_components(area)
        bodies = [name for name, count in counts.items() if count >= 20]
        sample = dict(label=label, elapsed_ms=round((time.monotonic() - self.started) * 1000, 2),
                      screenshot=path.name, sha256=sha(path), palette_pixels=counts,
                      visible_body_windows=bodies, window_geometries=geometries,
                      body_components=components, journal=self.journal())
        self.samples.append(sample)
        if len(bodies) > 1:
            raise AssertionError("sample contains body pixels in multiple native windows")
        if any(len(groups) > 1 for groups in components.values()):
            raise AssertionError('sample contains separated body ink groups inside one native window')
        return sample

    def wait_for(self, name, seconds=6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            sample = self.capture("waiting-" + name)
            state = sample["journal"]
            token = state and state["possible_body"]
            if (token and token["host_id"].startswith(name + "-") and
                    state["phase"] == "active" and sample["visible_body_windows"] == [name]):
                return True
            time.sleep(0.15)
        return False

    def run(self):
        self.start_display()
        self.launch_host(0)
        time.sleep(0.3)
        if self.capture("daemon-absent")["visible_body_windows"]:
            raise AssertionError("body appeared before coordinator authority")
        self.daemon = self.launch("daemon", [str(self.binaries["jcompaniond"]), str(self.root / "profile")])
        first = self.args.host[0][0]
        ready = self.wait_for(first)
        frozen = None
        if ready and self.args.freeze_owner:
            process = self.host_processes[first]
            frozen = self.journal()['possible_body']
            os.kill(process.pid, signal.SIGSTOP)
            deadline = time.monotonic() + 2
            while True:
                status = Path(f'/proc/{process.pid}/status').read_text()
                state = next(line for line in status.splitlines() if line.startswith('State:'))
                if '\tT' in state:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('owner SIGSTOP was not observed')
                time.sleep(.01)
        # Capture the second real frontend even if the first's native presentation
        # acknowledgement is unavailable; that failure must not be hidden.
        self.launch_host(1)
        second = self.args.host[1][0]
        freeze_blocked = False
        if frozen:
            held_from = time.monotonic()
            try:
                while time.monotonic() - held_from < 4:
                    sample = self.capture('frozen-' + first)
                    state = sample['journal']
                    if state['possible_body'] != frozen or second in sample['visible_body_windows']:
                        raise AssertionError('replacement body granted while owner is stopped')
                    freeze_blocked |= state['phase'] == 'awaiting_removal_proof'
                    time.sleep(.15)
            finally:
                os.kill(self.host_processes[first].pid, signal.SIGCONT)
            if not freeze_blocked:
                raise AssertionError('target never requested retirement of the stopped owner')
            self.focus(second)
        transferred = self.wait_for(second)
        returned = False
        if transferred:
            self.focus(first)
            returned = self.wait_for(first)
        recovered = False
        if returned and self.args.restart_daemon:
            old_token = self.journal()['possible_body']
            self.daemon.kill()
            self.daemon.wait(3)
            self.focus(second)
            self.daemon = self.launch('daemon-restarted', [str(self.binaries['jcompaniond']), str(self.root / 'profile')])
            recovered = self.wait_for(second, 10)
            if recovered:
                token = self.journal()['possible_body']
                if token['boot_id'] == old_token['boot_id'] or token['companion_id'] != old_token['companion_id']:
                    raise AssertionError('restart did not preserve identity and change boot')
        return dict(initial_presented=ready, transferred=transferred, returned=returned,
                    freeze_blocked=freeze_blocked, recovered=recovered,
                    passed=ready and transferred and returned and
                    (not self.args.freeze_owner or freeze_blocked) and
                    (not self.args.restart_daemon or recovered))

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGCONT)
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(3)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait(3)
        for log in self.logs:
            log.close()


def host(value):
    try:
        name, path = value.split("=", 1)
        if name not in ("forge", "anvil", "ember", "frost"):
            raise ValueError("unsupported frontend")
        return name, Path(path).resolve(strict=True)
    except (ValueError, OSError) as error:
        raise argparse.ArgumentTypeError("expected frontend=/absolute/binary: " + str(error))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daemon", type=Path, required=True)
    parser.add_argument("--host", type=host, action="append", required=True)
    parser.add_argument("--renderer", choices=("cairo", "gl"), default="cairo")
    parser.add_argument("--compositor", choices=("none", "xrender", "xpresent"), default="xrender")
    parser.add_argument("--wm", type=Path, help="Use this JWM binary instead of Metacity")
    parser.add_argument("--frame-sync", action="store_true", help="Enable opt-in JWM native frame feedback")
    parser.add_argument("--freeze-owner", action="store_true", help="Verify stopped owner's pixels do not permit a replacement")
    parser.add_argument("--restart-daemon", action="store_true", help="Verify native retirement recovery after SIGKILL")
    parser.add_argument("--shell", type=Path, help="Snapshot this real jsh for Ember/Frost; Ember task-canvas requires it")
    parser.add_argument("--task-canvas", action="store_true", help="Run and verify a local printf task in the isolated Ember window")
    args = parser.parse_args()
    if len(args.host) != 2 or args.host[0][0] == args.host[1][0]:
        parser.error("provide two distinct native frontends for a round-trip handoff")
    if f"XDG_SESSION_ID={SESSION}".encode() not in Path("/proc/self/environ").read_bytes().split(b"\0"):
        parser.error(f"launch with XDG_SESSION_ID={SESSION}")
    args.daemon = args.daemon.resolve(strict=True)
    if args.wm:
        args.wm = args.wm.resolve(strict=True)
    if args.shell:
        args.shell = args.shell.resolve(strict=True)
    if args.task_canvas and (not args.shell or not any(name == 'ember' for name, _ in args.host)):
        parser.error('--task-canvas requires --shell and an Ember host')
    if args.frame_sync and not args.wm:
        parser.error('--frame-sync requires --wm')
    session = NativeSession(args)
    result = {"passed": False}
    try:
        result = session.run()
    except Exception as error:
        result["error"] = str(error)
    finally:
        session.close()
        result.update(schema=2, scope=__doc__, renderer=args.renderer,
                      compositor='glx' if args.wm else args.compositor,
                      window_manager='jwm' if args.wm else 'metacity', frame_sync=args.frame_sync,
                      task_canvas_fixture=args.task_canvas,
                      task_canvas_completed=session.task_canvas_completed,
                      binary_sha256=session.binary_hashes, samples=session.samples)
        (session.root / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "report": str(session.root / "report.json"),
                      "error": result.get("error")}))
    raise SystemExit(0 if result["passed"] else 1)

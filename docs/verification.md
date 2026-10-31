# Verification scope

## Native GTK clock and surface identity (2026-10-31)

Monotonic per-GUI before-paint stamps are separate from native clock counters. Rebinding invalidates old clock/surface generations and disconnects old handlers; actual complete positive presentation time remains mandatory. A new surface cannot clear a body on an unretired old surface. The raw-counter regression is preserved as an expected failure.

Current source passes 176 targeted test executions and all-target Clippy with the three existing exceptions; nine independent helper tests also pass. Native evidence includes 102 terminal application cases, four separate real adapter cases with two windows in one test process, and the concurrent 8-GUI/32-PTY matrix. The positive rebuild cases retire the old surface before replacement; the negative cases retain the unknown old obligation. See [machine evidence](evidence/gtk-clock-checks-2026-10-31.json). This is not full terminal multiwindow, trusted destruction, physical uniqueness, P7 performance or complete-proposal acceptance.

## GTK captured-frame presentation (2026-10-31)

Immutable native frame identity prevents newer paints from replacing an older completed body receipt. The original FrameClock, token, connection/admission generations and body/cleared content remain bound; at most the first eight pending frames are retained. Only complete GDK timing with positive presentation time can acknowledge a frame. Existing HostGate submission/acceptance methods are unchanged.

The current binaries pass 166 targeted test executions, five independent ordering tests, 98 native GTK cases (four delayed-feedback, 84 lifecycle and ten pending-launch), and the 8-GUI/32-PTY matrix with observed concurrent GTK regression windows. Twelve delayed older body frames were accepted in the twelve new handoffs; including startup/warmup, all four runs accepted twenty older body frames. The old diagnostic Anvil run eventually passed while ignoring 28 initially pending older frames; it is not labeled a failing native control. See [machine evidence](evidence/gtk-presentation-checks-2026-10-31.json). The initial input-routing diagnostic, prior Granted failure, full-proposal gaps, three existing Clippy exceptions, trusted C11 and P7 limits remain explicit.

## GTK in-flight launch ownership (2026-10-31)

Application-owned fork/exec observation now retains a window-scoped launch ticket before fork, through pane removal, cancellation, failed exec and actual owned session drain. Late exits and startup input bind the exact launch and child. **158 targeted test executions**, **94 selected current native GTK cases** (84 existing + 10 pending launch) and the isolated 8-GUI/32-PTY matrix pass. See [machine evidence](evidence/gtk-launch-checks-2026-10-31.json). The original batch had two readiness failures whose corrected retries pass; all failures remain retained. A concurrent matrix run stayed Granted despite visible Anvil; its cause and load-dependent liveness remain open. No physical/trusted C11, P7, full same-process multiwindow, provider, voice, release or full-proposal acceptance is implied.

## Current attached shell jobs and natural parent exit (2026-10-31)

Ember/Frost now require the original shell identity, a clean semantic prompt,
and a complete bounded observation with no other live member of that PTY
session before ordinary window close. Background and stopped jobs count.
An unknown observation keeps the close guarded; existing explicit per-tab
termination remains available. Natural exit keeps the leader unreaped, drains
same-session members through pidfds, verifies two empty scans, then reports its
original status. It never signals a reused numeric PID; detached setsid sessions
are outside this ownership boundary.

Three baseline native failures are retained: Frost background close and both
frontends' separate-group descendants after natural shell exit. Ember's original
background-close case already passed. A further Frost candidate still waited for
slave EOF; its failed native report and binary are retained. Final Frost probes
the parent independently every 200ms and emits a bounded 1 MiB readable tail
before exit notification. Incomplete cleanup retries without closing the session.
The real-PTY open-slave/tail/status regression and transient-hangup regression
both pass. This does not promise unbounded output retention or performance.

**119 workspace tests**, strict workspace Clippy and **111 distinct frontend
window/PTY/Eva checks** pass. Zero-match filters are excluded. Close-role unit
fixtures wait for real shell startup work to finish before supplying synthetic
prompt marks. The 18-file source bundle keeps public Git pins; only the already
resolved libc dependency was added to companion-host's lockfile entry.

Current native cases, original failure reports, exact binaries and source freeze
are recorded in [machine evidence](evidence/shell-jobs-checks-2026-10-31.json).
The late-work fixture now arms a real shell trap through native input and starts
the job only after native clearance is published; it does not preload a background
job that the new guard must refuse, or suspend the parent to avoid competing reads.
The keyboard-only diagnostic that did not launch its helper is not a passing case.
Historical old-binary checks retain their own scope. Nothing was installed into
the daily desktop. Real providers, voice/API, other frontends/backends, detached
or threading/fork boundaries, IME/review, trusted C11 fences and P7 remain open.

```sh
env -u SSH_CONNECTION -u SSH_TTY XDG_SESSION_ID=eva-native-test \
  python3 tests/native_shell_jobs.py --daemon target/debug/jcompaniond \
  --wm /tmp/eva-jwm-target/debug/jwm --host frost=/tmp/eva-egui-target/debug/frost \
  --shell /home/yj/.cargo/bin/jsh --case parent-exit
# Cases: background, background-inactive, stopped, wait, loop, parent-exit.
cargo test --workspace --locked --offline
```

## Current single-profile native retirement compaction (2026-10-31)

Three actual same-frontend GUIs perform **71 native handoffs** in each of two
separate Ember/Frost profiles. A byte-preserving fault relay drops only the
original source's first exact retirement ACK. The other two GUIs rotate while
the source receives no new grant: the exact cache remains **64**, and the
original entry is absent. After actual coordinator SIGKILL/restart, the original
GUI reconnects with a new boot/nonce and must obtain a fresh native clearance
before resending that exact old token and receiving a newly generated ACK.
No old reply is retained or replayed. The ACK preserves a newer current body;
the original window/host and shell recover, accept a real PID-marker command,
then complete a fresh ordinary close with exact-token native retirement.

The independent retained-evidence audit checks each transition and publication /
scene / native-pass / captured-tree association, connection nonce, regenerated
ACK order and PNG hashes. Each frontend has **72** audited clearances; sampled
root images total **206 Ember / 262 Frost**. These are particular native profiles,
not the earlier 70 declared-serial IPC checks or continuous physical uniqueness.

An initial Frost fixture incorrectly equated native-pass and host-tree serials;
its failed report is retained. The Iced observer now supplies the original native
receipt ID alongside its captured snapshot for debug correlation. Existing API,
window lease, cancellation, pending bound and acceptance conditions are retained.
**10 feedback-code tests**, **11 Frost Eva tests**, strict feedback Clippy,
**4 relay-control tests** and **4 PNG-oracle tests** pass. Synthetic controls and
the harness's opaque window IDs are not native evidence. Coordinator/Ember
compiler inputs and binaries match the previous **115 workspace / strict Clippy /
11 real IPC** checkpoint exactly; those results are explicitly retained.
The changed Frost's targeted native regressions and full family matrix are listed
in [current evidence](evidence/native-retirement-compaction-checks-2026-10-31.json).
The old Frost 4bc45c5 suite remains historical; all 66 previous cases are not
claimed as re-executed for 5dacd58. Daily installations are unchanged.

Reproduce the actual private test with the existing local binaries:

```sh
env -u SSH_CONNECTION -u SSH_TTY XDG_SESSION_ID=eva-native-test \
  python3 tests/native_retirement_compaction.py \
  --daemon target/debug/jcompaniond --wm /tmp/eva-jwm-target/debug/jwm \
  --host frost=/tmp/eva-egui-target/debug/frost \
  --shell /home/yj/.cargo/bin/jsh --cycles 70
python3 tests/verify_native_retirement_compaction.py PATH_TO_RETAINED_RUN
python3 -m unittest discover -s tests -p test_native_retirement_proxy.py -v
```

The test never calls a provider or device. Other shell lifecycle cases, actual
providers/remote, multiwindow/suspend, IME/memory/approval/voice/API, trusted C11
fences/anchors and final performance/release remain open. See the full ledger.

## Previous shell exec/builtin close admission (2026-10-31)

Linux Ember/Frost close admission pins the interactive shell program and process
start, then requires a fresh clean semantic prompt. A root PID/PGID/SID or matching
executable alone cannot identify idle. Actual native baseline close killed both
same-PID exec processes (first SIGHUP retained) and same-image read builtins.
The **18** current native cases cover exec, same-image exec -c and read in active
and inactive tabs, plus six Frost raw-sh cases with explicit tab termination.
Native input returns to the exact original root/start/TTY/program and host tuple;
final close requires exact current-token retirement and actual new scene receipt.

A real final-candidate Frost regression after Ctrl+C was also fixed: the Agent
input capture included jsh's right-side elapsed decoration. Window closing now
uses clean semantic-prompt facts independently. Pending input/typeahead and the
alternate screen remain guarded; Agent input authorization is unchanged. Two
parsed-terminal regressions and the original native scenario pass.

Current checks: **115 workspace**, strict workspace Clippy, **183 focused + 6
additional distinct frontend tests**, **11 actual IPC**, locked/offline builds and
**931 recorded Rust/Cargo inputs**. **48** existing native regressions pass, for
**66** current cases including two expected crash-blocking negatives. Twenty exact
unchanged Ember runs are explicitly retained; the remaining 46 are current runs,
including all changed Frost cases. The full matrix is **8 GUI / 32 PTY / 72 actual
PID markers**, 24 rapid operations, full reverse, **70 root PNGs** and
**25 accepted WGPU scene receipts**. Main regressions use copied jsh in both
apps; uninstrumented raw sh requires its separately recorded explicit termination.

Original product failures and separate readiness/wrong-tab/log-only diagnostics
remain unmodified. Correctly waiting for the native prompt and targeting the busy
session does not establish input startup/throughput or performance. The late-work
fixture still pauses its original private shell; ordinary fg/parent-exit/descendant
acceptance is separate. Kernel/executable/prompt observations are not authenticated
shell attestation and never supply body retirement proof. Scene evidence remains
NativePresented, not CompositorPresented or physical/continuous uniqueness.

See [current evidence](evidence/shell-lifecycle-checks-2026-10-31.json) and the
[full ledger](implementation-status.md). The final snapshot verifies **2,633 family Rust/Cargo files**, **931 compiler
inputs** and **7 exact binaries**. Its independently reconstructed offline workspace
passes **115 tests**, plus four PNG-oracle tests. The 107-root process-hygiene audit
has no matching remaining process; it never substitutes for retirement/destruction
proof. This is not a bit-reproducible frontend/native build or hardware acceptance. More builtins/background jobs, single-profile native >64 compaction,
providers/remote, other editors/backends, multiwindow, suspend, actual IME/memory/
approval/voice/API, trusted single-node fences/anchors and performance/release stay
open. Known dependency warnings and two earlier Ember UI baselines are retained.

## Previous same-host withdrawal cancellation (2026-10-31)

Ember and Frost can explicitly keep a window open during withdrawal, complete the
original exact-token native retirement, then re-admit that same GUI/window/host.
Ordinary cancellation retains the IPC connection and original shell. A real
daemon restart changes boot/nonce while preserving host/window identity.

The opt-in HelloWithFeatures/HostAccepted exchange negotiates withdrawal_resume_v1.
Legacy Hello/Accepted schemas and Recall behavior remain unchanged. Connection
nonce, bounded intent and admission epoch reject stale metadata before caches
mutate. Re-admission clears old context/consent and sends fresh context before task
facts. The canonical companion-host crate is copied into versioned in-repo bundles;
byte/Cargo/public-base checks run in both frontend CIs. Public pins stay unchanged.

Two native failures are retained: a disappearing glyph prefix reset Frost's Eva
input, allowing draft-prefix routing to the shell or an unrelated panel; repeated
Revoke after restart advanced the gate's bound while the renderer's boolean stayed
armed. Stable form parents/reserved empty layout fix the first. Idempotent duplicate
Revoke, a fresh accepted-connection bound and token/frame request identity fix the
second; delayed old proof cannot be relabelled as a new native frame.

All **19** current native cancellation cases pass: keys/buttons, actual pending
scene, new foreground work, held Enter/Escape/blur, a focused Eva draft, real daemon
restart, queued fresh close and stale Force pointer release. Old/current tokens,
native scene receipts, window/GUI/shell identities and ordinary socket inodes are
checked. The final focused draft is also visually inspected in actual native
backing; subsequent native original-shell input verifies no prompt contamination.

Current checks: **112 workspace**, strict workspace Clippy, **179 frontend**, **11
real IPC** and the process-fault script. Locked/offline builds and **928 Rust/Cargo
inputs** match before/after. The additional **29** existing native regression
cases pass, for **48** current-binary native cases including two expected crash-blocking negatives. The full 8-GUI/32-PTY/72-PID-marker matrix has 24 rapid operations, full reverse traversal, **68 root samples** and **26 accepted WGPU scene receipts**.

A real GuardFailure image exposed a PNG-oracle false positive: its Dim effect cloud was a second ink group. The palette-hue predicate fixes this without changing join distance or ink minimum. Four PNG tests retain two close-body negatives; **686** saved frames / **1,752** regions replay without losing formerly observed body windows. The exact-binary failing scenario was rerun successfully; original 19 cancel and 9 passed regression state/proof runs are retained, not described as fresh runs after the oracle fix.

The 64-token exact retirement cache remains bounded. Monotonic durable record
coverage can only re-ack old epochs, never clear a current newer body or attest
that an arbitrary tuple was granted. The 70-retirement compaction/restart test is
real coordinator IPC with declared serial fixtures, not native scene acceptance.
The controlled late-foreground fixture pauses the original private shell to
exclude an already-blocked stdin read, then resumes it after work completion.
Normal fg and shell-exit/descendant lifecycle acceptance remain open.

See [current evidence](evidence/withdrawal-resume-checks-2026-10-31.json) and
[the full ledger](implementation-status.md). All native regressions and the 93-root cleanup audit pass. The exact binary/source snapshot retains Git bases, patches, current evidence and reconstruction records. Offline reconstruction verifies **2,630 family Rust/Cargo files**, **928 recorded compiler inputs** and **7 exact binaries**; its four PNG-oracle tests pass. This does not claim an independent bit-reproducible native build. Results remain supported Vulkan/JWM/X11 NativePresented,
not physical scanout/continuous uniqueness or CompositorPresented. Real voice/API,
providers/remote roles, other editors/backends, same-process windows, suspend,
IME/approval/memory UI, trusted fence/anchors and performance/release remain open;
known dependency warnings and two Ember UI baselines are retained.

## Previous command-owned PTY continuation (2026-10-31)

An explicit-argv command can itself be the PTY child, foreground process group
and session leader. Both old GUIs mistook that equality for an idle shell; real
native WM close terminated work (first SIGHUP preserved). Ember now uses its
existing SessionPurpose; Frost records command ownership at spawn and uses it
with current kernel PTY state for both window refusal and existing tab/batch
confirmation. A cached display name no longer admits a destructive tab close.

Five current native cases cover root command, inactive command tab in each app,
and Frost native confirmation/cancellation. Background cases execute actual input
and verify the exact original idle shell PID while the command stays live. Every
case then keeps the GUI open after work ends and requires a fresh healthy window
close with new native feedback and exact current-token retirement. Ember's path
uses its real composer, isolated Git worktree, durable registration and Start;
Frost uses its existing coding-CLI palette. Private controlled CLI executables do
not call providers/models or establish real Agent/task-outcome acceptance.

Current tests: **6 Ember window / 2 Ember Eva / 69 Frost close / 11 Frost Eva**,
both locked/offline builds, stable recorded compile inputs and modified-file
format. Frost Eva formatting also changed, without behavior changes; its focused
tests were rerun. Exact unchanged coordinator/JWM/receipt/key inputs explicitly
reuse prior **77/7**, **7/9**, **8** and recorded lint results. Full frontend Clippy
is not claimed; known dependency warnings and two Ember UI baselines remain.

The current binaries also pass all 24 existing native regression cases, including
embedded Vim9, delayed close, surface/authority lifecycle, and the complete
**8 GUI / 32 PTY / 72 marker** matrix with stopped owner, 24 rapid operations,
full reverse traversal, **77 root samples** and **23 accepted scene receipts**.
These are supported Vulkan/JWM/X11 sampled results, not CompositorPresented,
physical scanout or continuous uniqueness. Crash safety remains a blocked negative.

Explicit cancel/resumed residence for the same withdrawing host remains open.
It needs a compatible explicit handshake that retains exact old retirement;
changing legacy Recall semantics or replacing the host identity is not accepted.
Real providers/remote roles, shell exec/builtins/descendant lifecycles, other
editors/backends, same-process windows, suspend, memory/approval UI, voice/API,
trusted single-node fence/anchors and final performance/release remain pending.
See [current evidence](evidence/command-role-checks-2026-10-31.json) and
[the full ledger](implementation-status.md).

## Previous deferred-close continuation (2026-10-31)

A native close can already be waiting on real compositor evidence when new PTY
foreground work appears. Old Ember later auto-closed without renewed intent; old
Frost exited while that work was live (the repeated native fixture recorded actual
SIGHUP). Both now preserve in-flight withdrawal/proof but pause GUI exit until a
fresh explicit close. Frost uses current kernel foreground groups and removes its
blocking closing overlay while paused, so the kept-open terminal remains usable.
Explicit final-tab process confirmation retains its authorized exit path.

Current binaries pass both strengthened late-work cases: exact original retirement,
repeated refused close, real task completion, no auto-close, native input marker,
fresh close and surviving GUI acquisition. Ember's real embedded Vim9 also passes
modified-buffer refusal, exact native :w, deferred window close after explicit :q,
and editor-only exit that keeps the GUI open. Its bridge/modified state comes from
Vim, not terminal-name guessing. The Frost final-tab case separately confirms that
explicit native confirmation may end the work and exit after exact retirement.

Current checks: **68 Frost close / 11 Frost Eva / 5 Ember window / 2 Ember Eva**,
both locked/offline builds and recorded compile-input hashes. Exact unchanged
coordinator/JWM and receipt/key sources are checked before explicitly reusing
prior **77 workspace / 7 IPC**, **7/9 receipt**, **8 key** and recorded lint evidence.
Full frontend Clippy is not claimed; the existing iced_winit deprecations remain.

Eight work/visible-resize cases, eight surface regressions (two expected crash
blocks), two authority regressions and the **8 GUI / 32 PTY / 72 input** matrix pass
on current binaries. Its **77 root PNG samples**, stopped-owner case, 24 rapid
operations and full reverse traversal are sampled supported Vulkan/JWM/X11
acceptance. Close-intent cases add actual first-signal and final-residence evidence.

The late job is launched by native shell input, then a fixture trigger gives it
actual kernel PTY foreground ownership while private JWM feedback is withheld;
this is not an ordinary shell fg UX test. Protocol/native proof is never injected.
A kept-open window still has its already-started withdrawal; cancellation/resumed
residence is not implemented. Command-owned/Agent CLI/direct-child PTYs and remote
sessions need role-aware close tests, not an idle inference from child PID equality.
Other embedded editors, same-process native windows, suspend, IME, voice/API,
trusted single-node fences, performance/release and known UI baseline failures
remain open. See [current evidence](evidence/close-intent-checks-2026-10-31.json)
and [the full ledger](implementation-status.md).

## Previous native-work continuation (2026-10-31)

Ember now checks actual foreground ownership in every interactive pane before
ordinary window withdrawal/close. A native regression first demonstrated actual
Python SIGHUP/job loss. Busy foreground and inactive-pane work now survive the
normal close request; native Ctrl+C ends the exact task, and a fresh close obtains
native scene retirement. Both apps also preserve an actual modified external Vim
buffer and save its exact edited bytes with native :wq. Embedded Vim9 is separate.

A second native failure exposed a preparation liveness race: safe geometry can
vanish between Prepare and Prepared. Its return now replays only the same target
and committed epoch; no old body is revoked while unsafe. Both new real IPC tests
fail before the fix and pass afterward, including old-owner preservation.

External Vim testing also reproduced unmatched shifted logical releases. egui
kept Colon and curly-bracket keys down after real releases, hiding Eva despite
valid canvas. Known physical presses now retain their original logical identity
through repeat/release. Actual egui-state tests and the full native Vim flow pass;
Text, clipboard, unrepresentable printable and unidentified-key behavior remain
covered. Temporary diagnostic instrumentation is absent from final sources.

Current checks: **77 workspace / 7 real IPC / process faults**, strict coordinator
Clippy/format; **8 egui-winit key tests**, strict crate Clippy/format; **5 Ember
window tests**; both locked/offline builds with unchanged recorded compile inputs.
The unchanged receipt-source/harness 7/9 checks are explicitly reused. Eight native
work/visible-resize cases, eight surface regressions (two expected crash blocks),
two authority regressions and the complete **8 GUI / 32 PTY / 72 input** matrix pass.
The matrix retains **69 root samples**, owner freeze, 24 rapid actions and full
reverse traversal. This is sampled supported Vulkan/JWM/X11 evidence.

An idle PTY group is not eligible geometry: the corrected Ember work fixture
requests a real fresh empty prompt after proving no deferred auto-close. Original
failed reports, genuine shifted-key failures, diagnostics, exact binaries/source
hashes and cleanup audit remain in [current evidence](evidence/window-use-checks-2026-10-31.json)
and [the requirement ledger](implementation-status.md). Embedded Vim9, new work
during retirement, same-process windows, suspend, IME, other backends, trusted
single-node retirement, voice/API and performance/release remain incomplete.

## Previous mapping-lifecycle continuation (2026-10-31)

The stricter real same-size remap gate failed in both frontends before the fix:
an initial round trip could pass while a pre-unmap counter was still accepted.
Server Map/Unmap events now invalidate old flight/receipts/control values before
IME/app processing, keep counters monotonic, and require actual VIEWABLE state
for publication. A fresh mapped frame/scene receipt must finish retirement.

Production-source harnesses pass **7 Ember / 9 Frost tests**, strict Clippy and
format. Exact current native binaries pass same-size remap, unmapped shrink/restore
ABA, and ordinary idle WM close with actual new native scene feedback and exact
retirement. Owner SIGKILL in both apps remains recovery_blocked with the exact
token: these are expected-negative safety checks, not automatic crash recovery.
Both real compositor-loss/replacement tests also pass again. The complete family
matrix passes **8 GUI / 32 PTY / 72 input markers**, owner freeze, 24 rapid events
and full reverse traversal; **72 root PNG samples** detect at most one Cat body.

The coordinator executable and every recorded compile input match the preceding
77-test / 5-IPC / process-fault evidence; those suites were not rerun this turn.
Current reports, exact binaries, historical weaker/failed attempts and scope are
in [the new evidence](evidence/surface-lifecycle-checks-2026-10-31.json) and
[the full requirement ledger](implementation-status.md). Mapped resize, multiwindow
processes, busy/Vim close, real suspend, other backends, IME, voice/API, trusted
single-node retirement and release/performance remain incomplete.

## Previous authority-lifecycle continuation (2026-10-31)

The exact current coordinator passes **77 workspace tests**, strict all-target
Clippy/format, **5 real IPC contracts** and the process-fault contract. A new
regression first reproduced the actual daemon exit from delayed old-owner
Presented during another host's Preparing phase; the phase guard now rejects it
without changing exact retirement requirements. The adversarial trace generator
also includes presentation events.

Ember/Frost production-source receipt harnesses pass **6/6** and **8/8**, plus
strict Clippy/format. Real XFixes selection loss wakes native drawing, invalidates
old receipt/control state, and never issues proof. Two-process native lifecycle
tests pass in both apps: actual client backing pixels update without later
input/resize, the old token stays held with no accepted scene receipt, and real
replacement-JWM round trips recover even when the owner XID is reused.

The final complete native matrix passes **8 GUIs / 32 PTYs / 72 input PID markers**,
24 rapid native focus/pane events, stopped-owner blocking and full reverse
traversal. Its **66 root samples** contain at most one detected default-Cat body.
The earlier failing rapid matrix, UI-hang baseline and fixture attempts retain
their original false verdicts. Current sources/binaries, logs and caveats are in
[the lifecycle evidence](evidence/authority-lifecycle-checks-2026-10-31.json) and
[the full requirement ledger](implementation-status.md). This is sampled supported
Vulkan/JWM/X11 acceptance, not continuous/physical uniqueness or full release.

## Historical local continuation (2026-10-30 / earlier 2026-10-31 attempts)

2026-10-31 extension: actual **8 GUIs / 32 PTYs** and native spatial-input
routing are verified, but the complete matrix **fails**. A budgeted round-robin
texture refresh fix advances the prior blocked Forge recovery; a later root
PNG then shows two Ember bodies. Native WGPU submission is insufficient to
certify compositor clearance. JWM's relevant suite is now **298 passed**, strict
Clippy and XCB compilation pass. The matrix has not reached rapid burst or a
complete reverse traversal. See [the current failed-gate evidence](evidence/matrix-checks-2026-10-31.json)
and [the dual-body PNG](evidence/native-matrix-after-fairness-2026-10-31/023-waiting-ember-2.png).
Earlier scoped pairwise passes below remain historical scoped results.

The workspace now passes **76 tests**, including three per-task receipt/attention
regressions, and strict workspace all-target Clippy. In this local environment
the previously prepared `fault_processes.py` was actually run outside the socket-
restricted sandbox and passed. The four new `ipc_contracts.py` scenarios also
passed against a real coordinator, covering current-task isolation, exact single-
use selection consent, scoped reviewed memory/deletion/reopen and durable exclusive
voice leases. CI runs both process contracts; its remote result is separate.

Native X11 window sampling is now reproducible with `tests/native_windows.py`.
Initial Metacity runs failed because GTK presentation time was zero. The new
opt-in JWM extended frame-feedback path now passes three sampled native X11/GLX
round trips covering all four hosts: Forge↔Anvil, Ember↔Forge and Frost↔Forge.
Each also passes four-second SIGSTOP blocking and daemon SIGKILL/restart recovery.
The identical JWM binary without feedback still fails the strict transfer gate.
Ember's real task-canvas smoke also exposed and fixed an 88px padding cap that
could never fit the shared 242px-tall atlas. Its focused six geometry/guard
regressions pass; the broader UI suite is 77 pass / 2 fail, with both failures
reproduced on a separate clean source baseline. JWM's compositor scope passes
297 tests and strict all-target Clippy; XCB compilation passes separately.

These are native submission/sample checks, not physical scanout or continuous
pixel-uniqueness certificates. The compositor-owned body's stronger retirement
capability remains unchanged. Multi-instance/split, hardware/Wayland/IME/audio/API
and performance gates remain open. See [the full requirement ledger](implementation-status.md)
and [the new check manifest](evidence/native-frame-checks-2026-10-30.json).

The remainder records earlier cloud-workspace evidence and its original limits.

Current focused result (protocol/core/client/daemon; sibling memory/openai/atlas package tests reported separately): **41 focused tests passed**, and `cargo clippy -p companion-protocol -p companion-core -p companion-client -p jcompaniond --all-targets -- -D warnings` passed. Log: `tests/coordination-test-results.txt`.

Executed in this cloud workspace: Rust workspace builds/tests, pure deterministic traces (63 seeds ×1024 state transitions), identity/restart reducer behavior, invalid exact proofs, suppressed/target-disconnected transitions, journal invariant and counter exhaustion rejection, file durability/load, exclusive profile lock, corrupt journal rejection, simulated storage-write failure, bounded transport socketpair and queue tests, geometry input exclusion, behavior hard priorities and virtual time.

Prepared `tests/fault_processes.py` runs actual Unix IPC with a child host SIGSTOP/SIGCONT, daemon SIGKILL, exact old-token recovery, malformed proof, second profile lock rejection and disconnect blocking. **Not passed in this sandbox:** AF_UNIX socket creation returns EPERM. Run in a supported environment:

```sh
cargo build -p jcompaniond
XDG_SESSION_ID=eva-fault-test python3 tests/fault_processes.py target/debug/jcompaniond
```

These synthetic hosts acknowledge protocol retirement; even a successful process test would not establish native pixel removal. Real GTK/egui/iced/JWM windows, hardware GPU/scanout, Wayland/X11, IME, suspend/resume, multi-monitor and audio device tests require separate evidence. No physical uniqueness, 300ms transfer latency, frame-cost, 30minute idle network, or hardware audio-stop benchmark is claimed by these tests.

Additional executed coverage: queued Hidden/lock Recall without proof bypass, scene same-token suppression, idempotent durable retirement acknowledgement after restart, 129-reply backpressure isolation, handshake controls waiting for Accepted boot, final complete frame before EOF, exact task sharing/collision persistence, archived management grants not usable as model access, and memory reopen/expiry in Unix epoch milliseconds.

Packaging verification: relocated atlas plus exact Git-pinned jagent source passed **71 workspace tests** (including atlas, memory and provider fixtures). See `tests/relocated-workspace-results.txt`. This is synthetic/offline coverage, not live IPC/hardware acceptance.

## Archived scope discovery follow-up

The complete relocated workspace passes 73 tests and strict workspace Clippy after the paginated persisted-scope discovery addition. See `tests/scope-discovery-workspace-results.txt` and `tests/scope-discovery-clippy-results.txt`. This includes expired project-only scopes and management while paused; discovery never grants model retrieval. Native GUI, physical audio/GPU and live provider acceptance remain unverified. The CI workflow runs the self-contained local IPC fault contract on its runner; that result must be checked separately and is not native pixel proof.


## GTK shell-job lifecycle checkpoint (2026-10-31)

Scope correction: both applications normalize ordinary `--mode vte` to Block.
The archived reports below retain their original labels, but their VTE-labelled
runs were additional Block runs. They do not establish conventional VTE coverage.
Current revalidation uses the supported safe-mode entry and kernel backend evidence.

See [the machine report](evidence/gtk-jobs-checks-2026-10-31.json) for the exact binaries,
28 accepted native executions and eight matching old-binary failures. Each Forge/Anvil launch label
uses native jsh input in private X11/DBus/HOME directories. The final whole-window close
may require its real confirmation dialog when an empty prompt cannot be established.

`python3 scripts/vendor-process-adapter.py /path/to/family` checks canonical-source parity;
`python3 tools/check-process-bundle.py` in each GTK frontend checks its frozen local bundle.
Normal VTE children have an exclusive application reaper. Their observed parent exit and
full-session drain precede the emitted VTE exit notification. A pre-watch acquisition
failure remains an explicitly limited emergency path.

The fixture retains raw palette groups and PNG hashes. Its full-size Cat classification
excludes small same-colored GTK labels and still checks the previously occupied rectangle
for residue. It is bounded to this fixed-size fixture, not continuous/physical uniqueness.
GDK timing receipts plus exact-token acknowledgements are not trusted compositor certificates.
Existing Eva Clippy exceptions, interrupted builds and all earlier diagnostic failures are
listed separately; they are not counted as passed checks. Last-tab, late-job, multiwindow,
remote, provider and performance acceptance remain open.


## GTK detached-pane ownership checkpoint (2026-10-31)

[The machine report](evidence/gtk-close-checks-2026-10-31.json) separates 16 old-binary
controls (eight passes, eight failures), 16 last-tab/split native cases and 28 whole-window
job regressions. Cancellation preserves the original shell and work; confirmation uses
the real dialog and old-token native retirement before a survivor acquires.

Per-window retained child handles survive model/widget removal. An empty current tab list
joins any pending drain; later detached handles join the same wait. Real GTK tests exercise
reentrant completion, duplicate closes and a live unrelated child in another window object.
These are ownership tests, not full same-process multiwindow or new-work-during-withdrawal
acceptance. Batch-close code uses the same retention path; native multi-selection remains
separate. Legacy Eva Clippy exceptions are explicit. No process-hygiene observation is used
as a presentation or destruction certificate.

## 2026-10-31 GTK withdrawal resumption and bodyless offline close

Historical GTK reports labelled --mode vte actually exercised the public Block alias; they
do not establish conventional VTE coverage. Raw reports remain immutable. Current VTE
cases use the supported --safe-mode entry point, a private PATH sh symlink to the exact
recorded jsh executable, and /proc evidence of the application-owned VTE reaper thread.
Final production GTK binaries pass 84 private-native executions; eight failing old controls remain
separate. Same-window/host/shell/connection recovery, new work during pending native clearance,
bodyless offline shutdown, and owned-body shutdown requiring fresh reconnect proof are checked.
Current frontend/package QA totals 152 test executions with the three stated existing Clippy lint
exceptions; current family matrix is eight GUIs and 32 distinct PTYs. Evidence:
[gtk-resume-checks-2026-10-31.json](evidence/gtk-resume-checks-2026-10-31.json).
These gates do not complete the original proposal, trusted C11, physical uniqueness, same-process
multiwindow, real IME/provider/voice/API, P7 performance, or release acceptance.

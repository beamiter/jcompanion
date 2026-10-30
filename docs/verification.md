# Verification scope

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

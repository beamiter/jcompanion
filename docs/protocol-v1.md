# Coordination protocol 1

## Wire and source binding
Linux Unix-domain SOCK_STREAM, big-endian u32 byte length then UTF-8 JSON. Maximum payload 65536 bytes, max 32 peers, 200 received frames/second/peer. Typed structs reject unknown fields; recursive JSON prevalidation rejects duplicate keys. Rectangles must be finite, positive, bounded, with at most 64 candidates/exclusions. Identifier length <=128 and ASCII alphanumeric/`_-.:` only. Host/session/source sequence/event ID bind a connection. Sequence strictly increases, event ID cannot repeat; connection event registry is bounded to 4096 and requires a new connection upon exhaustion. Reconnect receives a fresh boot binding and full snapshot, not unbounded delta replay.

Envelope: protocol_version, event_id, source_id, source_seq, boot_id, session_id, body. Hello uses empty boot; Accepted supplies current boot. All later envelopes require current boot. A retirement **token** intentionally retains the old grant boot during crash reconciliation. Request enum in `companion-protocol/src/lib.rs` is the executable schema; never parse through a permissive Value-to-struct conversion alone.

Both client and server verify same-UID peer credentials. Server additionally compares the connection process's XDG_SESSION_ID and rejects SSH indicators. Socket 0600, app runtime/profile 0700. These constrain accidental cross-session peers, **not malicious same-UID programs**: a process with the user's authority can imitate metadata or fabricate a claimed renderer acknowledgement. No cryptographic/native trust or OS sandbox isolation is promised.

Roles are explicit Hello (native), CompositorHello (scene, only in persisted scene mode), EvaHello (one observation-only audio owner). Eva cannot request a body. Native hosts cannot acquire a body in compositor-only mode. The role is bound at registration, not inferred from a host-name prefix.

## Render handoff
1. Request target after stable focus (200ms, minimum dwell2s) or explicit Recall (bypasses cooldown). StayHere disables automatic focus migration.
2. Prepare carries next epoch; Prepared means readiness only, **never permission to draw**.
3. State persists old possible body + revoke intent, fsync file, rename, fsync directory before Revoke is enqueued.
4. Host synchronously suppresses drawing/interaction/callbacks, then reports Retired with exact companion/host/incarnation/boot/epoch/surface token and nonzero native presentation serial **only after a body-free frame was genuinely submitted/presented according to its capability**.
5. Reducer accepts exact token proof, durably records replacement possible-body grant, then sends Grant. This order deliberately prefers a missing body over a duplicate.
6. Presented marks activity, but is not retirement proof. Old-token callback/click/animation work must remain invalid.

`NativePresented`: renderer has truthfully reached its native successful body-free presentation/submission boundary. This alone is not compositor scanout/GPU completion under arbitrary freezing. `CompositorPresented`: integration has authoritative compositor retirement evidence; not implemented by merely naming this value. `None`: no evidence; native grants denied. Scene-only clean bootstrap may allow one None body, with no ability to retire it by timeout.

Requests: residency, geometry/focus/input, appearance, presence, content-free task observations, session lock/resume, audio observation, resync. Task status comes from bound source metadata; no command/output/cwd is transported. Appearance skin/motion are whitelist-validated and persisted once for all hosts. Audio speaking requires nonzero actual played counter; connecting/generated samples alone never imply listening/playback. Turn counter regression/replay is rejected, disconnect clears audio posture.

Passive geometry/focus are latest-value coalesced client-side before serialization. Retirement/task/control frames are never silently evicted. Queue max128; saturation returns explicit backpressure, and an integration unable to retry must disconnect/hide rather than pretend success. Daemon queue saturation terminates fail-closed with the durable possible body retained. No approval/execution messages exist in this foundational protocol; adding one requires a reviewed bounded control lane, not reusing geometry.

## Explicit desktop observer and healthy close
`DesktopHello` is a separate no-body role. It must originate from the exact executable configured by `EVA_COMPANION_DESKTOP_EXE` (absolute path matched against SO_PEERCRED PID's `/proc/PID/exe`) and the bound graphical session. Only that role may publish SessionLock/Resume; native hosts cannot grant themselves desktop-observer authority. CompositorHello also requires this executable allowlist. This is application provenance, not protection against a malicious same-UID process.

The real JWM observer is independently opt-in (`JWM_COMPANION_OBSERVER=1`, or scene mode) and detects suspend using kernel BOOTTIME versus MONOTONIC offset, not an Instant gap. Once observed, lost desktop status persists as unknown: data/model/voice starts and new residence are blocked until authoritative status returns. Lock cancels text work and withholds late generated text. Before an observer is configured, global lock detection is not claimed; native visibility and actual integration still require testing.

Native lock/Hidden revoke and require retirement. A compositor-only already-authorized current-boot scene may retain **the same token** while locally suppressed by lock or Hidden. It cannot grant another body. Unhide resumes only that retained token; snapshots never grant. Any uncertain disconnect/restart still records a possible body and requires real retirement evidence.

Recall unhides presentation but never unlocks the desktop or waives old removal proof. At most one original-host/incarnation recall is queued while blocked and is canceled on host/context destruction. It prepares only once the old body is proven retired and geometry is safe.

Withdraw marks the source unavailable and cancels speculative placement without setting global Hidden. The old owner must submit a real body-free frame and exact Retired proof before `RetirementAccepted`; `WithdrawalAccepted{host_id,incarnation}` is emitted only when that host has no possible body. Last64 accepted retirement tokens are durable and support idempotent ack replay after an acknowledgement is lost; this is evidence reuse, not timeout inference. Older evicted acknowledgements can conservatively require operator/native evidence handling.

Output backpressure is connection-local. An overfull/malformed/slow peer is disconnected, its possible body remains conservatively in recovery, and healthy peers/authority continue. Revoke/review/result messages are never silently discarded while pretending the connection is healthy. Ordinary operation errors use OperationError; Rejected is reserved for terminal registration/session failures and is followed by teardown.

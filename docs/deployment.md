# Opt-in deployment and diagnostics

This is source-preview integration, not hardware acceptance. Protocol version: **1**.
All hosts and the daemon must use a compatible release snapshot. Do not combine
an old independent pet with shared mode. Cargo fetches exact Git revisions from
published manifests; a sibling checkout is not required in a pinned release.

## Build and run

```sh
git clone https://github.com/beamiter/jcompanion.git
cd jcompanion
# Select the exact reviewed release commit, not a moving branch, for deployment.
cargo test --workspace --locked
cargo build --release --locked -p jcompaniond
install -d -m 755 "$HOME/.local/bin"
install -m 755 target/release/jcompaniond "$HOME/.local/bin/jcompaniond"
umask 077
mkdir -p "$HOME/.local/state/jcompanion-eva"
chmod 700 "$HOME/.local/state/jcompanion-eva"
# Run from the selected graphical session; XDG_SESSION_ID must be set.
"$HOME/.local/bin/jcompaniond" "$HOME/.local/state/jcompanion-eva"
```

This does not install/enable a service, modify terminal settings, or configure a
provider. Keep existing settings and private profile data when upgrading. For
custom XDG state paths pass the actual private profile explicitly. Provider
configuration is described in [companion-openai](../crates/companion-openai/README.md).
No key belongs in version control, frontend config, diagnostics or command arguments.

Launch upgraded frontends from the same graphical session with
`EVA_COMPANION_MODE=shared`. The default socket is
`$XDG_RUNTIME_DIR/jcompanion/eva.sock`; a custom `EVA_COMPANION_SOCKET` must match
in daemon and all clients and have an owned, private parent. The daemon refuses
cross-session peers. Existing JWM Eva voice installation is separate; this daemon
is not a replacement microphone or speech service.

## Optional user service (manual review only)

`packaging/jcompanion.service` is a **template**, not installed or enabled by any
script. It assumes the standard home-local paths above and one graphical session.
Review those paths, copy it to `~/.config/systemd/user/`, then from that session
import only the required session variables and explicitly start it:

```sh
systemctl --user import-environment XDG_SESSION_ID XDG_RUNTIME_DIR
systemctl --user daemon-reload
systemctl --user start jcompanion.service
```

Never import the full shell environment or provider secrets. Do not enable this
unit for login-wide or multiple-session startup: a user manager can outlive a
specific graphical session. Stop it before changing sessions. The template has no
automatic restart or enable target, so persisted recovery uncertainty is visible.

## Diagnosis

- `systemctl --user status jcompanion.service` / `journalctl --user -u jcompanion.service`:
  inspect locally; redact paths, prompts, IDs and environment before sharing.
- Socket errors: verify same UID, graphical session, matching socket override,
  profile mode 0700, socket mode 0600, and no second daemon/profile owner.
- No body after crash/disconnect: see [recovery](recovery.md). A missing/frozen
  former owner blocks replacement. **Do not delete residence.json to force a grant.**
- No reply: offline is the default; check explicit provider enable/model settings,
  private daemon credential availability and bounded request budget. Synthetic tests
  do not establish live model compatibility or paid API behavior.
- Run `cargo test --workspace --locked` for deterministic unit coverage. Run
  `tests/fault_processes.py` only in an environment permitting Unix sockets; this
  fixture does not verify real pixels or compositor fences.

Known limits: real multiwindow IPC faults, GPU/scanout, IME, monitor transitions,
physical audio and live provider behavior remain unverified. Native submission is
not proof of physical scanout removal. General recovery from permanently lost
ownership evidence is intentionally fail-closed, not a completed recovery UI.

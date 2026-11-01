# Eva Companion coordinator

Local Rust coordination foundation for one Eva across GUI hosts. **Enabled by default in the four terminals; started by JWM**. Default offline mode opens no network or audio. Optional explicitly configured Responses requests run in a bounded worker; GUI/renderer processes receive no provider credentials. No arbitrary shell executor exists. Source: https://github.com/beamiter/jcompanion. See [deployment](docs/deployment.md) for installation and diagnostics.

**Before enabling shared mode:** close/disable legacy independent pets and upgrade all open terminal instances. This protocol cannot remotely silence an older pet that never registered. Keep the existing local-only fallback explicitly OFF in shared mode.

```sh
cargo test --workspace
cargo build -p jcompaniond
mkdir -m 700 -p "$HOME/.local/state/jcompanion-eva"
# Run inside the one selected graphical session with XDG_SESSION_ID set.
./target/debug/jcompaniond "$HOME/.local/state/jcompanion-eva"
# Frontends explicitly opt in:
export EVA_COMPANION_MODE=shared
```

Default socket: `$XDG_RUNTIME_DIR/jcompanion/eva.sock`; without runtime directory: `PROFILE/companion.sock`. `EVA_COMPANION_SOCKET` overrides both ends; its parent must already be owned/private. Profile directory must be owned, nonsymlink, 0700. No OS security configuration is changed.

`EVA_COMPANION_REQUIRE_COMPOSITOR=1` persists the requirement for compositor retirement evidence. Normal native mode allows truthful native body-free presentation submission evidence, **not** guaranteed physical scanout removal. Frozen or disconnected owners always block new grants; no timeout permits a replacement body.

Before compositor-only launch, retire all native bodies with actual presentation evidence; an unknown old body still blocks entry. Set `EVA_COMPANION_DESKTOP_EXE` to the absolute actual JWM executable for the privileged observer/scene role.

`jcompaniond PROFILE --compositor-only` (or `EVA_COMPANION_COMPOSITOR_ONLY=1`) persists scene-only grants. Native hosts become anchor-only. A scene registering retirement `none` may acquire a first body only from an empty recovered journal; it cannot provide retirement evidence afterward. This restricted bootstrap is not proof that a compositor renderer has implemented presentation fences. Mode entry retains/reconciles every previously possible body; it never clears the journal to force progress.

## Packages
- `companion-protocol`: strict bounded versioned JSON, identities, roles, no arbitrary execution messages.
- `companion-core`: pure staged residence transitions, geometry and virtual-clock behavior.
- `companion-client`: nonblocking bounded Unix transport, passive geometry/focus coalescing, peer/path checks.
- `jcompaniond`: exclusive profile/runtime/socket authority, durable write-ahead residence checkpoint, singleton Eva observation role.

See [protocol](docs/protocol-v1.md), [recovery](docs/recovery.md), and [verification](docs/verification.md). The reviewed SQLite memory store and optional Responses worker are connected through explicit cards/consent IPC; see [cards and consent](docs/cards-and-consent.md). Native controls and real API/audio/pixel evidence require their separate validation; this is not a claim of full hardware acceptance.

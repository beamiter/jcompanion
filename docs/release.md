# Reproducible family publication

Publish this repository first. Record its immutable commit; do not publish sibling
path dependencies or a guessed future revision. From a family checkout parent:

```sh
python3 jcompanion/scripts/pin-family.py . --companion-rev FULL_PUBLISHED_SHA
# Review dry-run list, then repeat with --write.
```

Refresh/check jterm_core's lockfile against that commit, run its tests, and publish
jterm_core next. Then use `--core-rev FULL_PUBLISHED_CORE_SHA --write` to pin the
four terminal applications (including dev dependencies and test harnesses). The
JWM/Eva manifests depend directly on companion protocol/client and atlas. Cargo
fetches those pinned sources during source-install builds; installers do not need
an unversioned sibling clone. Prebuilt installers need no Rust dependency checkout.
Do not change users' existing settings or install/start services during packaging.

For every affected repository regenerate its lockfile without blanket upgrades,
check Cargo metadata, run relevant tests and native checks, and reconcile existing
`deny.toml` source allowlists and Nix `cargoLock.outputHashes` where applicable.
A changed Git source requires a real Nix output hash; never ship a fake hash as a
verified working Nix release. Existing vendored upstream licenses/integrity must
remain intact. Native toolchain libraries are platform requirements, not bundled
by this coordinator. Unverified build backends must remain explicitly marked.

`release-manifest.py FAMILY_PARENT > release-manifest.json` records each base
commit, dirty state, tracked binary-diff hash and SHA-256 of every Git-visible
source file. Write the output **outside** those repositories to avoid a self-hash.
Regenerate after owner edits and final pins; a snapshot is not a claim of a clean
release. Do not publish local profiles, keys, generated caches or the original
design HTML. Compact original ASCII/provenance and derived QA sheets are retained.

Atlas heavy exports are intentionally ignored. From `crates/eva-character-atlas`:

```sh
cargo run --locked --example export > qa/frames.json
cargo run --locked --example export -- --moods > qa/moods.json
python3 tools/preview.py  # requires Pillow and DejaVu system fonts
```

This regenerates the gallery/contact sheets from actual cell buffers. Derived
animation is not claimed to be extracted original animation.

For local development use a temporary, uncommitted Cargo patch config mapping
`https://github.com/beamiter/jcompanion.git` packages to the corresponding local
`jcompanion/crates/*` paths and `https://github.com/beamiter/jterm_core.git` to the
local core. Do not publish patched lockfiles as immutable-release verification.

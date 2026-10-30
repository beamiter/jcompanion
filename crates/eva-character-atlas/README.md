# Eva character atlas

A dependency-free Rust character/animation library for the **same Eva identity**.
It does not own presence, input focus, audio, tasks, model calls, IPC, or clocks.

## What is original, and what is derived

`design/original-ascii-skins.json` is the exact eight sketches from the supplied
HTML's `characterData`; `Skin::original_sketch()` reproduces them byte for byte,
including the ghost's unusual ` .----- .`. The accompanying original provenance
file is copied unchanged. Those are compact engineering sketches, not animation
frames.

`tools/art.py` contains **48 hand-authored anatomical templates** derived from
actual inspection of figure-4 and figure-5. `src/art.rs` is generated from it.
The rich renderer turns their contours into dense ASCII glyph clusters and adds
bounded, per-cell-colored features. These are new artistic implementations,
**not pixel-identical raster reconstructions, and not extracted original frames**.
No reference image is included in the runtime rendering path. The original
compact art remains separate and unmodified.

## Integration

```rust
use eva_character_atlas::{sample, Request, Skin, Pose, Motion};
let mut request = Request::new(Skin::Cat, Pose::Listen);
request.motion = Motion::Calm;
request.elapsed_ms = 450; // monotonic elapsed time since this action began
if let Some(frame) = sample(request) {
    let palette = request.skin.palette(false);
    for (i, cell) in frame.cells.iter().enumerate() {
        let (column, row) = (i % frame.width, i / frame.width);
        let rgb = palette.color(cell.ink);
        // Draw cell.glyph at (column,row) with rgb, in ONE authorized overlay.
        let _ = (column, row, rgb);
    }
    // Schedule only frame.next_frame_in_ms, if Some. No unconditional frame loop.
}
```

The stable output is 40×22 **printable ASCII** cells: no ambiguous-width Unicode,
combining marks, emoji, control characters, or embedded line breaks. Shape at the
host's chosen monospace font; measure one cell and preserve its aspect ratio.
`Frame::lines()` is for plain-text fallback; native renderers should use `cells`
to retain the six palette roles and `accessible_label`. Cache shaping by actual
frame cells / font / scale, not whole terminal content. High contrast is available
through `Skin::palette(true)`. Native accessibility must expose the text label;
failure, listening, speech and direction are not communicated only through color.

- `Skin::ALL`, `Skin::key/name/from_key`, `Pose::ALL/key/from_key` support pickers.
- Aliases: `classic_cat_dango` → `cat`; `night_cat` → `night`.
- `sample(Request)` is deterministic and has no external side effects.
- Hidden returns `None`; Static and reduced-motion return a stable representative
  frame with **no next callback**. Full has body displacement; Calm removes idle
  translations and halves cadence. Night halves cadence again and has lower light.
- One-shot poses finish and stop scheduling. No missed-frame queue exists; rebase
  elapsed time on suspend/resume rather than replaying elapsed actions.
- `seed` changes only bounded eligible decorative variation, never safety/ownership.
- At most eight isolated celebration/stardust sparkle glyphs. No face-containing
  particles, split bodies, clones, crossover fades, or secondary life instances.
- The host must revoke drawing/interaction/timers on loss of residence authority.
  This crate cannot establish that authority and must never be used as fallback
  permission to draw when a coordinator disconnects.

## Anatomical vocabulary

| Skin | Preserved figure-4 identity | Whole-body interpretation |
|---|---|---|
| Cat | broad round body, twin short ears, whiskers, short feet, thin hooked tail | seated paws, enclosed curl, tall stretch, four-leg stride, tucked retreat |
| Fox | oversize pointed pale ears, tapered muzzle, pale bib, broad pale-tipped brush | brush wraps curled body, long running body, braced forepaws, lifted stretch |
| Robot | cyan capsule, antenna light, inset face-screen, ear modules, docking slots | lowered shell, retractable foot modules, lifted arms, alternating leg modules |
| Ghost | lilac dome, pink cheeks, mitten arms, scalloped hem, no feet | flattened hide/curl, lengthened float, rising arms, waving hem |
| Cursor | hollow mint diagonal arrow with notch and stem | compressed triangle, elongated triangle, offset stepping pointer; never a round face |
| Beetle | amber low segmented shell, curled antennae, six mechanical limbs | retracted shell/legs, elevated shell, alternating feet and antenna attitude |
| Night | narrow tall purple cat, long curled tail, bright eyes | alert seated chest, side-on four-leg walk, low tail-wrapped sleep |
| Stardust | one crowned floating orb, purple/cyan specks | compressed/resting orb, stretched glow, one drifting body with finite orbit points |

## Poses, expressions and truth boundaries

All 13 required poses exist for all eight skins: idle, blink, peek, sit, curl_up,
stretch, retreat, walk, listen, speak, guard_failure, celebrate_briefly, look_at.
Walk is look → prepare → two alternating steps → sit. Sit/curl have transition
frames; stretch and celebration return to a low resting form. Peek preserves an
intact silhouette beside an edge. Failure uses a lowered body/cloud, never a false
success gesture. Voice marks are symbolic; no invented amplitude or lip sync.

The optional unlabeled footer expressions are exposed as **art-only** `Mood`,
not invented daemon/work states:

| Mood | Rendering |
|---|---|
| Neutral | skin-specific eyes and mouth |
| Sleepy | tucked curl, lowered eyes, z/Z |
| Affectionate | seated warmth, smiling eyes, ASCII heart `<3` |
| Curious | asymmetric questioning eyes and `?` |
| Surprised | extended body, wide eyes, `!!` |
| Tense | contracted body, tight mouth, `!` |
| Angry | braced seated body, inward brows, `!` |
| Happy | lifted body, smiling eyes, sparkle |
| Shy | seated body, lowered eyes, small blush mark |

Mood changes whole-body anatomy only in idle. Explicit voice/task/retreat poses
remain authoritative. These expressions are behavior simulation, not consciousness
claims or diagnoses of the user. Actual work facts and device events must be mapped
by the coordinator; generated text ending does not mean task success, connecting
does not mean microphone listening, and unknown must never map to failure.

## Reproduce validation and evidence

```sh
cargo test
cargo clippy --all-targets -- -D warnings
cargo run --example export > qa/frames.json
cargo run --example export -- --moods > qa/moods.json
python tools/preview.py # requires Pillow; runtime Rust has no dependencies
```

`qa/gallery.html` is a static contact gallery of actual Rust output, not a runtime
multi-body UI. `qa/eight-skins.png`, `*-poses.png`, `*-moods.png`, and `*-motion.png`
record render specimens; timestamps, frame index, seed and mode are printed.
`qa/eight-skins-line-study.png` preserves the earlier thin-contour study for A/B.
`frames.json` exports every action-frame boundary in Full/Calm plus all Static
representatives (888 frames); `moods.json` adds 72 expression specimens.

Pure atlas tests and rasterized cell previews do **not** establish native font,
GTK/egui/iced GPU, HiDPI, IME, physical handoff, audio, or frame-time acceptance.
Those require each host's integration evidence. This atlas is not the complete
Eva system by itself.

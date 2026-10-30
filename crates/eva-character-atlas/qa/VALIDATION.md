# Atlas validation record — 2026-10-30

## Passed locally

- Rust 1.99.1: `cargo test` (10 tests), `cargo clippy --all-targets -- -D warnings`.
- Exact original eight compact sketches preserved (golden literals including spaces).
- 48 anatomical templates: one face window each; ASCII only; <=31×13 local cells.
- Eight skins × 13 poses × Full/Calm/Static × 9 moods × 10 boundary/large times.
- Fixed 40×22 output; printable ASCII only; bounded positive callback intervals.
- Invisible returns no frame; Static and reduced-motion return no future callback.
- All six principal anatomical forms differ for each individual skin.
- One-shot terminal times (including u64::MAX) stop scheduling, no queued catch-up.
- Reproducibility for identical time/seed; isolated stardust face region, never clones.
- Actual Rust export: 888 pose-frame specimens and 72 optional mood specimens.

## Direct visual review and corrections

The actual supplied figure-4 and figure-5 image pixels were inspected first, along
with complete design prose and requirements, not just thumbnails/descriptions.

Reviewed actual rendered overview and individual sheets for eight skin silhouettes
and all 13 poses. Initial thin line study had insufficient contour weight compared
to figure-4. Revised rendering uses dense ASCII contour clusters, accent inner
edges, tall bright eyes, fox pale details, ghost blush/hem, robot segmented capsule,
beetle shell, night long tail, and single crowned orb. The old study is retained
only as A/B evidence, not the final art. Corrected a row-shift peek that broke the
cursor's outline and blocked decorative effects from overwriting body glyphs.

The sheets are program output, not the original figure images. They are artistic
reference-derived reproductions, not a claim of exact pixel equivalence. All source
compact sketches remain untouched. High-contrast colors are exposed and tested as
palette data; cross-host font/scale rendering is a separate native gate.

## Not established by this evidence

No claim of native widget/input/GPU/HiDPI/IME, runtime performance percentiles,
physical visible-single-body handoff, hardware audio, compositor behavior, or
whole-project completion. A host must enforce valid residence and no stale callback.
These static contact sheets intentionally show multiple **specimens**, not a live
multi-body application or runtime duplication.

use companion_protocol::Rect;
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Placement {
    Body(Rect),
    Compact(Rect),
    Hidden,
}
/// Candidates are ordered edge-first, then stable block whitespace. No reading anchor changes.
pub fn choose(
    viewport: Rect,
    candidates: &[Rect],
    exclusions: &[Rect],
    body: (f64, f64),
    compact: (f64, f64),
) -> Placement {
    if !viewport.valid() || exclusions.iter().any(|r| !r.valid()) {
        return Placement::Hidden;
    }
    for (size, small) in [(body, false), (compact, true)] {
        if !size.0.is_finite() || !size.1.is_finite() || size.0 <= 0.0 || size.1 <= 0.0 {
            continue;
        }
        for c in candidates {
            let r = Rect {
                x: c.x,
                y: c.y,
                width: size.0,
                height: size.1,
            };
            if c.valid()
                && c.contains(r)
                && viewport.contains(r)
                && !exclusions.iter().any(|e| r.overlaps(*e))
            {
                return if small {
                    Placement::Compact(r)
                } else {
                    Placement::Body(r)
                };
            }
        }
    }
    Placement::Hidden
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn input_protected() {
        let r = Rect {
            x: 0.0,
            y: 0.0,
            width: 100.0,
            height: 100.0,
        };
        assert_eq!(
            choose(r, &[r], &[r], (20.0, 20.0), (5.0, 5.0)),
            Placement::Hidden
        );
    }
}

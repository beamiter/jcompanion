//! Pure local rendering; no I/O, timers, authority, task inference or audio ownership.
//! All glyphs are printable ASCII, hence unambiguous single-cell monospace width.
//! A host must have current residence authority before calling or presenting sample.
mod art;
pub const WIDTH: usize = 40;
pub const HEIGHT: usize = 22;
pub const MAX_PARTICLES: usize = 8;
pub const PROVENANCE: &str = "implementation-derived; figure-4 anatomy and figure-5 pose grammar; not extracted raster frames";
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(usize)]
pub enum Skin {
    Cat,
    Fox,
    Robot,
    Ghost,
    Cursor,
    Beetle,
    Night,
    Stardust,
}
impl Skin {
    pub const ALL: [Self; 8] = [
        Self::Cat,
        Self::Fox,
        Self::Robot,
        Self::Ghost,
        Self::Cursor,
        Self::Beetle,
        Self::Night,
        Self::Stardust,
    ];
    pub fn key(self) -> &'static str {
        [
            "cat", "fox", "robot", "ghost", "cursor", "beetle", "night", "stardust",
        ][self as usize]
    }
    pub fn name(self) -> &'static str {
        [
            "经典猫团子",
            "像素小狐狸",
            "胶囊机器人",
            "软糯幽灵",
            "极简光标精灵",
            "机械小甲虫",
            "夜行小猫",
            "星尘团子",
        ][self as usize]
    }
    pub fn from_key(key: &str) -> Option<Self> {
        match key {
            "classic_cat_dango" => Some(Self::Cat),
            "night_cat" => Some(Self::Night),
            _ => Self::ALL.into_iter().find(|s| s.key() == key),
        }
    }
    /// Verbatim source sketch including all original spaces and ghost punctuation.
    pub fn original_sketch(self) -> &'static str {
        art::ORIGINAL[self as usize]
    }
    pub fn palette(self, high_contrast: bool) -> Palette {
        if high_contrast {
            return Palette {
                colors: [
                    [240, 248, 255],
                    [255, 255, 255],
                    [148, 255, 221],
                    [255, 255, 255],
                    [181, 197, 215],
                    [255, 230, 140],
                ],
            };
        }
        let colors = match self {
            Self::Cat => [
                [191, 238, 226],
                [245, 255, 251],
                [124, 224, 204],
                [244, 255, 252],
                [114, 163, 158],
                [255, 177, 201],
            ],
            Self::Fox => [
                [238, 151, 83],
                [255, 227, 184],
                [180, 100, 63],
                [255, 239, 207],
                [142, 95, 69],
                [255, 194, 98],
            ],
            Self::Robot => [
                [116, 210, 235],
                [214, 251, 255],
                [77, 172, 211],
                [162, 243, 255],
                [65, 118, 141],
                [125, 229, 255],
            ],
            Self::Ghost => [
                [209, 161, 235],
                [255, 222, 248],
                [229, 160, 217],
                [245, 204, 255],
                [126, 91, 149],
                [245, 183, 226],
            ],
            Self::Cursor => [
                [113, 235, 206],
                [207, 255, 240],
                [70, 189, 168],
                [183, 255, 231],
                [60, 130, 122],
                [131, 255, 221],
            ],
            Self::Beetle => [
                [225, 187, 80],
                [255, 238, 156],
                [165, 128, 46],
                [255, 238, 159],
                [127, 107, 57],
                [247, 209, 103],
            ],
            Self::Night => [
                [131, 105, 193],
                [184, 153, 231],
                [93, 78, 148],
                [207, 173, 255],
                [77, 67, 113],
                [177, 158, 233],
            ],
            Self::Stardust => [
                [204, 153, 237],
                [250, 224, 255],
                [115, 213, 239],
                [246, 220, 255],
                [123, 99, 160],
                [158, 239, 248],
            ],
        };
        Palette { colors }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(usize)]
pub enum Pose {
    Idle,
    Blink,
    Peek,
    Sit,
    CurlUp,
    Stretch,
    Retreat,
    Walk,
    Listen,
    Speak,
    GuardFailure,
    CelebrateBriefly,
    LookAt,
}
impl Pose {
    pub const ALL: [Self; 13] = [
        Self::Idle,
        Self::Blink,
        Self::Peek,
        Self::Sit,
        Self::CurlUp,
        Self::Stretch,
        Self::Retreat,
        Self::Walk,
        Self::Listen,
        Self::Speak,
        Self::GuardFailure,
        Self::CelebrateBriefly,
        Self::LookAt,
    ];
    pub fn key(self) -> &'static str {
        [
            "idle",
            "blink",
            "peek",
            "sit",
            "curl_up",
            "stretch",
            "retreat",
            "walk",
            "listen",
            "speak",
            "guard_failure",
            "celebrate_briefly",
            "look_at",
        ][self as usize]
    }
    pub fn label(self) -> &'static str {
        [
            "安静等待",
            "短暂眨眼",
            "好奇探头",
            "放松落座",
            "蜷起休息；任务状态不变",
            "舒展身体",
            "正在让路",
            "向安全锚点随行",
            "正在倾听",
            "正在表达（非唇同步）",
            "任务失败，安静守候",
            "已收到成功回执，短暂庆祝",
            "看向已授权的目标",
        ][self as usize]
    }
    pub fn from_key(key: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|p| p.key() == key)
    }
    pub fn is_looping(self) -> bool {
        matches!(
            self,
            Self::Idle | Self::Listen | Self::Speak | Self::GuardFailure
        )
    }
    pub fn durations(self) -> &'static [u64] {
        match self {
            Self::Idle => &[1800, 260, 1800, 260],
            Self::Blink => &[150, 120, 130, 400],
            Self::Peek => &[180, 220, 650, 200],
            Self::Sit => &[220, 300, 900],
            Self::CurlUp => &[240, 300, 1200],
            Self::Stretch => &[200, 350, 400, 250],
            Self::Retreat => &[100, 120, 200],
            Self::Walk => &[200, 160, 180, 180, 300],
            Self::Listen => &[450, 450, 450, 450],
            Self::Speak => &[300, 260, 300, 260],
            Self::GuardFailure => &[1400, 400, 1400, 400],
            Self::CelebrateBriefly => &[180, 220, 220, 360],
            Self::LookAt => &[160, 500, 200],
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Motion {
    Full,
    Calm,
    Static,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    Left,
    Right,
}
/// Optional artistic expressions from the unlabeled figure-5 footer. Never task facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mood {
    Neutral,
    Sleepy,
    Affectionate,
    Curious,
    Surprised,
    Tense,
    Angry,
    Happy,
    Shy,
}
impl Mood {
    pub const ALL: [Self; 9] = [
        Self::Neutral,
        Self::Sleepy,
        Self::Affectionate,
        Self::Curious,
        Self::Surprised,
        Self::Tense,
        Self::Angry,
        Self::Happy,
        Self::Shy,
    ];
    pub fn key(self) -> &'static str {
        [
            "neutral",
            "sleepy",
            "affectionate",
            "curious",
            "surprised",
            "tense",
            "angry",
            "happy",
            "shy",
        ][self as usize]
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(usize)]
pub enum Ink {
    Outline,
    Highlight,
    Accent,
    Face,
    Dim,
    Effect,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Layer {
    Body,
    Face,
    Effect,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Cell {
    pub glyph: char,
    pub ink: Ink,
    pub layer: Layer,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Palette {
    pub colors: [[u8; 3]; 6],
}
impl Palette {
    pub fn color(self, ink: Ink) -> [u8; 3] {
        self.colors[ink as usize]
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Request {
    pub skin: Skin,
    pub pose: Pose,
    pub motion: Motion,
    pub elapsed_ms: u64,
    pub seed: u64,
    pub visible: bool,
    pub reduced_motion: bool,
    pub mood: Mood,
    pub direction: Direction,
}
impl Request {
    pub fn new(skin: Skin, pose: Pose) -> Self {
        Self {
            skin,
            pose,
            motion: Motion::Calm,
            elapsed_ms: 0,
            seed: 0,
            visible: true,
            reduced_motion: false,
            mood: Mood::Neutral,
            direction: Direction::Right,
        }
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Frame {
    pub cells: Vec<Cell>,
    pub width: usize,
    pub height: usize,
    pub frame_index: usize,
    pub next_frame_in_ms: Option<u64>,
    pub accessible_label: String,
}
impl Frame {
    pub fn lines(&self) -> Vec<String> {
        self.cells
            .chunks(self.width)
            .map(|r| r.iter().map(|c| c.glyph).collect())
            .collect()
    }
    fn put(&mut self, x: i32, y: i32, glyph: char, ink: Ink, layer: Layer) {
        if glyph != ' ' && x >= 0 && y >= 0 && x < WIDTH as i32 && y < HEIGHT as i32 {
            if layer == Layer::Effect && self.cells[y as usize * WIDTH + x as usize].glyph != ' ' {
                return;
            }
            self.cells[y as usize * WIDTH + x as usize] = Cell { glyph, ink, layer };
        }
    }
    fn text(&mut self, x: i32, y: i32, s: &str, ink: Ink, layer: Layer) {
        for (i, c) in s.chars().enumerate() {
            self.put(x + i as i32, y, c, ink, layer);
        }
    }
}
/// Explicit elapsed monotonic time since this action started, never wall clock.
/// Rebase elapsed_ms to zero on resume: missed frames are not queued or replayed.
/// None means no visible body and absolutely no requested animation callback.
pub fn sample(r: Request) -> Option<Frame> {
    if !r.visible {
        return None;
    }
    let still = r.reduced_motion || r.motion == Motion::Static;
    let scale =
        if r.motion == Motion::Calm { 2 } else { 1 } * if r.skin == Skin::Night { 2 } else { 1 };
    let ds = r.pose.durations();
    let total = ds.iter().sum::<u64>() * scale;
    let looping = r.pose.is_looping();
    let mut index = 0;
    let mut next = None;
    if still {
        index = match r.pose {
            Pose::Blink => 1,
            Pose::Sit | Pose::CurlUp | Pose::Retreat => ds.len() - 1,
            Pose::Stretch | Pose::CelebrateBriefly => 1,
            Pose::Walk => 2,
            _ => 0,
        };
    } else if !looping && r.elapsed_ms >= total {
        index = ds.len() - 1;
    } else {
        let mut t = if looping {
            r.elapsed_ms % total
        } else {
            r.elapsed_ms
        };
        for (i, d) in ds.iter().enumerate() {
            let dur = d * scale;
            if t < dur {
                index = i;
                next = Some(dur - t);
                break;
            }
            t -= dur;
        }
    }
    let mut f = Frame {
        cells: vec![
            Cell {
                glyph: ' ',
                ink: Ink::Outline,
                layer: Layer::Body
            };
            WIDTH * HEIGHT
        ],
        width: WIDTH,
        height: HEIGHT,
        frame_index: index,
        next_frame_in_ms: next,
        accessible_label: format!(
            "Eva · {} · {} · {}",
            r.skin.name(),
            r.pose.label(),
            r.mood.key()
        ),
    };
    let mut variant = match r.pose {
        Pose::Sit => {
            if index == 0 {
                0
            } else {
                1
            }
        }
        Pose::GuardFailure => 1,
        Pose::CurlUp => match index {
            0 => 1,
            1 => 5,
            _ => 2,
        },
        Pose::Stretch => {
            if index == 0 || index == 3 {
                1
            } else {
                3
            }
        }
        Pose::Retreat => 5,
        Pose::Walk => {
            if index == 0 {
                0
            } else if index == 1 {
                5
            } else if index == 4 {
                1
            } else {
                4
            }
        }
        Pose::CelebrateBriefly => {
            if index == 3 {
                1
            } else {
                3
            }
        }
        _ => 0,
    };
    // Optional illustrative moods may shape an idle body, never override a work/voice pose.
    if r.pose == Pose::Idle {
        variant = match r.mood {
            Mood::Sleepy => 2,
            Mood::Affectionate | Mood::Shy | Mood::Angry => 1,
            Mood::Surprised | Mood::Happy => 3,
            Mood::Tense => 5,
            _ => variant,
        };
    }
    let moving = !still && r.motion == Motion::Full;
    let mut x = 5;
    let mut y = 5;
    if r.pose == Pose::CelebrateBriefly && index == 1 {
        y -= 1;
    }
    if r.pose == Pose::Retreat {
        x += index as i32;
        y += 2;
    }
    if r.pose == Pose::Walk && moving {
        x += match index {
            2 => 1,
            3 => 2,
            _ => 0,
        };
    }
    if r.pose == Pose::Idle && index % 2 == 1 && moving {
        y -= 1;
    }
    if r.skin == Skin::Ghost && index % 2 == 1 && moving {
        y -= 1;
    }
    let face = face(r, index);
    let body = art::ART[r.skin as usize][variant];
    for (row, line) in body.lines().enumerate() {
        let lean = if r.pose == Pose::Peek {
            if index == 0 {
                1
            } else {
                2
            }
        } else {
            0
        };
        let mut col = 0;
        while col < line.len() {
            if line.as_bytes()[col] == b'F' {
                f.text(
                    x + col as i32 + lean,
                    y + row as i32,
                    face,
                    Ink::Face,
                    Layer::Face,
                );
                if face.starts_with('0') {
                    for eye in [0, 6] {
                        f.put(
                            x + col as i32 + lean + eye,
                            y + row as i32 - 1,
                            '#',
                            Ink::Face,
                            Layer::Face,
                        );
                    }
                }
                col += 7;
                continue;
            }
            let mut c = line.as_bytes()[col] as char;
            // Alternate the anatomical legs, tail tip, antennae or skirt, not just the face.
            if index % 2 == 1 && matches!(r.pose, Pose::Walk | Pose::Listen | Pose::Speak) {
                if row > body.lines().count().saturating_sub(3) {
                    c = match c {
                        '/' => '\\',
                        '\\' => '/',
                        '_' => '-',
                        _ => c,
                    };
                }
                if r.skin == Skin::Beetle && row < 3 {
                    c = match c {
                        '/' => '|',
                        '\\' => '|',
                        _ => c,
                    };
                }
            }
            // Dense character-pixel contour, matching the reference's luminous glyph clusters.
            // The authored ASCII skeleton retains anatomical topology; runtime art is still
            // printable ASCII cells, not a bitmap or Unicode ambiguous-width block.
            let ink = match c {
                '.' if r.skin == Skin::Fox || r.skin == Skin::Stardust => Ink::Highlight,
                '.' if r.skin == Skin::Ghost => Ink::Accent,
                ':' if r.skin == Skin::Fox => Ink::Highlight,
                ':' => Ink::Accent,
                '=' | '#' | '[' | ']' => Ink::Highlight,
                '/' | '\\' if r.skin == Skin::Robot => Ink::Accent,
                'o' if matches!(r.skin, Skin::Robot | Skin::Beetle) => Ink::Highlight,
                '.' | '\'' => Ink::Outline,
                _ => Ink::Outline,
            };
            let dense = match c {
                '/' | '\\' | '|' | '_' | '-' | '\'' | '(' | ')' => '#',
                '.' if r.skin != Skin::Ghost && r.skin != Skin::Stardust && r.skin != Skin::Fox => {
                    '#'
                }
                '=' => '=',
                ':' => {
                    if r.skin == Skin::Fox {
                        '%'
                    } else {
                        '#'
                    }
                }
                _ => c,
            };
            let limb_offset =
                if index % 2 == 1 && r.pose == Pose::Walk && row + 2 >= body.lines().count() {
                    if col < line.len() / 2 {
                        -1
                    } else {
                        1
                    }
                } else {
                    0
                };
            f.put(
                x + col as i32 + lean + limb_offset,
                y + row as i32,
                dense,
                ink,
                Layer::Body,
            );
            // A restrained inner contour halo is made of real ASCII cells, not image glow.
            if dense == '#' && limb_offset == 0 {
                let first = line.bytes().position(|b| b != b' ').unwrap_or(0);
                let last = line.bytes().rposition(|b| b != b' ').unwrap_or(0);
                let inner =
                    if col == first && col + 1 < line.len() && line.as_bytes()[col + 1] == b' ' {
                        Some(col + 1)
                    } else if col == last && col > 0 && line.as_bytes()[col - 1] == b' ' {
                        Some(col - 1)
                    } else {
                        None
                    };
                if let Some(inner) = inner {
                    f.put(
                        x + inner as i32 + lean,
                        y + row as i32,
                        ':',
                        Ink::Accent,
                        Layer::Body,
                    );
                }
            }
            col += 1;
        }
    }
    // Decorations carry no eyes, mouth, character silhouette or independent life.
    match r.pose {
        Pose::Peek => {
            for yy in 5..19 {
                f.put(5, yy, '|', Ink::Dim, Layer::Effect);
            }
            f.text(30, 5, "?", Ink::Effect, Layer::Effect);
        }
        Pose::Listen => {
            f.text(
                1,
                9,
                if index & 1 == 0 { "((" } else { " (" },
                Ink::Effect,
                Layer::Effect,
            );
            f.text(
                35,
                9,
                if index & 1 == 0 { "))" } else { ") " },
                Ink::Effect,
                Layer::Effect,
            );
        }
        Pose::Speak => {
            f.text(31, 4, ".----.", Ink::Effect, Layer::Effect);
            f.text(31, 5, "|... |", Ink::Effect, Layer::Effect);
            f.text(30, 6, "/----'", Ink::Effect, Layer::Effect);
        }
        Pose::GuardFailure => {
            f.text(12, 1, ".-----.", Ink::Dim, Layer::Effect);
            f.text(11, 2, "(_______)", Ink::Dim, Layer::Effect);
            f.text(
                12,
                3,
                if index & 1 == 0 { "' ' '" } else { " ' ' " },
                Ink::Dim,
                Layer::Effect,
            );
        }
        Pose::CurlUp => f.text(30, 5, "z Z", Ink::Dim, Layer::Effect),
        Pose::Retreat => f.text(1, 15, "--", Ink::Dim, Layer::Effect),
        Pose::LookAt => f.text(
            33,
            8,
            if r.direction == Direction::Right {
                ">"
            } else {
                "<"
            },
            Ink::Effect,
            Layer::Effect,
        ),
        Pose::CelebrateBriefly if index < 3 => {
            for (px, py) in [(3, 6), (33, 7), (5, 17), (31, 17)] {
                f.put(px, py, '+', Ink::Effect, Layer::Effect);
            }
        }
        _ => {}
    }
    if r.skin == Skin::Stardust {
        let phase = (index as u64 + r.seed % 4) % 4;
        for (j, (px, py)) in [(3, 7), (34, 11), (6, 18), (30, 3)].into_iter().enumerate() {
            f.put(
                px,
                py,
                if (j as u64 + phase) & 1 == 0 {
                    '+'
                } else {
                    '.'
                },
                if j % 2 == 0 { Ink::Effect } else { Ink::Accent },
                Layer::Effect,
            );
        }
    }
    match r.mood {
        Mood::Sleepy => f.text(31, 3, "z Z", Ink::Dim, Layer::Effect),
        Mood::Affectionate => f.text(31, 3, "<3", Ink::Effect, Layer::Effect),
        Mood::Curious => f.text(31, 3, "?", Ink::Effect, Layer::Effect),
        Mood::Surprised => f.text(31, 3, "!!", Ink::Effect, Layer::Effect),
        Mood::Tense | Mood::Angry => f.text(31, 3, "!", Ink::Effect, Layer::Effect),
        Mood::Happy if r.pose != Pose::CelebrateBriefly => {
            f.text(31, 3, "+", Ink::Effect, Layer::Effect)
        }
        Mood::Shy => f.text(31, 3, "..", Ink::Effect, Layer::Effect),
        _ => {}
    }
    Some(f)
}
fn face(r: Request, index: usize) -> &'static str {
    if r.pose == Pose::Blink && index == 1 || r.pose == Pose::CurlUp {
        return "-  w  -";
    }
    if r.pose == Pose::GuardFailure {
        return "'  _  '";
    }
    if r.pose == Pose::Speak {
        return if index & 1 == 0 { "0  o  0" } else { "0  .  0" };
    }
    if r.pose == Pose::CelebrateBriefly {
        return ">  w  <";
    }
    if r.pose == Pose::LookAt || r.pose == Pose::Peek {
        return if r.direction == Direction::Right {
            " > w  >"
        } else {
            "<  w < "
        };
    }
    match r.mood {
        Mood::Sleepy => "-  .  -",
        Mood::Affectionate => "^  w  ^",
        Mood::Curious => "o  .  O",
        Mood::Surprised => "O  o  O",
        Mood::Tense => "|  _  |",
        Mood::Angry => ">  ^  <",
        Mood::Happy => "^  w  ^",
        Mood::Shy => "v  w  v",
        Mood::Neutral => match r.skin {
            Skin::Robot => "^  _  ^",
            Skin::Cursor => "^  v  ^",
            Skin::Fox => ">  x  <",
            Skin::Ghost => "0  u  0",
            Skin::Beetle => "0  v  0",
            Skin::Stardust => "0  v  0",
            _ => "0  w  0",
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_original_golden() {
        let expected = [
            " /\\_/\\\n( o.o )\n > ^ <",
            " /\\   /\\\n( o\\_/o )\n /  v  \\\n ~\\___/~",
            "   .|.\n .-===-.\n[  o_o  ]\n /|___|\\",
            " .----- .\n(  o  o )\n(   ~   )\n \\_~_~/",
            "   /|\n  /o|\n /_^|\n/___|",
            " \\  |  /\n  .-^-.\n / o o \\\n| \\___/ |\n \\_/ \\_/",
            " /\\_/\\\n( =.= )\n /)_(\\",
            "    *\n  .-o-.\n*( o.o )*\n  `-^-'\n    .",
        ];
        for (s, e) in Skin::ALL.into_iter().zip(expected) {
            assert_eq!(s.original_sketch(), e);
        }
    }
    #[test]
    fn templates_fit_ascii_and_have_one_face() {
        for skin in art::ART {
            for body in skin {
                assert_eq!(body.matches("FFFFFFF").count(), 1);
                assert!(body.is_ascii());
                assert!(body.lines().all(|l| l.len() <= 31));
                assert!(body.lines().count() <= 13);
            }
        }
    }
    #[test]
    fn all_skins_poses_modes_frames() {
        for s in Skin::ALL {
            for p in Pose::ALL {
                for motion in [Motion::Full, Motion::Calm, Motion::Static] {
                    for mood in Mood::ALL {
                        for t in [0, 100, 180, 300, 440, 600, 1000, 2400, 9000, u64::MAX] {
                            let mut r = Request::new(s, p);
                            r.motion = motion;
                            r.elapsed_ms = t;
                            r.mood = mood;
                            let f = sample(r).unwrap();
                            assert_eq!(f.cells.len(), WIDTH * HEIGHT);
                            assert_eq!(f.lines().len(), HEIGHT);
                            assert!(f.lines().iter().all(|l| l.len() == WIDTH));
                            assert!(f
                                .cells
                                .iter()
                                .all(|c| c.glyph.is_ascii_graphic() || c.glyph == ' '));
                            assert!([3, 5].contains(
                                &f.cells
                                    .iter()
                                    .filter(|c| c.layer == Layer::Face && c.glyph != ' ')
                                    .count()
                            ));
                            assert!(!f.accessible_label.is_empty());
                            if motion == Motion::Static {
                                assert!(f.next_frame_in_ms.is_none());
                            } else if let Some(ms) = f.next_frame_in_ms {
                                assert!(ms > 0 && ms <= 7200);
                            }
                        }
                    }
                }
            }
        }
    }
    #[test]
    fn hidden_and_reduced_have_no_callbacks() {
        for s in Skin::ALL {
            for p in Pose::ALL {
                let mut r = Request::new(s, p);
                r.visible = false;
                assert!(sample(r).is_none());
                r.visible = true;
                r.reduced_motion = true;
                let a = sample(r).unwrap();
                r.elapsed_ms = 9000;
                assert_eq!(a, sample(r).unwrap());
                assert_eq!(a.next_frame_in_ms, None);
            }
        }
    }
    #[test]
    fn static_is_time_and_seed_independent_except_star_palette_pattern() {
        for s in Skin::ALL {
            for p in Pose::ALL {
                let mut r = Request::new(s, p);
                r.motion = Motion::Static;
                let a = sample(r);
                r.elapsed_ms = u64::MAX;
                assert_eq!(a, sample(r));
            }
        }
    }
    #[test]
    fn deterministic_replay() {
        for s in Skin::ALL {
            for p in Pose::ALL {
                for seed in [0, 1, 42, u64::MAX] {
                    let mut r = Request::new(s, p);
                    r.seed = seed;
                    r.elapsed_ms = 512;
                    assert_eq!(sample(r), sample(r));
                }
            }
        }
    }
    #[test]
    fn every_skin_has_distinct_full_body_pose_silhouettes() {
        for s in Skin::ALL {
            let bodies: Vec<_> = [
                Pose::Idle,
                Pose::Sit,
                Pose::CurlUp,
                Pose::Stretch,
                Pose::Walk,
                Pose::Retreat,
            ]
            .into_iter()
            .map(|p| {
                let mut r = Request::new(s, p);
                r.motion = Motion::Static;
                sample(r)
                    .unwrap()
                    .cells
                    .into_iter()
                    .filter(|c| c.layer == Layer::Body)
                    .collect::<Vec<_>>()
            })
            .collect();
            for i in 0..bodies.len() {
                for j in i + 1..bodies.len() {
                    assert_ne!(bodies[i], bodies[j], "{s:?} {i} {j}");
                }
            }
        }
    }
    #[test]
    fn bounded_one_shots_and_no_catchup() {
        for p in Pose::ALL {
            let mut r = Request::new(Skin::Cat, p);
            r.motion = Motion::Full;
            r.elapsed_ms = u64::MAX;
            let f = sample(r).unwrap();
            if !p.is_looping() {
                assert!(f.next_frame_in_ms.is_none());
                assert_eq!(f.frame_index, p.durations().len() - 1);
            }
        }
    }
    #[test]
    fn stardust_never_splits() {
        for p in Pose::ALL {
            for t in 0..100 {
                let mut r = Request::new(Skin::Stardust, p);
                r.elapsed_ms = t * 50;
                let f = sample(r).unwrap();
                let face: Vec<_> = f
                    .cells
                    .iter()
                    .enumerate()
                    .filter(|(_, c)| c.layer == Layer::Face && c.glyph != ' ')
                    .map(|(i, _)| (i % WIDTH, i / WIDTH))
                    .collect();
                assert!([3, 5].contains(&face.len()));
                assert!(
                    face.iter().map(|p| p.0).max().unwrap()
                        - face.iter().map(|p| p.0).min().unwrap()
                        <= 6
                );
                assert!(
                    face.iter().map(|p| p.1).max().unwrap()
                        - face.iter().map(|p| p.1).min().unwrap()
                        <= 1
                );
            }
        }
    }
    #[test]
    fn aliases_and_unknown_rejected() {
        assert_eq!(Skin::from_key("classic_cat_dango"), Some(Skin::Cat));
        assert_eq!(Skin::from_key("night_cat"), Some(Skin::Night));
        assert_eq!(Skin::from_key("split"), None);
        assert_eq!(Pose::from_key("split"), None);
    }
}

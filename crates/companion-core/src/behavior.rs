//! Monotonic milliseconds supplied by caller; resume invalidates deadlines, never catches up.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Pose {
    Idle,
    Blink,
    LookAt,
    Sit,
    CurlUp,
    Stretch,
    Peek,
    Retreat,
    Walk,
    Listen,
    Speak,
    GuardFailure,
    CelebrateBriefly,
}
impl Pose {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "idle",
            Self::Blink => "blink",
            Self::LookAt => "look_at",
            Self::Sit => "sit",
            Self::CurlUp => "curl_up",
            Self::Stretch => "stretch",
            Self::Peek => "peek",
            Self::Retreat => "retreat",
            Self::Walk => "walk",
            Self::Listen => "listen",
            Self::Speak => "speak",
            Self::GuardFailure => "guard_failure",
            Self::CelebrateBriefly => "celebrate_briefly",
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Motion {
    Full,
    Calm,
    Static,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum Work {
    #[default]
    Unknown,
    Running,
    NeedsReview,
    Succeeded,
    Failed,
}
#[derive(Clone, Debug, Default)]
pub struct Facts {
    pub locked: bool,
    pub hidden: bool,
    pub input: bool,
    pub selecting: bool,
    pub listening: bool,
    pub playing: bool,
    pub text_output: bool,
    pub work: Work,
    pub work_event: Option<String>,
    pub quiet: bool,
    pub idle_since: u64,
}
#[derive(Clone, Debug)]
pub struct Scheduler {
    seed: u64,
    pub pose: Pose,
    next: u64,
    last_now: u64,
    work: Work,
    work_event: Option<String>,
    celebrate_until: u64,
    movement: Option<u64>,
    peek_until: u64,
}
impl Scheduler {
    pub fn new(seed: u64) -> Self {
        Self {
            seed: seed.max(1),
            pose: Pose::Idle,
            next: 0,
            last_now: 0,
            work: Work::Unknown,
            work_event: None,
            celebrate_until: 0,
            movement: None,
            peek_until: 0,
        }
    }
    pub fn transfer_started(&mut self, now: u64) {
        self.movement = Some(now);
    }
    pub fn content_entered_view(&mut self, now: u64) {
        self.peek_until = now.saturating_add(700);
    }
    pub fn resume(&mut self, now: u64) {
        self.movement = None;
        self.peek_until = 0;
        self.next = now.saturating_add(5000);
        self.last_now = now;
        self.celebrate_until = 0;
        self.pose = Pose::Idle;
    }
    pub fn tick(&mut self, now: u64, f: &Facts, m: Motion) -> Option<Pose> {
        if now < self.last_now || now.saturating_sub(self.last_now) > 10000 {
            self.resume(now)
        }
        self.last_now = now;
        if f.work != self.work || f.work_event != self.work_event {
            self.work_event = f.work_event.clone();
            self.work = f.work;
            if f.work == Work::Succeeded {
                self.celebrate_until = now.saturating_add(1200)
            }
        }
        if f.locked || f.hidden {
            return None;
        }
        let p = if f.input || f.selecting {
            Pose::Retreat
        } else if f.work == Work::NeedsReview {
            Pose::LookAt
        } else if f.listening {
            Pose::Listen
        } else if f.playing || f.text_output {
            Pose::Speak
        } else if f.work == Work::Failed {
            Pose::GuardFailure
        } else if f.work == Work::Succeeded && now < self.celebrate_until {
            Pose::CelebrateBriefly
        } else if f.work == Work::Succeeded
            && self.celebrate_until > 0
            && now < self.celebrate_until.saturating_add(700)
        {
            Pose::Stretch
        } else if f.work == Work::Running {
            Pose::LookAt
        } else if m != Motion::Static && self.movement.is_some_and(|t| now.saturating_sub(t) < 900)
        {
            match now.saturating_sub(self.movement.unwrap()) {
                0..=119 => Pose::LookAt,
                120..=199 => Pose::Sit,
                200..=599 => Pose::Walk,
                _ => Pose::Sit,
            }
        } else if now < self.peek_until && m != Motion::Static && !f.quiet {
            Pose::Peek
        } else if now.saturating_sub(f.idle_since) > 120000 {
            Pose::CurlUp
        } else if m == Motion::Static || f.quiet {
            Pose::Sit
        } else if now >= self.next {
            self.seed ^= self.seed << 13;
            self.seed ^= self.seed >> 7;
            self.seed ^= self.seed << 17;
            self.next = now.saturating_add(if m == Motion::Calm { 8000 } else { 4000 });
            let candidates = [
                Candidate {
                    pose: Pose::Blink,
                    relevance: 20,
                    preference: 0,
                    novelty: 3,
                    interruption: 0,
                    repetition: if self.pose == Pose::Blink { 5 } else { 0 },
                    eligible: true,
                },
                Candidate {
                    pose: Pose::Sit,
                    relevance: 18,
                    preference: 0,
                    novelty: 3,
                    interruption: 0,
                    repetition: if self.pose == Pose::Sit { 5 } else { 0 },
                    eligible: true,
                },
            ];
            select_candidate(&candidates, self.seed).unwrap_or(Pose::Idle)
        } else if self.pose == Pose::Blink
            && self.next.saturating_sub(now) > if m == Motion::Calm { 7800 } else { 3800 }
        {
            Pose::Blink
        } else {
            Pose::Idle
        };
        self.pose = p;
        Some(p)
    }
}
#[derive(Clone, Debug)]
pub struct FocusPolicy {
    pub stable_ms: u64,
    pub dwell_ms: u64,
    candidate: Option<(String, u64)>,
    last_grant: u64,
}
impl Default for FocusPolicy {
    fn default() -> Self {
        Self {
            stable_ms: 200,
            dwell_ms: 2000,
            candidate: None,
            last_grant: 0,
        }
    }
}
impl FocusPolicy {
    pub fn clear(&mut self, id: &str) {
        if self.candidate.as_ref().is_some_and(|c| c.0 == id) {
            self.candidate = None
        }
    }
    pub fn observe(&mut self, id: String, now: u64) {
        if self.candidate.as_ref().map(|x| &x.0) != Some(&id) {
            self.candidate = Some((id, now))
        }
    }
    pub fn eligible(&self, now: u64) -> Option<&str> {
        self.candidate
            .as_ref()
            .filter(|(_, t)| {
                now.saturating_sub(*t) >= self.stable_ms
                    && now.saturating_sub(self.last_grant) >= self.dwell_ms
            })
            .map(|x| x.0.as_str())
    }
    pub fn granted(&mut self, now: u64) {
        // Retain the last factual focus so a cleared lock can restore the same
        // focused host after retirement; repeated same-owner requests grant nothing.
        self.last_grant = now;
    }
    pub fn resume(&mut self, now: u64) {
        self.candidate = None;
        self.last_grant = now
    }
}
/// Scoring is only applied after hard eligibility; randomness is at most a two-point tie-break.
#[derive(Clone, Copy, Debug)]
pub struct Candidate {
    pub pose: Pose,
    pub relevance: i32,
    pub preference: i32,
    pub novelty: i32,
    pub interruption: i32,
    pub repetition: i32,
    pub eligible: bool,
}
pub fn select_candidate(candidates: &[Candidate], seed: u64) -> Option<Pose> {
    candidates
        .iter()
        .enumerate()
        .filter(|(_, c)| c.eligible)
        .max_by_key(|(i, c)| {
            i64::from(c.relevance) + i64::from(c.preference) + i64::from(c.novelty)
                - i64::from(c.interruption)
                - i64::from(c.repetition)
                + ((seed.rotate_left(*i as u32) % 3) as i64)
        })
        .map(|(_, c)| c.pose)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hard_priority() {
        let mut s = Scheduler::new(9);
        let mut f = Facts {
            input: true,
            playing: true,
            work: Work::Failed,
            ..Facts::default()
        };
        assert_eq!(s.tick(1, &f, Motion::Full), Some(Pose::Retreat));
        f.locked = true;
        assert_eq!(s.tick(2, &f, Motion::Full), None);
    }
    #[test]
    fn deterministic_trace() {
        let mut a = Scheduler::new(4);
        let mut b = a.clone();
        for t in (0..100000).step_by(73) {
            assert_eq!(
                a.tick(t, &Facts::default(), Motion::Full),
                b.tick(t, &Facts::default(), Motion::Full)
            );
        }
        a.resume(900000);
        assert_eq!(
            a.tick(
                900000,
                &Facts {
                    idle_since: 900000,
                    ..Facts::default()
                },
                Motion::Full
            ),
            Some(Pose::Idle)
        );
    }
}
#[cfg(test)]
mod activity_tests {
    use super::*;
    #[test]
    fn new_task_success_restarts_brief_fact_pose() {
        let mut s = Scheduler::new(1);
        let mut f = Facts {
            work: Work::Succeeded,
            work_event: Some("task-a:1".into()),
            ..Facts::default()
        };
        assert_eq!(s.tick(10, &f, Motion::Static), Some(Pose::CelebrateBriefly));
        assert_eq!(s.tick(3000, &f, Motion::Static), Some(Pose::Sit));
        f.work_event = Some("task-b:1".into());
        assert_eq!(
            s.tick(3001, &f, Motion::Static),
            Some(Pose::CelebrateBriefly)
        );
    }
    #[test]
    fn recent_activity_does_not_curl_after_daemon_uptime() {
        let mut s = Scheduler::new(1);
        assert_ne!(
            s.tick(
                200000,
                &Facts {
                    idle_since: 199999,
                    ..Facts::default()
                },
                Motion::Static
            ),
            Some(Pose::CurlUp)
        );
        assert_eq!(
            s.tick(
                400000,
                &Facts {
                    idle_since: 199999,
                    ..Facts::default()
                },
                Motion::Static
            ),
            Some(Pose::CurlUp)
        );
    }
    #[test]
    fn movement_and_content_cues_are_bounded() {
        let mut s = Scheduler::new(1);
        let f = Facts::default();
        s.transfer_started(1);
        assert_eq!(s.tick(2, &f, Motion::Full), Some(Pose::LookAt));
        assert_eq!(s.tick(250, &f, Motion::Full), Some(Pose::Walk));
        s.resume(50000);
        assert_ne!(s.tick(50001, &f, Motion::Full), Some(Pose::Walk));
        s.content_entered_view(50002);
        assert_eq!(s.tick(50003, &f, Motion::Full), Some(Pose::Peek));
    }
}

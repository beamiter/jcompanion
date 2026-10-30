//! Pure transitions. Caller MUST durably commit the returned state before dispatching effects.
use companion_protocol::*;
use serde::{Deserialize, Serialize};
pub mod behavior;
pub mod geometry;
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Unplaced,
    Preparing,
    AwaitingRemovalProof,
    Granted,
    Active,
    RecoveryBlocked,
    Suppressed,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct State {
    #[serde(default)]
    pub retired_tokens: Vec<Token>,
    #[serde(default)]
    pub pending_recall: Option<Host>,
    #[serde(default)]
    pub desktop_observed: bool,
    #[serde(default)]
    pub desktop_known: bool,
    #[serde(default = "default_name")]
    pub name: String,
    #[serde(default)]
    pub quiet: bool,
    #[serde(default)]
    pub night: bool,
    #[serde(default)]
    pub voice_lease: Option<VoiceLease>,
    #[serde(default)]
    pub require_compositor: bool,
    #[serde(default)]
    pub compositor_only: bool,
    #[serde(default)]
    pub locked: bool,
    #[serde(default = "default_skin")]
    pub skin: String,
    #[serde(default = "default_motion")]
    pub motion: String,
    pub schema: u16,
    pub companion_id: String,
    pub profile_revision: u64,
    pub boot_id: String,
    pub session_id: String,
    pub epoch: u64,
    pub revision: u64,
    pub mode: Presence,
    pub phase: Phase,
    /// Every grant is recorded before transmission; this token remains possibly visible until proof.
    pub possible_body: Option<Token>,
    pub target: Option<Host>,
    pub revoke_intent: bool,
}
#[derive(Clone, Debug)]
pub struct Effect {
    pub host: String,
    pub reply: Reply,
}
fn default_name() -> String {
    "Eva".into()
}
fn default_skin() -> String {
    "cat".into()
}
fn default_motion() -> String {
    "calm".into()
}
impl State {
    pub fn validate(&self) -> Result<(), String> {
        if self.retired_tokens.len() > 64
            || self.retired_tokens.iter().any(|t| {
                t.companion_id != self.companion_id
                    || t.epoch == 0
                    || t.epoch > self.epoch
                    || t.incarnation == 0
                    || ![&t.host_id, &t.boot_id, &t.surface_id]
                        .iter()
                        .all(|s| identifier(s))
            })
        {
            return Err("invalid_retirement_ledger".into());
        }
        if self.desktop_known && !self.desktop_observed {
            return Err("invalid_desktop_state".into());
        }
        if self.name.trim().is_empty()
            || self.name.len() > 64
            || self.name.chars().any(char::is_control)
        {
            return Err("invalid_profile_name".into());
        }
        if self
            .voice_lease
            .as_ref()
            .is_some_and(|v| !identifier(&v.source_id) || !identifier(&v.session_id))
        {
            return Err("invalid_voice_lease".into());
        }
        if self.schema != 1
            || ![&self.companion_id, &self.boot_id, &self.session_id]
                .iter()
                .all(|s| identifier(s))
            || self.profile_revision == 0
            || [self.epoch, self.revision, self.profile_revision]
                .iter()
                .any(|v| *v > u64::MAX - 1024)
        {
            return Err("invalid_identity_or_counter_exhausted".into());
        }
        if ![
            "cat", "fox", "robot", "ghost", "cursor", "beetle", "night", "stardust",
        ]
        .contains(&self.skin.as_str())
            || !["full", "calm", "static"].contains(&self.motion.as_str())
        {
            return Err("invalid_appearance".into());
        }
        if let Some(t) = &self.possible_body {
            if t.companion_id != self.companion_id
                || t.epoch == 0
                || t.epoch > self.epoch
                || t.incarnation == 0
                || ![&t.host_id, &t.boot_id, &t.surface_id]
                    .iter()
                    .all(|s| identifier(s))
            {
                return Err("invalid_possible_body".into());
            }
        }
        if let Some(h) = &self.pending_recall {
            if !identifier(&h.id) || !identifier(&h.surface_id) || h.incarnation == 0 {
                return Err("invalid_pending_recall".into());
            }
        }
        if let Some(h) = &self.target {
            if !identifier(&h.id)
                || !identifier(&h.surface_id)
                || h.incarnation == 0
                || (h.retirement == RetirementCapability::None && !self.compositor_only)
            {
                return Err("invalid_target".into());
            }
        }
        let valid = match self.phase {
            Phase::Unplaced | Phase::Suppressed => {
                self.possible_body.is_none() && self.target.is_none() && !self.revoke_intent
            }
            Phase::Preparing => self.target.is_some() && !self.revoke_intent,
            Phase::AwaitingRemovalProof | Phase::RecoveryBlocked => {
                self.possible_body.is_some() && self.revoke_intent
            }
            Phase::Granted | Phase::Active => {
                self.possible_body
                    .as_ref()
                    .is_some_and(|t| t.boot_id == self.boot_id)
                    && self.target.is_none()
                    && !self.revoke_intent
            }
        };
        if !valid {
            return Err("inconsistent_residence_journal".into());
        }
        Ok(())
    }

    pub fn new(id: String, boot: String, session: String) -> Self {
        Self {
            retired_tokens: vec![],
            pending_recall: None,
            desktop_observed: false,
            desktop_known: false,
            name: default_name(),
            quiet: false,
            night: false,
            voice_lease: None,
            locked: false,
            require_compositor: false,
            compositor_only: false,
            skin: default_skin(),
            motion: default_motion(),
            schema: 1,
            companion_id: id,
            profile_revision: 1,
            boot_id: boot,
            session_id: session,
            epoch: 0,
            revision: 0,
            mode: Presence::FollowMe,
            phase: Phase::Unplaced,
            possible_body: None,
            target: None,
            revoke_intent: false,
        }
    }
    pub fn recover(mut self, boot: String) -> Self {
        self.boot_id = boot;
        if self.desktop_observed {
            self.desktop_known = false;
        }
        self.target = None;
        self.pending_recall = None;
        self.revision += 1;
        self.phase = if self.possible_body.is_some() {
            self.revoke_intent = true;
            Phase::RecoveryBlocked
        } else if self.locked
            || (self.desktop_observed && !self.desktop_known)
            || self.mode == Presence::Hidden
        {
            Phase::Suppressed
        } else {
            Phase::Unplaced
        };
        self
    }
    pub fn request(&self, host: Host) -> Result<(Self, Vec<Effect>), String> {
        if self.locked
            || (self.desktop_observed && !self.desktop_known)
            || self.mode == Presence::Hidden
        {
            return Err("hidden".into());
        }
        if !self.revoke_intent
            && self.target.is_none()
            && self.possible_body.as_ref().is_some_and(|t| {
                t.host_id == host.id
                    && t.incarnation == host.incarnation
                    && t.surface_id == host.surface_id
                    && t.boot_id == self.boot_id
            })
        {
            return Ok((self.clone(), vec![]));
        }
        if self.require_compositor && host.retirement != RetirementCapability::CompositorPresented {
            return Err("compositor_retirement_required".into());
        }
        if host.retirement == RetirementCapability::None
            && !(self.compositor_only && self.possible_body.is_none())
        {
            return Err("retirement_capability_required".into());
        }
        if self.target.is_some() || self.revoke_intent {
            return Err("handoff_or_recovery_pending".into());
        }
        if self
            .possible_body
            .as_ref()
            .is_some_and(|t| t.host_id == host.id && t.incarnation == host.incarnation)
        {
            return Ok((self.clone(), vec![]));
        }
        let mut n = self.clone();
        n.epoch = n.epoch.checked_add(1).ok_or("epoch_exhausted")?;
        n.revision += 1;
        n.phase = Phase::Preparing;
        n.target = Some(host.clone());
        Ok((
            n.clone(),
            vec![Effect {
                host: host.id,
                reply: Reply::Prepare { epoch: n.epoch },
            }],
        ))
    }
    pub fn prepared(&self, host: &Host, epoch: u64) -> Result<(Self, Vec<Effect>), String> {
        if self.phase != Phase::Preparing
            || self.target.as_ref() != Some(host)
            || epoch != self.epoch
        {
            return Err("stale_prepare".into());
        }
        let mut n = self.clone();
        n.revision += 1;
        if let Some(old) = &n.possible_body {
            let e = Effect {
                host: old.host_id.clone(),
                reply: Reply::Revoke { token: old.clone() },
            };
            n.revoke_intent = true;
            n.phase = Phase::AwaitingRemovalProof;
            Ok((n, vec![e]))
        } else {
            n.grant()
        }
    }
    fn grant(mut self) -> Result<(Self, Vec<Effect>), String> {
        if self.possible_body.is_some() {
            return Err("old_body_unproven".into());
        }
        if self.locked
            || (self.desktop_observed && !self.desktop_known)
            || self.mode == Presence::Hidden
        {
            self.target = None;
            self.phase = Phase::Suppressed;
            return Ok((self, vec![]));
        }
        let Some(h) = self.target.take() else {
            self.phase = Phase::Unplaced;
            return Ok((self, vec![]));
        };
        let t = Token {
            companion_id: self.companion_id.clone(),
            host_id: h.id.clone(),
            incarnation: h.incarnation,
            boot_id: self.boot_id.clone(),
            epoch: self.epoch,
            surface_id: h.surface_id,
        };
        self.possible_body = Some(t.clone());
        self.phase = Phase::Granted;
        self.revision += 1;
        let revision = self.revision;
        Ok((
            self,
            vec![Effect {
                host: h.id,
                reply: Reply::Grant { token: t, revision },
            }],
        ))
    }
    pub fn retired(
        &self,
        host: &Host,
        token: &Token,
        serial: u64,
    ) -> Result<(Self, Vec<Effect>), String> {
        if host.id == token.host_id
            && host.incarnation == token.incarnation
            && host.surface_id == token.surface_id
            && self.retired_tokens.contains(token)
        {
            return Ok((self.clone(), vec![]));
        }
        if self.require_compositor && host.retirement != RetirementCapability::CompositorPresented {
            return Err("compositor_retirement_required".into());
        }
        if !self.revoke_intent
            || self.possible_body.as_ref() != Some(token)
            || host.id != token.host_id
            || host.incarnation != token.incarnation
            || host.surface_id != token.surface_id
            || host.retirement == RetirementCapability::None
            || serial == 0
        {
            return Err("invalid_retirement_proof".into());
        }
        let mut n = self.clone();
        n.possible_body = None;
        if n.retired_tokens.len() == 64 {
            n.retired_tokens.remove(0);
        }
        n.retired_tokens.push(token.clone());
        n.revoke_intent = false;
        n.revision += 1;
        n.grant()
    }
    pub fn presented(&self, host: &Host, token: &Token) -> Result<(Self, Vec<Effect>), String> {
        if self.revoke_intent
            || self.possible_body.as_ref() != Some(token)
            || token.boot_id != self.boot_id
            || token.host_id != host.id
            || token.incarnation != host.incarnation
        {
            return Err("stale_presented".into());
        }
        let mut n = self.clone();
        n.phase = Phase::Active;
        n.revision += 1;
        Ok((n, vec![]))
    }
    pub fn recall(&self, host: Host) -> (Self, Vec<Effect>) {
        let mut n = self.clone();
        n.revision += 1;
        if n.mode == Presence::Hidden {
            n.mode = Presence::FollowMe;
        }
        n.pending_recall = Some(host);
        if n.target.is_some() {
            n.target = None;
            if !n.revoke_intent {
                n.phase = if n.possible_body.is_some() {
                    Phase::Granted
                } else {
                    Phase::Unplaced
                };
            }
        }
        (n, vec![])
    }
    pub fn cancel_recall(&self, id: &str) -> Self {
        let mut n = self.clone();
        if n.pending_recall.as_ref().is_some_and(|h| h.id == id) {
            n.pending_recall = None;
            n.revision += 1;
        }
        n
    }
    pub fn drive_recall(&self, host: &Host) -> Result<(Self, Vec<Effect>), String> {
        if self.pending_recall.as_ref() != Some(host) {
            return Err("recall_target_changed".into());
        }
        let mut n = self.clone();
        n.pending_recall = None;
        let (mut n, e) = n.request(host.clone())?;
        n.revision += 1;
        Ok((n, e))
    }
    pub fn withdraw(&self, host: &Host) -> Result<(Self, Vec<Effect>), String> {
        let mut n = self.clone();
        n.revision += 1;
        if n.target.as_ref() == Some(host) {
            n.target = None;
            if !n.revoke_intent {
                n.phase = if n.possible_body.is_some() {
                    Phase::Granted
                } else {
                    Phase::Unplaced
                };
            }
        }
        if let Some(t) = n
            .possible_body
            .clone()
            .filter(|t| t.host_id == host.id && t.incarnation == host.incarnation)
        {
            n.target = None;
            n.revoke_intent = true;
            n.phase = Phase::AwaitingRemovalProof;
            Ok((
                n,
                vec![Effect {
                    host: host.id.clone(),
                    reply: Reply::Revoke { token: t },
                }],
            ))
        } else {
            Ok((n, vec![]))
        }
    }
    pub fn desktop_status(&self, locked: bool, known: bool) -> (Self, Vec<Effect>) {
        let mut n = self.clone();
        n.desktop_observed = true;
        n.desktop_known = known;
        n.revision += 1;
        if n.compositor_only {
            if known {
                n.locked = locked;
            }
            (n, vec![])
        } else if known {
            n.lock(locked)
        } else {
            let lock = n.locked;
            let (mut n, e) = n.lock(true);
            n.locked = lock;
            (n, e)
        }
    }
    pub fn lock(&self, locked: bool) -> (Self, Vec<Effect>) {
        let mut n = self.clone();
        n.locked = locked;
        n.revision += 1;
        if locked {
            let mode = n.mode;
            let (mut n, e) = n.presence(Presence::Hidden);
            n.mode = mode;
            (n, e)
        } else {
            (n, vec![])
        }
    }
    pub fn presence(&self, mode: Presence) -> (Self, Vec<Effect>) {
        let mut n = self.clone();
        n.mode = mode;
        n.revision += 1;
        if mode != Presence::Hidden {
            return (n, vec![]);
        }
        n.target = None;
        n.pending_recall = None;
        if n.compositor_only
            && !n.revoke_intent
            && n.possible_body
                .as_ref()
                .is_some_and(|t| t.boot_id == n.boot_id)
        {
            return (n, vec![]);
        }
        if let Some(t) = n.possible_body.clone() {
            n.revoke_intent = true;
            n.phase = Phase::AwaitingRemovalProof;
            (
                n,
                vec![Effect {
                    host: t.host_id.clone(),
                    reply: Reply::Revoke { token: t },
                }],
            )
        } else {
            n.phase = Phase::Suppressed;
            (n, vec![])
        }
    }
    pub fn disconnected(&self, id: &str) -> Self {
        let mut n = self.cancel_recall(id);
        if n.target.as_ref().is_some_and(|h| h.id == id) {
            n.target = None;
        }
        if n.possible_body.as_ref().is_some_and(|t| t.host_id == id) {
            n.phase = Phase::RecoveryBlocked;
            n.revoke_intent = true;
        } else if n.target.is_none() && !n.revoke_intent {
            n.phase = if n.possible_body.is_none() {
                Phase::Unplaced
            } else {
                Phase::Granted
            };
        }
        n.revision += 1;
        n
    }
    pub fn reconciliation(&self, h: &Host) -> Option<Reply> {
        self.possible_body
            .as_ref()
            .filter(|t| {
                self.revoke_intent
                    && t.host_id == h.id
                    && t.incarnation == h.incarnation
                    && t.surface_id == h.surface_id
            })
            .map(|t| Reply::Revoke { token: t.clone() })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn host(id: &str) -> Host {
        Host {
            id: id.into(),
            incarnation: 1,
            surface_id: "surface".into(),
            retirement: RetirementCapability::NativePresented,
        }
    }
    fn initial() -> State {
        State::new("eva".into(), "boot1".into(), "session".into())
    }
    fn active() -> State {
        let (s, _) = initial().request(host("a")).unwrap();
        let (s, _) = s.prepared(&host("a"), 1).unwrap();
        s
    }
    #[test]
    fn transfer_requires_exact_proof() {
        let s = active();
        let old = s.possible_body.clone().unwrap();
        let (s, e) = s.request(host("b")).unwrap();
        assert!(matches!(e[0].reply, Reply::Prepare { .. }));
        let (s, e) = s.prepared(&host("b"), 2).unwrap();
        assert!(matches!(e[0].reply, Reply::Revoke { .. }));
        assert_eq!(s.possible_body, Some(old.clone()));
        let mut wrong = old.clone();
        wrong.boot_id = "wrong".into();
        assert!(s.retired(&host("a"), &wrong, 1).is_err());
        let (s, e) = s.retired(&host("a"), &old, 1).unwrap();
        assert_eq!(s.possible_body.unwrap().host_id, "b");
        assert!(matches!(e[0].reply, Reply::Grant { .. }));
    }
    #[test]
    fn stopped_disconnected_or_restarted_owner_never_expires() {
        let s = active();
        let old = s.possible_body.clone().unwrap();
        let s = s.disconnected("a").recover("boot2".into());
        assert!(s.request(host("b")).is_err());
        assert_eq!(s.possible_body, Some(old.clone()));
        let (s, e) = s.retired(&host("a"), &old, 7).unwrap();
        assert!(e.is_empty());
        assert!(s.possible_body.is_none());
        assert!(s.request(host("b")).is_ok());
    }
    #[test]
    fn hidden_revokes_not_forgets() {
        let (s, e) = active().presence(Presence::Hidden);
        assert!(s.possible_body.is_some());
        assert_eq!(e.len(), 1);
        assert!(s.request(host("b")).is_err());
    }
    #[test]
    fn old_callbacks_rejected() {
        let s = active();
        let t = s.possible_body.clone().unwrap();
        let (s, _) = s.presence(Presence::Hidden);
        assert!(s.presented(&host("a"), &t).is_err());
    }
    #[test]
    fn target_disconnect_does_not_grant() {
        let s = active();
        let old = s.possible_body.clone().unwrap();
        let (s, _) = s.request(host("b")).unwrap();
        let (s, _) = s.prepared(&host("b"), 2).unwrap();
        let s = s.disconnected("b");
        let (s, e) = s.retired(&host("a"), &old, 1).unwrap();
        assert!(e.is_empty());
        assert!(s.possible_body.is_none());
    }
}
#[cfg(test)]
mod fault_traces {
    use super::*;
    fn h(n: u64) -> Host {
        Host {
            id: format!("h{n}"),
            incarnation: 1,
            surface_id: "s".into(),
            retirement: RetirementCapability::NativePresented,
        }
    }
    #[test]
    fn virtual_clock_adversarial_transitions_preserve_journal() {
        for seed in 1..64 {
            let mut rng = seed;
            let mut s = State::new("eva".into(), "boot".into(), "session".into());
            for i in 0..1024 {
                rng ^= rng << 13;
                rng ^= rng >> 7;
                rng ^= rng << 17;
                let result = match rng % 8 {
                    0 => s.request(h(rng % 4)),
                    1 => s
                        .target
                        .clone()
                        .map(|h| s.prepared(&h, s.epoch))
                        .unwrap_or_else(|| Err("none".into())),
                    2 => s
                        .possible_body
                        .clone()
                        .map(|t| {
                            s.retired(
                                &Host {
                                    id: t.host_id.clone(),
                                    incarnation: t.incarnation,
                                    surface_id: t.surface_id.clone(),
                                    retirement: RetirementCapability::NativePresented,
                                },
                                &t,
                                i + 1,
                            )
                        })
                        .unwrap_or_else(|| Err("none".into())),
                    3 => Ok(s.presence(Presence::Hidden)),
                    4 => Ok(s.presence(Presence::FollowMe)),
                    5 => Ok((s.disconnected(&format!("h{}", rng % 4)), vec![])),
                    6 => Ok((s.clone().recover(format!("boot{i}")), vec![])),
                    _ => Ok(s.lock(rng & 8 != 0)),
                };
                if let Ok((n, e)) = result {
                    n.validate().unwrap();
                    for effect in e {
                        if matches!(effect.reply, Reply::Grant { .. }) {
                            assert!(!n.revoke_intent);
                            assert!(n.possible_body.is_some());
                            assert!(n.target.is_none());
                        }
                    }
                    s = n;
                }
            }
        }
    }
    #[test]
    fn compositor_policy_cannot_accept_native_proof() {
        let mut s = State::new("eva".into(), "boot".into(), "session".into());
        s.require_compositor = true;
        assert!(s.request(h(1)).is_err());
    }
    #[test]
    fn counter_and_inconsistent_journal_fail_closed() {
        let mut s = State::new("eva".into(), "boot".into(), "session".into());
        s.revision = u64::MAX;
        assert!(s.validate().is_err());
        s.revision = 0;
        s.revoke_intent = true;
        assert!(s.validate().is_err());
    }
}
#[cfg(test)]
mod scene_tests {
    use super::*;
    #[test]
    fn unproven_scene_bootstrap_never_proves_removal() {
        let mut s = State::new("eva".into(), "boot".into(), "session".into());
        s.compositor_only = true;
        let h = Host {
            id: "jwm".into(),
            incarnation: 1,
            surface_id: "scene".into(),
            retirement: RetirementCapability::None,
        };
        let (s, _) = s.request(h.clone()).unwrap();
        s.validate().unwrap();
        let (s, _) = s.prepared(&h, 1).unwrap();
        let token = s.possible_body.clone().unwrap();
        let (s, _) = s.presence(Presence::Hidden);
        assert!(s.retired(&h, &token, 1).is_err());
        assert!(s.clone().recover("next".into()).possible_body.is_some());
    }
}
#[cfg(test)]
mod recall_and_retirement_tests {
    use super::*;
    fn host(id: &str) -> Host {
        Host {
            id: id.into(),
            incarnation: 1,
            surface_id: "s".into(),
            retirement: RetirementCapability::NativePresented,
        }
    }
    fn active() -> State {
        let (s, _) = State::new("eva".into(), "boot".into(), "session".into())
            .request(host("a"))
            .unwrap();
        s.prepared(&host("a"), 1).unwrap().0
    }
    #[test]
    fn hidden_recall_waits_exact_proof_then_prepares() {
        let s = active();
        let token = s.possible_body.clone().unwrap();
        let (s, _) = s.presence(Presence::Hidden);
        let (s, e) = s.recall(host("b"));
        assert_eq!(s.mode, Presence::FollowMe);
        assert!(e.is_empty());
        assert!(s.drive_recall(&host("b")).is_err());
        let (s, _) = s.retired(&host("a"), &token, 1).unwrap();
        let (s, e) = s.drive_recall(&host("b")).unwrap();
        assert!(matches!(e[0].reply, Reply::Prepare { .. }));
        assert!(s.possible_body.is_none());
    }
    #[test]
    fn locked_recall_never_unhides_lock_or_overrides_proof() {
        let (s, _) = active().lock(true);
        let (s, _) = s.recall(host("b"));
        assert!(s.locked);
        assert!(s.drive_recall(&host("b")).is_err());
        let (s, _) = s.lock(false);
        assert!(s.drive_recall(&host("b")).is_err());
        assert!(s.disconnected("b").pending_recall.is_none());
    }
    #[test]
    fn lost_retirement_ack_is_idempotent_across_restart() {
        let s = active();
        let t = s.possible_body.clone().unwrap();
        let (s, _) = s.withdraw(&host("a")).unwrap();
        let (s, _) = s.retired(&host("a"), &t, 8).unwrap();
        let s = s.recover("new-boot".into());
        let (n, e) = s.retired(&host("a"), &t, 8).unwrap();
        assert!(e.is_empty());
        assert!(n.possible_body.is_none());
        assert_eq!(n.retired_tokens, vec![t]);
    }
    #[test]
    fn scene_hide_recall_and_lock_keep_one_same_token() {
        let mut h = host("jwm");
        h.retirement = RetirementCapability::None;
        let mut s = State::new("eva".into(), "boot".into(), "session".into());
        s.compositor_only = true;
        let (s, _) = s.request(h.clone()).unwrap();
        let (s, _) = s.prepared(&h, 1).unwrap();
        let token = s.possible_body.clone();
        let (s, e) = s.presence(Presence::Hidden);
        assert!(e.is_empty());
        assert_eq!(s.possible_body, token);
        let (s, _) = s.recall(h.clone());
        let (s, e) = s.drive_recall(&h).unwrap();
        assert!(e.is_empty());
        assert_eq!(s.possible_body, token);
        let (s, e) = s.desktop_status(true, true);
        assert!(e.is_empty());
        assert_eq!(s.possible_body, token);
        assert!(s.request(host("other")).is_err());
        s.validate().unwrap();
    }
}

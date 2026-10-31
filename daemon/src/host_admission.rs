//! Connection-bound modern admission; legacy hosts keep their original path.
//! Residence commits precede ready replies. No absence, timeout or PID is proof.
use companion_core::State;
use companion_protocol::{Host, Reply, Token};

#[derive(Clone, Debug)]
struct Withdrawal {
    intent: u64,
    token: Option<Token>,
    ready: bool,
}

pub struct Admission {
    nonce: Option<String>,
    pub admitted: bool,
    pub epoch: u64,
    last_intent: u64,
    last_resumed: Option<(u64, Option<Token>)>,
    withdrawal: Option<Withdrawal>,
}
impl Default for Admission {
    fn default() -> Self {
        Self {
            nonce: None,
            admitted: true,
            epoch: 0,
            last_intent: 0,
            last_resumed: None,
            withdrawal: None,
        }
    }
}
impl Admission {
    pub fn negotiate(&mut self, nonce: String) {
        *self = Self {
            nonce: Some(nonce),
            admitted: false,
            ..Self::default()
        };
    }
    pub fn modern(&self) -> bool {
        self.nonce.is_some()
    }
    fn check(&self, nonce: &str) -> Result<(), String> {
        match self.nonce.as_deref() {
            None => Err("host_feature_required".into()),
            Some(current) if current != nonce => Err("stale_host_connection".into()),
            Some(_) => Ok(()),
        }
    }
    fn no_body(state: &State, host: &Host) -> bool {
        !state
            .possible_body
            .as_ref()
            .is_some_and(|t| t.host_id == host.id && t.incarnation == host.incarnation)
    }
    fn next_epoch(&mut self) -> Result<(), String> {
        self.epoch = self
            .epoch
            .checked_add(1)
            .filter(|n| *n < u64::MAX - 1024)
            .ok_or_else(|| "admission_epoch_exhausted".to_owned())?;
        Ok(())
    }
    pub fn activate(&mut self, nonce: &str, host: &Host, state: &State) -> Result<Reply, String> {
        self.check(nonce)?;
        if self.withdrawal.is_some() {
            return Err("host_withdrawing".into());
        }
        if !self.admitted {
            if !Self::no_body(state, host) {
                return Err("old_surface_clearance_required".into());
            }
            self.next_epoch()?;
            self.admitted = true;
        }
        Ok(Reply::HostActivated {
            connection_nonce: nonce.into(),
            host_id: host.id.clone(),
            incarnation: host.incarnation,
            surface_id: host.surface_id.clone(),
            admission_epoch: self.epoch,
        })
    }
    pub fn metadata_matches(&self, nonce: &str, epoch: u64) -> bool {
        self.admitted && self.check(nonce).is_ok() && self.epoch == epoch
    }
    /// Returns false only for the exact active intent's harmless retry.
    pub fn withdraw(
        &mut self,
        nonce: &str,
        intent: u64,
        previous: Option<Token>,
        host: &Host,
        state: &State,
    ) -> Result<bool, String> {
        self.check(nonce)?;
        if let Some(active) = &self.withdrawal {
            return if active.intent == intent {
                Ok(false)
            } else {
                Err("withdrawal_pending".into())
            };
        }
        if intent == 0 || intent >= u64::MAX - 1024 || intent <= self.last_intent {
            return Err("stale_withdrawal_intent".into());
        }
        let current = state
            .possible_body
            .as_ref()
            .filter(|t| t.host_id == host.id && t.incarnation == host.incarnation)
            .cloned();
        if previous.as_ref().is_some_and(|t| {
            current.as_ref() != Some(t) && !state.retirement_record_covers(host, t)
        }) {
            return Err("unknown_previous_retirement".into());
        }
        if current
            .as_ref()
            .is_some_and(|t| t.surface_id != host.surface_id)
        {
            return Err("wrong_host_surface".into());
        }
        self.last_intent = intent;
        self.withdrawal = Some(Withdrawal {
            intent,
            token: current.or(previous),
            ready: false,
        });
        self.admitted = false;
        Ok(true)
    }
    pub fn withdrawal_token(&self) -> Option<&Token> {
        self.withdrawal.as_ref().and_then(|w| w.token.as_ref())
    }
    /// Called only while constructing effects of a transition that will be
    /// fsynced by `commit` before those replies can be dispatched.
    pub fn ready(&mut self, host: &Host, state: &State) -> Option<Reply> {
        if !Self::no_body(state, host) {
            return None;
        }
        let withdrawal = self.withdrawal.as_mut()?;
        if !withdrawal.ready
            && withdrawal
                .token
                .as_ref()
                .is_some_and(|t| !state.retirement_record_covers(host, t))
        {
            return None;
        }
        withdrawal.ready = true;
        Some(Reply::WithdrawalReady {
            connection_nonce: self.nonce.clone()?,
            host_id: host.id.clone(),
            incarnation: host.incarnation,
            surface_id: host.surface_id.clone(),
            intent: withdrawal.intent,
            retired_token: withdrawal.token.clone(),
        })
    }
    /// `changed=false` is an idempotent retry: it must not invalidate metadata
    /// and consent a second time, or accidentally cancel a newer intent.
    pub fn resume(
        &mut self,
        nonce: &str,
        intent: u64,
        host: &Host,
        state: &State,
    ) -> Result<(Reply, bool), String> {
        self.check(nonce)?;
        let (token, changed) = if let Some(active) = &self.withdrawal {
            if active.intent != intent {
                return Err("stale_withdrawal_intent".into());
            }
            if !active.ready || !Self::no_body(state, host) {
                return Err("withdrawal_proof_pending".into());
            }
            (active.token.clone(), true)
        } else if let Some((old, token)) = &self.last_resumed {
            if *old != intent || intent != self.last_intent {
                return Err("stale_withdrawal_intent".into());
            }
            (token.clone(), false)
        } else {
            return Err("withdrawal_intent_required".into());
        };
        if changed {
            self.next_epoch()?;
            self.withdrawal = None;
            self.last_resumed = Some((intent, token.clone()));
            self.admitted = true;
        }
        Ok((
            Reply::WithdrawalResumed {
                connection_nonce: nonce.into(),
                host_id: host.id.clone(),
                incarnation: host.incarnation,
                surface_id: host.surface_id.clone(),
                intent,
                retired_token: token,
                admission_epoch: self.epoch,
            },
            changed,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use companion_protocol::{Presence, RetirementCapability};
    fn host(id: &str) -> Host {
        Host {
            id: id.into(),
            incarnation: 1,
            surface_id: "surface".into(),
            retirement: RetirementCapability::NativePresented,
        }
    }
    fn granted(state: &State, host: &Host) -> State {
        let (state, _) = state.request(host.clone()).unwrap();
        state.prepared(host, state.epoch).unwrap().0
    }
    fn fresh() -> State {
        State::new("eva".into(), "boot".into(), "session".into())
    }
    #[test]
    fn activation_barrier_nonce_and_metadata_epoch_are_explicit() {
        let h = host("h");
        let state = fresh();
        let mut a = Admission::default();
        assert!(a.admitted);
        assert!(a.activate("nonce", &h, &state).is_err());
        a.negotiate("nonce".into());
        assert!(!a.admitted);
        assert!(a.activate("old-nonce", &h, &state).is_err());
        assert_eq!(a.epoch, 0);
        a.activate("nonce", &h, &state).unwrap();
        assert!(a.metadata_matches("nonce", 1));
        assert!(!a.metadata_matches("old-nonce", 1));
        assert!(!a.metadata_matches("nonce", 0));
        let active = granted(&state, &h);
        a.activate("nonce", &h, &active).unwrap();
        assert_eq!(a.epoch, 1);
        let mut other = Admission::default();
        other.negotiate("other".into());
        assert!(other.activate("other", &h, &active).is_err());
        assert!(!other.admitted);
    }
    #[test]
    fn live_body_blocks_resume_until_exact_actual_retirement_transition() {
        let h = host("h");
        let state = granted(&fresh(), &h);
        let token = state.possible_body.clone().unwrap();
        let mut a = Admission::default();
        a.negotiate("nonce".into());
        assert!(a
            .withdraw("nonce", 1, Some(token.clone()), &h, &state)
            .unwrap());
        assert!(a.ready(&h, &state).is_none());
        assert!(a.resume("nonce", 1, &h, &state).is_err());
        let state = state.withdraw(&h).unwrap().0;
        assert!(a.ready(&h, &state).is_none());
        assert!(state.retired(&h, &token, 0).is_err());
        let retired = state.retired(&h, &token, 8).unwrap().0;
        assert!(
            matches!(a.ready(&h,&retired),Some(Reply::WithdrawalReady {intent:1,retired_token:Some(t),..}) if t==token)
        );
        assert!(a.resume("old-nonce", 1, &h, &retired).is_err());
        assert!(a.resume("nonce", 2, &h, &retired).is_err());
        let (_, changed) = a.resume("nonce", 1, &h, &retired).unwrap();
        assert!(changed);
        assert!(a.admitted);
        assert_eq!(retired.retired_tokens.last(), Some(&token));
    }
    #[test]
    fn stale_cancel_and_reused_intent_cannot_cancel_new_work_or_reset_metadata() {
        let h = host("h");
        let state = fresh();
        let mut a = Admission::default();
        a.negotiate("nonce".into());
        a.activate("nonce", &h, &state).unwrap();
        a.withdraw("nonce", 1, None, &h, &state).unwrap();
        a.ready(&h, &state).unwrap();
        a.resume("nonce", 1, &h, &state).unwrap();
        assert_eq!(a.epoch, 2);
        assert!(a.metadata_matches("nonce", 2));
        let (_, changed) = a.resume("nonce", 1, &h, &state).unwrap();
        assert!(!changed);
        assert_eq!(a.epoch, 2);
        assert!(a.withdraw("nonce", 1, None, &h, &state).is_err());
        a.withdraw("nonce", 2, None, &h, &state).unwrap();
        assert!(!a.metadata_matches("nonce", 2));
        assert!(a.resume("nonce", 1, &h, &state).is_err());
        assert!(!a.admitted);
        assert!(!a.withdraw("nonce", 2, None, &h, &state).unwrap());
        assert!(a.withdraw("nonce", 3, None, &h, &state).is_err());
        a.ready(&h, &state).unwrap();
        a.resume("nonce", 2, &h, &state).unwrap();
        assert_eq!(a.epoch, 3);
        assert!(!a.metadata_matches("nonce", 2));
        assert!(a.metadata_matches("nonce", 3));
    }
    #[test]
    fn compacted_retirement_records_reconnect_without_clearing_a_current_body() {
        let first = host("first");
        let mut state = granted(&fresh(), &first);
        let old = state.possible_body.clone().unwrap();
        state = state.withdraw(&first).unwrap().0;
        state = state.retired(&first, &old, 1).unwrap().0;
        for _ in 0..70 {
            let h = host("other");
            state = granted(&state, &h);
            let t = state.possible_body.clone().unwrap();
            state = state.withdraw(&h).unwrap().0;
            state = state.retired(&h, &t, 2).unwrap().0;
        }
        assert_eq!(state.retired_tokens.len(), 64);
        assert!(!state.retired_tokens.contains(&old));
        let current_host = host("current");
        state = granted(&state, &current_host);
        let current = state.possible_body.clone();
        state.validate().unwrap();
        assert!(state.retirement_record_covers(&first, &old));
        assert!(!state.retirement_record_covers(&current_host, current.as_ref().unwrap()));
        assert!(
            state.retired(&first, &old, 3).is_err(),
            "legacy exact-token replay remains unchanged"
        );
        let mut a = Admission::default();
        a.negotiate("reconnected".into());
        a.withdraw("reconnected", 8, Some(old.clone()), &first, &state)
            .unwrap();
        assert!(
            matches!(a.ready(&first,&state),Some(Reply::WithdrawalReady{retired_token:Some(t),..}) if t==old)
        );
        a.resume("reconnected", 8, &first, &state).unwrap();
        assert_eq!(state.possible_body, current);
        assert_eq!(state.mode, Presence::FollowMe);
        let mut wrong = old.clone();
        wrong.companion_id = "another".into();
        assert!(!state.retirement_record_covers(&first, &wrong));
        wrong = old.clone();
        wrong.surface_id = "other-surface".into();
        assert!(!state.retirement_record_covers(&first, &wrong));
        wrong = old;
        wrong.epoch = state.epoch + 1;
        assert!(!state.retirement_record_covers(&first, &wrong));
    }
}

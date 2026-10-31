//! One ledger for text and authenticated Eva voice observations. Turn metadata
//! and result references are durable; optional dialogue text is session-only.
//! Selection evidence, PCM, credentials and execution permits are never retained.
use crate::dialogue_store::Journal;
use companion_openai::{ContextRef, Error, Usage};
use companion_protocol::{AudioState, Host, TaskStatus, VoiceLease};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

const ENTRY_LIMIT: usize = 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Route {
    TextResponses,
    EvaVoice,
    Offline,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(
    tag = "kind",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum Origin {
    Text(ContextRef),
    Voice {
        companion_id: String,
        owner: VoiceLease,
    },
}
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Key {
    Text(String),
    // Keep the original source/turn tombstone across subsequent voice leases.
    // A new lease must not relabel a delayed frame from an older activation.
    Voice { source: String, turn: String },
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum End {
    ResponseComplete,
    Interrupted,
    NextVoiceTurn,
    AudioStopped,
    Error,
    ObservationLost,
    ResourcesReleased,
    RestartedUnknown,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AudioProgress {
    pub generated_samples: u64,
    pub reported_played_samples: Option<u64>,
    /// A previously observed lower bound remains true when a later clock is unknown.
    pub confirmed_played_samples: u64,
    pub state: Option<AudioState>,
    pub observed_at_ns: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Publisher {
    pub source_id: String,
    pub host_incarnation: u64,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub origin: Origin,
    pub route: Route,
    pub generated: bool,
    pub displayed: bool,
    pub audio: Option<AudioProgress>,
    pub interrupted: bool,
    pub finished: bool,
    pub end: Option<End>,
    pub model: Option<String>,
    pub usage: Option<Usage>,
    pub publisher: Option<Publisher>,
    #[serde(skip)]
    pub user_input: Option<String>,
    #[serde(skip)]
    pub model_output: Option<String>,
    /// Session-only: the turn carried reviewed terminal text. Its dialogue
    /// text is then shown only to the exact original context.
    #[serde(skip)]
    pub reviewed_selection: bool,
}
impl Entry {
    fn new(origin: Origin, route: Route) -> Self {
        Self {
            origin,
            route,
            generated: false,
            displayed: false,
            audio: None,
            interrupted: false,
            finished: false,
            end: None,
            model: None,
            usage: None,
            publisher: None,
            user_input: None,
            model_output: None,
            reviewed_selection: false,
        }
    }
}
/// Samples are supplied only after the caller authenticates the existing Eva
/// owner and its current durable lease. No sample-rate/duration is inferred.
pub struct VoiceObservation<'a> {
    pub companion_id: &'a str,
    pub owner: &'a VoiceLease,
    pub turn_id: &'a str,
    pub state: AudioState,
    pub generated_samples: u64,
    pub played_samples: Option<u64>,
    pub interrupted: bool,
    pub observed_at_ns: u64,
    pub received_at_ns: u64,
}
#[derive(Default)]
pub struct Ledger {
    entries: BTreeMap<Key, Entry>,
    active: Option<Key>,
    journal: Option<Journal>,
    journal_failed: bool,
    voice_events: Option<crate::dialogue_events::Journal>,
}
fn same_context(a: &ContextRef, b: &ContextRef) -> bool {
    a.host_id == b.host_id
        && a.pane_id == b.pane_id
        && a.task_id == b.task_id
        && a.project_id == b.project_id
}
fn in_scope(
    origin: &Origin,
    context: &ContextRef,
    scope: companion_protocol::history::Scope,
) -> bool {
    use companion_protocol::history::Scope;
    match (origin, scope) {
        (Origin::Text(c), Scope::Context) => same_context(c, context),
        (Origin::Text(c), Scope::Task) => {
            context.task_id.is_some()
                && c.task_id == context.task_id
                && c.project_id == context.project_id
        }
        (Origin::Text(c), Scope::Project) => {
            context.project_id.is_some() && c.project_id == context.project_id
        }
        (Origin::Voice { .. }, Scope::Voice) => true,
        _ => false,
    }
}
fn history_cursor(row: &crate::dialogue_store::Turn) -> String {
    use sha2::{Digest, Sha256};
    let identity = serde_json::to_vec(&(&row.boot_id, &row.turn_id, &row.entry.origin))
        .expect("history identity is plain data");
    Sha256::digest(identity)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
impl Ledger {
    /// One read-only page, newest first. The caller has already checked that
    /// `context` is the requesting host's current context and the desktop is
    /// unlocked. Dialogue text exists only for this coordinator session.
    pub fn history(
        &self,
        context: &ContextRef,
        scope: companion_protocol::history::Scope,
        before: Option<&str>,
    ) -> Result<(Vec<companion_protocol::history::Entry>, Option<String>), &'static str> {
        use companion_protocol::history::{self as view, Text};
        if !scope.available(context) {
            return Err("scope_unavailable");
        }
        let journal = self
            .journal
            .as_ref()
            .filter(|_| !self.journal_failed)
            .ok_or("history_unavailable")?;
        let rows: Vec<_> = journal
            .turns()
            .iter()
            .rev()
            .filter(|row| in_scope(&row.entry.origin, context, scope))
            .collect();
        let start = match before {
            Some(before) => {
                rows.iter()
                    .position(|row| history_cursor(row) == before)
                    .ok_or("history_cursor_stale")?
                    + 1
            }
            None => 0,
        };
        let mut entries = Vec::new();
        let mut bytes = 0;
        for row in &rows[start..] {
            let current = row.boot_id == journal.boot_id();
            let key = match &row.entry.origin {
                Origin::Text(_) => Key::Text(row.turn_id.clone()),
                Origin::Voice { owner, .. } => Key::Voice {
                    source: owner.source_id.clone(),
                    turn: row.turn_id.clone(),
                },
            };
            let live = current
                .then(|| self.entries.get(&key))
                .flatten()
                .filter(|live| live.origin == row.entry.origin);
            let entry = live.unwrap_or(&row.entry);
            let (source, text, receipts) = match &entry.origin {
                Origin::Text(origin) => {
                    let text = match live {
                        None if !current => Text::EarlierSession,
                        None => Text::NotRecorded,
                        Some(live) if live.reviewed_selection && !same_context(origin, context) => {
                            Text::WithheldOutsideOrigin
                        }
                        Some(_) => Text::Shown,
                    };
                    (Some(origin.clone()), text, None)
                }
                Origin::Voice { owner, .. } => (
                    None,
                    Text::NotRecorded,
                    self.voice_events.as_ref().and_then(|events| {
                        events.receipts(
                            &row.boot_id,
                            &owner.source_id,
                            &owner.session_id,
                            &row.turn_id,
                        )
                    }),
                ),
            };
            let shown = text == Text::Shown;
            let mut page = view::Entry {
                cursor: history_cursor(row),
                turn_id: row.turn_id.clone(),
                created_at_ms: row.created_at_ms,
                route: match entry.route {
                    Route::TextResponses => view::Route::Text,
                    Route::Offline => view::Route::Offline,
                    Route::EvaVoice => view::Route::Voice,
                },
                source,
                text,
                input: shown.then(|| entry.user_input.clone()).flatten(),
                reply: shown.then(|| entry.model_output.clone()).flatten(),
                generated: entry.generated,
                displayed: entry.displayed,
                interrupted: entry.interrupted,
                finished: entry.finished,
                end: entry.end.map(|end| match end {
                    End::ResponseComplete => view::End::ResponseComplete,
                    End::Interrupted => view::End::Interrupted,
                    End::NextVoiceTurn => view::End::NextVoiceTurn,
                    End::AudioStopped => view::End::AudioStopped,
                    End::Error => view::End::Error,
                    End::ObservationLost => view::End::ObservationLost,
                    End::ResourcesReleased => view::End::ResourcesReleased,
                    End::RestartedUnknown => view::End::RestartedUnknown,
                }),
                recovered_after_restart: row.recovered_after_restart,
                generated_samples: entry.audio.as_ref().map(|a| a.generated_samples),
                confirmed_played_samples: entry.audio.as_ref().map(|a| a.confirmed_played_samples),
                receipts,
            };
            let mut size = serde_json::to_vec(&page)
                .map_err(|_| "history_unavailable")?
                .len();
            if size > view::MAX_PAGE_BYTES {
                page.text = Text::TooLarge;
                page.input = None;
                page.reply = None;
                size = serde_json::to_vec(&page)
                    .map_err(|_| "history_unavailable")?
                    .len();
            }
            if entries.len() == view::MAX_PAGE || bytes + size > view::MAX_PAGE_BYTES {
                break;
            }
            debug_assert!(page.valid());
            bytes += size;
            entries.push(page);
        }
        let next = (start + entries.len() < rows.len())
            .then(|| entries.last().map(|e| e.cursor.clone()))
            .flatten();
        Ok((entries, next))
    }
    pub fn open(dir: &std::path::Path, companion: &str, boot: &str) -> std::io::Result<Self> {
        Ok(Self {
            journal: Some(Journal::open(dir, companion, boot)?),
            voice_events: Some(crate::dialogue_events::Journal::open(dir, companion, boot)?),
            ..Self::default()
        })
    }
    pub fn unavailable() -> Self {
        Self {
            journal_failed: true,
            ..Self::default()
        }
    }
    pub fn journal_failed(&self) -> bool {
        self.journal_failed
    }
    /// See [`crate::dialogue_events::Journal::latest_reply`].
    pub fn latest_voice_reply(&self, source: &str) -> Option<(String, String, Vec<String>)> {
        if self.journal_failed {
            return None;
        }
        self.voice_events.as_ref()?.latest_reply(source)
    }
    pub fn voice_event(
        &mut self,
        source: &str,
        record: &companion_voice::dialogue::Record,
        received_at_ns: u64,
    ) -> Result<(), &'static str> {
        if self.journal_failed {
            return Err("voice_dialogue_unavailable");
        }
        if !record.valid() || record.observed_at_ns > received_at_ns {
            return Err("voice_dialogue_invalid_time_or_record");
        }
        let key = Key::Voice {
            source: source.into(),
            turn: record.turn_id.clone(),
        };
        let entry = self
            .entries
            .get(&key)
            .ok_or("voice_dialogue_turn_unknown")?;
        let Origin::Voice {
            companion_id,
            owner,
        } = &entry.origin
        else {
            return Err("voice_dialogue_origin");
        };
        if owner.session_id != record.voice_session_id
            || (entry.finished
                && !matches!(
                    record.event,
                    companion_voice::dialogue::Event::ToolResult { .. }
                        | companion_voice::dialogue::Event::OperationSettled { .. }
                ))
        {
            return Err("voice_dialogue_activation_or_finished");
        }
        let journal = self
            .voice_events
            .get_or_insert_with(|| crate::dialogue_events::Journal::memory(companion_id));
        journal.record(source, record).map_err(|error| {
            if error.kind() == std::io::ErrorKind::InvalidInput {
                "voice_dialogue_order_or_reference"
            } else {
                self.journal_failed = true;
                "voice_dialogue_persistence_failed"
            }
        })?;
        if matches!(
            record.event,
            companion_voice::dialogue::Event::ReplyGenerated { .. }
        ) {
            self.entries
                .get_mut(&key)
                .expect("validated voice entry")
                .generated = true;
            self.checkpoint(&key)
                .map_err(|_| "voice_dialogue_persistence_failed")?;
        }
        Ok(())
    }
    fn checkpoint(&mut self, key: &Key) -> Result<(), Error> {
        if self.journal_failed {
            return Err(Error::LocalHistoryUnavailable);
        }
        if let Some(journal) = &mut self.journal {
            let turn_id = match key {
                Key::Text(id) | Key::Voice { turn: id, .. } => id,
            };
            if journal.record(turn_id, &self.entries[key]).is_err() {
                self.journal_failed = true;
                return Err(Error::LocalHistoryUnavailable);
            }
        }
        Ok(())
    }
    pub fn record_task_result(
        &mut self,
        host: &Host,
        task: &str,
        project: Option<&str>,
        revision: u64,
        status: TaskStatus,
    ) -> Result<(), Error> {
        if self.journal_failed {
            return Err(Error::LocalHistoryUnavailable);
        }
        if let Some(journal) = &mut self.journal {
            if let Err(error) = journal.result(host, task, project, revision, status) {
                if error.kind() == std::io::ErrorKind::InvalidInput {
                    return Err(Error::Stale);
                }
                self.journal_failed = true;
                return Err(Error::LocalHistoryUnavailable);
            }
        }
        Ok(())
    }
    #[cfg(test)]
    pub fn begin(&mut self, id: &str, context: ContextRef, route: Route) -> Result<(), Error> {
        self.begin_text(id, context, route, None, None)
    }
    pub fn begin_input(
        &mut self,
        turn: &companion_openai::UserTurn,
        route: Route,
        publisher: Option<Publisher>,
    ) -> Result<(), Error> {
        turn.validate()?;
        self.begin_text(
            &turn.turn_id,
            turn.context.clone(),
            route,
            Some(turn.text.clone()),
            publisher,
        )?;
        if turn.approved_selection.is_some() {
            if let Some(entry) = self.entries.get_mut(&Key::Text(turn.turn_id.clone())) {
                entry.reviewed_selection = true;
            }
        }
        Ok(())
    }
    fn begin_text(
        &mut self,
        id: &str,
        context: ContextRef,
        route: Route,
        input: Option<String>,
        publisher: Option<Publisher>,
    ) -> Result<(), Error> {
        if self.journal_failed {
            return Err(Error::LocalHistoryUnavailable);
        }
        if route == Route::EvaVoice {
            return Err(Error::InvalidInput);
        }
        let key = Key::Text(id.into());
        if self.entries.contains_key(&key) {
            return Err(Error::Duplicate);
        }
        if self.active.is_some() {
            return Err(Error::Busy);
        }
        if self.entries.len() >= ENTRY_LIMIT {
            return Err(Error::Budget);
        }
        let mut entry = Entry::new(Origin::Text(context), route);
        entry.user_input = input;
        entry.publisher = publisher;
        self.entries.insert(key.clone(), entry);
        self.active = Some(key.clone());
        if let Err(error) = self.checkpoint(&key) {
            self.entries.remove(&key);
            self.active = None;
            return Err(error);
        }
        Ok(())
    }
    pub fn finish(&mut self, id: &str, generated: bool) -> Result<(), Error> {
        self.finish_text(id, generated, None)
    }
    pub fn finish_output(&mut self, id: &str, output: &str) -> Result<(), Error> {
        if output.len() > companion_openai::MAX_REPLY {
            return Err(Error::TooLarge);
        }
        self.finish_text(id, true, Some(output.into()))
    }
    fn finish_text(
        &mut self,
        id: &str,
        generated: bool,
        output: Option<String>,
    ) -> Result<(), Error> {
        let key = Key::Text(id.into());
        if self.active.as_ref() != Some(&key) {
            return Err(Error::Stale);
        }
        let entry = self.entries.get_mut(&key).ok_or(Error::Stale)?;
        entry.generated = generated;
        entry.finished = true;
        entry.end = Some(if generated {
            End::ResponseComplete
        } else {
            End::Error
        });
        entry.model_output = output;
        self.active = None;
        self.checkpoint(&key)
    }
    pub fn displayed(&mut self, id: &str, context: &ContextRef) -> Result<(), Error> {
        let entry = self
            .entries
            .get_mut(&Key::Text(id.into()))
            .ok_or(Error::Stale)?;
        if entry.origin != Origin::Text(context.clone()) || !entry.generated || entry.interrupted {
            return Err(Error::Stale);
        }
        entry.displayed = true;
        self.checkpoint(&Key::Text(id.into()))
    }
    pub fn interrupt(&mut self, id: &str) -> Result<(), Error> {
        let key = Key::Text(id.into());
        let entry = self.entries.get_mut(&key).ok_or(Error::Stale)?;
        entry.interrupted = true;
        entry.finished = true;
        entry.end = Some(End::Interrupted);
        if self.active.as_ref() == Some(&key) {
            self.active = None;
        }
        self.checkpoint(&key)
    }
    pub fn account(&mut self, id: &str, model: String, usage: Option<Usage>) -> Result<(), Error> {
        let entry = self
            .entries
            .get_mut(&Key::Text(id.into()))
            .ok_or(Error::Stale)?;
        entry.model = Some(model);
        entry.usage = usage;
        self.checkpoint(&Key::Text(id.into()))
    }
    /// Do not open another primary activation if its first observed turn could
    /// not be recorded. An existing lease can still reconnect for cleanup.
    pub fn voice_capacity(&self) -> bool {
        !self.journal_failed
            && self.entries.len() < ENTRY_LIMIT
            && !matches!(self.active, Some(Key::Text(_)))
    }
    pub fn observe_voice(&mut self, observation: VoiceObservation<'_>) -> Result<(), &'static str> {
        let VoiceObservation {
            companion_id,
            owner,
            turn_id,
            state,
            generated_samples,
            played_samples,
            interrupted,
            observed_at_ns,
            received_at_ns,
        } = observation;
        if !companion_voice::fresh(observed_at_ns, received_at_ns) {
            return Err("audio_observation_stale_or_future");
        }
        let key = Key::Voice {
            source: owner.source_id.clone(),
            turn: turn_id.into(),
        };
        let origin = Origin::Voice {
            companion_id: companion_id.into(),
            owner: owner.clone(),
        };
        if played_samples.is_some_and(|n| n > generated_samples) {
            return Err("audio_counter_regression");
        }
        let new_turn = !self.entries.contains_key(&key);
        if let Some(entry) = self.entries.get(&key) {
            if entry.origin != origin {
                return Err("audio_lease_binding");
            }
            if entry.finished || self.active.as_ref() != Some(&key) {
                return Err("audio_turn_replay_or_limit");
            }
            let audio = entry
                .audio
                .as_ref()
                .expect("voice entry has audio metadata");
            if observed_at_ns < audio.observed_at_ns {
                return Err("audio_observation_reordered");
            }
            if generated_samples < audio.generated_samples
                || played_samples.is_some_and(|n| n < audio.confirmed_played_samples)
            {
                return Err("audio_counter_regression");
            }
        } else {
            if self.entries.len() >= ENTRY_LIMIT {
                return Err("audio_turn_replay_or_limit");
            }
            if interrupted
                || matches!(
                    state,
                    AudioState::Idle | AudioState::Stopped | AudioState::Error
                )
            {
                return Err("audio_unknown_terminal_turn");
            }
            if let Some(active) = self.active.as_ref() {
                let entry = &self.entries[active];
                if entry.origin != origin {
                    return Err("audio_route_or_owner_conflict");
                }
            }
            // Validate everything first: a rejected new turn must not retire
            // the existing turn or clear its last actual playback observation.
            self.close_active_voice(End::NextVoiceTurn);
            let mut entry = Entry::new(origin, Route::EvaVoice);
            entry.audio = Some(AudioProgress::default());
            self.entries.insert(key.clone(), entry);
            self.active = Some(key.clone());
        }
        let entry = self.entries.get_mut(&key).expect("validated voice entry");
        let audio = entry
            .audio
            .as_mut()
            .expect("voice entry has audio metadata");
        audio.generated_samples = generated_samples;
        audio.reported_played_samples = played_samples;
        if let Some(played) = played_samples {
            audio.confirmed_played_samples = played;
        }
        audio.state = Some(state);
        audio.observed_at_ns = observed_at_ns;
        entry.generated |= generated_samples > 0;
        entry.interrupted |= interrupted;
        let end = if interrupted {
            Some(End::Interrupted)
        } else {
            match state {
                AudioState::Stopped | AudioState::Idle => Some(End::AudioStopped),
                AudioState::Error => Some(End::Error),
                _ => None,
            }
        };
        if let Some(end) = end {
            self.close_active_voice(end);
        } else if new_turn {
            // Only turn boundaries hit disk. 80ms playback observations stay
            // in memory; a crash cannot promote an uncommitted sample to heard.
            let _ = self.checkpoint(&key);
        }
        Ok(())
    }
    fn close_active_voice(&mut self, end: End) {
        let Some(key @ Key::Voice { .. }) = self.active.as_ref().cloned() else {
            return;
        };
        self.active = None;
        let entry = self.entries.get_mut(&key).expect("active entry exists");
        entry.finished = true;
        entry.end = Some(end);
        if end == End::ObservationLost {
            entry
                .audio
                .as_mut()
                .expect("voice audio")
                .reported_played_samples = None;
        }
        let _ = self.checkpoint(&key);
    }
    pub fn release_voice(&mut self, owner: &VoiceLease) -> Option<serde_json::Value> {
        self.end_voice_if(|current| current == owner, End::ResourcesReleased)
    }
    pub fn disconnect_voice(&mut self, source: &str) -> Option<serde_json::Value> {
        self.end_voice_if(|current| current.source_id == source, End::ObservationLost)
    }
    fn end_voice_if(
        &mut self,
        matches: impl FnOnce(&VoiceLease) -> bool,
        end: End,
    ) -> Option<serde_json::Value> {
        let key = self.active.as_ref()?;
        let Origin::Voice { owner, .. } = &self.entries[key].origin else {
            return None;
        };
        if !matches(owner) {
            return None;
        }
        let key = key.clone();
        self.close_active_voice(end);
        self.voice_record(&key)
    }
    pub fn voice_facts(&self, now_ns: u64) -> (bool, bool) {
        let Some(key @ Key::Voice { .. }) = self.active.as_ref() else {
            return (false, false);
        };
        let audio = self.entries[key].audio.as_ref().expect("voice audio");
        if !companion_voice::fresh(audio.observed_at_ns, now_ns) {
            return (false, false);
        }
        let listening = audio.state == Some(AudioState::Listening);
        let playing = audio.state == Some(AudioState::Speaking)
            && audio
                .reported_played_samples
                .is_some_and(|n| n > 0 && n < audio.generated_samples);
        (listening, playing)
    }
    pub fn voice_record_for(&self, owner: &VoiceLease, turn: &str) -> Option<serde_json::Value> {
        let key = Key::Voice {
            source: owner.source_id.clone(),
            turn: turn.into(),
        };
        let Origin::Voice {
            owner: recorded, ..
        } = &self.entries.get(&key)?.origin
        else {
            return None;
        };
        if recorded != owner {
            return None;
        }
        self.voice_record(&key)
    }
    fn voice_record(&self, key: &Key) -> Option<serde_json::Value> {
        let Key::Voice { turn, .. } = key else {
            return None;
        };
        let entry = self.entries.get(key)?;
        let Origin::Voice {
            companion_id,
            owner,
        } = &entry.origin
        else {
            return None;
        };
        let audio = entry.audio.as_ref()?;
        Some(serde_json::json!({
            "route": entry.route, "companion_id": companion_id,
            "source_id": owner.source_id, "session_id": owner.session_id, "turn_id": turn,
            "generated": entry.generated, "displayed": entry.displayed,
            "generated_samples": audio.generated_samples,
            "reported_played_samples": audio.reported_played_samples,
            "confirmed_played_samples": audio.confirmed_played_samples,
            "interrupted": entry.interrupted, "finished": entry.finished, "end": entry.end,
            "observed_at_ns": audio.observed_at_ns,
        }))
    }
    #[cfg(test)]
    pub fn entry(&self, id: &str) -> Option<&Entry> {
        self.entries.get(&Key::Text(id.into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn context() -> ContextRef {
        ContextRef {
            host_id: "host".into(),
            pane_id: "pane".into(),
            task_id: None,
            project_id: Some("project-a".into()),
            revision: 1,
        }
    }
    fn owner() -> VoiceLease {
        VoiceLease {
            source_id: "eva-process-nonce".into(),
            session_id: "activation-1".into(),
        }
    }
    fn observe(
        ledger: &mut Ledger,
        owner: &VoiceLease,
        id: &str,
        state: AudioState,
        generated: u64,
        played: Option<u64>,
        interrupted: bool,
    ) -> Result<(), &'static str> {
        ledger.observe_voice(VoiceObservation {
            companion_id: "shared-eva",
            owner,
            turn_id: id,
            state,
            generated_samples: generated,
            played_samples: played,
            interrupted,
            observed_at_ns: 1_000_000_000,
            received_at_ns: 1_000_000_000,
        })
    }
    fn record(ledger: &Ledger, id: &str) -> serde_json::Value {
        ledger.voice_record_for(&owner(), id).unwrap()
    }
    #[test]
    fn stale_observation_hides_pose_without_finishing_or_releasing_the_turn() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        let before = record(&ledger, "v");
        assert_eq!(
            ledger.voice_facts(1_000_000_000 + companion_voice::MAX_AGE_NS),
            (false, true)
        );
        assert_eq!(
            ledger.voice_facts(1_000_000_001 + companion_voice::MAX_AGE_NS),
            (false, false)
        );
        assert_eq!(ledger.voice_facts(999_999_999), (false, false));
        assert_eq!(record(&ledger, "v"), before);
        assert_eq!(
            ledger.begin("text", context(), Route::Offline),
            Err(Error::Busy)
        );
        ledger
            .observe_voice(VoiceObservation {
                companion_id: "shared-eva",
                owner: &owner(),
                turn_id: "v",
                state: AudioState::Speaking,
                generated_samples: 2400,
                played_samples: Some(480),
                interrupted: false,
                observed_at_ns: 2_000_000_000,
                received_at_ns: 2_000_000_000,
            })
            .unwrap();
        assert_eq!(ledger.voice_facts(2_000_000_000), (false, true));
        assert_eq!(record(&ledger, "v")["confirmed_played_samples"], 480);
    }
    #[test]
    fn old_future_or_reordered_packets_cannot_refresh_a_turn() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        let before = record(&ledger, "v");
        for (observed, received) in [
            (1_000_000_000, 2_000_000_000),
            (0, 1_000_000_000),
            (2_000_000_000, 1_000_000_000),
            (999_999_999, 1_000_000_000),
        ] {
            assert!(ledger
                .observe_voice(VoiceObservation {
                    companion_id: "shared-eva",
                    owner: &owner(),
                    turn_id: "v",
                    state: AudioState::Speaking,
                    generated_samples: 2400,
                    played_samples: Some(960),
                    interrupted: false,
                    observed_at_ns: observed,
                    received_at_ns: received
                })
                .is_err());
        }
        assert_eq!(record(&ledger, "v"), before);
        assert_eq!(ledger.voice_facts(2_000_000_000), (false, false));
    }
    #[test]
    fn text_generation_and_display_do_not_become_audio() {
        let mut ledger = Ledger::default();
        ledger.begin("t", context(), Route::TextResponses).unwrap();
        ledger.finish("t", true).unwrap();
        ledger.displayed("t", &context()).unwrap();
        let entry = ledger.entry("t").unwrap();
        assert!(entry.generated && entry.displayed);
        assert!(entry.audio.is_none());
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, false));
        assert_eq!(
            ledger.begin("v", context(), Route::EvaVoice),
            Err(Error::InvalidInput)
        );
    }
    #[test]
    fn text_receipt_keeps_original_context() {
        let mut ledger = Ledger::default();
        ledger.begin("t", context(), Route::TextResponses).unwrap();
        ledger.finish("t", true).unwrap();
        let mut other = context();
        other.project_id = Some("project-b".into());
        assert!(ledger.displayed("t", &other).is_err());
    }
    #[test]
    fn text_and_voice_names_have_separate_origins() {
        let mut ledger = Ledger::default();
        ledger.begin("same", context(), Route::Offline).unwrap();
        ledger.finish("same", true).unwrap();
        observe(
            &mut ledger,
            &owner(),
            "same",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        assert_eq!(record(&ledger, "same")["route"], "eva_voice");
        assert_eq!(
            ledger.entry("same").unwrap().origin,
            Origin::Text(context())
        );
        assert!(!record(&ledger, "same")["displayed"].as_bool().unwrap());
        assert!(record(&ledger, "same").get("project_id").is_none());
        assert!(record(&ledger, "same").get("pane_id").is_none());
    }
    #[test]
    fn generated_or_unknown_clock_never_proves_speaking() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            None,
            false,
        )
        .unwrap();
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, false));
        assert_eq!(record(&ledger, "v")["confirmed_played_samples"], 0);
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(0),
            false,
        )
        .unwrap();
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, false));
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, true));
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            None,
            false,
        )
        .unwrap();
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, false));
        assert_eq!(record(&ledger, "v")["confirmed_played_samples"], 480);
        assert!(record(&ledger, "v")["reported_played_samples"].is_null());
    }
    #[test]
    fn drained_position_is_a_fact_without_ongoing_speaking() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            480,
            Some(480),
            false,
        )
        .unwrap();
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, false));
        assert_eq!(record(&ledger, "v")["confirmed_played_samples"], 480);
    }
    #[test]
    fn interruption_preserves_only_confirmed_samples_and_closes_turn() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            24000,
            Some(2400),
            false,
        )
        .unwrap();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Cancelling,
            24000,
            Some(2880),
            true,
        )
        .unwrap();
        let ended = record(&ledger, "v");
        assert_eq!(ended["confirmed_played_samples"], 2880);
        assert_eq!(ended["generated_samples"], 24000);
        assert_eq!(ended["end"], "interrupted");
        assert_eq!(ended["interrupted"], true);
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, false));
        assert!(observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            24000,
            Some(4800),
            false
        )
        .is_err());
        assert_eq!(record(&ledger, "v"), ended);
    }
    #[test]
    fn invalid_frames_do_not_mutate_or_close_the_current_turn() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        let before = record(&ledger, "v");
        for (id, state, generated, played) in [
            ("v", AudioState::Speaking, 240, Some(200)),
            ("v", AudioState::Speaking, 2400, Some(479)),
            ("new", AudioState::Speaking, 240, Some(241)),
            ("new", AudioState::Stopped, 0, None),
        ] {
            assert!(observe(&mut ledger, &owner(), id, state, generated, played, false).is_err());
        }
        assert_eq!(record(&ledger, "v"), before);
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, true));
    }
    #[test]
    fn next_turn_closes_previous_without_inventing_success_or_interrupt() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "first",
            AudioState::Thinking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        observe(
            &mut ledger,
            &owner(),
            "second",
            AudioState::Listening,
            0,
            None,
            false,
        )
        .unwrap();
        let first = record(&ledger, "first");
        assert_eq!(first["end"], "next_voice_turn");
        assert_eq!(first["interrupted"], false);
        assert_eq!(first["confirmed_played_samples"], 480);
        assert_eq!(ledger.voice_facts(1_000_000_000), (true, false));
        assert!(observe(
            &mut ledger,
            &owner(),
            "first",
            AudioState::Speaking,
            2400,
            Some(960),
            false
        )
        .is_err());
        assert_eq!(ledger.voice_facts(1_000_000_000), (true, false));
    }
    #[test]
    fn lost_observation_keeps_a_lower_bound_and_refuses_old_replay() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        let ended = ledger.disconnect_voice(&owner().source_id).unwrap();
        assert_eq!(ended["end"], "observation_lost");
        assert!(ended["reported_played_samples"].is_null());
        assert_eq!(ended["confirmed_played_samples"], 480);
        assert!(!ended["interrupted"].as_bool().unwrap());
        assert!(observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Speaking,
            2400,
            Some(960),
            false
        )
        .is_err());
        observe(
            &mut ledger,
            &owner(),
            "next",
            AudioState::Listening,
            0,
            None,
            false,
        )
        .unwrap();
        assert_eq!(ledger.voice_facts(1_000_000_000), (true, false));
    }
    #[test]
    fn source_and_activation_binding_survive_release_and_new_lease() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Listening,
            0,
            None,
            false,
        )
        .unwrap();
        let wrong = VoiceLease {
            session_id: "activation-2".into(),
            ..owner()
        };
        assert!(ledger.release_voice(&wrong).is_none());
        assert!(ledger.disconnect_voice("different-process").is_none());
        assert!(observe(
            &mut ledger,
            &wrong,
            "v",
            AudioState::Stopped,
            0,
            None,
            false
        )
        .is_err());
        assert!(observe(
            &mut ledger,
            &wrong,
            "new",
            AudioState::Listening,
            0,
            None,
            false
        )
        .is_err());
        assert_eq!(ledger.voice_facts(1_000_000_000), (true, false));
        assert_eq!(
            ledger.release_voice(&owner()).unwrap()["end"],
            "resources_released"
        );
        observe(
            &mut ledger,
            &wrong,
            "new",
            AudioState::Listening,
            0,
            None,
            false,
        )
        .unwrap();
        assert!(observe(
            &mut ledger,
            &wrong,
            "v",
            AudioState::Thinking,
            0,
            None,
            false
        )
        .is_err());
        assert_eq!(ledger.voice_facts(1_000_000_000), (true, false));
    }
    #[test]
    fn both_routes_share_admission_and_only_matching_release_frees_it() {
        let mut ledger = Ledger::default();
        ledger.begin("t", context(), Route::TextResponses).unwrap();
        assert!(!ledger.voice_capacity());
        assert!(observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Listening,
            0,
            None,
            false
        )
        .is_err());
        assert_eq!(ledger.active, Some(Key::Text("t".into())));
        ledger.finish("t", true).unwrap();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Listening,
            0,
            None,
            false,
        )
        .unwrap();
        assert_eq!(
            ledger.begin("another", context(), Route::Offline),
            Err(Error::Busy)
        );
        ledger.release_voice(&owner()).unwrap();
        ledger.begin("another", context(), Route::Offline).unwrap();
    }
    #[test]
    fn capacity_failure_keeps_current_evidence_and_all_replay_tombstones() {
        let mut ledger = Ledger::default();
        for i in 0..ENTRY_LIMIT - 1 {
            let id = format!("t-{i}");
            ledger.begin(&id, context(), Route::Offline).unwrap();
            ledger.finish(&id, true).unwrap();
        }
        observe(
            &mut ledger,
            &owner(),
            "last",
            AudioState::Speaking,
            2400,
            Some(480),
            false,
        )
        .unwrap();
        assert!(!ledger.voice_capacity());
        assert!(observe(
            &mut ledger,
            &owner(),
            "overflow",
            AudioState::Listening,
            0,
            None,
            false
        )
        .is_err());
        assert_eq!(ledger.voice_facts(1_000_000_000), (false, true));
        observe(
            &mut ledger,
            &owner(),
            "last",
            AudioState::Stopped,
            2400,
            Some(960),
            false,
        )
        .unwrap();
        assert_eq!(
            ledger.begin("overflow", context(), Route::Offline),
            Err(Error::Budget)
        );
        assert_eq!(
            ledger.begin("t-0", context(), Route::Offline),
            Err(Error::Duplicate)
        );
    }
    #[test]
    fn diagnostic_record_is_metadata_only_and_does_not_invent_duration() {
        let mut ledger = Ledger::default();
        observe(
            &mut ledger,
            &owner(),
            "v",
            AudioState::Thinking,
            2400,
            None,
            false,
        )
        .unwrap();
        let encoded = record(&ledger, "v");
        let expected = [
            "route",
            "companion_id",
            "source_id",
            "session_id",
            "turn_id",
            "generated",
            "displayed",
            "generated_samples",
            "reported_played_samples",
            "confirmed_played_samples",
            "interrupted",
            "finished",
            "end",
            "observed_at_ns",
        ];
        assert_eq!(encoded.as_object().unwrap().len(), expected.len());
        assert!(expected.iter().all(|key| encoded.get(key).is_some()));
    }
}

#[cfg(test)]
mod voice_event_tests {
    use super::*;
    use companion_voice::dialogue::{Event, Phase, Record, ResponseStatus, Tool};
    use std::{fs, os::unix::fs::PermissionsExt, path::PathBuf};

    fn open() -> (PathBuf, Ledger, VoiceLease) {
        let dir = std::env::temp_dir().join(format!(
            "eva-voice-event-{}",
            crate::storage::random_id().unwrap()
        ));
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        let mut ledger = Ledger::open(&dir, "eva", "boot").unwrap();
        let owner = VoiceLease {
            source_id: "source".into(),
            session_id: "activation".into(),
        };
        ledger
            .observe_voice(VoiceObservation {
                companion_id: "eva",
                owner: &owner,
                turn_id: "turn",
                state: AudioState::Thinking,
                generated_samples: 0,
                played_samples: None,
                interrupted: false,
                observed_at_ns: 10,
                received_at_ns: 10,
            })
            .unwrap();
        (dir, ledger, owner)
    }
    fn record(event: Event) -> Record {
        Record {
            voice_session_id: "activation".into(),
            turn_id: "turn".into(),
            observed_at_ns: 10,
            event,
        }
    }
    #[test]
    fn voice_references_are_bound_and_generation_is_separate_from_playback() {
        let (dir, mut ledger, owner) = open();
        let input = record(Event::InputCommitted {
            item_id: "input".into(),
        });
        assert!(ledger.voice_event("other-source", &input, 10).is_err());
        assert!(ledger.voice_event("source", &input, 9).is_err());
        ledger.voice_event("source", &input, 10).unwrap();
        let response = record(Event::ResponseCompleted {
            response_id: "response".into(),
            phase: Phase::Plan,
            status: ResponseStatus::Completed,
        });
        ledger.voice_event("source", &response, 10).unwrap();
        ledger
            .voice_event(
                "source",
                &record(Event::ToolCall {
                    response_id: "response".into(),
                    call_id: "call".into(),
                    tool: Tool::SubmitPlan,
                    arguments_digest: "a".repeat(64),
                }),
                10,
            )
            .unwrap();
        let feedback = record(Event::ResponseCompleted {
            response_id: "feedback".into(),
            phase: Phase::Feedback,
            status: ResponseStatus::Completed,
        });
        ledger.voice_event("source", &feedback, 10).unwrap();
        ledger
            .voice_event(
                "source",
                &record(Event::ReplyGenerated {
                    response_id: "feedback".into(),
                    content_digest: "c".repeat(64),
                }),
                10,
            )
            .unwrap();
        let facts = ledger.voice_record_for(&owner, "turn").unwrap();
        assert_eq!(facts["generated"], true);
        assert_eq!(facts["displayed"], false);
        assert_eq!(facts["confirmed_played_samples"], 0);
        ledger.release_voice(&owner);
        assert!(ledger.voice_event("source", &feedback, 10).is_err());
        let mut result = record(Event::ToolResult {
            call_id: "call".into(),
            result_digest: "b".repeat(64),
            outcome: companion_voice::dialogue::Outcome::Unknown,
            operations: vec![],
        });
        result.voice_session_id = "later-activation".into();
        assert!(ledger.voice_event("source", &result, 10).is_err());
        result.voice_session_id = "activation".into();
        ledger.voice_event("source", &result, 10).unwrap();
        assert_eq!(ledger.voice_facts(10), (false, false));
        let bytes = fs::read(dir.join("dialogue-events.json")).unwrap();
        drop(ledger);
        let mut restarted = Ledger::open(&dir, "eva", "next-boot").unwrap();
        assert!(restarted.voice_event("source", &result, 10).is_err());
        assert_eq!(restarted.voice_facts(10), (false, false));
        assert_eq!(fs::read(dir.join("dialogue-events.json")).unwrap(), bytes);
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn failed_reference_persistence_disables_admission_but_does_not_block_release() {
        let (dir, mut ledger, owner) = open();
        fs::create_dir(dir.join("dialogue-events.json")).unwrap();
        let input = record(Event::InputCommitted {
            item_id: "input".into(),
        });
        assert_eq!(
            ledger.voice_event("source", &input, 10),
            Err("voice_dialogue_persistence_failed")
        );
        assert!(ledger.journal_failed());
        assert!(!ledger.voice_capacity());
        assert!(ledger.release_voice(&owner).is_some());
        assert_eq!(ledger.voice_facts(10), (false, false));
        fs::remove_dir_all(dir).unwrap();
    }
}

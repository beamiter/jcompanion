//! Bounded local metadata index. Transcript bodies and selection evidence never
//! enter this file, and historical records never restore execution or audio rights.
use crate::dialogue::{End, Entry, Origin, Route};
use companion_protocol::{identifier, valid_context, Host, TaskStatus};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
};

const MAX_BYTES: usize = 8 * 1024 * 1024;
const MAX_TURNS: usize = 4096;
const MAX_RESULTS: usize = 4096;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Turn {
    pub boot_id: String,
    pub turn_id: String,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
    pub recovered_after_restart: bool,
    pub entry: Entry,
}

/// A reference to an already authenticated task receipt, not its output, an
/// action permit, or a replacement for the original executor's result ledger.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResultRef {
    pub boot_id: String,
    pub host_id: String,
    pub host_incarnation: u64,
    pub task_id: String,
    pub project_id: Option<String>,
    pub revision: u64,
    pub status: TaskStatus,
    pub observed_at_ms: u64,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    schema: u16,
    companion_id: String,
    turns: Vec<Turn>,
    results: Vec<ResultRef>,
}

pub struct Journal {
    path: PathBuf,
    boot_id: String,
    document: Document,
}

fn invalid(reason: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}
fn now_ms() -> io::Result<u64> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()
        .and_then(|d| u64::try_from(d.as_millis()).ok())
        .ok_or_else(|| invalid("dialogue_clock"))
}

pub(crate) fn write_private(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let temp = path.with_file_name(format!("dialogue-{}.next", crate::storage::random_id()?));
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temp)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&temp, path)?;
        File::open(path.parent().ok_or_else(|| invalid("dialogue_parent"))?)?.sync_all()
    })();
    if result.is_err() {
        let _ = fs::remove_file(temp);
    }
    result
}
fn entry_valid(entry: &Entry) -> bool {
    let origin = match &entry.origin {
        Origin::Text(c) => {
            valid_context(c) && entry.route != Route::EvaVoice && entry.audio.is_none()
        }
        Origin::Voice {
            companion_id,
            owner,
        } => {
            identifier(companion_id)
                && identifier(&owner.source_id)
                && identifier(&owner.session_id)
                && entry.route == Route::EvaVoice
                && entry.audio.is_some()
        }
    };
    origin
        && entry
            .publisher
            .as_ref()
            .is_none_or(|p| identifier(&p.source_id) && p.host_incarnation > 0)
        && entry.model.as_ref().is_none_or(|m| identifier(m))
        && entry.audio.as_ref().is_none_or(|a| {
            a.confirmed_played_samples <= a.generated_samples
                && a.reported_played_samples
                    .is_none_or(|p| p >= a.confirmed_played_samples && p <= a.generated_samples)
        })
}
fn metadata(entry: &Entry) -> Entry {
    let mut entry = entry.clone();
    entry.user_input = None;
    entry.model_output = None;
    entry
}

impl Journal {
    /// Creation order, oldest first. Records are metadata only.
    pub(crate) fn turns(&self) -> &[Turn] {
        &self.document.turns
    }
    pub(crate) fn boot_id(&self) -> &str {
        &self.boot_id
    }
    /// Called while the daemon already holds the exclusive profile lock.
    /// An invalid/unreadable journal is never silently discarded or reset.
    pub fn open(dir: &Path, companion_id: &str, boot_id: &str) -> io::Result<Self> {
        let m = fs::symlink_metadata(dir)?;
        if !m.is_dir()
            || m.uid() != unsafe { libc::geteuid() }
            || m.mode() & 0o077 != 0
            || !identifier(companion_id)
            || !identifier(boot_id)
        {
            return Err(invalid("dialogue_private_profile"));
        }
        let path = dir.join("dialogue-index.json");
        let mut document = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&path)
        {
            Ok(f) => {
                let m = f.metadata()?;
                if !m.is_file()
                    || m.uid() != unsafe { libc::geteuid() }
                    || m.mode() & 0o077 != 0
                    || m.len() > MAX_BYTES as u64
                {
                    return Err(invalid("dialogue_private_file"));
                }
                let mut bytes = Vec::new();
                f.take(MAX_BYTES as u64 + 1).read_to_end(&mut bytes)?;
                if bytes.len() > MAX_BYTES {
                    return Err(invalid("dialogue_limit"));
                }
                companion_protocol::strict_json::parse(&bytes)
                    .map_err(|_| invalid("dialogue_json"))?;
                serde_json::from_slice::<Document>(&bytes)
                    .map_err(|_| invalid("dialogue_schema"))?
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => Document {
                schema: 1,
                companion_id: companion_id.into(),
                turns: vec![],
                results: vec![],
            },
            Err(e) => return Err(e),
        };
        if document.schema != 1
            || document.companion_id != companion_id
            || document.turns.len() > MAX_TURNS
            || document.results.len() > MAX_RESULTS
            || document.turns.iter().any(|t| {
                !identifier(&t.boot_id)
                    || !identifier(&t.turn_id)
                    || t.created_at_ms == 0
                    || t.updated_at_ms == 0
                    || !entry_valid(&t.entry)
            })
            || document.results.iter().any(|r| {
                !identifier(&r.boot_id)
                    || !identifier(&r.host_id)
                    || r.host_incarnation == 0
                    || !identifier(&r.task_id)
                    || r.project_id.as_ref().is_some_and(|p| !identifier(p))
            })
        {
            return Err(invalid("dialogue_invalid_index"));
        }
        let mut recovered = false;
        for turn in &mut document.turns {
            if !turn.entry.finished {
                recovered = true;
                turn.recovered_after_restart = true;
                turn.entry.finished = true;
                turn.entry.end = Some(End::RestartedUnknown);
                if let Some(audio) = &mut turn.entry.audio {
                    audio.state = None;
                    audio.observed_at_ns = 0;
                    audio.reported_played_samples = None;
                }
            }
        }
        let mut journal = Self {
            path,
            boot_id: boot_id.into(),
            document,
        };
        if recovered {
            journal.commit(journal.document.clone())?;
        }
        Ok(journal)
    }

    fn commit(&mut self, next: Document) -> io::Result<()> {
        let bytes = serde_json::to_vec(&next).map_err(|_| invalid("dialogue_encoding"))?;
        if bytes.len() > MAX_BYTES {
            return Err(invalid("dialogue_limit"));
        }
        write_private(&self.path, &bytes)?;
        self.document = next;
        Ok(())
    }

    pub fn record(&mut self, turn_id: &str, entry: &Entry) -> io::Result<()> {
        if !identifier(turn_id) || !entry_valid(entry) {
            return Err(invalid("dialogue_record"));
        }
        let mut next = self.document.clone();
        let time = now_ms()?;
        if let Some(turn) = next.turns.iter_mut().find(|t| {
            t.boot_id == self.boot_id && t.turn_id == turn_id && t.entry.origin == entry.origin
        }) {
            turn.entry = metadata(entry);
            turn.updated_at_ms = time;
        } else {
            if next.turns.len() >= MAX_TURNS {
                let oldest = next
                    .turns
                    .iter()
                    .position(|t| t.boot_id != self.boot_id && t.entry.finished)
                    .ok_or_else(|| invalid("dialogue_capacity"))?;
                next.turns.remove(oldest);
            }
            next.turns.push(Turn {
                boot_id: self.boot_id.clone(),
                turn_id: turn_id.into(),
                created_at_ms: time,
                updated_at_ms: time,
                recovered_after_restart: false,
                entry: metadata(entry),
            });
        }
        self.commit(next)
    }

    pub fn result(
        &mut self,
        host: &Host,
        task: &str,
        project: Option<&str>,
        revision: u64,
        status: TaskStatus,
    ) -> io::Result<()> {
        if !identifier(&host.id)
            || host.incarnation == 0
            || !identifier(task)
            || project.is_some_and(|p| !identifier(p))
        {
            return Err(invalid("dialogue_result_ref"));
        }
        let mut next = self.document.clone();
        let receipt = ResultRef {
            boot_id: self.boot_id.clone(),
            host_id: host.id.clone(),
            host_incarnation: host.incarnation,
            task_id: task.into(),
            project_id: project.map(str::to_owned),
            revision,
            status,
            observed_at_ms: now_ms()?,
        };
        if let Some(old) = next.results.iter_mut().find(|r| {
            r.boot_id == self.boot_id
                && r.host_id == host.id
                && r.host_incarnation == host.incarnation
                && r.task_id == task
        }) {
            if old.revision > revision
                || old
                    .project_id
                    .as_ref()
                    .is_some_and(|p| Some(p) != receipt.project_id.as_ref())
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "dialogue_stale_result",
                ));
            }
            *old = receipt;
        } else {
            if next.results.len() >= MAX_RESULTS {
                next.results.remove(0);
            }
            next.results.push(receipt);
        }
        self.commit(next)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dialogue::{Ledger, Publisher, VoiceObservation};
    use companion_protocol::{AudioState, ContextRef, RetirementCapability, VoiceLease};
    use std::os::unix::fs::PermissionsExt;

    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let p = std::env::temp_dir().join(format!(
                "eva-dialogue-{}",
                crate::storage::random_id().unwrap()
            ));
            fs::create_dir(&p).unwrap();
            fs::set_permissions(&p, fs::Permissions::from_mode(0o700)).unwrap();
            Self(p)
        }
        fn path(&self) -> PathBuf {
            self.0.join("dialogue-index.json")
        }
        fn document(&self) -> Document {
            serde_json::from_slice(&fs::read(self.path()).unwrap()).unwrap()
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn context() -> ContextRef {
        ContextRef {
            host_id: "host".into(),
            pane_id: "pane".into(),
            task_id: Some("task".into()),
            project_id: Some("project".into()),
            revision: 1,
        }
    }
    fn host() -> Host {
        Host {
            id: "host".into(),
            incarnation: 1,
            surface_id: "surface".into(),
            retirement: RetirementCapability::None,
        }
    }

    #[test]
    fn text_bodies_are_volatile_but_generated_and_displayed_remain_distinct() {
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot1").unwrap();
        let turn = companion_openai::UserTurn {
            turn_id: "text".into(),
            context: context(),
            text: "private-user-dialogue".into(),
            approved_selection: Some(companion_protocol::SelectionEvidence {
                context: context(),
                text: "private-selected-shell-output".into(),
                source_event_id: "event".into(),
                consent_id: "consent".into(),
                captured_at_ms: 1,
            }),
        };
        ledger
            .begin_input(
                &turn,
                Route::TextResponses,
                Some(Publisher {
                    source_id: "source".into(),
                    host_incarnation: 1,
                }),
            )
            .unwrap();
        ledger
            .finish_output("text", "private-model-output")
            .unwrap();
        assert_eq!(
            ledger.entry("text").unwrap().user_input.as_deref(),
            Some("private-user-dialogue")
        );
        assert_eq!(
            ledger.entry("text").unwrap().model_output.as_deref(),
            Some("private-model-output")
        );
        let bytes = fs::read_to_string(temp.path()).unwrap();
        for secret in [
            "private-user-dialogue",
            "private-selected-shell-output",
            "private-model-output",
            "consent",
        ] {
            assert!(!bytes.contains(secret));
        }
        let doc = temp.document();
        assert_eq!(doc.turns.len(), 1);
        assert!(doc.turns[0].entry.generated);
        assert!(!doc.turns[0].entry.displayed);
        assert!(doc.turns[0].entry.audio.is_none());
        assert_eq!(
            doc.turns[0].entry.publisher.as_ref().unwrap().source_id,
            "source"
        );
        ledger.displayed("text", &context()).unwrap();
        assert!(temp.document().turns[0].entry.displayed);
        let restarted = Ledger::open(&temp.0, "eva", "boot2").unwrap();
        assert!(restarted.entry("text").is_none());
        assert!(restarted.voice_capacity());
    }

    #[test]
    fn restart_never_restores_active_audio_or_promotes_uncommitted_playback() {
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot1").unwrap();
        let owner = VoiceLease {
            source_id: "voice".into(),
            session_id: "activation".into(),
        };
        let mut observe = |generated, played, at| {
            ledger
                .observe_voice(VoiceObservation {
                    companion_id: "eva",
                    owner: &owner,
                    turn_id: "voice-turn",
                    state: AudioState::Speaking,
                    generated_samples: generated,
                    played_samples: Some(played),
                    interrupted: false,
                    observed_at_ns: at,
                    received_at_ns: at,
                })
                .unwrap()
        };
        observe(100, 10, 1_000_000_000);
        let first = fs::read(temp.path()).unwrap();
        observe(300, 150, 1_100_000_000);
        assert_eq!(
            fs::read(temp.path()).unwrap(),
            first,
            "progress must not fsync at audio frequency"
        );
        drop(ledger);
        let restarted = Ledger::open(&temp.0, "eva", "boot2").unwrap();
        assert_eq!(restarted.voice_facts(1_100_000_000), (false, false));
        let doc = temp.document();
        let entry = &doc.turns[0].entry;
        assert!(doc.turns[0].recovered_after_restart);
        assert_eq!(entry.end, Some(End::RestartedUnknown));
        assert!(entry.finished);
        assert!(!entry.interrupted);
        let audio = entry.audio.as_ref().unwrap();
        assert_eq!(audio.generated_samples, 100);
        assert_eq!(audio.confirmed_played_samples, 10);
        assert_eq!(audio.reported_played_samples, None);
        assert_eq!(audio.state, None);
        assert_eq!(audio.observed_at_ns, 0);
    }

    #[test]
    fn close_commits_last_real_played_count_and_new_boot_has_no_replay_authority() {
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot1").unwrap();
        let owner = VoiceLease {
            source_id: "voice".into(),
            session_id: "activation".into(),
        };
        for (played, at) in [(10, 1_000_000_000), (75, 1_100_000_000)] {
            ledger
                .observe_voice(VoiceObservation {
                    companion_id: "eva",
                    owner: &owner,
                    turn_id: "turn",
                    state: AudioState::Speaking,
                    generated_samples: 100,
                    played_samples: Some(played),
                    interrupted: false,
                    observed_at_ns: at,
                    received_at_ns: at,
                })
                .unwrap();
        }
        ledger.release_voice(&owner).unwrap();
        let doc = temp.document();
        assert_eq!(
            doc.turns[0]
                .entry
                .audio
                .as_ref()
                .unwrap()
                .confirmed_played_samples,
            75
        );
        assert_eq!(doc.turns[0].entry.end, Some(End::ResourcesReleased));
        let mut restarted = Ledger::open(&temp.0, "eva", "boot2").unwrap();
        assert!(restarted.release_voice(&owner).is_none());
        assert_eq!(restarted.voice_facts(1_100_000_000), (false, false));
    }

    #[test]
    fn result_reference_keeps_source_project_and_rejects_old_receipts() {
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot1").unwrap();
        ledger
            .record_task_result(&host(), "task", Some("A"), 2, TaskStatus::Running)
            .unwrap();
        let before = fs::read(temp.path()).unwrap();
        assert_eq!(
            ledger.record_task_result(&host(), "task", Some("A"), 1, TaskStatus::Succeeded),
            Err(companion_openai::Error::Stale)
        );
        assert_eq!(
            ledger.record_task_result(&host(), "task", Some("B"), 3, TaskStatus::Succeeded),
            Err(companion_openai::Error::Stale)
        );
        assert_eq!(fs::read(temp.path()).unwrap(), before);
        assert!(!ledger.journal_failed());
        ledger
            .record_task_result(&host(), "task", Some("A"), 3, TaskStatus::Failed)
            .unwrap();
        let doc = temp.document();
        assert_eq!(doc.results.len(), 1);
        assert_eq!(doc.results[0].project_id.as_deref(), Some("A"));
        assert_eq!(doc.results[0].status, TaskStatus::Failed);
        assert_eq!(doc.results[0].host_incarnation, 1);
    }

    fn at(host: &str, pane: &str, task: Option<&str>, project: Option<&str>) -> ContextRef {
        ContextRef {
            host_id: host.into(),
            pane_id: pane.into(),
            task_id: task.map(str::to_owned),
            project_id: project.map(str::to_owned),
            revision: 7,
        }
    }
    fn say(ledger: &mut Ledger, id: &str, context: &ContextRef, selection: bool) {
        let turn = companion_openai::UserTurn {
            turn_id: id.into(),
            context: context.clone(),
            text: format!("input {id}"),
            approved_selection: selection.then(|| companion_protocol::SelectionEvidence {
                context: context.clone(),
                text: "reviewed terminal text".into(),
                source_event_id: "event".into(),
                consent_id: "consent".into(),
                captured_at_ms: 1,
            }),
        };
        ledger.begin_input(&turn, Route::Offline, None).unwrap();
        ledger.finish_output(id, &format!("reply {id}")).unwrap();
    }
    fn ids(page: &[companion_protocol::history::Entry]) -> Vec<&str> {
        page.iter().map(|e| e.turn_id.as_str()).collect()
    }

    #[test]
    fn history_scopes_never_cross_projects_tasks_or_panes() {
        use companion_protocol::history::Scope;
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot").unwrap();
        let a = at("ember-1", "pane-a", Some("task-1"), Some("project-a"));
        let same_task_other_host = at("forge-1", "pane-b", Some("task-1"), Some("project-a"));
        let other_task = at("forge-1", "pane-c", Some("task-2"), Some("project-a"));
        let other_project = at("forge-1", "pane-d", Some("task-1"), Some("project-b"));
        let no_project = at("ember-1", "pane-a", None, None);
        for (id, context) in [
            ("a", &a),
            ("b", &same_task_other_host),
            ("c", &other_task),
            ("d", &other_project),
            ("e", &no_project),
        ] {
            say(&mut ledger, id, context, false);
        }
        let page = |context: &ContextRef, scope| ledger.history(context, scope, None);
        assert_eq!(ids(&page(&a, Scope::Context).unwrap().0), ["a"]);
        let mut revised = a.clone();
        revised.revision = 99;
        assert_eq!(ids(&page(&revised, Scope::Context).unwrap().0), ["a"]);
        assert_eq!(ids(&page(&a, Scope::Task).unwrap().0), ["b", "a"]);
        assert_eq!(ids(&page(&a, Scope::Project).unwrap().0), ["c", "b", "a"]);
        assert_eq!(ids(&page(&other_project, Scope::Project).unwrap().0), ["d"]);
        assert_eq!(ids(&page(&other_project, Scope::Task).unwrap().0), ["d"]);
        assert_eq!(ids(&page(&no_project, Scope::Context).unwrap().0), ["e"]);
        assert_eq!(
            page(&no_project, Scope::Project).err(),
            Some("scope_unavailable")
        );
        assert_eq!(
            page(&no_project, Scope::Task).err(),
            Some("scope_unavailable")
        );
        assert!(page(&a, Scope::Voice).unwrap().0.is_empty());
        let shown = &page(&a, Scope::Project).unwrap().0[1];
        assert_eq!(shown.source.as_ref(), Some(&same_task_other_host));
        assert_eq!(shown.input.as_deref(), Some("input b"));
    }

    #[test]
    fn history_pages_newest_first_and_reject_unknown_cursors() {
        use companion_protocol::history::{Scope, MAX_PAGE};
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot").unwrap();
        let context = at("host", "pane", None, Some("project"));
        let all: Vec<String> = (0..20).map(|n| format!("turn-{n:02}")).collect();
        for id in &all {
            say(&mut ledger, id, &context, false);
        }
        let mut seen = vec![];
        let mut before = None;
        let mut pages = 0;
        loop {
            let (page, next) = ledger
                .history(&context, Scope::Project, before.as_deref())
                .unwrap();
            assert!(page.len() <= MAX_PAGE && !page.is_empty());
            seen.extend(page.iter().map(|e| e.turn_id.clone()));
            pages += 1;
            match next {
                Some(cursor) => {
                    assert_eq!(Some(&cursor), page.last().map(|e| &e.cursor));
                    before = Some(cursor);
                }
                None => break,
            }
        }
        assert_eq!(pages, 3);
        let mut newest_first = all.clone();
        newest_first.reverse();
        assert_eq!(seen, newest_first);
        assert_eq!(
            ledger
                .history(&context, Scope::Project, Some(&"0".repeat(64)))
                .err(),
            Some("history_cursor_stale")
        );
        // A cursor from another scope is not a position in this one.
        let elsewhere = at("host", "other-pane", None, Some("project"));
        say(&mut ledger, "elsewhere", &elsewhere, false);
        let foreign = ledger.history(&elsewhere, Scope::Context, None).unwrap().0[0]
            .cursor
            .clone();
        assert_eq!(
            ledger
                .history(&context, Scope::Context, Some(&foreign))
                .err(),
            Some("history_cursor_stale")
        );
        // New turns do not shift an existing cursor.
        let (first, next) = ledger.history(&context, Scope::Context, None).unwrap();
        say(&mut ledger, "late", &context, false);
        let (second, _) = ledger
            .history(&context, Scope::Context, next.as_deref())
            .unwrap();
        assert_eq!(second[0].turn_id, "turn-11");
        assert!(second
            .iter()
            .all(|e| first.iter().all(|f| f.cursor != e.cursor)));
    }

    #[test]
    fn history_text_is_session_only_and_reviewed_selection_stays_with_origin() {
        use companion_protocol::history::{Scope, Text};
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot1").unwrap();
        let origin = at("ember-1", "pane-a", None, Some("project"));
        let other = at("forge-1", "pane-b", None, Some("project"));
        say(&mut ledger, "plain", &origin, false);
        say(&mut ledger, "selected", &origin, true);
        let (page, _) = ledger.history(&other, Scope::Project, None).unwrap();
        assert_eq!(page[0].turn_id, "selected");
        assert_eq!(page[0].text, Text::WithheldOutsideOrigin);
        assert!(page[0].input.is_none() && page[0].reply.is_none());
        assert_eq!(page[1].text, Text::Shown);
        assert_eq!(page[1].reply.as_deref(), Some("reply plain"));
        let (page, _) = ledger.history(&origin, Scope::Context, None).unwrap();
        assert_eq!(page[0].text, Text::Shown);
        assert_eq!(page[0].input.as_deref(), Some("input selected"));
        let serialized = serde_json::to_string(&page).unwrap();
        assert!(!serialized.contains("reviewed terminal text"));
        assert!(!serialized.contains("consent"));
        drop(ledger);
        let ledger = Ledger::open(&temp.0, "eva", "boot2").unwrap();
        let (page, _) = ledger.history(&origin, Scope::Context, None).unwrap();
        assert_eq!(ids(&page), ["selected", "plain"]);
        for entry in &page {
            assert_eq!(entry.text, Text::EarlierSession);
            assert!(entry.input.is_none() && entry.reply.is_none());
            assert!(entry.generated && entry.finished);
        }
    }

    #[test]
    fn history_page_fits_one_frame_and_marks_oversize_text() {
        use companion_protocol::history::{Scope, Text, MAX_PAGE_BYTES};
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot").unwrap();
        let context = at("host", "pane", None, None);
        for n in 0..8 {
            let id = format!("large-{n}");
            // Control characters expand six-fold in JSON.
            let text = "\u{1}".repeat(8192);
            let turn = companion_openai::UserTurn {
                turn_id: id.clone(),
                context: context.clone(),
                text: text.clone(),
                approved_selection: None,
            };
            ledger.begin_input(&turn, Route::Offline, None).unwrap();
            ledger.finish_output(&id, &"x".repeat(8192)).unwrap();
        }
        let (page, next) = ledger.history(&context, Scope::Context, None).unwrap();
        assert!(page
            .iter()
            .all(|e| e.text == Text::TooLarge && e.input.is_none()));
        assert_eq!(page.len(), 8);
        assert!(next.is_none());
        let reply = companion_protocol::Reply::DialogueHistory {
            request_id: u64::MAX,
            context: context.clone(),
            scope: Scope::Context,
            status: "ok".into(),
            entries: page,
            next_before: None,
        };
        assert!(serde_json::to_vec(&reply).unwrap().len() <= companion_protocol::MAX_FRAME);
        let mut ledger = Ledger::open(&temp.0, "eva", "boot2").unwrap();
        for n in 0..8 {
            let id = format!("medium-{n}");
            let turn = companion_openai::UserTurn {
                turn_id: id.clone(),
                context: context.clone(),
                text: "m".repeat(8192),
                approved_selection: None,
            };
            ledger.begin_input(&turn, Route::Offline, None).unwrap();
            ledger.finish_output(&id, &"r".repeat(8192)).unwrap();
        }
        let (page, next) = ledger.history(&context, Scope::Context, None).unwrap();
        let bytes: usize = page
            .iter()
            .map(|e| serde_json::to_vec(e).unwrap().len())
            .sum();
        assert!(bytes <= MAX_PAGE_BYTES);
        assert!(page.len() < 8 && page.iter().all(|e| e.text == Text::Shown));
        assert_eq!(next, page.last().map(|e| e.cursor.clone()));
    }

    #[test]
    fn voice_history_reports_counters_without_transcripts_or_text_scopes() {
        use companion_protocol::history::{Route as View, Scope, Text};
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot").unwrap();
        let owner = VoiceLease {
            source_id: "voice".into(),
            session_id: "activation".into(),
        };
        ledger
            .observe_voice(VoiceObservation {
                companion_id: "eva",
                owner: &owner,
                turn_id: "spoken",
                state: AudioState::Speaking,
                generated_samples: 4800,
                played_samples: Some(1200),
                interrupted: false,
                observed_at_ns: 1_000_000_000,
                received_at_ns: 1_000_000_000,
            })
            .unwrap();
        let context = at("host", "pane", Some("task"), Some("project"));
        for scope in [Scope::Context, Scope::Task, Scope::Project] {
            assert!(ledger.history(&context, scope, None).unwrap().0.is_empty());
        }
        let (page, _) = ledger.history(&context, Scope::Voice, None).unwrap();
        assert_eq!(page.len(), 1);
        let entry = &page[0];
        assert!(entry.valid());
        assert_eq!(entry.route, View::Voice);
        assert_eq!(entry.text, Text::NotRecorded);
        assert!(entry.source.is_none() && entry.input.is_none());
        assert_eq!(entry.generated_samples, Some(4800));
        assert_eq!(entry.confirmed_played_samples, Some(1200));
        assert!(!entry.finished);
    }

    #[test]
    fn corrupt_public_or_foreign_profile_index_is_not_reset() {
        let temp = Temp::new();
        fs::write(temp.path(), b"{}").unwrap();
        fs::set_permissions(temp.path(), fs::Permissions::from_mode(0o644)).unwrap();
        assert!(Journal::open(&temp.0, "eva", "boot").is_err());
        fs::set_permissions(temp.path(), fs::Permissions::from_mode(0o600)).unwrap();
        assert!(Journal::open(&temp.0, "eva", "boot").is_err());
        assert_eq!(fs::read(temp.path()).unwrap(), b"{}");
        fs::remove_file(temp.path()).unwrap();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot1").unwrap();
        ledger.begin("pending", context(), Route::Offline).unwrap();
        let before = fs::read(temp.path()).unwrap();
        assert!(Journal::open(&temp.0, "another-companion", "boot2").is_err());
        assert_eq!(fs::read(temp.path()).unwrap(), before);
    }

    #[test]
    fn failed_write_disables_new_turns_without_claiming_persistence() {
        let temp = Temp::new();
        let mut ledger = Ledger::open(&temp.0, "eva", "boot").unwrap();
        ledger.begin("first", context(), Route::Offline).unwrap();
        ledger.finish("first", true).unwrap();
        fs::rename(temp.path(), temp.0.join("preserved.json")).unwrap();
        fs::create_dir(temp.path()).unwrap();
        assert_eq!(
            ledger.begin("blocked", context(), Route::TextResponses),
            Err(companion_openai::Error::LocalHistoryUnavailable)
        );
        assert!(ledger.entry("blocked").is_none());
        assert!(ledger.journal_failed());
        assert!(!ledger.voice_capacity());
        assert!(ledger.entry("first").unwrap().finished);
        assert!(temp.0.join("preserved.json").is_file());
    }
}

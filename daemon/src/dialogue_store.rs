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

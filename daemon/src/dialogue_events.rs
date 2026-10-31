//! Durable references for Eva's already-admitted model/tool/result pipeline.
//! A separate versioned file keeps the existing dialogue index rollback-readable.
use companion_protocol::identifier;
use companion_voice::dialogue::{Event, Outcome, Phase, Record, ResponseStatus, Tool};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::{self, Read},
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
};

const MAX_BYTES: usize = 8 * 1024 * 1024;
const MAX_TURNS: usize = 4096;
const MAX_EVENTS: usize = 128;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Turn {
    boot_id: String,
    source_id: String,
    voice_session_id: String,
    turn_id: String,
    events: Vec<Record>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    schema: u16,
    companion_id: String,
    turns: Vec<Turn>,
}

pub struct Journal {
    path: Option<PathBuf>,
    boot_id: String,
    document: Document,
}

fn invalid(reason: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, reason)
}

/// Validate references and monotonic refinements, never infer success from a
/// model response or from the fact that a tool call was accepted.
fn follows(previous: &[Record], incoming: &Record) -> bool {
    if !incoming.valid()
        || previous.len() >= MAX_EVENTS
        || previous
            .last()
            .is_some_and(|last| last.observed_at_ns > incoming.observed_at_ns)
    {
        return false;
    }
    match &incoming.event {
        Event::InputCommitted { .. } => previous.is_empty(),
        Event::ResponseCompleted { response_id, .. } => {
            !previous.is_empty()
                && !previous.iter().any(|p| {
                    matches!(&p.event,
                    Event::ResponseCompleted { response_id: old, .. } if old == response_id)
                })
        }
        Event::ReplyGenerated { response_id, .. } => {
            previous.iter().any(|p| matches!(&p.event,
                Event::ResponseCompleted { response_id: old, phase: Phase::Feedback, status: ResponseStatus::Completed }
                    if old == response_id))
                && !previous.iter().any(|p| matches!(&p.event,
                    Event::ReplyGenerated { response_id: old, .. } if old == response_id))
        }
        Event::OperationRegistered { call_id, operation_id, .. } => {
            previous.iter().any(|p| matches!(&p.event,
                Event::ToolCall { call_id: old, tool: Tool::SubmitPlan, .. } if old == call_id))
                && !previous.iter().any(|p| matches!(&p.event,
                    Event::OperationRegistered { operation_id: old, .. } if old == operation_id))
        },
        Event::OperationSettled { operation_id, request_digest, .. } => {
            previous.iter().any(|p| matches!(&p.event,
                Event::OperationRegistered { operation_id: old, request_digest: request, .. }
                    if old == operation_id && request == request_digest))
                && previous.iter().rev().find_map(|p| match &p.event {
                    Event::OperationSettled { operation_id: old, outcome, .. } if old == operation_id => Some(outcome),
                    _ => None,
                }).is_none_or(|outcome| *outcome == Outcome::Unknown)
        },
        Event::ToolCall {
            response_id,
            call_id,
            ..
        } => {
            previous.iter().any(|p| {
                matches!(&p.event,
                Event::ResponseCompleted { response_id: old, status: ResponseStatus::Completed, .. }
                    if old == response_id)
            }) && !previous.iter().any(|p| {
                matches!(&p.event,
                    Event::ToolCall { call_id: old, .. } if old == call_id)
            })
        }
        Event::ToolResult {
            call_id,
            outcome,
            operations,
            ..
        } => {
            let Some(tool) = previous.iter().find_map(|p| match &p.event {
                Event::ToolCall {
                    call_id: old, tool, ..
                } if old == call_id => Some(tool),
                _ => None,
            }) else {
                return false;
            };
            if *tool == Tool::DescribeActions
                && (!matches!(outcome, Outcome::Described | Outcome::Rejected)
                    || !operations.is_empty())
            {
                return false;
            }
            if *tool == Tool::SubmitPlan && *outcome == Outcome::Described {
                return false;
            }
            match previous.iter().rev().find_map(|p| match &p.event {
                Event::ToolResult {
                    call_id: old,
                    outcome,
                    operations,
                    ..
                } if old == call_id => Some((outcome, operations)),
                _ => None,
            }) {
                None => true,
                Some((old, before)) => {
                    *old == Outcome::Unknown
                        && before.len() == operations.len()
                        && before.iter().zip(operations).all(|(old, new)| {
                            old.operation_id == new.operation_id
                                && (old.outcome == Outcome::Unknown || old.outcome == new.outcome)
                        })
                }
            }
        }
    }
}

impl Journal {
    pub fn memory(companion: &str) -> Self {
        Self {
            path: None,
            boot_id: "memory".into(),
            document: Document {
                schema: 1,
                companion_id: companion.into(),
                turns: vec![],
            },
        }
    }
    pub fn open(dir: &Path, companion: &str, boot: &str) -> io::Result<Self> {
        let metadata = fs::symlink_metadata(dir)?;
        if !metadata.is_dir()
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.mode() & 0o077 != 0
            || !identifier(companion)
            || !identifier(boot)
        {
            return Err(invalid("voice_dialogue_private_profile"));
        }
        let path = dir.join("dialogue-events.json");
        let document = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&path)
        {
            Ok(file) => {
                let metadata = file.metadata()?;
                if !metadata.is_file()
                    || metadata.uid() != unsafe { libc::geteuid() }
                    || metadata.mode() & 0o077 != 0
                    || metadata.len() > MAX_BYTES as u64
                {
                    return Err(invalid("voice_dialogue_private_file"));
                }
                let mut bytes = vec![];
                file.take(MAX_BYTES as u64 + 1).read_to_end(&mut bytes)?;
                if bytes.len() > MAX_BYTES {
                    return Err(invalid("voice_dialogue_limit"));
                }
                companion_protocol::strict_json::parse(&bytes)
                    .map_err(|_| invalid("voice_dialogue_json"))?;
                serde_json::from_slice::<Document>(&bytes)
                    .map_err(|_| invalid("voice_dialogue_schema"))?
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => Document {
                schema: 1,
                companion_id: companion.into(),
                turns: vec![],
            },
            Err(error) => return Err(error),
        };
        let mut identities = std::collections::BTreeSet::new();
        if !matches!(document.schema, 1 | 2)
            || document.companion_id != companion
            || document.turns.len() > MAX_TURNS
            || document.turns.iter().any(|turn| {
                !identifier(&turn.boot_id)
                    || !identifier(&turn.source_id)
                    || !identifier(&turn.voice_session_id)
                    || !identifier(&turn.turn_id)
                    || turn.events.is_empty()
                    || turn.events.len() > MAX_EVENTS
                    || (document.schema == 1
                        && turn.events.iter().any(|event| {
                            matches!(
                                event.event,
                                Event::OperationRegistered { .. } | Event::OperationSettled { .. }
                            )
                        }))
                    || !identities.insert((
                        &turn.boot_id,
                        &turn.source_id,
                        &turn.voice_session_id,
                        &turn.turn_id,
                    ))
                    || turn.events.iter().enumerate().any(|(index, event)| {
                        event.voice_session_id != turn.voice_session_id
                            || event.turn_id != turn.turn_id
                            || !follows(&turn.events[..index], event)
                    })
            })
        {
            return Err(invalid("voice_dialogue_invalid_index"));
        }
        Ok(Self {
            path: Some(path),
            boot_id: boot.into(),
            document,
        })
    }

    pub fn record(&mut self, source: &str, record: &Record) -> io::Result<()> {
        if !identifier(source) || !record.valid() {
            return Err(invalid("voice_dialogue_record"));
        }
        let mut next = self.document.clone();
        if let Event::OperationRegistered { operation_id, .. } = &record.event {
            if next.turns.iter().any(|turn| {
                turn.boot_id == self.boot_id
                    && turn.source_id == source
                    && (turn.voice_session_id != record.voice_session_id
                        || turn.turn_id != record.turn_id)
                    && turn.events.iter().any(|previous| {
                        matches!(&previous.event,
                    Event::OperationRegistered { operation_id: old, .. } if old == operation_id)
                    })
            }) {
                return Err(invalid("voice_operation_already_bound"));
            }
        }
        if matches!(
            record.event,
            Event::OperationRegistered { .. } | Event::OperationSettled { .. }
        ) {
            next.schema = 2;
        }
        let index = next.turns.iter().position(|turn| {
            turn.boot_id == self.boot_id
                && turn.source_id == source
                && turn.voice_session_id == record.voice_session_id
                && turn.turn_id == record.turn_id
        });
        let index = match index {
            Some(index) => index,
            None => {
                if next.turns.len() >= MAX_TURNS {
                    return Err(io::Error::other("voice_dialogue_capacity"));
                }
                next.turns.push(Turn {
                    boot_id: self.boot_id.clone(),
                    source_id: source.into(),
                    voice_session_id: record.voice_session_id.clone(),
                    turn_id: record.turn_id.clone(),
                    events: vec![],
                });
                next.turns.len() - 1
            }
        };
        let events = &mut next.turns[index].events;
        // A producer may repeat the exact immutable receipt; it cannot replace
        // its outcome or rebind the call to a new response/activation.
        if events.contains(record) {
            return Ok(());
        }
        if events.len() >= MAX_EVENTS {
            return Err(io::Error::other("voice_dialogue_capacity"));
        }
        if !follows(events, record) {
            return Err(invalid("voice_dialogue_order_or_reference"));
        }
        events.push(record.clone());
        if let Some(path) = &self.path {
            let bytes =
                serde_json::to_vec(&next).map_err(|_| invalid("voice_dialogue_encoding"))?;
            if bytes.len() > MAX_BYTES {
                return Err(io::Error::other("voice_dialogue_limit"));
            }
            crate::dialogue_store::write_private(path, &bytes)?;
        }
        self.document = next;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use companion_voice::dialogue::Operation;
    use std::os::unix::fs::PermissionsExt;

    fn record(sequence: u64, event: Event) -> Record {
        Record {
            voice_session_id: "activation-1".into(),
            turn_id: "turn-1".into(),
            observed_at_ns: sequence,
            event,
        }
    }
    fn events() -> Vec<Record> {
        vec![
            record(
                1,
                Event::InputCommitted {
                    item_id: "input-1".into(),
                },
            ),
            record(
                2,
                Event::ResponseCompleted {
                    response_id: "response-1".into(),
                    phase: Phase::Plan,
                    status: ResponseStatus::Completed,
                },
            ),
            record(
                3,
                Event::ToolCall {
                    response_id: "response-1".into(),
                    call_id: "call-1".into(),
                    tool: Tool::SubmitPlan,
                    arguments_digest: "a".repeat(64),
                },
            ),
            record(
                4,
                Event::ToolResult {
                    call_id: "call-1".into(),
                    result_digest: "b".repeat(64),
                    outcome: Outcome::Unknown,
                    operations: vec![Operation {
                        operation_id: "operation-1".into(),
                        outcome: Outcome::Unknown,
                    }],
                },
            ),
        ]
    }
    #[test]
    fn completed_call_references_and_unknown_refinement_are_required() {
        let mut journal = Journal::memory("eva");
        let events = events();
        assert!(journal.record("voice", &events[3]).is_err());
        for event in &events {
            journal.record("voice", event).unwrap();
        }
        journal.record("voice", &events[3]).unwrap();
        assert_eq!(journal.document.turns[0].events.len(), 4);
        let mut refined = events[3].clone();
        refined.observed_at_ns = 5;
        if let Event::ToolResult {
            outcome,
            operations,
            ..
        } = &mut refined.event
        {
            *outcome = Outcome::Succeeded;
            operations[0].outcome = Outcome::Succeeded;
        }
        journal.record("voice", &refined).unwrap();
        let mut contradicted = events[3].clone();
        contradicted.observed_at_ns = 6;
        assert!(journal.record("voice", &contradicted).is_err());
        refined.voice_session_id = "activation-2".into();
        assert!(journal.record("voice", &refined).is_err());
        assert!(journal.record("another-voice", &events[3]).is_err());
    }
    #[test]
    fn incomplete_or_missing_response_never_becomes_a_tool_call() {
        let mut journal = Journal::memory("eva");
        let mut events = events();
        journal.record("voice", &events[0]).unwrap();
        assert!(journal.record("voice", &events[2]).is_err());
        if let Event::ResponseCompleted { status, .. } = &mut events[1].event {
            *status = ResponseStatus::Incomplete;
        }
        journal.record("voice", &events[1]).unwrap();
        assert!(journal.record("voice", &events[2]).is_err());
        assert!(journal.record("voice", &events[3]).is_err());
    }
    #[test]
    fn contradictory_discovery_and_out_of_order_events_are_rejected() {
        let mut journal = Journal::memory("eva");
        let mut events = events();
        if let Event::ToolCall { tool, .. } = &mut events[2].event {
            *tool = Tool::DescribeActions;
        }
        for event in &events[..3] {
            journal.record("voice", event).unwrap();
        }
        assert!(journal.record("voice", &events[3]).is_err());
        let described = record(
            4,
            Event::ToolResult {
                call_id: "call-1".into(),
                result_digest: "b".repeat(64),
                outcome: Outcome::Described,
                operations: vec![],
            },
        );
        journal.record("voice", &described).unwrap();
        let old = record(
            2,
            Event::ResponseCompleted {
                response_id: "old".into(),
                phase: Phase::Feedback,
                status: ResponseStatus::Completed,
            },
        );
        assert!(journal.record("voice", &old).is_err());
    }
    #[test]
    fn persisted_references_survive_restart_without_changing_unknown_to_success() {
        let root = std::env::temp_dir().join(format!(
            "eva-dialogue-events-{}",
            crate::storage::random_id().unwrap()
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let mut journal = Journal::open(&root, "eva", "boot-1").unwrap();
        for event in events() {
            journal.record("voice", &event).unwrap();
        }
        let file = root.join("dialogue-events.json");
        assert_eq!(
            fs::metadata(&file).unwrap().permissions().mode() & 0o777,
            0o600
        );
        let before = fs::read(&file).unwrap();
        let restarted = Journal::open(&root, "eva", "boot-2").unwrap();
        assert_eq!(restarted.document.turns.len(), 1);
        assert!(matches!(
            restarted.document.turns[0].events.last().unwrap().event,
            Event::ToolResult {
                outcome: Outcome::Unknown,
                ..
            }
        ));
        assert_eq!(fs::read(&file).unwrap(), before);
        assert!(!root.join("dialogue-index.json").exists());
        assert!(Journal::open(&root, "another-eva", "boot-2").is_err());
        fs::write(&file, b"{\"schema\":1,\"schema\":2}").unwrap();
        let damaged = fs::read(&file).unwrap();
        assert!(Journal::open(&root, "eva", "boot-2").is_err());
        assert_eq!(fs::read(&file).unwrap(), damaged);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn operation_receipts_require_original_registration_and_terminal_facts_are_immutable() {
        let mut journal = Journal::memory("eva");
        for event in &events()[..3] {
            journal.record("voice", event).unwrap();
        }
        let registered = record(
            4,
            Event::OperationRegistered {
                call_id: "call-1".into(),
                operation_id: "operation-1".into(),
                plan_hash: "c".repeat(64),
                wm_instance_id: "wm".into(),
                request_digest: "d".repeat(64),
            },
        );
        let mut settled = record(
            5,
            Event::OperationSettled {
                operation_id: "operation-1".into(),
                request_digest: "d".repeat(64),
                result_digest: "e".repeat(64),
                outcome: Outcome::Unknown,
            },
        );
        assert!(journal.record("voice", &settled).is_err());
        journal.record("voice", &registered).unwrap();
        assert_eq!(journal.document.schema, 2);
        let mut mismatch = settled.clone();
        if let Event::OperationSettled { request_digest, .. } = &mut mismatch.event {
            *request_digest = "f".repeat(64);
        }
        assert!(journal.record("voice", &mismatch).is_err());
        journal.record("voice", &settled).unwrap();
        settled.observed_at_ns = 6;
        if let Event::OperationSettled { outcome, .. } = &mut settled.event {
            *outcome = Outcome::Succeeded;
        }
        journal.record("voice", &settled).unwrap();
        journal.record("voice", &settled).unwrap();
        settled.observed_at_ns = 7;
        if let Event::OperationSettled { outcome, .. } = &mut settled.event {
            *outcome = Outcome::Failed;
        }
        assert!(journal.record("voice", &settled).is_err());
        let mut other_input = events()[0].clone();
        other_input.turn_id = "other-turn".into();
        journal.record("voice", &other_input).unwrap();
        let mut other_response = events()[1].clone();
        other_response.turn_id = "other-turn".into();
        journal.record("voice", &other_response).unwrap();
        let mut other_call = events()[2].clone();
        other_call.turn_id = "other-turn".into();
        journal.record("voice", &other_call).unwrap();
        let mut rebound = registered.clone();
        rebound.turn_id = "other-turn".into();
        assert!(journal.record("voice", &rebound).is_err());
    }

    #[test]
    fn operation_journal_requires_schema_two_and_keeps_references_on_restart() {
        let root = std::env::temp_dir().join(format!(
            "eva-operation-journal-{}",
            crate::storage::random_id().unwrap()
        ));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let mut journal = Journal::open(&root, "eva", "boot-1").unwrap();
        for event in &events()[..3] {
            journal.record("voice", event).unwrap();
        }
        journal
            .record(
                "voice",
                &record(
                    4,
                    Event::OperationRegistered {
                        call_id: "call-1".into(),
                        operation_id: "operation-1".into(),
                        plan_hash: "a".repeat(64),
                        wm_instance_id: "wm".into(),
                        request_digest: "b".repeat(64),
                    },
                ),
            )
            .unwrap();
        journal
            .record(
                "voice",
                &record(
                    5,
                    Event::OperationSettled {
                        operation_id: "operation-1".into(),
                        request_digest: "b".repeat(64),
                        result_digest: "c".repeat(64),
                        outcome: Outcome::Unknown,
                    },
                ),
            )
            .unwrap();
        let file = root.join("dialogue-events.json");
        let saved = fs::read(&file).unwrap();
        assert_eq!(
            Journal::open(&root, "eva", "boot-2")
                .unwrap()
                .document
                .schema,
            2
        );
        assert_eq!(fs::read(&file).unwrap(), saved);
        let mut downgraded: serde_json::Value = serde_json::from_slice(&saved).unwrap();
        downgraded["schema"] = serde_json::json!(1);
        fs::write(&file, serde_json::to_vec(&downgraded).unwrap()).unwrap();
        assert!(Journal::open(&root, "eva", "boot-2").is_err());
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&fs::read(&file).unwrap()).unwrap(),
            downgraded
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn new_field_or_plain_text_cannot_enter_the_reference_schema() {
        let mut value = serde_json::to_value(&events()[2]).unwrap();
        value["event"]["arguments"] = serde_json::json!({"private":"terminal text"});
        assert!(serde_json::from_value::<Record>(value).is_err());
        let mut invalid = events()[2].clone();
        if let Event::ToolCall {
            arguments_digest, ..
        } = &mut invalid.event
        {
            *arguments_digest = "private terminal text".into();
        }
        assert!(!invalid.valid());
        let mut contradicted = events()[3].clone();
        if let Event::ToolResult { outcome, .. } = &mut contradicted.event {
            *outcome = Outcome::Succeeded;
        }
        assert!(
            !contradicted.valid(),
            "unknown operation cannot become an overall success"
        );
    }
}

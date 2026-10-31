//! Relay of one explicit voice-text review between a host and Eva. The
//! coordinator holds no voice text: an offer is verified against the reply
//! digest already recorded for that turn and becomes an ordinary exact-change
//! memory proposal, which still needs the host's explicit approval.
use companion_protocol::{identifier, ContextRef, MemoryChange, MemoryScope};
use companion_voice::text::Offer;
use sha2::{Digest, Sha256};
use std::time::{Duration, Instant};

/// Eva answers from memory; a slow answer means the request is dropped.
pub const DEADLINE: Duration = Duration::from_secs(5);
const MAX_VALUE_BYTES: usize = 8192;

pub enum Kind {
    Review {
        scope: MemoryScope,
        voice_session_id: String,
        turn_id: String,
        digests: Vec<String>,
    },
    Forget,
}

/// The single in-flight relay. A second request waits for this one.
pub struct Pending {
    pub id: u64,
    pub host: u64,
    pub host_request: u64,
    pub context: ContextRef,
    pub eva: u64,
    pub kind: Kind,
    pub deadline: Instant,
}

/// Same digest Eva records for `ReplyGenerated`: SHA-256 of the JSON string.
pub fn reply_digest(reply: &str) -> String {
    let bytes = serde_json::to_vec(&serde_json::Value::String(reply.into()))
        .expect("a string is serializable");
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// Builds the proposal only for the exact turn that was requested and only
/// if the reply text matches a recorded digest of that turn.
pub fn proposal(
    offer: &Offer,
    scope: MemoryScope,
    voice_session_id: &str,
    turn_id: &str,
    digests: &[String],
) -> Result<MemoryChange, &'static str> {
    if !offer.valid() {
        return Err("voice_text_invalid_offer");
    }
    if offer.voice_session_id != voice_session_id || offer.turn_id != turn_id {
        return Err("voice_text_wrong_turn");
    }
    let digest = reply_digest(&offer.reply);
    if !digests.contains(&digest) {
        return Err("voice_text_digest_mismatch");
    }
    let source = format!("voice:{voice_session_id}:{turn_id}");
    if !identifier(&source) {
        return Err("voice_text_source_too_long");
    }
    let user = match &offer.caption {
        Some(caption) => {
            format!("You said (provider transcription, at most 160 characters): {caption}")
        }
        None => "Your request was not transcribed; only Eva's reply is saved.".into(),
    };
    let value = format!(
        "Eva spoken reply · voice activation {voice_session_id} · turn {turn_id}\n\
         Text matches the reply digest recorded for that turn.\n{user}\nEva: {}",
        offer.reply
    );
    if value.len() > MAX_VALUE_BYTES {
        return Err("voice_text_too_large");
    }
    Ok(MemoryChange::Put {
        scope,
        key: format!("voice-reply-{}", &digest[..16]),
        value,
        source_event_id: source,
        expected_revision: None,
        expires_at: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn offer(reply: &str) -> Offer {
        Offer {
            request_id: 1,
            voice_session_id: "eva-1-2-3".into(),
            turn_id: "eva-2-1-4".into(),
            reply: reply.into(),
            caption: None,
        }
    }
    #[test]
    fn digest_matches_eva_canonical_json_string() {
        // jwm_eva_core::protocol::digest(&json!("好的")) for the same text.
        let expected: String = Sha256::digest("\"好的\"".as_bytes())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(reply_digest("好的"), expected);
        assert_ne!(reply_digest("a\"b"), reply_digest("a'b"));
    }
    #[test]
    fn only_the_recorded_reply_of_the_requested_turn_becomes_a_proposal() {
        let digests = vec![reply_digest("Done. The window moved.")];
        let change = proposal(
            &offer("Done. The window moved."),
            MemoryScope::Global,
            "eva-1-2-3",
            "eva-2-1-4",
            &digests,
        )
        .unwrap();
        let MemoryChange::Put {
            key,
            value,
            source_event_id,
            expected_revision,
            ..
        } = change
        else {
            panic!("put")
        };
        assert!(key.starts_with("voice-reply-") && identifier(&key));
        assert_eq!(source_event_id, "voice:eva-1-2-3:eva-2-1-4");
        assert!(value.contains("Eva: Done. The window moved."));
        assert!(value.contains("not transcribed"));
        assert_eq!(expected_revision, None, "never overwrites an entry");
        for (offered, session, turn, reason) in [
            (
                "A different text",
                "eva-1-2-3",
                "eva-2-1-4",
                "voice_text_digest_mismatch",
            ),
            (
                "Done. The window moved.",
                "eva-1-2-9",
                "eva-2-1-4",
                "voice_text_wrong_turn",
            ),
            (
                "Done. The window moved.",
                "eva-1-2-3",
                "eva-2-1-5",
                "voice_text_wrong_turn",
            ),
        ] {
            assert_eq!(
                proposal(
                    &offer(offered),
                    MemoryScope::Global,
                    session,
                    turn,
                    &digests
                )
                .err(),
                Some(reason)
            );
        }
    }
    #[test]
    fn caption_is_labelled_and_oversized_values_are_refused_not_truncated() {
        let mut spoken = offer("好");
        spoken.caption = Some("把窗口移到右边".into());
        let digests = vec![reply_digest("好")];
        let Ok(MemoryChange::Put { value, .. }) = proposal(
            &spoken,
            MemoryScope::Project("p".into()),
            "eva-1-2-3",
            "eva-2-1-4",
            &digests,
        ) else {
            panic!("put")
        };
        assert!(value.contains("provider transcription") && value.contains("把窗口移到右边"));
        let long = "长".repeat(4000);
        let digests = vec![reply_digest(&long)];
        assert_eq!(
            proposal(
                &offer(&long),
                MemoryScope::Global,
                "eva-1-2-3",
                "eva-2-1-4",
                &digests
            )
            .err(),
            Some("voice_text_too_large")
        );
    }
}

# Dialogue, memory and explicit context cards

The daemon now connects the local coordination protocol to the reviewed SQLite store and bounded Responses worker. GUI adapters own real text/review controls; no text is sent to a PTY. Protocol type declarations are authoritative.

## Context registration
A native GUI publishes `ContextObserved` from its actual pane/project/task/revision. An independent companion card can use `pane_id=companion-card` with no task/project. The host ID must match the bound connection. Dialogue and memory review operations require the exact current ContextRef, not merely the same host. Context change invalidates pending memory approvals and selected-text consent. Replies always carry original context. Late generation is labeled `generated_for_previous_context` and must remain in its original source card; it is never permission to attach content to the newly active pane/project.

## Explicit selection
`ContextAccessRequested` includes only user-selected text <=4096 bytes, source_event_id and Unix captured_at_ms (at most5min old). It is local review data, not a provider call. The daemon returns `ContextAccessReview` containing a random consent_id. UI shows the exact text/source/scope and only a deliberate approve action sends `ContextAccessGranted`. A subsequent DialogueStart may include that exact SelectionEvidence once, within60s, in the same current context. A guessed consent string, changed text, expired review or changed context is rejected. No filesystem, scrollback, clipboard, screenshot or raw-audio collector exists.

## Dialogue
DialogueStart carries explicit user text <=8192 bytes. With no valid enabled private `PROFILE/provider.json`, the reply is honestly labeled offline and contains a local fixed explanation; no model request is sent. Enabled config is loaded strictly, duplicate/unknown fields rejected, file owner/mode checked; invalid config also leaves provider unavailable. The provider adapter README lists the exact configuration. Credentials are read by the worker only for an explicit enabled request. No live paid/API smoke test was run.

One text request is in-flight at a time. Context and source peer are retained in the turn ledger; reconnect does not replay old turns. Cancel requests remain pending until the bounded worker exits. `generated` and `DialogueDisplayed` are separate; generation never implies task success or actual audio playback. Model gesture/intent proposals do not execute actions or override behavior. A memory proposal is shown as **pending review, not saved**, and cannot invoke memory approval.

## Dialogue history
History is a read-only page, never fetched until the user presses Load. A modern host asks for `HelloWithFeatures[withdrawal_resume_v1, dialogue_history_v1]` (only this ordered pair or the base feature alone is valid); the coordinator echoes exactly the requested set. A coordinator that predates history rejects the extended hello with `invalid_schema`; the host then reconnects with the base feature and shows "Update the Eva coordinator" instead of losing its body. Hosts that did not negotiate history never receive history replies.

`DialogueHistory{request_id>0, context, scope, before}` must carry the host's exact current ContextRef. Scopes: `context` (same host/pane/task/project), `task` (same task within the same project, any host that legitimately holds that task), `project` (same project, any host) and `voice` (voice turns only). Task/project scopes need that identity in the current context; a host cannot name another project. Pages are newest first, at most 8 entries and 48 KiB of entries, below one frame. `before` is an opaque SHA-256 cursor of the last entry; an unknown cursor returns `history_cursor_stale` rather than a guessed position. The host view keeps at most 32 entries.

Text is session-only. Entries from an earlier coordinator session show `earlier_session` and metadata only. Voice entries never carry transcripts; they show raw generated/confirmed-played sample counters (no sample rate or duration is inferred) and counts of recorded tool calls and latest operation receipts, where unsettled operations stay unknown and unsubmitted steps are not implied. A turn that used reviewed terminal text shows its dialogue text only to the exact original context; elsewhere it is `withheld_outside_origin`. Selection evidence and consent IDs are never part of a page.

While the desktop is locked or its state unknown (including a lost observer), requests return `desktop_locked_or_unknown`, and each negotiated host receives `DialogueHistoryWithdrawn` and clears its page. Context or scope changes, disconnect and malformed or out-of-scope pages also clear the view. History never restores audio, execution rights, consent or model context.

## Spoken reply review
Saving what Eva said is an explicit, reviewed memory write that starts in a terminal. Hosts negotiate `voice_text_v1` (ordered after `dialogue_history_v1`); Eva negotiates dialogue version 3. Older coordinators reject either; hosts then drop one feature level and Eva falls back to version 2, and nothing is retained.

The coordinator never holds voice text. It tells a version-3 Eva whether retention is allowed (`voice_text_retention`): only while memory is not paused and the desktop is unlocked and known. Eva keeps, in memory only, at most 4 generated replies for 10 minutes, plus the provider caption of the request when `input_transcription` is explicitly on. Pause, lock, unknown desktop, disconnect and an explicit forget drop everything.

`VoiceTextReview{request_id, context, scope}` needs the host's exact current context, an unlocked desktop, unpaused memory and a scope allowed for that context (Global must be chosen explicitly). The coordinator picks the newest turn of the connected Eva in this coordinator session that recorded a generated reply and asks Eva for exactly that turn. The offered reply must hash to a `ReplyGenerated` digest recorded for that turn; otherwise nothing is proposed. A verified offer becomes an ordinary `MemoryPropose` bound to the requesting host connection: key `voice-reply-<digest prefix>`, source `voice:<activation>:<turn>`, a value that labels the source and whether the request was transcribed, no overwrite, no truncation (over 8192 bytes is refused). It is saved only if the user approves the exact review. `VoiceTextForget` asks Eva to drop its retained text. One relay runs at a time; a missing answer times out after 5 seconds. `Reply::VoiceText{request_id, status}` reports each outcome and never claims a save.

## Memory UI
MemoryList pages exactly one entry, including expired entries for management. This bounds even worst-case JSON escaping under64KiB. Next cursor permits complete browsing; scope/key/value/source/revision/expiry remain visible. Management list/delete/clear works when paused; new puts and model retrieval do not. MemoryPropose produces an exact digest-bound review. MemoryApprove requires the originating connection, unchanged ContextRef, review ID and digest. Commit failure is reported and never called remembered. Delete/clear are also reviewed, not hidden irreversible buttons.

Task/project scope must match current ContextRef. Global management is an explicitly named global UI operation. Dialogue defaults to current-task retrieval only. `MemoryUse` explicitly opts additional current-project/global scopes in; it never authorizes another project/task. Retrieval metadata is preserved as untrusted evidence, bounded to4096 bytes; an oversized selected memory set asks for narrower scope instead of silently truncating values. Deletion clears local derived records but cannot retract content already transmitted to a provider. No automatic legacy-memory import is implemented.

## Voice preflight
Eva's optional bridge obtains VoiceAcquire before its primary Realtime startup. The exact source/session lease is fsynced before VoicePermit. An in-flight text worker denies acquisition; any persisted voice lease blocks new text starts. VoiceRelease after actual native cleanup clears it; absent lease release is idempotent, a different owner's lease cannot be cleared. IPC loss or daemon restart **does not expire the lease**. The current bridge does not automatically recover a lost cleanup message; manual trusted recovery integration remains required. Existing separately enabled idle/wake sessions are outside this new primary-turn preflight; do not claim retroactive control over them.

Audio observation remains separate: played sample counters are not fabricated playback milliseconds. No microphone or speaker owner is created here.

## Comfort
ProfileName changes only editable display/model identity text, never companion_id. Comfort quiet/night is persisted: quiet filters idle play, night selects night skin; explicit skin selection exits night appearance. Motion full/calm/static is shared. Per-owner real activity drives rest; task identity/revision distinguishes repeated completion facts. These are simulated character behavior, not inferences about the user's feelings or health.

## Archived tasks and sharing
Task namespaces are separately persisted in `task-authority.json` (4096 tasks, at most4 explicitly shared hosts each; bounded8MiB file). A different host cannot silently claim an existing task ID or change its recorded project. Active sharing requires `TaskSharePropose` by the registered owner, a visible exact task/target-host/incarnation review, then digest-bound `TaskShareApprove` while that target still exists. No model suggestion can approve it. A new window is not automatically the old window's task owner.

This does **not** orphan old memories: `TaskScopes` paginates metadata discovery; `MemoryScopeReviewRequested` / `MemoryScopeApprove` grants explicit management access to a selected archived task/project. That grant is connection/current-context bound and permits inspect/edit/delete/clear only. It never enables model retrieval or changes task ownership. Changing context/disconnecting clears it. This lets the user clean up an old task after its original GUI has gone, without automatic takeover.

Persisted memory `created_at` and `expires_at` are **Unix epoch milliseconds**. Residence cooldowns, presentation animation and review deadlines use monotonic time instead. Tests cover reopen and expiry progression in epoch milliseconds.

### Archived scope discovery
`MemoryScopes { after }` lists at most 16 persisted scope names and `next_after`
(canonical `global`, `project:<id>`, or `task:<id>` cursor). Unlike the task
registry's `TaskScopes`, this also finds project-only memories with no registered
task. Expired records remain discoverable for management while memory is paused.
Discovery returns no entry content and grants no management or model access:
foreign archived scopes still require exact current-context scope review/approval.
Locked or unknown observed desktop state blocks discovery.

Task project bindings are not silently reassigned: the registered owner can bind
an initially unassigned task once; changing an existing nonempty project requires
a fresh task context. Frontends may assign a named project to a taskless pane,
or use a fresh host-qualified task on explicit project change. Context revision
must increase, invalidating pending consent/reviews; old memories retain their
original scope and can be managed through the archived-scope review flow.

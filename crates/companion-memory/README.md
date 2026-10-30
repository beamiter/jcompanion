# Explicit scoped memory

This crate stores only reviewed structured entries. It does not inspect terminal
output, files, credentials, old application profiles or a network endpoint.

## Review contract

1. The daemon receives an explicit request or a model *proposal* and validates its
   originating connection, context revision and exact requested scope.
2. `Store::propose` returns a bounded in-memory review, with a SHA-256 digest of
   the exact change and generation. Nothing has been persisted yet.
3. The native UI displays that scope, value, target and digest. Only a real user
   approval action may call `approve`. It returns a private, single-use value.
4. `commit` checks the originating store, generation and record revision inside
   a SQLite transaction. Only a successful transaction means "remembered".

The API is a trust boundary between application components, not protection from
malicious code running inside the daemon or another malicious same-UID process.
Do not expose `approve` as a model-callable tool. Bind UI review IDs to the source
connection and original context; an ID/digest supplied by the model is not consent.

## Scope and management

`Global`, `Project(id)` and `Task(id)` are disjoint. Retrieval does not silently
union global or other-project entries. IDs are opaque validated identifiers,
not directories to open. `retrieve` is the model-read entry point and refuses
when paused; a separate current context grant is still required at the daemon.

Explicit management uses `get`, `list`, `search`, or `list_page`. Pausing memory
does not prevent the user from inspecting or deleting it. `list_page` supports
expired entries and a stable descending-ID cursor, so all entries remain
reachable. Search treats user input as literal text, never SQL/FTS syntax.
SQLite case folding here covers ASCII; other Unicode matches exactly.

Updates and deletes require a matching revision. All changes advance the store
generation and invalidate outstanding reviews. Deletion and edits clear local
derived rows. Clearing is reviewed and scoped; deleting global preferences does
not silently delete task/project entries. Existing application memories are not
automatically imported or modified.

## Storage and limits

The database requires an existing private non-symlink directory and private
regular file, uses foreign keys, secure-delete, DELETE journal and FULL
synchronization. SQLite busy waits are bounded to 250 ms. No extensions load.
Same-UID path races are not a strong sandbox guarantee.

Limits: 4,096 entries, 8,192 UTF-8 bytes per value, 32 pending reviews, 256-byte
literal search query and 100 entries per internal page. IPC must additionally
bound the **serialized** response size (JSON escaping may expand values), not
merely count entries, and return an accurate cursor when shortening a page.

An entry's confirmed consent status means it passed this review path, not that
the stored proposition is objectively true. Source event, revision and expiry
remain visible. There is no automatic cloud persistence, vector database or
claim of revoking data already sent to a provider. Raw original material is not
silently retained as a memory.

## Verification

Run `cargo test -p companion-memory` and
`cargo clippy -p companion-memory --all-targets -- -D warnings` from the workspace.
Tests cover scope isolation, proposals versus committed memory, exact digest
approval, stale/cross-store approval, record CAS, DB-write failure, expiry,
pause, literal keyword search, persistent reopening, concurrent-generation
conflicts, deletion of derived records and pagination of expired records.
These are database/API tests, not native UI or live model validation.

Dependency API: <https://docs.rs/rusqlite/0.41.1/rusqlite/>.

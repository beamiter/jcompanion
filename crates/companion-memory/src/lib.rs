//! Local explicitly reviewed memory. No file scanning, automatic import or network.
//! The host must call `approve` only from its real review UI, never model output.
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::HashMap, path::Path};

pub const MAX_VALUE_BYTES: usize = 8192;
pub const MAX_ENTRIES: i64 = 4096;
#[derive(Debug)]
pub enum Error {
    Database(rusqlite::Error),
    Io(std::io::Error),
    Invalid(&'static str),
    Conflict,
    StaleReview,
    Paused,
}
impl From<rusqlite::Error> for Error {
    fn from(e: rusqlite::Error) -> Self {
        Self::Database(e)
    }
}
impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}
pub type Result<T> = std::result::Result<T, Error>;
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(
    tag = "kind",
    content = "id",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum Scope {
    Global,
    Project(String),
    Task(String),
}
fn identifier(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 128
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-.:".contains(&b))
}
impl Scope {
    fn key(&self) -> Result<String> {
        match self {
            Self::Global => Ok("global".into()),
            Self::Project(id) if identifier(id) => Ok(format!("project:{id}")),
            Self::Task(id) if identifier(id) => Ok(format!("task:{id}")),
            _ => Err(Error::Invalid("scope")),
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub id: i64,
    pub scope: Scope,
    pub key: String,
    pub value: String,
    pub source_event_id: String,
    /// All persisted entries passed explicit user review; never an automatic model write.
    pub consent_status: String,
    pub revision: u64,
    pub created_at: u64,
    pub expires_at: Option<u64>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
pub enum Change {
    Put {
        scope: Scope,
        key: String,
        value: String,
        source_event_id: String,
        expected_revision: Option<u64>,
        expires_at: Option<u64>,
    },
    Delete {
        id: i64,
        expected_revision: u64,
    },
    Clear {
        scope: Scope,
    },
}
#[derive(Clone, Debug, Serialize)]
pub struct Review {
    pub id: u64,
    pub digest: String,
    pub change: Change,
    pub generation: u64,
}
/// Private, single-use approval bound to exact reviewed change and store generation.
pub struct Approved {
    review: Review,
    store_id: u64,
}
#[derive(Clone, Debug, Serialize)]
pub struct Page {
    pub entries: Vec<Entry>,
    pub next_cursor: Option<i64>,
}
pub struct Store {
    db: Connection,
    pending: HashMap<u64, Review>,
    next: u64,
    generation: u64,
    paused: bool,
    store_id: u64,
}
static STORE_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);
impl Store {
    pub fn open(path: &Path) -> Result<Self> {
        use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
        let parent = path
            .parent()
            .ok_or(Error::Invalid("private parent required"))?;
        let m = std::fs::symlink_metadata(parent)?;
        if !m.is_dir() || m.file_type().is_symlink() || m.mode() & 0o077 != 0 {
            return Err(Error::Invalid("private non-symlink parent required"));
        }
        // create_new avoids following a preexisting symlink. SQLite opens only checked regular files.
        match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(path)
        {
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(e) => return Err(e.into()),
        }
        let f = std::fs::symlink_metadata(path)?;
        if !f.is_file() || f.file_type().is_symlink() || f.mode() & 0o077 != 0 || f.uid() != m.uid()
        {
            return Err(Error::Invalid("private regular memory database required"));
        }
        Self::from_connection(Connection::open(path)?)
    }
    pub fn in_memory() -> Result<Self> {
        Self::from_connection(Connection::open_in_memory()?)
    }
    fn from_connection(db: Connection) -> Result<Self> {
        db.busy_timeout(std::time::Duration::from_millis(250))?;
        db.execute_batch("PRAGMA foreign_keys=ON; PRAGMA secure_delete=ON; PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;
   CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
   INSERT OR IGNORE INTO settings VALUES('schema',1),('generation',0),('paused',0);
   CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY,scope TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,source TEXT NOT NULL,revision INTEGER NOT NULL,created INTEGER NOT NULL,expires INTEGER,UNIQUE(scope,key));
   CREATE TABLE IF NOT EXISTS derived(entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,value TEXT NOT NULL);")?;
        let schema: i64 =
            db.query_row("SELECT value FROM settings WHERE key='schema'", [], |r| {
                r.get(0)
            })?;
        if schema != 1 {
            return Err(Error::Invalid("unsupported memory schema"));
        }
        let generation: i64 = db.query_row(
            "SELECT value FROM settings WHERE key='generation'",
            [],
            |r| r.get(0),
        )?;
        let paused: i64 =
            db.query_row("SELECT value FROM settings WHERE key='paused'", [], |r| {
                r.get(0)
            })?;
        if generation < 0 || !matches!(paused, 0 | 1) {
            return Err(Error::Invalid("corrupt memory settings"));
        }
        let store_id = loop {
            let old = STORE_ID.load(std::sync::atomic::Ordering::Relaxed);
            let new = old
                .checked_add(1)
                .ok_or(Error::Invalid("store id exhausted"))?;
            if STORE_ID
                .compare_exchange_weak(
                    old,
                    new,
                    std::sync::atomic::Ordering::Relaxed,
                    std::sync::atomic::Ordering::Relaxed,
                )
                .is_ok()
            {
                break old;
            }
        };
        Ok(Self {
            db,
            pending: HashMap::new(),
            next: 0,
            generation: generation as u64,
            paused: paused == 1,
            store_id,
        })
    }
    pub fn paused(&self) -> bool {
        self.paused
    }
    /// Explicit user setting; invalidates outstanding reviews and derived retrievals.
    pub fn set_paused(&mut self, paused: bool) -> Result<()> {
        let generation = self
            .generation
            .checked_add(1)
            .filter(|x| *x <= i64::MAX as u64)
            .ok_or(Error::Invalid("generation exhausted"))?;
        let tx = self.db.transaction()?;
        let actual: i64 = tx.query_row(
            "SELECT value FROM settings WHERE key='generation'",
            [],
            |r| r.get(0),
        )?;
        if actual as u64 != self.generation {
            return Err(Error::Conflict);
        }
        tx.execute(
            "UPDATE settings SET value=?1 WHERE key='paused'",
            [paused as i64],
        )?;
        tx.execute(
            "UPDATE settings SET value=?1 WHERE key='generation'",
            [generation as i64],
        )?;
        tx.commit()?;
        self.generation = generation;
        self.paused = paused;
        self.pending.clear();
        Ok(())
    }
    pub fn propose(&mut self, change: Change) -> Result<Review> {
        if self.paused && matches!(change, Change::Put { .. }) {
            return Err(Error::Paused);
        }
        if self.pending.len() >= 32 {
            return Err(Error::Invalid("pending review limit"));
        }
        match &change {
            Change::Put {
                scope,
                key,
                value,
                source_event_id,
                expected_revision,
                expires_at,
            } => {
                scope.key()?;
                if !identifier(key)
                    || !identifier(source_event_id)
                    || value.is_empty()
                    || value.len() > MAX_VALUE_BYTES
                    || value.contains('\0')
                    || expected_revision.is_some_and(|r| r == 0 || r >= i64::MAX as u64)
                    || expires_at.is_some_and(|t| t > i64::MAX as u64)
                {
                    return Err(Error::Invalid("memory entry"));
                }
            }
            Change::Delete {
                id,
                expected_revision,
            } if *id <= 0 || *expected_revision == 0 || *expected_revision >= i64::MAX as u64 => {
                return Err(Error::Invalid("memory target"))
            }
            Change::Clear { scope } => {
                scope.key()?;
            }
            _ => {}
        }
        self.next = self
            .next
            .checked_add(1)
            .ok_or(Error::Invalid("review id exhausted"))?;
        let bytes = serde_json::to_vec(&(self.next, self.generation, &change))
            .map_err(|_| Error::Invalid("review encoding"))?;
        let review = Review {
            id: self.next,
            digest: format!("{:x}", Sha256::digest(bytes)),
            change,
            generation: self.generation,
        };
        self.pending.insert(review.id, review.clone());
        Ok(review)
    }
    /// Caller must bind this UI action to the presented exact scope and digest.
    /// No model-facing endpoint is allowed to call this method automatically.
    pub fn approve(&mut self, id: u64, digest: &str) -> Result<Approved> {
        let r = self.pending.get(&id).ok_or(Error::StaleReview)?;
        if (self.paused && matches!(r.change, Change::Put { .. }))
            || r.digest != digest
            || r.generation != self.generation
        {
            return Err(Error::StaleReview);
        }
        Ok(Approved {
            review: self.pending.remove(&id).unwrap(),
            store_id: self.store_id,
        })
    }
    pub fn cancel(&mut self, id: u64) {
        self.pending.remove(&id);
    }
    pub fn commit(&mut self, approved: Approved, now: u64) -> Result<()> {
        if self.paused && matches!(approved.review.change, Change::Put { .. }) {
            return Err(Error::Paused);
        }
        if approved.store_id != self.store_id || approved.review.generation != self.generation {
            return Err(Error::StaleReview);
        }
        if now > i64::MAX as u64 {
            return Err(Error::Invalid("timestamp"));
        }
        let next = self
            .generation
            .checked_add(1)
            .filter(|x| *x <= i64::MAX as u64)
            .ok_or(Error::Invalid("generation exhausted"))?;
        let tx = self.db.transaction()?;
        let actual: i64 = tx.query_row(
            "SELECT value FROM settings WHERE key='generation'",
            [],
            |r| r.get(0),
        )?;
        if actual as u64 != self.generation {
            return Err(Error::Conflict);
        }
        match approved.review.change {
            Change::Put {
                scope,
                key,
                value,
                source_event_id,
                expected_revision,
                expires_at,
            } => {
                if expires_at.is_some_and(|t| t <= now) {
                    return Err(Error::Invalid("expired proposal"));
                }
                let scope = scope.key()?;
                let old: Option<(i64, i64)> = tx
                    .query_row(
                        "SELECT id,revision FROM entries WHERE scope=?1 AND key=?2",
                        params![scope, key],
                        |r| Ok((r.get(0)?, r.get(1)?)),
                    )
                    .optional()?;
                match (old, expected_revision) {
                    (None, None) => {
                        let count: i64 =
                            tx.query_row("SELECT COUNT(*) FROM entries", [], |r| r.get(0))?;
                        if count >= MAX_ENTRIES {
                            return Err(Error::Invalid("memory capacity"));
                        }
                        tx.execute("INSERT INTO entries(scope,key,value,source,revision,created,expires) VALUES(?1,?2,?3,?4,1,?5,?6)",params![scope,key,value,source_event_id,now as i64,expires_at.map(|t|t as i64)])?;
                    }
                    (Some((id, revision)), Some(expected)) if revision as u64 == expected => {
                        tx.execute("UPDATE entries SET value=?1,source=?2,revision=revision+1,expires=?3 WHERE id=?4",params![value,source_event_id,expires_at.map(|t|t as i64),id])?;
                        tx.execute("DELETE FROM derived WHERE entry_id=?1", [id])?;
                    }
                    _ => return Err(Error::Conflict),
                }
            }
            Change::Delete {
                id,
                expected_revision,
            } => {
                if tx.execute(
                    "DELETE FROM entries WHERE id=?1 AND revision=?2",
                    params![id, expected_revision as i64],
                )? != 1
                {
                    return Err(Error::Conflict);
                }
            }
            Change::Clear { scope } => {
                tx.execute("DELETE FROM entries WHERE scope=?1", [scope.key()?])?;
            }
        }
        tx.execute(
            "UPDATE settings SET value=?1 WHERE key='generation'",
            [next as i64],
        )?;
        tx.commit()?;
        self.generation = next;
        self.pending.clear();
        Ok(())
    }
    /// Explicit management reads remain available when automatic memory use is paused.
    pub fn list(&self, scope: &Scope, now: u64, limit: usize) -> Result<Vec<Entry>> {
        self.search(scope, "", now, limit)
    }
    pub fn search(&self, scope: &Scope, query: &str, now: u64, limit: usize) -> Result<Vec<Entry>> {
        Ok(self
            .list_page(scope, query, now, limit, None, false)?
            .entries)
    }
    /// Model retrieval must use this entry point, and separately hold current context consent.
    pub fn retrieve(
        &self,
        scope: &Scope,
        query: &str,
        now: u64,
        limit: usize,
    ) -> Result<Vec<Entry>> {
        if self.paused {
            return Err(Error::Paused);
        }
        self.search(scope, query, now, limit)
    }
    /// Exact scope, literal search, stable descending ID cursor. No hidden cross-project union.
    /// `include_expired` is only for explicit memory management, never model retrieval.
    pub fn list_page(
        &self,
        scope: &Scope,
        query: &str,
        now: u64,
        limit: usize,
        before_id: Option<i64>,
        include_expired: bool,
    ) -> Result<Page> {
        if query.len() > 256
            || query.contains('\0')
            || now > i64::MAX as u64
            || limit == 0
            || limit > 100
            || before_id.is_some_and(|id| id <= 0)
        {
            return Err(Error::Invalid("retrieval bounds"));
        }
        let key = scope.key()?;
        let mut stmt=self.db.prepare("SELECT id,scope,key,value,source,revision,created,expires FROM entries WHERE scope=?1 AND (?3=1 OR expires IS NULL OR expires>?2) AND (?4='' OR instr(lower(key),lower(?4))>0 OR instr(lower(value),lower(?4))>0) AND (?5 IS NULL OR id<?5) ORDER BY id DESC LIMIT ?6")?;
        let raw = stmt
            .query_map(
                params![
                    key,
                    now as i64,
                    include_expired as i64,
                    query,
                    before_id,
                    (limit + 1) as i64
                ],
                decode_row,
            )?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let mut entries = raw
            .into_iter()
            .map(validate_entry)
            .collect::<Result<Vec<_>>>()?;
        let next_cursor = if entries.len() > limit {
            entries.truncate(limit);
            entries.last().map(|e| e.id)
        } else {
            None
        };
        Ok(Page {
            entries,
            next_cursor,
        })
    }
    /// Management lookup includes expired entries so they can still be reviewed/deleted.
    pub fn get(&self, id: i64) -> Result<Option<Entry>> {
        if id <= 0 {
            return Err(Error::Invalid("memory id"));
        }
        self.db.query_row("SELECT id,scope,key,value,source,revision,created,expires FROM entries WHERE id=?1",[id],decode_row).optional()?.map(validate_entry).transpose()
    }
}
fn decode_row(r: &rusqlite::Row<'_>) -> rusqlite::Result<Entry> {
    let key: String = r.get(1)?;
    let scope = if key == "global" {
        Scope::Global
    } else if let Some(id) = key.strip_prefix("project:") {
        Scope::Project(id.into())
    } else if let Some(id) = key.strip_prefix("task:") {
        Scope::Task(id.into())
    } else {
        return Err(rusqlite::Error::InvalidQuery);
    };
    Ok(Entry {
        id: r.get(0)?,
        scope,
        key: r.get(2)?,
        value: r.get(3)?,
        source_event_id: r.get(4)?,
        consent_status: "confirmed".into(),
        revision: r.get::<_, i64>(5)? as u64,
        created_at: r.get::<_, i64>(6)? as u64,
        expires_at: r.get::<_, Option<i64>>(7)?.map(|v| v as u64),
    })
}
fn validate_entry(e: Entry) -> Result<Entry> {
    e.scope.key()?;
    if e.id <= 0
        || e.created_at > i64::MAX as u64
        || e.expires_at.is_some_and(|t| t > i64::MAX as u64)
        || e.revision == 0
        || e.revision > i64::MAX as u64
        || !identifier(&e.key)
        || !identifier(&e.source_event_id)
        || e.value.is_empty()
        || e.value.len() > MAX_VALUE_BYTES
        || e.value.contains('\0')
    {
        return Err(Error::Invalid("corrupt memory record"));
    }
    Ok(e)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn put(scope: Scope, value: &str) -> Change {
        Change::Put {
            scope,
            key: "preference".into(),
            value: value.into(),
            source_event_id: "explicit-user-1".into(),
            expected_revision: None,
            expires_at: None,
        }
    }
    fn save(s: &mut Store, c: Change) {
        let p = s.propose(c).unwrap();
        let a = s.approve(p.id, &p.digest).unwrap();
        s.commit(a, 10).unwrap();
    }
    #[test]
    fn proposals_are_not_memory() {
        let mut s = Store::in_memory().unwrap();
        let p = s.propose(put(Scope::Global, "quiet")).unwrap();
        assert!(s.list(&Scope::Global, 10, 10).unwrap().is_empty());
        assert!(s.approve(p.id, "different").is_err());
        let a = s.approve(p.id, &p.digest).unwrap();
        s.commit(a, 10).unwrap();
        assert_eq!(s.list(&Scope::Global, 10, 10).unwrap()[0].value, "quiet");
    }
    #[test]
    fn exact_scope_isolation() {
        let mut s = Store::in_memory().unwrap();
        save(&mut s, put(Scope::Project("a".into()), "A"));
        save(&mut s, put(Scope::Task("a".into()), "task"));
        save(&mut s, put(Scope::Global, "global"));
        assert_eq!(
            s.list(&Scope::Project("a".into()), 10, 10).unwrap().len(),
            1
        );
        assert!(s
            .list(&Scope::Project("b".into()), 10, 10)
            .unwrap()
            .is_empty());
    }
    #[test]
    fn stale_and_cross_store_approval_rejected() {
        let mut a = Store::in_memory().unwrap();
        let mut b = Store::in_memory().unwrap();
        let p = a.propose(put(Scope::Global, "x")).unwrap();
        let token = a.approve(p.id, &p.digest).unwrap();
        assert!(b.commit(token, 10).is_err());
        let p = a.propose(put(Scope::Global, "x")).unwrap();
        let token = a.approve(p.id, &p.digest).unwrap();
        a.set_paused(true).unwrap();
        a.set_paused(false).unwrap();
        assert!(a.commit(token, 10).is_err());
    }
    #[test]
    fn edits_require_matching_revision() {
        let mut s = Store::in_memory().unwrap();
        save(&mut s, put(Scope::Global, "first"));
        let p = s.propose(put(Scope::Global, "overwrite")).unwrap();
        let a = s.approve(p.id, &p.digest).unwrap();
        assert!(matches!(s.commit(a, 10), Err(Error::Conflict)));
        let mut c = put(Scope::Global, "second");
        if let Change::Put {
            expected_revision, ..
        } = &mut c
        {
            *expected_revision = Some(1)
        }
        save(&mut s, c);
        assert_eq!(s.list(&Scope::Global, 10, 10).unwrap()[0].revision, 2);
    }
    #[test]
    fn delete_clears_derived() {
        let mut s = Store::in_memory().unwrap();
        save(&mut s, put(Scope::Global, "x"));
        let e = s.list(&Scope::Global, 10, 10).unwrap().remove(0);
        s.db.execute("INSERT INTO derived VALUES(?1,'cached')", [e.id])
            .unwrap();
        save(
            &mut s,
            Change::Delete {
                id: e.id,
                expected_revision: e.revision,
            },
        );
        assert_eq!(
            s.db.query_row("SELECT COUNT(*) FROM derived", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            0
        );
    }
    #[test]
    fn expired_hidden_and_pause_retrieval() {
        let mut s = Store::in_memory().unwrap();
        let mut c = put(Scope::Global, "x");
        if let Change::Put { expires_at, .. } = &mut c {
            *expires_at = Some(11)
        }
        save(&mut s, c);
        assert!(s.list(&Scope::Global, 11, 10).unwrap().is_empty());
        s.set_paused(true).unwrap();
        assert!(matches!(
            s.retrieve(&Scope::Global, "", 10, 10),
            Err(Error::Paused)
        ));
        assert_eq!(s.list(&Scope::Global, 10, 10).unwrap().len(), 1);
    }
    #[test]
    fn db_failure_never_commits() {
        let mut s = Store::in_memory().unwrap();
        let p = s.propose(put(Scope::Global, "x")).unwrap();
        let a = s.approve(p.id, &p.digest).unwrap();
        s.db.execute_batch("PRAGMA query_only=ON").unwrap();
        assert!(s.commit(a, 10).is_err());
        s.db.execute_batch("PRAGMA query_only=OFF").unwrap();
        assert!(s.list(&Scope::Global, 10, 10).unwrap().is_empty());
    }

    #[test]
    fn literal_search_is_scoped_and_bounded() {
        let mut s = Store::in_memory().unwrap();
        save(
            &mut s,
            put(Scope::Project("a".into()), "Quiet work; 用户偏好"),
        );
        assert_eq!(
            s.search(&Scope::Project("a".into()), "quiet", 10, 10)
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            s.search(&Scope::Project("a".into()), "用户", 10, 10)
                .unwrap()
                .len(),
            1
        );
        assert!(s
            .search(&Scope::Global, "quiet", 10, 10)
            .unwrap()
            .is_empty());
        assert!(s
            .search(&Scope::Project("a".into()), "%", 10, 10)
            .unwrap()
            .is_empty());
        assert!(s.search(&Scope::Global, &"x".repeat(257), 10, 10).is_err());
    }
    #[test]
    fn persistent_reopen_and_cross_connection_conflicts() {
        use std::os::unix::fs::DirBuilderExt;
        let id = STORE_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let path =
            std::env::temp_dir().join(format!("eva-memory-test-{}-{id}", std::process::id()));
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&path)
            .unwrap();
        let file = path.join("memory.sqlite");
        let mut first = Store::open(&file).unwrap();
        let mut stale = Store::open(&file).unwrap();
        save(&mut first, put(Scope::Global, "durable"));
        assert!(matches!(stale.set_paused(true), Err(Error::Conflict)));
        drop(first);
        drop(stale);
        let mut next = Store::open(&file).unwrap();
        assert_eq!(
            next.list(&Scope::Global, 10, 10).unwrap()[0].value,
            "durable"
        );
        next.set_paused(true).unwrap();
        drop(next);
        assert!(Store::open(&file).unwrap().paused());
        std::fs::remove_dir_all(path).unwrap();
    }

    #[test]
    fn paging_includes_all_records_and_expired_management() {
        let mut s = Store::in_memory().unwrap();
        for i in 0..7 {
            let mut c = put(Scope::Global, "entry");
            if let Change::Put {
                key, expires_at, ..
            } = &mut c
            {
                *key = format!("item{i}");
                *expires_at = Some(11)
            }
            save(&mut s, c);
        }
        assert!(s.list(&Scope::Global, 12, 100).unwrap().is_empty());
        let mut ids = vec![];
        let mut cursor = None;
        loop {
            let page = s
                .list_page(&Scope::Global, "", 12, 2, cursor, true)
                .unwrap();
            ids.extend(page.entries.into_iter().map(|e| e.id));
            cursor = page.next_cursor;
            if cursor.is_none() {
                break;
            }
        }
        assert_eq!(ids.len(), 7);
        assert!(ids.windows(2).all(|w| w[0] > w[1]));
        s.set_paused(true).unwrap();
        let e = s.get(ids[0]).unwrap().unwrap();
        save(
            &mut s,
            Change::Delete {
                id: e.id,
                expected_revision: e.revision,
            },
        );
        assert!(s.get(e.id).unwrap().is_none());
        assert!(s.propose(put(Scope::Global, "new")).is_err());
    }
    #[test]
    fn protocol_style_opaque_ids_are_preserved() {
        let mut s = Store::in_memory().unwrap();
        let scope = Scope::Task("ember:session-1:block-2".into());
        save(&mut s, put(scope.clone(), "task fact"));
        assert_eq!(s.list(&scope, 10, 1).unwrap().len(), 1);
        assert!(s
            .list(&Scope::Project("ember:session-1:block-2".into()), 10, 1)
            .unwrap()
            .is_empty());
    }
}

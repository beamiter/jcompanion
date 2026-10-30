//! Explicit management requests only. Models cannot call this gateway.
use companion_memory as memory;
use companion_protocol::*;
use sha2::{Digest, Sha256};
use std::{collections::HashMap, path::Path};
pub struct Gateway {
    scope_reviews: HashMap<String, (u64, ContextRef, MemoryScope, String)>,
    grants: HashMap<u64, Vec<MemoryScope>>,
    store: Option<memory::Store>,
    reviews: HashMap<(u64, u64), ContextRef>,
}
fn convert<T: serde::Serialize, U: serde::de::DeserializeOwned>(v: &T) -> Result<U, String> {
    serde_json::to_vec(v)
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .ok_or_else(|| "memory_schema".into())
}
fn error(e: memory::Error) -> String {
    match e {
        memory::Error::Paused => "memory_paused",
        memory::Error::Conflict => "memory_conflict",
        memory::Error::StaleReview => "memory_stale_review",
        memory::Error::Invalid(_) => "memory_invalid_or_limit",
        _ => "memory_storage_failure",
    }
    .into()
}
fn allowed(scope: &MemoryScope, c: &ContextRef) -> bool {
    match scope {
        MemoryScope::Global => true,
        MemoryScope::Project(id) => c.project_id.as_ref() == Some(id),
        MemoryScope::Task(id) => c.task_id.as_ref() == Some(id),
    }
}
impl Gateway {
    pub fn open(path: &Path) -> Self {
        Self {
            scope_reviews: HashMap::new(),
            grants: HashMap::new(),
            store: memory::Store::open(path).ok(),
            reviews: HashMap::new(),
        }
    }
    pub fn invalidate(&mut self, peer: u64) {
        self.scope_reviews.retain(|_, r| r.0 != peer);
        self.grants.remove(&peer);
        let ids: Vec<_> = self
            .reviews
            .keys()
            .filter(|(p, _)| *p == peer)
            .copied()
            .collect();
        for key in ids {
            self.reviews.remove(&key);
            if let Some(s) = &mut self.store {
                s.cancel(key.1)
            }
        }
    }
    pub fn handle(
        &mut self,
        peer: u64,
        current: Option<&ContextRef>,
        request: &Request,
        now: u64,
    ) -> Result<Reply, String> {
        let granted = self.grants.get(&peer).cloned().unwrap_or_default();
        let s = self.store.as_mut().ok_or("memory_unavailable")?;
        let validate = |c: &ContextRef| {
            if current == Some(c) {
                Ok(())
            } else {
                Err("memory_stale_context".to_owned())
            }
        };
        match request {
            Request::MemoryScopes { after } => {
                let (scopes, next_after) = s.list_scopes(after.as_deref(), 16).map_err(error)?;
                Ok(Reply::MemoryScopes {
                    scopes: convert(&scopes)?,
                    next_after,
                })
            }
            Request::MemoryScopeReviewRequested { context, scope } => {
                validate(context)?;
                if self.scope_reviews.len() >= 32 {
                    return Err("scope_review_limit".into());
                }
                let review_id = crate::storage::random_id().map_err(|_| "random_unavailable")?;
                let digest = format!(
                    "{:x}",
                    Sha256::digest(
                        serde_json::to_vec(&(context, scope, "management_only"))
                            .map_err(|_| "scope_schema")?
                    )
                );
                self.scope_reviews.insert(
                    review_id.clone(),
                    (peer, context.clone(), scope.clone(), digest.clone()),
                );
                Ok(Reply::MemoryScopeReview {
                    context: context.clone(),
                    scope: scope.clone(),
                    review_id,
                    digest,
                })
            }
            Request::MemoryScopeApprove {
                context,
                review_id,
                digest,
            } => {
                validate(context)?;
                let (owner, original, scope, hash) = self
                    .scope_reviews
                    .get(review_id)
                    .ok_or("scope_review_missing")?;
                if *owner != peer || original != context || hash != digest {
                    return Err("scope_review_not_owned_or_stale".into());
                }
                let scope = scope.clone();
                let grants = self.grants.entry(peer).or_default();
                if !grants.contains(&scope) {
                    if grants.len() >= 16 {
                        return Err("management_scope_limit".into());
                    }
                    grants.push(scope);
                }
                self.scope_reviews.remove(review_id);
                Ok(Reply::MemoryResult {
                    review_id: None,
                    status: "management_scope_granted_not_model_access".into(),
                })
            }
            Request::MemoryList {
                context,
                scope,
                query,
                before_id,
            } => {
                validate(context)?;
                if !allowed(scope, context) && !granted.contains(scope) {
                    return Err("memory_scope_denied".into());
                }
                let scope_db = convert(scope)?;
                let page = s
                    .list_page(&scope_db, query, now, 1, *before_id, true)
                    .map_err(error)?;
                let entries = page
                    .entries
                    .iter()
                    .map(convert)
                    .collect::<Result<Vec<MemoryEntry>, _>>()?;
                Ok(Reply::MemoryList {
                    context: context.clone(),
                    scope: scope.clone(),
                    entries,
                    next_before_id: page.next_cursor,
                    paused: s.paused(),
                })
            }
            Request::MemoryPropose { context, change } => {
                validate(context)?;
                let scope = match change {
                    MemoryChange::Put { scope, .. } | MemoryChange::Clear { scope } => {
                        scope.clone()
                    }
                    MemoryChange::Delete { id, .. } => convert(
                        &s.get(*id)
                            .map_err(error)?
                            .ok_or("memory_entry_missing")?
                            .scope,
                    )?,
                };
                if !allowed(&scope, context) && !granted.contains(&scope) {
                    return Err("memory_scope_denied".into());
                }
                let review = s.propose(convert(change)?).map_err(error)?;
                self.reviews.insert((peer, review.id), context.clone());
                Ok(Reply::MemoryReview {
                    context: context.clone(),
                    review: convert(&review)?,
                })
            }
            Request::MemoryApprove {
                context,
                review_id,
                digest,
            } => {
                validate(context)?;
                if self.reviews.get(&(peer, *review_id)) != Some(context) {
                    return Err("memory_review_not_owned".into());
                }
                let approved = s.approve(*review_id, digest).map_err(error)?;
                self.reviews.remove(&(peer, *review_id));
                s.commit(approved, now).map_err(error)?;
                self.reviews.clear();
                Ok(Reply::MemoryResult {
                    review_id: Some(*review_id),
                    status: "committed".into(),
                })
            }
            Request::MemoryCancel { review_id } => {
                if self.reviews.remove(&(peer, *review_id)).is_none() {
                    return Err("memory_review_not_owned".into());
                }
                s.cancel(*review_id);
                Ok(Reply::MemoryResult {
                    review_id: Some(*review_id),
                    status: "cancelled".into(),
                })
            }
            Request::MemoryPause { paused } => {
                s.set_paused(*paused).map_err(error)?;
                self.reviews.clear();
                Ok(Reply::MemoryResult {
                    review_id: None,
                    status: if *paused { "paused" } else { "resumed" }.into(),
                })
            }
            _ => Err("not_memory_management".into()),
        }
    }
    pub fn retrieve(
        &self,
        context: &ContextRef,
        scopes: &[MemoryScope],
        now: u64,
    ) -> Result<Vec<String>, String> {
        if scopes.is_empty() {
            return Ok(vec![]);
        }
        let s = self.store.as_ref().ok_or("memory_unavailable")?;
        let mut out = vec![];
        let mut bytes = 0;
        for scope in scopes {
            if !allowed(scope, context) {
                return Err("memory_scope_denied".into());
            }
            for entry in s.retrieve(&convert(scope)?, "", now, 4).map_err(error)? {
                let text = serde_json::to_string(&entry).map_err(|_| "memory_schema")?;
                bytes += text.len();
                if bytes > 4096 {
                    return Err("memory_context_budget_narrow_scope".into());
                }
                out.push(text)
            }
        }
        Ok(out)
    }
    pub fn voice_global(&self, now: u64) -> Result<Vec<MemoryEntry>, String> {
        let s = self.store.as_ref().ok_or("memory_unavailable")?;
        let entries = s
            .retrieve(&memory::Scope::Global, "", now, 4)
            .map_err(error)?;
        let entries = entries
            .iter()
            .map(convert)
            .collect::<Result<Vec<MemoryEntry>, _>>()?;
        if serde_json::to_vec(&entries)
            .map_err(|_| "memory_schema")?
            .len()
            > 4096
        {
            return Err("memory_context_budget".into());
        }
        Ok(entries)
    }
    pub fn scopes_allowed(context: &ContextRef, scopes: &[MemoryScope]) -> bool {
        scopes.iter().all(|s| allowed(s, context))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn c() -> ContextRef {
        ContextRef {
            host_id: "h".into(),
            pane_id: "p".into(),
            task_id: Some("task".into()),
            project_id: Some("project".into()),
            revision: 1,
        }
    }
    #[test]
    fn review_is_connection_and_context_bound() {
        let mut g = Gateway {
            scope_reviews: HashMap::new(),
            grants: HashMap::new(),
            store: Some(memory::Store::in_memory().unwrap()),
            reviews: HashMap::new(),
        };
        let ctx = c();
        let request = Request::MemoryPropose {
            context: ctx.clone(),
            change: MemoryChange::Put {
                scope: MemoryScope::Task("task".into()),
                key: "key".into(),
                value: "value".into(),
                source_event_id: "event".into(),
                expected_revision: None,
                expires_at: None,
            },
        };
        let Reply::MemoryReview { review, .. } = g.handle(1, Some(&ctx), &request, 1).unwrap()
        else {
            panic!()
        };
        let approve = Request::MemoryApprove {
            context: ctx.clone(),
            review_id: review.id,
            digest: review.digest,
        };
        assert!(g.handle(2, Some(&ctx), &approve, 2).is_err());
        assert!(g.handle(1, Some(&ctx), &approve, 2).is_ok());
        assert!(g.handle(1, Some(&ctx), &approve, 2).is_err());
        assert!(g
            .retrieve(&ctx, &[MemoryScope::Project("other".into())], 2)
            .is_err());
    }
}
#[cfg(test)]
mod archived_scope_tests {
    use super::*;
    fn ctx() -> ContextRef {
        ContextRef {
            host_id: "new-host".into(),
            pane_id: "companion-card".into(),
            task_id: None,
            project_id: None,
            revision: 1,
        }
    }
    #[test]
    fn archived_management_grant_never_becomes_model_scope() {
        let mut g = Gateway {
            store: Some(memory::Store::in_memory().unwrap()),
            reviews: HashMap::new(),
            scope_reviews: HashMap::new(),
            grants: HashMap::new(),
        };
        let c = ctx();
        let scope = MemoryScope::Task("old-task".into());
        let req = Request::MemoryList {
            context: c.clone(),
            scope: scope.clone(),
            query: String::new(),
            before_id: None,
        };
        assert!(g.handle(1, Some(&c), &req, 1800000000000).is_err());
        let Reply::MemoryScopeReview {
            review_id, digest, ..
        } = g
            .handle(
                1,
                Some(&c),
                &Request::MemoryScopeReviewRequested {
                    context: c.clone(),
                    scope: scope.clone(),
                },
                1800000000000,
            )
            .unwrap()
        else {
            panic!()
        };
        g.handle(
            1,
            Some(&c),
            &Request::MemoryScopeApprove {
                context: c.clone(),
                review_id,
                digest,
            },
            1800000000000,
        )
        .unwrap();
        assert!(g.handle(1, Some(&c), &req, 1800000000000).is_ok());
        assert!(g.retrieve(&c, &[scope], 1800000000000).is_err());
        g.invalidate(1);
        assert!(g.handle(1, Some(&c), &req, 1800000000000).is_err());
    }
    #[test]
    fn pure_project_discovery_does_not_grant_content_or_model_access() {
        let mut g = Gateway {
            store: Some(memory::Store::in_memory().unwrap()),
            reviews: HashMap::new(),
            scope_reviews: HashMap::new(),
            grants: HashMap::new(),
        };
        let mut owner = ctx();
        owner.project_id = Some("archived-project".into());
        let scope = MemoryScope::Project("archived-project".into());
        let Reply::MemoryReview { review, .. } = g
            .handle(
                1,
                Some(&owner),
                &Request::MemoryPropose {
                    context: owner.clone(),
                    change: MemoryChange::Put {
                        scope: scope.clone(),
                        key: "preference".into(),
                        value: "quiet".into(),
                        source_event_id: "explicit-user".into(),
                        expected_revision: None,
                        expires_at: Some(1800000001000),
                    },
                },
                1800000000000,
            )
            .unwrap()
        else {
            panic!()
        };
        g.handle(
            1,
            Some(&owner),
            &Request::MemoryApprove {
                context: owner.clone(),
                review_id: review.id,
                digest: review.digest,
            },
            1800000000000,
        )
        .unwrap();
        g.invalidate(1); // Original owner/context has gone away.
        g.store.as_mut().unwrap().set_paused(true).unwrap();
        let c = ctx();
        let Reply::MemoryScopes { scopes, next_after } = g
            .handle(
                2,
                Some(&c),
                &Request::MemoryScopes { after: None },
                1800000002000,
            )
            .unwrap()
        else {
            panic!()
        };
        assert_eq!(scopes, vec![scope.clone()]);
        assert!(next_after.is_none());
        assert!(g
            .handle(
                2,
                Some(&c),
                &Request::MemoryList {
                    context: c.clone(),
                    scope: scope.clone(),
                    query: String::new(),
                    before_id: None,
                },
                1800000002000
            )
            .is_err());
        assert!(g.retrieve(&c, &[scope], 1800000002000).is_err());
    }
    #[test]
    fn persisted_expiry_uses_epoch_milliseconds() {
        use std::os::unix::fs::PermissionsExt;
        let dir = std::env::temp_dir().join(crate::storage::random_id().unwrap());
        std::fs::create_dir(&dir).unwrap();
        std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700)).unwrap();
        let path = dir.join("memory.sqlite");
        let mut g = Gateway::open(&path);
        let c = ctx();
        let now = 1800000000000;
        let Reply::MemoryReview { review, .. } = g
            .handle(
                1,
                Some(&c),
                &Request::MemoryPropose {
                    context: c.clone(),
                    change: MemoryChange::Put {
                        scope: MemoryScope::Global,
                        key: "preference".into(),
                        value: "quiet".into(),
                        source_event_id: "explicit-user".into(),
                        expected_revision: None,
                        expires_at: Some(now + 1000),
                    },
                },
                now,
            )
            .unwrap()
        else {
            panic!()
        };
        g.handle(
            1,
            Some(&c),
            &Request::MemoryApprove {
                context: c.clone(),
                review_id: review.id,
                digest: review.digest,
            },
            now,
        )
        .unwrap();
        drop(g);
        let g = Gateway::open(&path);
        assert_eq!(g.voice_global(now + 500).unwrap().len(), 1);
        assert_eq!(g.voice_global(now + 1001).unwrap().len(), 0);
        std::fs::remove_dir_all(dir).unwrap();
    }
}

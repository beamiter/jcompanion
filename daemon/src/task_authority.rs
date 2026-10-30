//! Persistent task namespaces. Explicit peer-bound sharing never grants model/tool authority.
use companion_protocol::*;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::unix::fs::OpenOptionsExt,
    path::{Path, PathBuf},
};
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Owner {
    id: String,
    incarnation: u64,
}
impl From<&Host> for Owner {
    fn from(h: &Host) -> Self {
        Self {
            id: h.id.clone(),
            incarnation: h.incarnation,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Binding {
    owner: Owner,
    project: Option<String>,
    shared: Vec<Owner>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Registry {
    schema: u16,
    tasks: BTreeMap<String, Binding>,
}
struct Pending {
    peer: u64,
    context: Option<ContextRef>,
    task: String,
    target: Owner,
    digest: String,
}
pub struct Authority {
    path: PathBuf,
    registry: Option<Registry>,
    pending: HashMap<String, Pending>,
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
impl Authority {
    pub fn open(dir: &Path) -> Self {
        let path = dir.join("task-authority.json");
        let registry = (|| -> Result<Registry, ()> {
            match OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW)
                .open(&path)
            {
                Ok(f) => {
                    let mut b = vec![];
                    f.take(8 * 1024 * 1024 + 1)
                        .read_to_end(&mut b)
                        .map_err(|_| ())?;
                    if b.len() > 8 * 1024 * 1024 {
                        return Err(());
                    }
                    strict_json::parse(&b).map_err(|_| ())?;
                    let r: Registry = serde_json::from_slice(&b).map_err(|_| ())?;
                    if r.schema != 1
                        || r.tasks.len() > 4096
                        || r.tasks.iter().any(|(id, b)| {
                            !identifier(id)
                                || !identifier(&b.owner.id)
                                || b.owner.incarnation == 0
                                || b.project.as_ref().is_some_and(|p| !identifier(p))
                                || b.shared.len() > 4
                                || b.shared
                                    .iter()
                                    .any(|o| !identifier(&o.id) || o.incarnation == 0)
                        })
                    {
                        return Err(());
                    }
                    Ok(r)
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Registry {
                    schema: 1,
                    tasks: BTreeMap::new(),
                }),
                Err(_) => Err(()),
            }
        })()
        .ok();
        Self {
            path,
            registry,
            pending: HashMap::new(),
        }
    }
    fn persist(&mut self, next: Registry) -> Result<(), String> {
        let bytes = serde_json::to_vec(&next).map_err(|_| "task_registry_schema")?;
        if bytes.len() > 8 * 1024 * 1024 {
            return Err("task_registry_limit".into());
        }
        let temp = self.path.with_extension("next");
        let write = (|| -> std::io::Result<()> {
            let mut f = OpenOptions::new()
                .create(true)
                .truncate(true)
                .write(true)
                .mode(0o600)
                .custom_flags(libc::O_NOFOLLOW)
                .open(&temp)?;
            f.write_all(&bytes)?;
            f.sync_all()?;
            fs::rename(temp, &self.path)?;
            File::open(self.path.parent().unwrap())?.sync_all()
        })();
        if write.is_err() {
            self.registry = None;
            return Err("task_registry_storage_failure".into());
        }
        self.registry = Some(next);
        Ok(())
    }
    pub fn bind(&mut self, host: &Host, task: &str, project: Option<&str>) -> Result<(), String> {
        if !identifier(task) || project.is_some_and(|p| !identifier(p)) {
            return Err("task_registry_identifier".into());
        }
        let current = self.registry.as_ref().ok_or("task_registry_unavailable")?;
        let owner = Owner::from(host);
        let mut next = current.clone();
        if let Some(b) = next.tasks.get_mut(task) {
            if b.owner != owner && !b.shared.contains(&owner) {
                return Err("task_scope_owned_by_other_host_review_required".into());
            }
            if project.is_some() && b.project.is_some() && project != b.project.as_deref() {
                return Err("task_project_collision".into());
            }
            if b.owner == owner && b.project.is_none() && project.is_some() {
                b.project = project.map(str::to_owned);
                b.shared.clear();
                self.persist(next)?;
            }
            return Ok(());
        }
        if next.tasks.len() >= 4096 {
            return Err("task_registry_limit".into());
        }
        next.tasks.insert(
            task.into(),
            Binding {
                owner,
                project: project.map(str::to_owned),
                shared: vec![],
            },
        );
        self.persist(next)
    }
    pub fn scopes(&self, after: Option<&str>) -> Result<Reply, String> {
        let r = self.registry.as_ref().ok_or("task_registry_unavailable")?;
        let mut iter = r
            .tasks
            .iter()
            .filter(|(id, _)| after.is_none_or(|a| id.as_str() > a));
        let scopes = iter
            .by_ref()
            .take(16)
            .map(|(id, b)| TaskScopeInfo {
                task_id: id.clone(),
                project_id: b.project.clone(),
                owner_host_id: b.owner.id.clone(),
            })
            .collect::<Vec<_>>();
        let next_after = if iter.next().is_some() {
            scopes.last().map(|s| s.task_id.clone())
        } else {
            None
        };
        Ok(Reply::TaskScopes { scopes, next_after })
    }
    pub fn invalidate(&mut self, peer: u64) {
        self.pending.retain(|_, p| p.peer != peer);
    }
    pub fn propose(
        &mut self,
        peer: u64,
        context: Option<&ContextRef>,
        owner: &Host,
        task: String,
        target: &Host,
    ) -> Result<Reply, String> {
        let r = self.registry.as_ref().ok_or("task_registry_unavailable")?;
        let b = r.tasks.get(&task).ok_or("task_not_registered")?;
        if b.owner != Owner::from(owner) {
            return Err("task_share_owner_required".into());
        }
        if self.pending.len() >= 32 {
            return Err("task_review_limit".into());
        }
        let id = crate::storage::random_id().map_err(|_| "random_unavailable")?;
        let target = Owner::from(target);
        let hash = digest(
            &serde_json::to_vec(&(&task, &b.project, &b.owner, &target, &context))
                .map_err(|_| "task_review_schema")?,
        );
        let reply = Reply::TaskShareReview {
            review_id: id.clone(),
            digest: hash.clone(),
            task_id: task.clone(),
            project_id: b.project.clone(),
            owner_host_id: b.owner.id.clone(),
            target_host_id: target.id.clone(),
            target_incarnation: target.incarnation,
        };
        self.pending.insert(
            id,
            Pending {
                peer,
                context: context.cloned(),
                task,
                target,
                digest: hash,
            },
        );
        Ok(reply)
    }
    pub fn approve(
        &mut self,
        peer: u64,
        context: Option<&ContextRef>,
        id: &str,
        hash: &str,
        live: &[(String, u64)],
    ) -> Result<Reply, String> {
        let p = self.pending.get(id).ok_or("task_review_missing")?;
        if p.peer != peer
            || p.context.as_ref() != context
            || p.digest != hash
            || !live.contains(&(p.target.id.clone(), p.target.incarnation))
        {
            return Err("task_review_stale_or_not_owned".into());
        }
        let p = self.pending.remove(id).unwrap();
        let mut next = self
            .registry
            .as_ref()
            .ok_or("task_registry_unavailable")?
            .clone();
        let b = next.tasks.get_mut(&p.task).ok_or("task_not_registered")?;
        if !b.shared.contains(&p.target) {
            if b.shared.len() >= 4 {
                return Err("task_share_limit".into());
            }
            b.shared.push(p.target);
        }
        self.persist(next)?;
        Ok(Reply::OperationResult {
            operation: "task_share".into(),
            status: "committed".into(),
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn host(id: &str) -> Host {
        Host {
            id: id.into(),
            incarnation: 1,
            surface_id: "s".into(),
            retirement: RetirementCapability::NativePresented,
        }
    }
    #[test]
    fn collision_rejected_until_explicit_shared_review_and_persists() {
        let dir = std::env::temp_dir().join(crate::storage::random_id().unwrap());
        fs::create_dir(&dir).unwrap();
        let mut a = Authority::open(&dir);
        a.bind(&host("a"), "task", Some("project")).unwrap();
        assert!(a.bind(&host("b"), "task", Some("project")).is_err());
        let Reply::TaskShareReview {
            review_id, digest, ..
        } = a
            .propose(1, None, &host("a"), "task".into(), &host("b"))
            .unwrap()
        else {
            panic!()
        };
        assert!(a
            .approve(2, None, &review_id, &digest, &[("b".into(), 1)])
            .is_err());
        a.approve(1, None, &review_id, &digest, &[("b".into(), 1)])
            .unwrap();
        let mut a = Authority::open(&dir);
        a.bind(&host("b"), "task", Some("project")).unwrap();
        assert!(a.bind(&host("b"), "task", Some("other")).is_err());
        fs::remove_dir_all(dir).unwrap();
    }
}

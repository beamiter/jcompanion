use companion_core::State;
use std::{
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    os::unix::{
        fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
        io::AsRawFd,
    },
    path::{Path, PathBuf},
};
pub struct Store {
    dir: PathBuf,
    _lock: File,
}
fn bad(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, s)
}
pub fn random_id() -> io::Result<String> {
    let mut b = [0; 16];
    File::open("/dev/urandom")?.read_exact(&mut b)?;
    Ok(b.iter().map(|v| format!("{v:02x}")).collect())
}
impl Store {
    pub fn open(dir: &Path) -> io::Result<Self> {
        if !dir.exists() {
            fs::create_dir(dir)?;
            fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
        }
        let m = fs::symlink_metadata(dir)?;
        if !m.is_dir()
            || m.file_type().is_symlink()
            || m.uid() != unsafe { libc::geteuid() }
            || m.mode() & 0o077 != 0
        {
            return Err(bad("profile directory must be owned, non-symlink, 0700"));
        }
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(dir.join("profile.lock"))?;
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self {
            dir: dir.to_owned(),
            _lock: lock,
        })
    }
    pub fn load(&self) -> io::Result<Option<State>> {
        let p = self.dir.join("residence.json");
        match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(p)
        {
            Ok(f) => {
                let mut b = vec![];
                f.take(65537).read_to_end(&mut b)?;
                if b.len() > 65536 {
                    return Err(bad("state_limit"));
                }
                let s: State = serde_json::from_slice(&b)
                    .map_err(|_| bad("corrupt residence journal; recovery required, NOT reset"))?;
                s.validate().map_err(|e| bad(&e))?;
                Ok(Some(s))
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(e),
        }
    }
    pub fn commit(&self, state: &State) -> io::Result<()> {
        state.validate().map_err(|e| bad(&e))?;
        let p = self.dir.join("residence.next");
        let mut f = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&p)?;
        let b = serde_json::to_vec(state).map_err(|_| bad("encode state"))?;
        f.write_all(&b)?;
        f.sync_all()?;
        fs::rename(p, self.dir.join("residence.json"))?;
        File::open(&self.dir)?.sync_all()
    }
}
/// Separate socket namespace lock prevents two profiles racing stale-socket cleanup.
pub fn lock_socket(path: &Path) -> io::Result<File> {
    let f = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path.with_extension("lock"))?;
    if unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(f)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn dir() -> PathBuf {
        let p = std::env::temp_dir().join(format!("eva-store-{}", random_id().unwrap()));
        fs::create_dir(&p).unwrap();
        fs::set_permissions(&p, fs::Permissions::from_mode(0o700)).unwrap();
        p
    }
    #[test]
    fn durable_identity_and_exclusive_profile() {
        let p = dir();
        {
            let store = Store::open(&p).unwrap();
            assert!(Store::open(&p).is_err());
            let s = State::new("eva".into(), "boot".into(), "session".into());
            store.commit(&s).unwrap();
            assert_eq!(store.load().unwrap().unwrap().companion_id, "eva");
        }
        assert!(Store::open(&p).is_ok());
        fs::remove_dir_all(p).unwrap();
    }
    #[test]
    fn corrupt_journal_never_resets() {
        let p = dir();
        let store = Store::open(&p).unwrap();
        fs::write(p.join("residence.json"), b"{}").unwrap();
        assert!(store.load().is_err());
        fs::remove_dir_all(p).unwrap();
    }
    #[test]
    fn storage_failure_and_invariant_rejection() {
        let p = dir();
        let store = Store::open(&p).unwrap();
        let mut s = State::new("eva".into(), "boot".into(), "session".into());
        s.revoke_intent = true;
        assert!(store.commit(&s).is_err());
        s.revoke_intent = false;
        fs::create_dir(p.join("residence.next")).unwrap();
        assert!(store.commit(&s).is_err());
        assert!(!p.join("residence.json").exists());
        fs::remove_dir_all(p).unwrap();
    }
}

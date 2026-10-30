//! Daemon-only network worker. curl is executed directly (never a shell); keys
//! travel through stdin, not arguments, frontend payloads, Debug, or logs.
//! No transport is invoked except by a successful explicit start().
use crate::dialogue::{Ledger, Route};
use companion_openai::{self as adapter, Config, ContextRef, Error, Suggestion, UserTurn};
use std::{
    collections::BTreeSet,
    io::{Read, Write},
    os::unix::io::AsRawFd,
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc,
    },
    thread,
    time::{Duration, Instant},
};
pub trait Transport: Send + Sync + 'static {
    fn send(
        &self,
        config: &Config,
        body: &[u8],
        cancel: &AtomicBool,
    ) -> Result<(u16, Vec<u8>), Error>;
}
/// Contains no credentials. Only this implementation reads the daemon credential.
pub struct CurlTransport;
fn quote(s: &str) -> String {
    format!(
        "\"{}\"",
        s.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('\n', "\\n")
            .replace('\r', "\\r")
    )
}
impl Transport for CurlTransport {
    fn send(
        &self,
        config: &Config,
        body: &[u8],
        cancel: &AtomicBool,
    ) -> Result<(u16, Vec<u8>), Error> {
        config.validate()?;
        if cancel.load(Ordering::Acquire) {
            return Err(Error::Cancelled);
        }
        // Reuse Eva's existing environment credential strategy. An optional
        // daemon-only override does not alter Eva's configured model or voice.
        let key = std::env::var("EVA_COMPANION_OPENAI_API_KEY")
            .or_else(|_| std::env::var("OPENAI_API_KEY"))
            .map_err(|_| Error::InvalidConfig)?;
        if key.is_empty() || key.len() > 4096 || !key.bytes().all(|b| b.is_ascii_graphic()) {
            return Err(Error::InvalidConfig);
        }
        let config_stdin=format!("url = {}\nrequest = \"POST\"\nheader = {}\nheader = \"Content-Type: application/json\"\ndata-binary = {}\n",quote(&config.endpoint),quote(&format!("Authorization: Bearer {key}")),quote(std::str::from_utf8(body).map_err(|_|Error::Malformed)?));
        // -q must be first: never read ambient curlrc. No redirects or custom URL. Trusted proxy/TLS policy is preserved.
        let mut child = Command::new("/usr/bin/curl")
            .args([
                "-q",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--max-redirs",
                "0",
                "--connect-timeout",
                "10",
                "--max-time",
                &format!("{:.3}", config.timeout_ms as f64 / 1000.0),
                "--write-out",
                "\n%{http_code}",
                "--config",
                "-",
            ])
            .env_remove("EVA_COMPANION_OPENAI_API_KEY")
            .env_remove("OPENAI_API_KEY")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| Error::Transport)?;
        let start = Instant::now();
        let mut input = child.stdin.take().ok_or(Error::Transport)?;
        // Both credential upload and download are nonblocking and cancellation-bound.
        let fd = input.as_raw_fd();
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
        if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
            let _ = child.kill();
            let _ = child.wait();
            return Err(Error::Transport);
        }
        let mut sent = 0;
        while sent < config_stdin.len() {
            let failure = if cancel.load(Ordering::Acquire) {
                Some(Error::Cancelled)
            } else if start.elapsed() >= Duration::from_millis(config.timeout_ms) {
                Some(Error::Timeout)
            } else {
                None
            };
            if let Some(e) = failure {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e);
            }
            match input.write(&config_stdin.as_bytes()[sent..]) {
                Ok(0) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(Error::Transport);
                }
                Ok(n) => sent += n,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(5))
                }
                Err(_) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(Error::Transport);
                }
            }
        }
        drop(input);
        let mut out = child.stdout.take().ok_or(Error::Transport)?;
        let fd = out.as_raw_fd();
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
        if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
            let _ = child.kill();
            let _ = child.wait();
            return Err(Error::Transport);
        }
        let result = (|| {
            let mut bytes = Vec::new();
            let mut buf = [0u8; 8192];
            loop {
                if cancel.load(Ordering::Acquire) {
                    return Err(Error::Cancelled);
                }
                if start.elapsed() >= Duration::from_millis(config.timeout_ms) {
                    return Err(Error::Timeout);
                }
                match out.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        if bytes.len() + n > adapter::MAX_ENVELOPE + 4 {
                            return Err(Error::TooLarge);
                        }
                        bytes.extend_from_slice(&buf[..n]);
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(5))
                    }
                    Err(_) => return Err(Error::Transport),
                }
            }
            let status = loop {
                if cancel.load(Ordering::Acquire) {
                    return Err(Error::Cancelled);
                }
                if start.elapsed() >= Duration::from_millis(config.timeout_ms) {
                    return Err(Error::Timeout);
                }
                if let Some(status) = child.try_wait().map_err(|_| Error::Transport)? {
                    break status;
                }
                thread::sleep(Duration::from_millis(5));
            };
            if !status.success() {
                return Err(if status.code() == Some(28) {
                    Error::Timeout
                } else {
                    Error::Transport
                });
            }
            let split = bytes
                .iter()
                .rposition(|b| *b == b'\n')
                .ok_or(Error::Transport)?;
            let status = std::str::from_utf8(&bytes[split + 1..])
                .ok()
                .and_then(|s| s.parse().ok())
                .ok_or(Error::Transport)?;
            bytes.truncate(split);
            Ok((status, bytes))
        })();
        if result.is_err() {
            let _ = child.kill();
            let _ = child.wait();
        }
        result
    }
}
pub struct Completion {
    pub turn_id: String,
    pub context: ContextRef,
    pub result: Result<Suggestion, Error>,
    pub usage: Option<adapter::Usage>,
}
struct Active {
    turn_id: String,
    context: ContextRef,
    cancel: Arc<AtomicBool>,
    started: Instant,
}
pub struct Service {
    config: Config,
    transport: Arc<dyn Transport>,
    active: Option<Active>,
    tx: mpsc::SyncSender<Completion>,
    rx: mpsc::Receiver<Completion>,
    pub ledger: Ledger,
    requests: u32,
}
impl Service {
    pub fn active_turn(&self) -> Option<&str> {
        self.active.as_ref().map(|a| a.turn_id.as_str())
    }
    pub fn disabled() -> Self {
        Self::with_transport_unchecked(Config::default(), Arc::new(CurlTransport))
    }
    pub fn from_config(config: Config) -> Result<Self, Error> {
        config.validate()?;
        Ok(Self::with_transport_unchecked(
            config,
            Arc::new(CurlTransport),
        ))
    }
    #[allow(dead_code)] // Injectable daemon transport/credential resolver; mock tests exercise the same seam.
    pub fn with_transport(config: Config, transport: Arc<dyn Transport>) -> Result<Self, Error> {
        config.validate()?;
        Ok(Self::with_transport_unchecked(config, transport))
    }
    fn with_transport_unchecked(config: Config, transport: Arc<dyn Transport>) -> Self {
        let (tx, rx) = mpsc::sync_channel(1);
        Self {
            config,
            transport,
            active: None,
            tx,
            rx,
            ledger: Ledger::default(),
            requests: 0,
        }
    }
    /// Caller must authenticate host, exact current context, and one-use selection
    /// consent before this method. Raw filesystem/scrollback collection is absent.
    pub fn start(
        &mut self,
        turn: UserTurn,
        identity: &str,
        memory: &[String],
        targets: BTreeSet<String>,
    ) -> Result<(), Error> {
        if !self.config.enabled {
            return Err(Error::Disabled);
        }
        if self.active.is_some() {
            return Err(Error::Busy);
        }
        if self.requests >= self.config.max_requests_per_session {
            return Err(Error::Budget);
        }
        let body = adapter::request(&self.config, &turn, identity, memory, &targets)?;
        self.ledger
            .begin(&turn.turn_id, turn.context.clone(), Route::TextResponses)?;
        let cancel = Arc::new(AtomicBool::new(false));
        self.active = Some(Active {
            turn_id: turn.turn_id.clone(),
            context: turn.context.clone(),
            cancel: cancel.clone(),
            started: Instant::now(),
        });
        self.requests += 1;
        let tx = self.tx.clone();
        let config = self.config.clone();
        let transport = self.transport.clone();
        let turn_id = turn.turn_id.clone();
        let spawned = thread::Builder::new()
            .name("eva-responses".into())
            .spawn(move || {
                let mut usage = None;
                let result = transport
                    .send(&config, &body, &cancel)
                    .and_then(|(status, bytes)| {
                        if cancel.load(Ordering::Acquire) {
                            Err(Error::Cancelled)
                        } else {
                            let reply = adapter::response(&config, status, &bytes, &targets);
                            if (200..300).contains(&status) {
                                usage = adapter::usage(&bytes).ok().flatten();
                            }
                            reply
                        }
                    });
                let _ = tx.send(Completion {
                    turn_id: turn.turn_id,
                    context: turn.context,
                    result,
                    usage,
                });
            });
        if spawned.is_err() {
            self.active = None;
            let _ = self.ledger.finish(&turn_id, false);
            return Err(Error::Transport);
        }
        Ok(())
    }
    /// Cancellation keeps the inflight slot until the bounded worker exits; never
    /// spawn unbounded orphan requests or automatically retry 429/unknown outcomes.
    pub fn cancel(&mut self, id: &str) -> Result<(), Error> {
        let a = self.active.as_ref().ok_or(Error::Stale)?;
        if a.turn_id != id {
            return Err(Error::Stale);
        }
        a.cancel.store(true, Ordering::Release);
        self.ledger.interrupt(id)
    }
    pub fn poll(&mut self) -> Option<Completion> {
        if let Some(a) = &self.active {
            if a.started.elapsed() > Duration::from_millis(self.config.timeout_ms) {
                a.cancel.store(true, Ordering::Release);
            }
        }
        let mut c = self.rx.try_recv().ok()?;
        let a = self.active.take()?;
        if c.turn_id != a.turn_id || c.context != a.context {
            c.result = Err(Error::Stale)
        } else if a.cancel.load(Ordering::Acquire) {
            c.result = Err(
                if a.started.elapsed() > Duration::from_millis(self.config.timeout_ms) {
                    Error::Timeout
                } else {
                    Error::Cancelled
                },
            )
        }
        let _ = self
            .ledger
            .account(&c.turn_id, self.config.model.clone(), c.usage.clone());
        let _ = self.ledger.finish(&c.turn_id, c.result.is_ok());
        Some(c)
    }
    pub fn displayed(&mut self, id: &str, context: &ContextRef) -> Result<(), Error> {
        self.ledger.displayed(id, context)
    }
}
impl Drop for Service {
    fn drop(&mut self) {
        if let Some(a) = &self.active {
            a.cancel.store(true, Ordering::Release);
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;
    struct Mock {
        calls: AtomicUsize,
        wait_cancel: bool,
        status: u16,
    }
    impl Transport for Mock {
        fn send(&self, _: &Config, _: &[u8], cancel: &AtomicBool) -> Result<(u16, Vec<u8>), Error> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            if self.wait_cancel {
                while !cancel.load(Ordering::Acquire) {
                    thread::sleep(Duration::from_millis(1));
                }
                return Err(Error::Cancelled);
            }
            Ok((self.status,br#"{"status":"completed","output":[{"type":"message","role":"assistant","status":"completed","content":[{"type":"output_text","text":"hello"}]}]}"#.to_vec()))
        }
    }
    fn cfg() -> Config {
        Config {
            enabled: true,
            model: "fixture-only".into(),
            timeout_ms: 100,
            ..Config::default()
        }
    }
    fn turn(id: &str) -> UserTurn {
        UserTurn {
            turn_id: id.into(),
            context: ContextRef {
                host_id: "h".into(),
                pane_id: "p".into(),
                project_id: Some("A".into()),
                task_id: None,
                revision: 1,
            },
            text: "hello".into(),
            approved_selection: None,
        }
    }
    fn finish(s: &mut Service) -> Completion {
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            if let Some(c) = s.poll() {
                return c;
            }
            assert!(Instant::now() < deadline, "mock worker did not terminate");
            thread::sleep(Duration::from_millis(1));
        }
    }
    #[test]
    fn mock_only_zero_idle_one_inflight_cancel_no_replay() {
        let m = Arc::new(Mock {
            calls: AtomicUsize::new(0),
            wait_cancel: true,
            status: 200,
        });
        let mut s = Service::with_transport(cfg(), m.clone()).unwrap();
        assert!(s.poll().is_none());
        assert_eq!(m.calls.load(Ordering::SeqCst), 0);
        s.start(turn("1"), "Eva", &[], BTreeSet::new()).unwrap();
        assert_eq!(
            s.start(turn("2"), "Eva", &[], BTreeSet::new()),
            Err(Error::Busy)
        );
        s.cancel("1").unwrap();
        assert_eq!(finish(&mut s).result, Err(Error::Cancelled));
        assert_eq!(
            s.start(turn("1"), "Eva", &[], BTreeSet::new()),
            Err(Error::Duplicate)
        );
    }
    #[test]
    fn mock_only_completed_is_not_displayed_or_heard() {
        let m = Arc::new(Mock {
            calls: AtomicUsize::new(0),
            wait_cancel: false,
            status: 200,
        });
        let mut s = Service::with_transport(cfg(), m).unwrap();
        s.start(turn("1"), "Eva", &[], BTreeSet::new()).unwrap();
        let c = finish(&mut s);
        assert!(c.result.is_ok());
        let e = s.ledger.entry("1").unwrap();
        assert!(e.generated);
        assert!(!e.displayed);
        assert_eq!(e.audibly_played_ms, 0);
        let mut other = c.context.clone();
        other.project_id = Some("B".into());
        assert_eq!(s.displayed("1", &other), Err(Error::Stale));
        s.displayed("1", &c.context).unwrap();
    }
    #[test]
    fn mock_only_timeout_rate_limit_budget() {
        let m = Arc::new(Mock {
            calls: AtomicUsize::new(0),
            wait_cancel: true,
            status: 200,
        });
        let mut s = Service::with_transport(cfg(), m).unwrap();
        s.start(turn("1"), "Eva", &[], BTreeSet::new()).unwrap();
        assert_eq!(finish(&mut s).result, Err(Error::Timeout));
        let m = Arc::new(Mock {
            calls: AtomicUsize::new(0),
            wait_cancel: false,
            status: 429,
        });
        let mut c = cfg();
        c.max_requests_per_session = 1;
        let mut s = Service::with_transport(c, m.clone()).unwrap();
        s.start(turn("1"), "Eva", &[], BTreeSet::new()).unwrap();
        assert_eq!(finish(&mut s).result, Err(Error::RateLimited));
        assert_eq!(
            s.start(turn("2"), "Eva", &[], BTreeSet::new()),
            Err(Error::Budget)
        );
        assert_eq!(m.calls.load(Ordering::SeqCst), 1);
    }
}
#[cfg(test)]
mod privacy_tests {
    use super::*;
    struct Never;
    impl Transport for Never {
        fn send(&self, _: &Config, _: &[u8], _: &AtomicBool) -> Result<(u16, Vec<u8>), Error> {
            panic!("denied input reached transport")
        }
    }
    #[test]
    fn disabled_and_cross_scope_input_never_reaches_transport() {
        let c = Config {
            enabled: false,
            model: "fixture-only".into(),
            ..Config::default()
        };
        let mut s = Service::with_transport(c.clone(), Arc::new(Never)).unwrap();
        let context = ContextRef {
            host_id: "h".into(),
            pane_id: "p".into(),
            task_id: None,
            project_id: Some("A".into()),
            revision: 1,
        };
        let mut t = UserTurn {
            turn_id: "1".into(),
            context: context.clone(),
            text: "explicit question".into(),
            approved_selection: None,
        };
        assert_eq!(
            s.start(t.clone(), "Eva", &[], BTreeSet::new()),
            Err(Error::Disabled)
        );
        let mut c = c;
        c.enabled = true;
        let mut s = Service::with_transport(c, Arc::new(Never)).unwrap();
        let mut wrong = context;
        wrong.project_id = Some("B".into());
        t.approved_selection = Some(adapter::SelectedEvidence {
            context: wrong,
            text: "PRIVATE_CROSS_PROJECT".into(),
            consent_id: "review".into(),
            source_event_id: "source".into(),
            captured_at_ms: 1,
        });
        assert_eq!(
            s.start(t, "Eva", &[], BTreeSet::new()),
            Err(Error::UnauthorizedContext)
        );
        assert!(s.active_turn().is_none());
    }
}

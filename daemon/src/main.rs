//! Single-threaded authority. Durable state is committed BEFORE any revoke/grant is enqueued.
mod dialogue;
mod memory_gateway;
mod providers;
mod storage;
mod task_authority;
use companion_client::Framed;
use companion_core::{
    behavior::{Facts, FocusPolicy, Motion, Scheduler, Work},
    Effect, Phase, State,
};
use companion_protocol::*;
use std::{
    collections::{HashMap, HashSet},
    env, fs, io,
    os::unix::{
        fs::{FileTypeExt, PermissionsExt},
        io::AsRawFd,
        net::{UnixListener, UnixStream},
    },
    path::PathBuf,
    time::{Duration, Instant},
};
use storage::{random_id, Store};
struct Peer {
    withdrawing: bool,
    desktop: Option<String>,
    desktop_authorized: bool,
    delivery_failed: bool,
    last_activity: u64,
    context: Option<ContextRef>,
    memory_scopes: Vec<MemoryScope>,
    selection: Option<(SelectionEvidence, bool, Instant)>,
    compositor: bool,
    focused: bool,
    geometry_revision: u64,
    task: Option<(String, u64, TaskStatus)>,
    eva: Option<String>,
    io: Framed,
    host: Option<Host>,
    seq: u64,
    events: HashSet<String>,
    window: Instant,
    count: u32,
    geometry: bool,
    input: bool,
    selecting: bool,
}
fn isolate_delivery(failed: &mut bool, result: io::Result<()>) {
    if result.is_err() {
        *failed = true;
    }
}
impl Peer {
    // Uniform call sites retain Result for storage/encoding workflow; wire failure is
    // recorded for connection-local teardown, never escalated to authority failure.
    fn queue(&mut self, reply: &Reply) -> io::Result<()> {
        if !self.delivery_failed {
            let result = self.io.queue(reply);
            isolate_delivery(&mut self.delivery_failed, result);
        }
        Ok(())
    }
}
fn peer_session(s: &UnixStream, session: &str) -> io::Result<PathBuf> {
    let mut cred: libc::ucred = unsafe { std::mem::zeroed() };
    let mut n = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            s.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            &mut cred as *mut _ as *mut _,
            &mut n,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    if cred.uid != unsafe { libc::geteuid() } {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "wrong_uid"));
    }
    let bytes = fs::read(format!("/proc/{}/environ", cred.pid))?;
    let entries: Vec<_> = bytes.split(|b| *b == 0).collect();
    let expected = format!("XDG_SESSION_ID={session}");
    if !entries.contains(&expected.as_bytes())
        || entries
            .iter()
            .any(|e| e.starts_with(b"SSH_CONNECTION=") || e.starts_with(b"SSH_TTY="))
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "graphical_session_mismatch_or_ssh",
        ));
    }
    fs::read_link(format!("/proc/{}/exe", cred.pid))
}
fn commit(
    store: &Store,
    state: &mut State,
    change: (State, Vec<Effect>),
    peers: &mut HashMap<u64, Peer>,
) -> io::Result<()> {
    store.commit(&change.0)?;
    *state = change.0;
    for e in change.1 {
        for p in peers
            .values_mut()
            .filter(|p| p.host.as_ref().is_some_and(|h| h.id == e.host))
        {
            p.queue(&e.reply)?;
        }
    }
    Ok(())
}
fn snapshot(s: &State, pose: &str) -> Reply {
    Reply::Snapshot {
        revision: s.revision,
        token: s.possible_body.clone().filter(|_| !s.revoke_intent),
        pose: pose.into(),
        mode: s.mode,
        recovery_blocked: s.phase == Phase::RecoveryBlocked,
    }
}
fn main() {
    if let Err(e) = run() {
        eprintln!("jcompaniond fail-closed: {e}");
        std::process::exit(1)
    }
}
fn run() -> io::Result<()> {
    let session = env::var("XDG_SESSION_ID").map_err(|_| {
        io::Error::other("XDG_SESSION_ID required; SSH and unbound sessions unsupported")
    })?;
    if !identifier(&session) || env::var_os("SSH_CONNECTION").is_some() {
        return Err(io::Error::other("invalid/local graphical session required"));
    }
    let dir = env::args_os().nth(1).map(PathBuf::from).ok_or_else(|| {
        io::Error::other(
            "usage: jcompaniond PRIVATE_PROFILE_DIRECTORY; enabled only by explicit launch",
        )
    })?;
    let desktop_exe = env::var_os("EVA_COMPANION_DESKTOP_EXE")
        .map(|path| {
            let path = PathBuf::from(path);
            if !path.is_absolute() {
                return Err(io::Error::other("desktop executable must be absolute"));
            }
            fs::canonicalize(path)
        })
        .transpose()?;
    let store = Store::open(&dir)?;
    let boot = random_id()?;
    let mut state = match store.load()? {
        Some(s) => {
            if s.session_id != session {
                return Err(io::Error::other("profile bound to another session; retire old surface before explicit session migration"));
            }
            s.recover(boot)
        }
        None => State::new(random_id()?, boot, session.clone()),
    };
    if env::var("EVA_COMPANION_REQUIRE_COMPOSITOR").as_deref() == Ok("1") {
        state.require_compositor = true;
    }
    if env::args().any(|a| a == "--compositor-only")
        || env::var("EVA_COMPANION_COMPOSITOR_ONLY").as_deref() == Ok("1")
    {
        state.compositor_only = true;
    }
    store.commit(&state)?;
    let mut runtime_lock = None;
    let socket = if let Some(path) = env::var_os("EVA_COMPANION_SOCKET") {
        PathBuf::from(path)
    } else if let Some(runtime) = env::var_os("XDG_RUNTIME_DIR") {
        let runtime = PathBuf::from(runtime).join("jcompanion");
        if runtime.canonicalize().ok() != dir.canonicalize().ok() {
            runtime_lock = Some(Store::open(&runtime)?);
        }
        runtime.join("eva.sock")
    } else {
        dir.join("companion.sock")
    };
    // Parent must already be a private application directory for explicit overrides.
    let parent = socket
        .parent()
        .ok_or_else(|| io::Error::other("socket parent required"))?;
    let m = fs::symlink_metadata(parent)?;
    use std::os::unix::fs::MetadataExt;
    if !m.is_dir()
        || m.file_type().is_symlink()
        || m.uid() != unsafe { libc::geteuid() }
        || m.mode() & 0o077 != 0
    {
        return Err(io::Error::other(
            "socket parent must be owned private directory",
        ));
    }
    let _socket_lock = storage::lock_socket(&socket)?;
    if let Ok(m) = fs::symlink_metadata(&socket) {
        if UnixStream::connect(&socket).is_ok() {
            return Err(io::Error::other("socket already served by another profile"));
        }
        if !m.file_type().is_socket() {
            return Err(io::Error::other("socket path is not socket"));
        }
        fs::remove_file(&socket)?;
    }
    let _runtime_lock = runtime_lock;
    let listener = UnixListener::bind(&socket)?;
    fs::set_permissions(&socket, fs::Permissions::from_mode(0o600))?;
    listener.set_nonblocking(true)?;
    let mut peers = HashMap::<u64, Peer>::new();
    let mut next_id = 0u64;
    let start = Instant::now();
    let mut focus = FocusPolicy::default();
    let mut scheduler = Scheduler::new(1);
    let mut last_tick = 0;
    let mut pose = "idle".to_owned();
    let mut audio = AudioTracker::default();
    let mut memories = memory_gateway::Gateway::open(&dir.join("memory.sqlite"));
    let mut task_authority = task_authority::Authority::open(&dir);
    let (mut provider, provider_diagnostic) = load_provider(&dir);
    let mut turn_owners = HashMap::<String, (u64, ContextRef)>::new();
    loop {
        loop {
            match listener.accept() {
                Ok((s, _)) => {
                    if peers.len() >= 32 {
                        continue;
                    }
                    let executable = match peer_session(&s, &session) {
                        Ok(exe) => exe,
                        Err(_) => continue,
                    };
                    next_id += 1;
                    peers.insert(
                        next_id,
                        Peer {
                            withdrawing: false,
                            desktop: None,
                            desktop_authorized: desktop_exe.as_ref() == Some(&executable),
                            delivery_failed: false,
                            last_activity: start.elapsed().as_millis() as u64,
                            context: None,
                            memory_scopes: vec![],
                            selection: None,
                            compositor: false,
                            focused: false,
                            geometry_revision: 0,
                            task: None,
                            eva: None,
                            io: Framed::new(s)?,
                            host: None,
                            seq: 0,
                            events: HashSet::new(),
                            window: Instant::now(),
                            count: 0,
                            geometry: false,
                            input: false,
                            selecting: false,
                        },
                    );
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                Err(e) => return Err(e),
            }
        }
        let mut incoming = vec![];
        let mut dead = vec![];
        for (&id, p) in peers.iter_mut() {
            if p.selection
                .as_ref()
                .is_some_and(|(_, _, t)| t.elapsed() >= Duration::from_secs(60))
            {
                p.selection = None;
            }
            if p.delivery_failed {
                dead.push(id);
                continue;
            }
            if p.io.flush().is_err() {
                dead.push(id);
                continue;
            }
            match p.io.read() {
                Ok(frames) => {
                    for b in frames {
                        incoming.push((id, b))
                    }
                }
                Err(_) => dead.push(id),
            }
        }
        for (id, bytes) in incoming {
            let live_hosts: Vec<Host> = peers.values().filter_map(|p| p.host.clone()).collect();
            if dead.contains(&id) || peers.get(&id).is_some_and(|p| p.delivery_failed) {
                continue;
            }
            let result = decode(&bytes);
            let mut rejection = None;
            if let Some(p) = peers.get_mut(&id) {
                if p.window.elapsed() >= Duration::from_secs(1) {
                    p.window = Instant::now();
                    p.count = 0;
                }
                p.count += 1;
                if p.count > 200 {
                    dead.push(id);
                    continue;
                }
            }
            match result {
                Err(e) => {
                    if let Some(p) = peers
                        .get_mut(&id)
                        .filter(|p| p.host.is_some() || p.eva.is_some() || p.desktop.is_some())
                    {
                        p.queue(&Reply::OperationError {
                            operation: "invalid_request".into(),
                            reason: e,
                        })?;
                    } else {
                        rejection = Some(e)
                    }
                }
                Ok(e) => {
                    let p = peers.get_mut(&id).unwrap();
                    if e.session_id != session
                        || e.source_seq <= p.seq
                        || p.events.contains(&e.event_id)
                        || p.events.len() >= 4096
                    {
                        rejection = Some("session_or_replay_reconnect_required".into())
                    } else if matches!(e.body, Request::DesktopHello) {
                        if p.host.is_some()
                            || p.eva.is_some()
                            || p.desktop.is_some()
                            || !p.desktop_authorized
                            || !e.boot_id.is_empty()
                            || peers.values().any(|p| p.desktop.is_some())
                        {
                            rejection = Some("desktop_role_not_authorized_or_busy".into());
                        } else {
                            let p = peers.get_mut(&id).unwrap();
                            p.seq = e.source_seq;
                            p.events.insert(e.event_id);
                            p.desktop = Some(e.source_id);
                            p.queue(&Reply::Accepted {
                                boot_id: state.boot_id.clone(),
                                companion_id: state.companion_id.clone(),
                                session_id: session.clone(),
                            })?;
                            let change = state.desktop_status(state.locked, false);
                            commit(&store, &mut state, change, &mut peers)?;
                        }
                    } else if matches!(e.body, Request::EvaHello) {
                        if p.host.is_some()
                            || p.eva.is_some()
                            || !e.boot_id.is_empty()
                            || peers.values().any(|p| p.eva.is_some())
                        {
                            rejection = Some("audio_owner_already_bound".into())
                        } else {
                            let p = peers.get_mut(&id).unwrap();
                            p.seq = e.source_seq;
                            p.events.insert(e.event_id);
                            p.eva = Some(e.source_id);
                            p.queue(&Reply::Accepted {
                                boot_id: state.boot_id.clone(),
                                companion_id: state.companion_id.clone(),
                                session_id: session.clone(),
                            })?;
                        }
                    } else if let Request::Hello { host } | Request::CompositorHello { host } =
                        e.body.clone()
                    {
                        let compositor = matches!(e.body, Request::CompositorHello { .. });
                        if p.host.is_some()
                            || p.eva.is_some()
                            || p.desktop.is_some()
                            || !e.boot_id.is_empty()
                        {
                            rejection = Some("duplicate_hello".into())
                        } else if compositor
                            && (!p.desktop_authorized
                                || !state.compositor_only
                                || peers.values().any(|p| p.compositor))
                        {
                            rejection = Some("compositor_mode_or_owner_conflict".into());
                        } else if peers.iter().any(|(other, p)| {
                            *other != id && p.host.as_ref().is_some_and(|h| h.id == host.id)
                        }) {
                            rejection = Some("host_already_connected".into())
                        } else {
                            let p = peers.get_mut(&id).unwrap();
                            p.seq = e.source_seq;
                            p.events.insert(e.event_id);
                            p.host = Some(host.clone());
                            p.compositor = compositor;
                            p.queue(&Reply::Accepted {
                                boot_id: state.boot_id.clone(),
                                companion_id: state.companion_id.clone(),
                                session_id: session.clone(),
                            })?;
                            p.queue(&snapshot(&state, &pose))?;
                            p.queue(&Reply::Appearance {
                                skin: if state.night {
                                    "night".into()
                                } else {
                                    state.skin.clone()
                                },
                                motion: state.motion.clone(),
                            })?;
                            if let Some(reason) = &provider_diagnostic {
                                p.queue(&Reply::OperationError {
                                    operation: "provider_configuration".into(),
                                    reason: reason.clone(),
                                })?;
                            }
                            p.queue(&Reply::ProfileName {
                                name: state.name.clone(),
                            })?;
                            p.queue(&Reply::Comfort {
                                quiet: state.quiet,
                                night: state.night,
                            })?;
                            for t in state.retired_tokens.iter().filter(|t| {
                                t.host_id == host.id
                                    && t.incarnation == host.incarnation
                                    && t.surface_id == host.surface_id
                            }) {
                                p.queue(&Reply::RetirementAccepted { token: t.clone() })?;
                            }
                            if let Some(r) = state.reconciliation(&host) {
                                p.queue(&r)?
                            }
                        }
                    } else if let Some(source) = &p.desktop {
                        if *source != e.source_id || e.boot_id != state.boot_id {
                            rejection = Some("desktop_binding".into())
                        } else {
                            p.seq = e.source_seq;
                            p.events.insert(e.event_id);
                            match e.body {
                                Request::SessionLock { locked } => {
                                    if locked {
                                        if let Some(turn) =
                                            provider.active_turn().map(str::to_owned)
                                        {
                                            let _ = provider.cancel(&turn);
                                        }
                                    }
                                    let change = state.desktop_status(locked, true);
                                    commit(&store, &mut state, change, &mut peers)?;
                                }
                                Request::Resume => {
                                    let now = start.elapsed().as_millis() as u64;
                                    scheduler.resume(now);
                                    focus.resume(now);
                                    for p in peers.values_mut() {
                                        p.last_activity = now;
                                        p.selection = None;
                                    }
                                }
                                _ => rejection = Some("desktop_observer_role_only".into()),
                            }
                        }
                    } else if let Some(source) = &p.eva {
                        if *source != e.source_id || e.boot_id != state.boot_id {
                            rejection = Some("audio_binding".into())
                        } else {
                            p.seq = e.source_seq;
                            p.events.insert(e.event_id);
                            match e.body {
                                Request::VoiceContext {
                                    session_id: voice_session,
                                    include_global_memory,
                                } => {
                                    if !state.locked
                                        && !(state.desktop_observed && !state.desktop_known)
                                        && unix_millis() > 0
                                        && state.voice_lease.as_ref()
                                            == Some(&VoiceLease {
                                                source_id: source.clone(),
                                                session_id: voice_session.clone(),
                                            })
                                    {
                                        let (entries, status) = if include_global_memory {
                                            match memories.voice_global(unix_millis()) {
                                                Ok(entries) => (
                                                    entries,
                                                    "explicit_confirmed_global_latest4".into(),
                                                ),
                                                Err(error) => (vec![], error),
                                            }
                                        } else {
                                            (vec![], "not_requested".into())
                                        };
                                        p.queue(&Reply::VoiceContext {
                                            session_id: voice_session,
                                            companion_id: state.companion_id.clone(),
                                            profile_revision: state.profile_revision,
                                            name: state.name.clone(),
                                            global_memory: entries,
                                            memory_status: status,
                                        })?;
                                    } else {
                                        p.queue(&Reply::OperationError {
                                            operation: "voice_context".into(),
                                            reason: "voice_lease_not_owned".into(),
                                        })?;
                                    }
                                }
                                Request::VoiceAcquire {
                                    session_id: voice_session,
                                } => {
                                    let desired = VoiceLease {
                                        source_id: source.clone(),
                                        session_id: voice_session.clone(),
                                    };
                                    let granted = !state.locked
                                        && !(state.desktop_observed && !state.desktop_known)
                                        && provider.active_turn().is_none()
                                        && (state.voice_lease.is_none()
                                            || state.voice_lease.as_ref() == Some(&desired));
                                    if granted && state.voice_lease.is_none() {
                                        let mut n = state.clone();
                                        n.voice_lease = Some(desired);
                                        n.revision += 1;
                                        store.commit(&n)?;
                                        state = n;
                                    }
                                    p.queue(&Reply::VoicePermit {
                                        session_id: voice_session,
                                        granted,
                                    })?;
                                }
                                Request::VoiceRelease {
                                    session_id: voice_session,
                                } => {
                                    if state.voice_lease.as_ref()
                                        == Some(&VoiceLease {
                                            source_id: source.clone(),
                                            session_id: voice_session.clone(),
                                        })
                                    {
                                        let mut n = state.clone();
                                        n.voice_lease = None;
                                        n.revision += 1;
                                        store.commit(&n)?;
                                        state = n;
                                        audio.disconnect();
                                        p.queue(&Reply::VoiceReleased {
                                            session_id: voice_session.clone(),
                                        })?;
                                    } else if state.voice_lease.is_none() {
                                        p.queue(&Reply::VoiceReleased {
                                            session_id: voice_session.clone(),
                                        })?;
                                    } else {
                                        p.queue(&Reply::OperationError {
                                            operation: "voice_release".into(),
                                            reason: "voice_lease_not_owned".into(),
                                        })?;
                                    }
                                }
                                Request::Audio {
                                    turn_id,
                                    state: status,
                                    generated_samples,
                                    played_samples,
                                    interrupted,
                                } => {
                                    if !matches!(
                                        status,
                                        AudioState::Idle | AudioState::Stopped | AudioState::Error
                                    ) && state
                                        .voice_lease
                                        .as_ref()
                                        .is_none_or(|v| v.source_id != *source)
                                    {
                                        p.queue(&Reply::OperationError {
                                            operation: "audio".into(),
                                            reason: "voice_permit_required".into(),
                                        })?;
                                        continue;
                                    }
                                    if let Err(e) = audio.observe(
                                        turn_id,
                                        status,
                                        generated_samples,
                                        played_samples,
                                        interrupted,
                                    ) {
                                        p.queue(&Reply::OperationError {
                                            operation: "audio".into(),
                                            reason: e,
                                        })?;
                                    }
                                }
                                _ => rejection = Some("audio_role_only".into()),
                            }
                        }
                    } else if p.host.as_ref().is_none_or(|h| h.id != e.source_id)
                        || e.boot_id != state.boot_id
                    {
                        rejection = Some("not_bound_or_stale_boot".into())
                    } else {
                        p.seq = e.source_seq;
                        p.events.insert(e.event_id);
                        let h = p.host.clone().unwrap();
                        if (unix_millis() == 0
                            || state.locked
                            || (state.desktop_observed && !state.desktop_known))
                            && matches!(
                                e.body,
                                Request::ContextAccessRequested { .. }
                                    | Request::ContextAccessGranted { .. }
                                    | Request::MemoryScopeReviewRequested { .. }
                                    | Request::MemoryScopeApprove { .. }
                                    | Request::TaskScopes { .. }
                                    | Request::MemoryScopes { .. }
                                    | Request::TaskSharePropose { .. }
                                    | Request::TaskShareApprove { .. }
                                    | Request::MemoryList { .. }
                                    | Request::MemoryUse { .. }
                                    | Request::MemoryPropose { .. }
                                    | Request::MemoryApprove { .. }
                                    | Request::DialogueStart { .. }
                            )
                        {
                            p.queue(&Reply::OperationError {
                                operation: "privacy".into(),
                                reason: "desktop_locked_or_unknown".into(),
                            })?;
                            continue;
                        }
                        if matches!(
                            e.body,
                            Request::DialogueStart { .. }
                                | Request::ContextAccessRequested { .. }
                                | Request::MemoryUse { .. }
                        ) {
                            if let Some(context) = &p.context {
                                if let Some(task) = &context.task_id {
                                    if let Err(reason) =
                                        task_authority.bind(&h, task, context.project_id.as_deref())
                                    {
                                        p.queue(&Reply::OperationError {
                                            operation: "task_context".into(),
                                            reason,
                                        })?;
                                        continue;
                                    }
                                }
                            }
                        }
                        let now = start.elapsed().as_millis() as u64;
                        let change = match e.body {
                            Request::ContextObserved { context } => {
                                if context.host_id != h.id
                                    || p.context.as_ref().is_some_and(|old| {
                                        old.pane_id == context.pane_id
                                            && context.revision < old.revision
                                    })
                                {
                                    p.queue(&Reply::OperationError {
                                        operation: "context".into(),
                                        reason: "stale_context".into(),
                                    })?;
                                } else if p.context.as_ref() != Some(&context) {
                                    if let Some(task) = &context.task_id {
                                        if let Err(reason) = task_authority.bind(
                                            &h,
                                            task,
                                            context.project_id.as_deref(),
                                        ) {
                                            p.queue(&Reply::OperationError {
                                                operation: "task_context".into(),
                                                reason,
                                            })?;
                                            continue;
                                        }
                                    }
                                    memories.invalidate(id);
                                    task_authority.invalidate(id);
                                    if p.context.is_some() {
                                        let n = state.cancel_recall(&h.id);
                                        if n.revision != state.revision {
                                            store.commit(&n)?;
                                            state = n;
                                        }
                                    }

                                    p.selection = None;
                                    p.memory_scopes = context
                                        .task_id
                                        .as_ref()
                                        .map(|t| vec![MemoryScope::Task(t.clone())])
                                        .unwrap_or_default();
                                    p.context = Some(context);
                                    p.last_activity = now;
                                    if state
                                        .possible_body
                                        .as_ref()
                                        .is_some_and(|t| t.host_id == h.id)
                                    {
                                        scheduler.content_entered_view(now);
                                    }
                                }
                                None
                            }
                            Request::ContextAccessRequested {
                                context,
                                text,
                                source_event_id,
                                captured_at_ms,
                            } => {
                                if p.context.as_ref() != Some(&context)
                                    || captured_at_ms > unix_millis().saturating_add(5000)
                                    || unix_millis().saturating_sub(captured_at_ms) > 300000
                                {
                                    p.queue(&Reply::OperationError {
                                        operation: "context_review".into(),
                                        reason: "stale_context_or_capture".into(),
                                    })?;
                                } else {
                                    let evidence = SelectionEvidence {
                                        context,
                                        text,
                                        source_event_id,
                                        captured_at_ms,
                                        consent_id: random_id()?,
                                    };
                                    p.selection = Some((evidence.clone(), false, Instant::now()));
                                    p.queue(&Reply::ContextAccessReview { evidence })?;
                                }
                                None
                            }
                            Request::ContextAccessGranted {
                                context,
                                consent_id,
                            } => {
                                if p.context.as_ref() == Some(&context)
                                    && p.selection.as_ref().is_some_and(|(e, _, t)| {
                                        e.context == context
                                            && e.consent_id == consent_id
                                            && t.elapsed() < Duration::from_secs(60)
                                    })
                                {
                                    p.selection.as_mut().unwrap().1 = true;
                                    p.queue(&Reply::Ack)?;
                                } else {
                                    p.queue(&Reply::OperationError {
                                        operation: "context_approve".into(),
                                        reason: "stale_selection_review".into(),
                                    })?;
                                }
                                None
                            }
                            Request::MemoryUse { context, scopes } => {
                                if p.context.as_ref() == Some(&context)
                                    && memory_gateway::Gateway::scopes_allowed(&context, &scopes)
                                {
                                    p.memory_scopes = scopes;
                                    p.queue(&Reply::MemoryResult {
                                        review_id: None,
                                        status: "retrieval_scopes_updated".into(),
                                    })?;
                                } else {
                                    p.queue(&Reply::MemoryResult {
                                        review_id: None,
                                        status: "scope_or_context_denied".into(),
                                    })?;
                                }
                                None
                            }
                            request @ (Request::MemoryScopes { .. }
                            | Request::MemoryScopeReviewRequested { .. }
                            | Request::MemoryScopeApprove { .. }
                            | Request::MemoryList { .. }
                            | Request::MemoryPropose { .. }
                            | Request::MemoryApprove { .. }
                            | Request::MemoryCancel { .. }
                            | Request::MemoryPause { .. }) => {
                                let reply = memories
                                    .handle(id, p.context.as_ref(), &request, unix_millis())
                                    .unwrap_or_else(|error| Reply::MemoryResult {
                                        review_id: None,
                                        status: error,
                                    });
                                p.queue(&reply)?;
                                None
                            }
                            Request::DialogueStart {
                                turn_id,
                                context,
                                text,
                                approved_selection,
                            } => {
                                let consent_ok =
                                    approved_selection.as_ref().is_none_or(|selection| {
                                        p.selection.as_ref().is_some_and(|(e, approved, t)| {
                                            *approved
                                                && e == selection
                                                && t.elapsed() < Duration::from_secs(60)
                                        })
                                    });
                                let error = if p.context.as_ref() != Some(&context) {
                                    Some("stale_context".into())
                                } else if !consent_ok {
                                    Some("selection_review_required".into())
                                } else if state.voice_lease.is_some() {
                                    Some("eva_voice_route_active_or_recovery_blocked".into())
                                } else if turn_owners.contains_key(&turn_id)
                                    || turn_owners.len() >= 1024
                                {
                                    Some("duplicate_turn_or_session_limit".into())
                                } else {
                                    None
                                };
                                if let Some(error) = error {
                                    p.queue(&Reply::Dialogue {
                                        turn_id,
                                        context,
                                        status: error,
                                        reply: None,
                                    })?;
                                } else {
                                    let memory = memories.retrieve(
                                        &context,
                                        &p.memory_scopes,
                                        unix_millis(),
                                    );
                                    match memory {
                                        Err(error) => p.queue(&Reply::Dialogue {
                                            turn_id,
                                            context,
                                            status: error,
                                            reply: None,
                                        })?,
                                        Ok(memory) => {
                                            if approved_selection.is_some() {
                                                p.selection = None;
                                            }
                                            let turn = companion_openai::UserTurn {
                                                turn_id: turn_id.clone(),
                                                context: context.clone(),
                                                text,
                                                approved_selection,
                                            };
                                            let targets = context.task_id.iter().cloned().collect();
                                            match provider.start(
                                                turn,
                                                &state.name,
                                                &memory,
                                                targets,
                                            ) {
                                                Ok(()) => {
                                                    turn_owners.insert(
                                                        turn_id.clone(),
                                                        (id, context.clone()),
                                                    );
                                                    p.queue(&Reply::Dialogue {
                                                        turn_id,
                                                        context,
                                                        status: "generating".into(),
                                                        reply: None,
                                                    })?;
                                                }
                                                Err(companion_openai::Error::Disabled) => {
                                                    let offline = provider
                                                        .ledger
                                                        .begin(
                                                            &turn_id,
                                                            context.clone(),
                                                            dialogue::Route::Offline,
                                                        )
                                                        .and_then(|_| {
                                                            provider.ledger.finish(&turn_id, true)
                                                        });
                                                    if offline.is_ok() {
                                                        turn_owners.insert(
                                                            turn_id.clone(),
                                                            (id, context.clone()),
                                                        );
                                                    }
                                                    p.queue(&Reply::Dialogue{turn_id,context,status:if offline.is_ok(){"offline"}else{"duplicate_turn"}.into(),reply:offline.ok().map(|_|"我在这里。当前是离线陪伴模式：可以换形象、跟随、安静陪伴和管理经过确认的本地记忆；云端文字模型未启用或配置不可用。我不会读取终端内容或执行命令。".into())})?;
                                                }
                                                Err(error) => p.queue(&Reply::Dialogue {
                                                    turn_id,
                                                    context,
                                                    status: format!("provider_{error}"),
                                                    reply: None,
                                                })?,
                                            }
                                        }
                                    }
                                }
                                None
                            }
                            Request::DialogueCancel { turn_id } => {
                                if turn_owners
                                    .get(&turn_id)
                                    .is_some_and(|(owner, _)| *owner == id)
                                {
                                    if let Err(error) = provider.cancel(&turn_id) {
                                        p.queue(&Reply::OperationError {
                                            operation: "dialogue_cancel".into(),
                                            reason: error.to_string(),
                                        })?;
                                    }
                                } else {
                                    p.queue(&Reply::OperationError {
                                        operation: "dialogue_cancel".into(),
                                        reason: "turn_not_owned".into(),
                                    })?;
                                }
                                None
                            }
                            Request::DialogueDisplayed { turn_id } => {
                                if let Some((owner, context)) = turn_owners.get(&turn_id) {
                                    if *owner == id {
                                        let _ = provider.displayed(&turn_id, context);
                                    }
                                }
                                None
                            }
                            Request::Withdraw => {
                                p.withdrawing = true;
                                p.geometry = false;
                                p.focused = false;
                                focus.clear(&h.id);
                                Some(state.withdraw(&h).map(|(n, mut effects)| {
                                    if n.possible_body.as_ref().is_none_or(|t| {
                                        t.host_id != h.id || t.incarnation != h.incarnation
                                    }) {
                                        effects.push(Effect {
                                            host: h.id.clone(),
                                            reply: Reply::WithdrawalAccepted {
                                                host_id: h.id.clone(),
                                                incarnation: h.incarnation,
                                            },
                                        });
                                    }
                                    (n, effects)
                                }))
                            }
                            Request::TaskScopes { after } => {
                                p.queue(&task_authority.scopes(after.as_deref()).unwrap_or_else(
                                    |reason| Reply::OperationError {
                                        operation: "task_scopes".into(),
                                        reason,
                                    },
                                ))?;
                                None
                            }
                            Request::TaskSharePropose {
                                task_id,
                                target_host_id,
                            } => {
                                let result = live_hosts
                                    .iter()
                                    .find(|h| h.id == target_host_id)
                                    .ok_or_else(|| "target_host_not_live".to_owned())
                                    .and_then(|target| {
                                        task_authority.propose(
                                            id,
                                            p.context.as_ref(),
                                            &h,
                                            task_id,
                                            target,
                                        )
                                    });
                                p.queue(&result.unwrap_or_else(|reason| Reply::OperationError {
                                    operation: "task_share".into(),
                                    reason,
                                }))?;
                                None
                            }
                            Request::TaskShareApprove { review_id, digest } => {
                                let live = live_hosts
                                    .iter()
                                    .map(|h| (h.id.clone(), h.incarnation))
                                    .collect::<Vec<_>>();
                                p.queue(
                                    &task_authority
                                        .approve(id, p.context.as_ref(), &review_id, &digest, &live)
                                        .unwrap_or_else(|reason| Reply::OperationError {
                                            operation: "task_share".into(),
                                            reason,
                                        }),
                                )?;
                                None
                            }
                            Request::Prepared { epoch } => Some(if p.geometry {
                                state.prepared(&h, epoch)
                            } else {
                                Err("safe_geometry_required".into())
                            }),
                            Request::Retired {
                                token,
                                presentation_serial,
                            } => Some(state.retired(&h, &token, presentation_serial).map(
                                |(n, mut effects)| {
                                    effects.push(Effect {
                                        host: h.id.clone(),
                                        reply: Reply::RetirementAccepted { token },
                                    });
                                    if p.withdrawing
                                        && n.possible_body.as_ref().is_none_or(|t| {
                                            t.host_id != h.id || t.incarnation != h.incarnation
                                        })
                                    {
                                        effects.push(Effect {
                                            host: h.id.clone(),
                                            reply: Reply::WithdrawalAccepted {
                                                host_id: h.id.clone(),
                                                incarnation: h.incarnation,
                                            },
                                        });
                                    }
                                    (n, effects)
                                },
                            )),
                            Request::Presented { token } => Some(state.presented(&h, &token)),
                            Request::Recall => Some(if state.compositor_only != p.compositor {
                                Err("host_is_anchor_only_in_current_mode".into())
                            } else if p.withdrawing {
                                Err("host_withdrawing".into())
                            } else {
                                Ok(state.recall(h))
                            }),
                            Request::Presence { mode } => Some(Ok(state.presence(mode))),
                            Request::Focus { focused } => {
                                if focused && !p.focused {
                                    p.last_activity = now;
                                }
                                p.focused = focused;
                                if focused {
                                    focus.observe(h.id, now)
                                } else {
                                    focus.clear(&h.id)
                                }
                                None
                            }
                            Request::Geometry {
                                revision,
                                viewport,
                                candidates,
                                exclusions,
                            } => {
                                if revision <= p.geometry_revision {
                                    p.queue(&Reply::OperationError {
                                        operation: "geometry".into(),
                                        reason: "stale_geometry".into(),
                                    })?;
                                } else {
                                    p.geometry_revision = revision;
                                    p.geometry = !matches!(
                                        companion_core::geometry::choose(
                                            viewport,
                                            &candidates,
                                            &exclusions,
                                            (56.0, 32.0),
                                            (16.0, 16.0)
                                        ),
                                        companion_core::geometry::Placement::Hidden
                                    );
                                }
                                None
                            }
                            Request::SessionLock { .. } => {
                                p.queue(&Reply::OperationError {
                                    operation: "desktop".into(),
                                    reason: "desktop_observer_required".into(),
                                })?;
                                None
                            }
                            Request::Resume => {
                                p.queue(&Reply::OperationError {
                                    operation: "desktop".into(),
                                    reason: "desktop_observer_required".into(),
                                })?;
                                None
                            }
                            Request::ProfileName { name } => {
                                let mut n = state.clone();
                                n.name = name.clone();
                                n.profile_revision += 1;
                                n.revision += 1;
                                let effects = peers
                                    .values()
                                    .filter_map(|p| p.host.as_ref())
                                    .map(|h| Effect {
                                        host: h.id.clone(),
                                        reply: Reply::ProfileName { name: name.clone() },
                                    })
                                    .collect();
                                Some(Ok((n, effects)))
                            }
                            Request::Comfort { quiet, night } => {
                                let mut n = state.clone();
                                n.quiet = quiet;
                                n.night = night;
                                n.profile_revision += 1;
                                n.revision += 1;
                                let effective = if night {
                                    "night".into()
                                } else {
                                    n.skin.clone()
                                };
                                let effects = peers
                                    .values()
                                    .filter_map(|p| p.host.as_ref())
                                    .flat_map(|h| {
                                        [
                                            Effect {
                                                host: h.id.clone(),
                                                reply: Reply::Comfort { quiet, night },
                                            },
                                            Effect {
                                                host: h.id.clone(),
                                                reply: Reply::Appearance {
                                                    skin: effective.clone(),
                                                    motion: n.motion.clone(),
                                                },
                                            },
                                        ]
                                    })
                                    .collect();
                                Some(Ok((n, effects)))
                            }
                            Request::Appearance { skin, motion } => {
                                let mut n = state.clone();
                                n.skin = skin.clone();
                                n.night = false;
                                n.motion = motion.clone();
                                n.profile_revision += 1;
                                n.revision += 1;
                                Some(Ok((
                                    n,
                                    peers
                                        .values()
                                        .filter_map(|p| p.host.as_ref())
                                        .map(|h| Effect {
                                            host: h.id.clone(),
                                            reply: Reply::Appearance {
                                                skin: skin.clone(),
                                                motion: motion.clone(),
                                            },
                                        })
                                        .collect(),
                                )))
                            }
                            Request::TaskObservation {
                                task_id,
                                context_revision,
                                status,
                            } => {
                                let project = p
                                    .context
                                    .as_ref()
                                    .filter(|c| c.task_id.as_ref() == Some(&task_id))
                                    .and_then(|c| c.project_id.as_deref());
                                if let Err(reason) = task_authority.bind(&h, &task_id, project) {
                                    p.queue(&Reply::OperationError {
                                        operation: "task_observation".into(),
                                        reason,
                                    })?;
                                    continue;
                                }

                                if p.task.as_ref().is_some_and(|(id, r, _)| {
                                    *id == task_id && context_revision < *r
                                }) {
                                    p.queue(&Reply::OperationError {
                                        operation: "task".into(),
                                        reason: "stale_task".into(),
                                    })?;
                                } else {
                                    if p.task.as_ref().is_none_or(|(id, rev, s)| {
                                        id != &task_id || *rev != context_revision || *s != status
                                    }) {
                                        p.last_activity = now;
                                    }
                                    p.task = Some((task_id, context_revision, status));
                                }
                                None
                            }
                            Request::Input { active, selecting } => {
                                if active
                                    || selecting
                                    || p.input != active
                                    || p.selecting != selecting
                                {
                                    p.last_activity = now;
                                }
                                p.input = active;
                                p.selecting = selecting;
                                None
                            }
                            Request::Resync => {
                                p.queue(&snapshot(&state, &pose))?;
                                None
                            }
                            Request::Hello { .. } | Request::CompositorHello { .. } => {
                                unreachable!()
                            }
                            Request::DesktopHello
                            | Request::EvaHello
                            | Request::Audio { .. }
                            | Request::VoiceAcquire { .. }
                            | Request::VoiceRelease { .. }
                            | Request::VoiceContext { .. } => {
                                p.queue(&Reply::OperationError {
                                    operation: "audio".into(),
                                    reason: "audio_role_required".into(),
                                })?;
                                None
                            }
                        };
                        if let Some(c) = change {
                            match c {
                                Ok(c) => {
                                    let grants =
                                        c.1.iter().any(|e| matches!(e.reply, Reply::Grant { .. }));
                                    commit(&store, &mut state, c, &mut peers)?;
                                    if grants {
                                        focus.granted(now);
                                        scheduler.transfer_started(now)
                                    }
                                }
                                Err(e) => {
                                    if let Some(p) = peers.get_mut(&id) {
                                        p.queue(&Reply::OperationError {
                                            operation: "residence".into(),
                                            reason: e,
                                        })?;
                                    }
                                }
                            }
                        }
                    }
                }
            }
            if let Some(reason) = rejection {
                if let Some(p) = peers.get_mut(&id) {
                    p.queue(&Reply::Rejected { reason })?;
                    let _ = p.io.flush();
                    p.delivery_failed = true;
                }
            }
        }
        dead.extend(
            peers
                .iter()
                .filter(|(_, p)| p.delivery_failed)
                .map(|(id, _)| *id),
        );
        for id in dead {
            if let Some(p) = peers.remove(&id) {
                memories.invalidate(id);
                task_authority.invalidate(id);
                if p.desktop.is_some() {
                    let change = state.desktop_status(state.locked, false);
                    commit(&store, &mut state, change, &mut peers)?;
                }
                if let Some(turn) = provider.active_turn().map(str::to_owned) {
                    if turn_owners
                        .get(&turn)
                        .is_some_and(|(owner, _)| *owner == id)
                    {
                        let _ = provider.cancel(&turn);
                    }
                }
                if p.eva.is_some() {
                    audio.disconnect();
                }
                if let Some(h) = p.host {
                    let s = state.disconnected(&h.id);
                    store.commit(&s)?;
                    state = s;
                }
            }
        }
        while let Some(completion) = provider.poll() {
            if let Some((owner, original)) = turn_owners.get(&completion.turn_id) {
                if original != &completion.context {
                    continue;
                }
                if let Some(p) = peers.get_mut(owner) {
                    let (status, reply) =
                        if state.locked || (state.desktop_observed && !state.desktop_known) {
                            ("withheld_while_locked_or_unknown".into(), None)
                        } else {
                            match completion.result {
                                Ok(suggestion) => {
                                    let mut text = suggestion.reply;
                                    if let Some(proposal) = suggestion.memory_proposal {
                                        text.push_str("\n\n待审阅的记忆建议（尚未保存）：");
                                        text.push_str(&proposal);
                                    }
                                    (
                                        if p.context.as_ref() == Some(original) {
                                            "generated".to_owned()
                                        } else {
                                            "generated_for_previous_context".to_owned()
                                        },
                                        Some(text),
                                    )
                                }
                                Err(error) => (format!("provider_{error}"), None),
                            }
                        };
                    p.queue(&Reply::Dialogue {
                        turn_id: completion.turn_id,
                        context: completion.context,
                        status,
                        reply,
                    })?;
                }
            }
        }
        let now = start.elapsed().as_millis() as u64;
        if let Some(wanted) = state.pending_recall.clone() {
            if peers.values().any(|p| {
                p.geometry
                    && !p.withdrawing
                    && p.compositor == state.compositor_only
                    && p.host.as_ref() == Some(&wanted)
            }) {
                if let Ok(change) = state.drive_recall(&wanted) {
                    commit(&store, &mut state, change, &mut peers)?;
                }
            }
        }
        if state.mode == Presence::FollowMe && state.pending_recall.is_none() {
            if let Some(id) = focus.eligible(now) {
                if let Some(h) = peers
                    .values()
                    .find(|p| {
                        !p.withdrawing
                            && p.compositor == state.compositor_only
                            && p.geometry
                            && p.focused
                            && p.host.as_ref().is_some_and(|h| h.id == id)
                    })
                    .and_then(|p| p.host.clone())
                {
                    if let Ok(c) = state.request(h) {
                        if !c.1.is_empty() {
                            commit(&store, &mut state, c, &mut peers)?;
                        }
                    }
                }
            }
        }
        if now.saturating_sub(last_tick) >= 100 {
            last_tick = now;
            let owner = state.possible_body.as_ref().and_then(|t| {
                peers
                    .values()
                    .find(|p| p.host.as_ref().is_some_and(|h| h.id == t.host_id))
            });
            let facts = Facts {
                quiet: state.quiet,
                idle_since: owner.map(|p| p.last_activity).unwrap_or(now),
                work_event: owner.and_then(|p| {
                    p.task.as_ref().map(|(id, rev, _)| {
                        format!(
                            "{}:{id}:{rev}",
                            p.host.as_ref().map(|h| h.id.as_str()).unwrap_or("")
                        )
                    })
                }),
                locked: state.locked,
                work: owner
                    .and_then(|p| p.task.as_ref())
                    .map(|(_, _, s)| match s {
                        TaskStatus::Running => Work::Running,
                        TaskStatus::NeedsReview => Work::NeedsReview,
                        TaskStatus::Succeeded => Work::Succeeded,
                        TaskStatus::Failed => Work::Failed,
                        TaskStatus::Unknown => Work::Unknown,
                    })
                    .unwrap_or(Work::Unknown),
                listening: audio.listening,
                playing: audio.playing,
                hidden: state.mode == Presence::Hidden
                    || (state.desktop_observed && !state.desktop_known),
                input: owner.is_some_and(|p| p.input),
                selecting: owner.is_some_and(|p| p.selecting),
                ..Facts::default()
            };
            let next = scheduler
                .tick(
                    now,
                    &facts,
                    match state.motion.as_str() {
                        "full" => Motion::Full,
                        "static" => Motion::Static,
                        _ => Motion::Calm,
                    },
                )
                .map(|p| p.as_str())
                .unwrap_or("hidden");
            if pose != next {
                pose = next.into();
                for p in peers.values_mut() {
                    if p.host.is_some() {
                        p.queue(&snapshot(&state, &pose))?
                    }
                }
            }
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn unix_millis() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}
fn load_provider(dir: &std::path::Path) -> (providers::Service, Option<String>) {
    use std::io::Read;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    let result = (|| -> Result<providers::Service, String> {
        let file = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(dir.join("provider.json"))
            .map_err(|e| {
                if e.kind() == io::ErrorKind::NotFound {
                    "provider_absent"
                } else {
                    "provider_config_read"
                }
            })?;
        let m = file.metadata().map_err(|_| "provider_metadata")?;
        if !m.is_file() || m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o077 != 0 {
            return Err("provider_config_not_private".into());
        }
        let mut bytes = vec![];
        file.take(8193)
            .read_to_end(&mut bytes)
            .map_err(|_| "provider_read")?;
        if bytes.len() > 8192 {
            return Err("provider_config_limit".into());
        }
        companion_protocol::strict_json::parse(&bytes).map_err(|_| "provider_duplicate_or_json")?;
        let config: companion_openai::Config =
            serde_json::from_slice(&bytes).map_err(|_| "provider_schema")?;
        providers::Service::from_config(config).map_err(|_| "provider_invalid".into())
    })();
    match result {
        Ok(service) => (service, None),
        Err(reason) => (
            providers::Service::disabled(),
            if reason == "provider_absent" {
                None
            } else {
                Some(reason)
            },
        ),
    }
}
#[derive(Default)]
struct AudioTracker {
    turn: Option<String>,
    finished: HashSet<String>,
    generated: u64,
    played: u64,
    listening: bool,
    playing: bool,
}
impl AudioTracker {
    fn disconnect(&mut self) {
        if let Some(t) = self.turn.take() {
            self.finished.insert(t);
        }
        self.listening = false;
        self.playing = false;
        self.generated = 0;
        self.played = 0;
    }
    fn observe(
        &mut self,
        t: String,
        s: AudioState,
        g: u64,
        p: Option<u64>,
        interrupted: bool,
    ) -> Result<(), String> {
        if self.finished.contains(&t) || self.finished.len() > 4096 {
            return Err("audio_turn_replay_or_limit".into());
        }
        if self.turn.as_ref() != Some(&t) {
            self.disconnect();
            self.turn = Some(t.clone());
        }
        if g < self.generated || p.is_some_and(|p| p < self.played || p > g) {
            return Err("audio_counter_regression".into());
        }
        self.generated = g;
        if let Some(p) = p {
            self.played = p;
        }
        self.listening = s == AudioState::Listening && !interrupted;
        self.playing = s == AudioState::Speaking && p.is_some_and(|p| p > 0) && !interrupted;
        if matches!(s, AudioState::Stopped | AudioState::Error) || interrupted {
            self.disconnect();
        }
        Ok(())
    }
}
#[cfg(test)]
mod audio_tests {
    use super::*;
    #[test]
    fn generated_is_not_played() {
        let mut a = AudioTracker::default();
        a.observe("t".into(), AudioState::Speaking, 100, None, false)
            .unwrap();
        assert!(!a.playing);
        a.observe("t".into(), AudioState::Speaking, 100, Some(20), false)
            .unwrap();
        assert!(a.playing);
        a.disconnect();
        assert!(!a.playing);
        assert!(a
            .observe("t".into(), AudioState::Speaking, 100, Some(20), false)
            .is_err());
    }
    #[test]
    fn audio_counter_regression_and_interruption() {
        let mut a = AudioTracker::default();
        a.observe("t".into(), AudioState::Listening, 0, None, false)
            .unwrap();
        assert!(a.listening);
        a.observe("t".into(), AudioState::Speaking, 100, Some(30), false)
            .unwrap();
        assert!(a
            .observe("t".into(), AudioState::Speaking, 100, Some(20), false)
            .is_err());
        a.observe("t".into(), AudioState::Cancelling, 100, Some(30), true)
            .unwrap();
        assert!(!a.playing && !a.listening);
    }
}
#[cfg(test)]
mod peer_backpressure_tests {
    use super::*;
    #[test]
    fn one_hundred_twenty_nine_replies_isolate_only_slow_peer() {
        let mut slow_failed = false;
        let mut healthy_failed = false;
        let mut depth = 0;
        for _ in 0..129 {
            let result = if depth < 128 {
                depth += 1;
                Ok(())
            } else {
                Err(io::Error::new(io::ErrorKind::WouldBlock, "bounded queue"))
            };
            isolate_delivery(&mut slow_failed, result);
        }
        isolate_delivery(&mut healthy_failed, Ok(()));
        assert!(slow_failed);
        assert!(!healthy_failed);
        assert_eq!(depth, 128);
        let s = State::new("eva".into(), "boot".into(), "session".into());
        let h = Host {
            id: "slow".into(),
            incarnation: 1,
            surface_id: "surface".into(),
            retirement: RetirementCapability::NativePresented,
        };
        let (s, _) = s.request(h.clone()).unwrap();
        let (s, _) = s.prepared(&h, 1).unwrap();
        let n = s.disconnected("slow");
        assert_eq!(n.possible_body, s.possible_body);
        assert!(n.revoke_intent);
        assert_eq!(n.phase, Phase::RecoveryBlocked);
    }
}

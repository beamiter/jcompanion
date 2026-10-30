//! Volatile turn ledger. Generation, display and actual Eva playback are distinct.
//! No durable memory writes, execution, microphone ownership, or task-state inference.
use companion_openai::{ContextRef, Error, Usage};
use std::collections::BTreeMap;
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Route {
    TextResponses,
    #[allow(dead_code)] // Reserved for authenticated Eva bridge, not synthesized text speech.
    EvaVoice,
    Offline,
}
#[derive(Clone, Debug)]
pub struct Entry {
    pub context: ContextRef,
    #[allow(dead_code)] // Voice bridge integration seam; text never marks playback.
    pub route: Route,
    pub generated: bool,
    pub displayed: bool,
    #[allow(dead_code)] // Requires actual device duration, never inferred from tokens.
    pub audibly_played_ms: u64,
    pub interrupted: bool,
    pub finished: bool,
    pub model: Option<String>,
    pub usage: Option<Usage>,
}
#[derive(Default)]
pub struct Ledger {
    entries: BTreeMap<String, Entry>,
    active: Option<String>,
}
impl Ledger {
    pub fn begin(&mut self, id: &str, context: ContextRef, route: Route) -> Result<(), Error> {
        if self.entries.contains_key(id) {
            return Err(Error::Duplicate);
        }
        if self.active.is_some() {
            return Err(Error::Busy);
        }
        // Bound a session without evicting deduplication tombstones and replaying old turns.
        if self.entries.len() >= 1024 {
            return Err(Error::Budget);
        }
        self.entries.insert(
            id.into(),
            Entry {
                context,
                route,
                generated: false,
                displayed: false,
                audibly_played_ms: 0,
                interrupted: false,
                finished: false,
                model: None,
                usage: None,
            },
        );
        self.active = Some(id.into());
        Ok(())
    }
    pub fn finish(&mut self, id: &str, generated: bool) -> Result<(), Error> {
        if self.active.as_deref() != Some(id) {
            return Err(Error::Stale);
        }
        let e = self.entries.get_mut(id).ok_or(Error::Stale)?;
        e.generated = generated;
        e.finished = true;
        self.active = None;
        Ok(())
    }
    pub fn displayed(&mut self, id: &str, context: &ContextRef) -> Result<(), Error> {
        let e = self.entries.get_mut(id).ok_or(Error::Stale)?;
        if &e.context != context || !e.generated || e.interrupted {
            return Err(Error::Stale);
        }
        e.displayed = true;
        Ok(())
    }
    /// Only the authenticated sole Eva owner may call this with actual device progress.
    /// Text turns cannot also be spoken through an independent response route.
    #[allow(dead_code)] // Callable by authenticated Eva owner when true milliseconds are available.
    pub fn played(&mut self, id: &str, context: &ContextRef, played_ms: u64) -> Result<(), Error> {
        let e = self.entries.get_mut(id).ok_or(Error::Stale)?;
        if &e.context != context
            || e.route != Route::EvaVoice
            || e.interrupted
            || played_ms < e.audibly_played_ms
        {
            return Err(Error::Stale);
        }
        e.audibly_played_ms = played_ms;
        Ok(())
    }
    pub fn interrupt(&mut self, id: &str) -> Result<(), Error> {
        let e = self.entries.get_mut(id).ok_or(Error::Stale)?;
        e.interrupted = true;
        if self.active.as_deref() == Some(id) {
            e.finished = true;
            self.active = None;
        }
        Ok(())
    }
    pub fn account(&mut self, id: &str, model: String, usage: Option<Usage>) -> Result<(), Error> {
        let e = self.entries.get_mut(id).ok_or(Error::Stale)?;
        e.model = Some(model);
        e.usage = usage;
        Ok(())
    }
    #[allow(dead_code)] // Inspector/test accessor; contains no model transcript or credentials.
    pub fn entry(&self, id: &str) -> Option<&Entry> {
        self.entries.get(id)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn c() -> ContextRef {
        ContextRef {
            host_id: "host".into(),
            pane_id: "pane".into(),
            task_id: None,
            project_id: None,
            revision: 1,
        }
    }
    #[test]
    fn routes_and_heard_are_not_generation() {
        let mut l = Ledger::default();
        l.begin("t", c(), Route::TextResponses).unwrap();
        assert_eq!(l.begin("t", c(), Route::EvaVoice), Err(Error::Duplicate));
        l.finish("t", true).unwrap();
        assert_eq!(l.entry("t").unwrap().audibly_played_ms, 0);
        assert!(l.played("t", &c(), 1).is_err());
        l.displayed("t", &c()).unwrap();
        l.begin("v", c(), Route::EvaVoice).unwrap();
        l.played("v", &c(), 43).unwrap();
        l.interrupt("v").unwrap();
        assert!(l.played("v", &c(), 80).is_err());
        assert_eq!(l.entry("v").unwrap().audibly_played_ms, 43);
    }
    #[test]
    fn stale_context_not_displayed() {
        let mut l = Ledger::default();
        l.begin("t", c(), Route::TextResponses).unwrap();
        l.finish("t", true).unwrap();
        let mut other = c();
        other.project_id = Some("other".into());
        assert!(l.displayed("t", &other).is_err());
    }
}

//! Receipt facts are indexed by task, while attention follows the exact current
//! context. A late receipt does not change the active pane's task or revision.
use companion_protocol::{ContextRef, TaskStatus};
use std::collections::HashMap;

const MAX_TASKS: usize = 4096;

#[derive(Debug, PartialEq, Eq)]
pub struct Fact {
    pub revision: u64,
    pub status: TaskStatus,
}

#[derive(Default)]
pub struct TaskFacts {
    facts: HashMap<String, Fact>,
}

impl TaskFacts {
    pub fn observe(
        &mut self,
        task: String,
        revision: u64,
        status: TaskStatus,
    ) -> Result<bool, &'static str> {
        if let Some(old) = self.facts.get(&task) {
            if revision < old.revision {
                return Err("stale_task");
            }
            if revision == old.revision && status == old.status {
                return Ok(false);
            }
        } else if self.facts.len() >= MAX_TASKS {
            return Err("task_fact_limit");
        }
        self.facts.insert(task, Fact { revision, status });
        Ok(true)
    }

    pub fn current(&self, context: Option<&ContextRef>) -> Option<(&str, &Fact)> {
        let task = context?.task_id.as_ref()?;
        self.facts
            .get_key_value(task)
            .map(|(id, fact)| (id.as_str(), fact))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn context(task: Option<&str>) -> ContextRef {
        ContextRef {
            host_id: "host".into(),
            pane_id: "pane".into(),
            task_id: task.map(str::to_owned),
            project_id: None,
            revision: 1,
        }
    }

    #[test]
    fn late_background_receipt_never_changes_current_task() {
        let mut facts = TaskFacts::default();
        facts.observe("a".into(), 10, TaskStatus::Failed).unwrap();
        assert!(facts.current(Some(&context(Some("b")))).is_none());
        facts.observe("b".into(), 20, TaskStatus::Running).unwrap();
        facts.observe("a".into(), 11, TaskStatus::Failed).unwrap();
        let (task, fact) = facts.current(Some(&context(Some("b")))).unwrap();
        assert_eq!((task, fact.status), ("b", TaskStatus::Running));
        assert!(facts.current(None).is_none());
        assert!(facts.current(Some(&context(None))).is_none());
    }

    #[test]
    fn revision_high_water_survives_other_task_observations() {
        let mut facts = TaskFacts::default();
        assert!(facts.observe("a".into(), 10, TaskStatus::Running).unwrap());
        facts.observe("b".into(), 20, TaskStatus::Failed).unwrap();
        assert_eq!(
            facts.observe("a".into(), 9, TaskStatus::Succeeded),
            Err("stale_task")
        );
        assert!(!facts.observe("a".into(), 10, TaskStatus::Running).unwrap());
        assert_eq!(
            facts.current(Some(&context(Some("a")))).unwrap().1.status,
            TaskStatus::Running
        );
    }

    #[test]
    fn capacity_rejects_new_facts_without_losing_existing_receipts() {
        let mut facts = TaskFacts::default();
        for i in 0..MAX_TASKS {
            facts
                .observe(i.to_string(), 1, TaskStatus::Running)
                .unwrap();
        }
        assert_eq!(
            facts.observe("overflow".into(), 1, TaskStatus::Running),
            Err("task_fact_limit")
        );
        assert!(facts.observe("0".into(), 2, TaskStatus::Failed).unwrap());
        assert_eq!(
            facts.current(Some(&context(Some("0")))).unwrap().1.status,
            TaskStatus::Failed
        );
    }
}

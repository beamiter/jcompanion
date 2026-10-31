//! Runs an exact copy of the production Eva observation worker.
//! PlaybackHistory is metadata supplied by a fixture, not audio-device proof.
#![allow(dead_code)]
use serde_json::{Value, json};
use std::io::{BufRead, Write};
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};

mod audio {
    use super::*;
    #[derive(Clone)]
    pub struct PlaybackHistory(pub Arc<Mutex<(u64, Option<u64>, bool, Option<u64>)>>);
    impl PlaybackHistory {
        pub(crate) fn companion_snapshot(&self) -> Option<(u64, Option<u64>, bool, Option<u64>)> {
            self.0.try_lock().ok().map(|v| (v.0, v.1, v.2, v.3.or_else(companion_voice::boottime_ns)))
        }
    }
}

#[path = "production_companion.rs"]
mod companion;

fn answer(value: Value) {
    println!("{value}");
    std::io::stdout().flush().unwrap();
}

fn main() {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_time()
        .build()
        .unwrap();
    companion::start();
    let mut lease = None;
    let mut playback: Option<audio::PlaybackHistory> = None;
    let capture_stop = Arc::new(AtomicBool::new(true));
    let mut capture_thread: Option<std::thread::JoinHandle<()>> = None;
    answer(json!({"ready":true,"pid":std::process::id(),"audio_device":false}));
    for line in std::io::stdin().lock().lines() {
        let request: Value = serde_json::from_str(&line.unwrap()).unwrap();
        let result = match request["command"].as_str().unwrap() {
            "acquire" => {
                assert!(lease.is_none());
                match runtime.block_on(companion::acquire(request["generation"].as_u64().unwrap())) {
                    Ok(acquired) => {
                        let id = acquired.session_id().map(str::to_owned);
                        lease = Some(acquired);
                        json!({"acquired":true,"session_id":id})
                    }
                    Err(error) => json!({"acquired":false,"error":error.to_string()}),
                }
            }
            "context" => {
                let id = lease.as_ref().unwrap().session_id().unwrap();
                match runtime.block_on(companion::context(id)) {
                    Ok(value) => json!({"context":value}),
                    Err(error) => json!({"error":error.to_string()}),
                }
            }
            "release" => {
                drop(lease.take());
                json!({"release_queued":true})
            }
            "milestone" => {
                companion::milestone(request["stage"].as_str().unwrap(), &request["labels"]);
                json!({"event_queued":true})
            }
            "dialogue" => {
                companion::dialogue(
                    request["session_id"].as_str().unwrap(),
                    &request["labels"],
                    serde_json::from_value(request["event"].clone()).unwrap(),
                );
                json!({"reference_queued":true})
            }
            "capture" => {
                if request["active"].as_bool().unwrap() {
                    if capture_thread.is_none() {
                        capture_stop.store(false, Ordering::Release);
                        let stop = capture_stop.clone();
                        capture_thread = Some(std::thread::spawn(move || {
                            while !stop.load(Ordering::Acquire) {
                                companion::capture_frame(std::time::Instant::now(), true);
                                std::thread::sleep(std::time::Duration::from_millis(20));
                            }
                        }));
                    }
                } else {
                    capture_stop.store(true, Ordering::Release);
                    if let Some(thread) = capture_thread.take() { thread.join().unwrap(); }
                    companion::capture_stopped();
                }
                json!({"capture_metadata_updated":true})
            }
            "playback" => {
                let history = audio::PlaybackHistory(Arc::new(Mutex::new((
                    request["generated"].as_u64().unwrap(),
                    request["played"].as_u64(),
                    request["drained"].as_bool().unwrap(),
                    request["observed_at_ns"].as_u64(),
                ))));
                companion::playback(&request["labels"], history.clone());
                playback = Some(history);
                json!({"fixture_metadata_queued":true})
            }
            "progress" => {
                *playback.as_ref().unwrap().0.lock().unwrap() = (
                    request["generated"].as_u64().unwrap(),
                    request["played"].as_u64(),
                    request["drained"].as_bool().unwrap(),
                    request["observed_at_ns"].as_u64(),
                );
                json!({"fixture_metadata_updated":true})
            }
            "end_playback" => {
                companion::playback_ended(
                    &request["labels"],
                    request["generated"].as_u64().unwrap(),
                    request["played"].as_u64(),
                    !request["interrupted"].as_bool().unwrap(),
                );
                json!({"event_queued":true})
            }
            "exit" => break,
            other => panic!("unknown command {other}"),
        };
        answer(result);
    }
    capture_stop.store(true, Ordering::Release);
    if let Some(thread) = capture_thread.take() { thread.join().unwrap(); }
}

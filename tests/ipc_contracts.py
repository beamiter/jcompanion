#!/usr/bin/env python3
"""Real daemon IPC contracts. No native pixels, audio devices or provider calls."""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest

SESSION = "eva-fault-test"
MAX_FRAME = 65536
BINARY = None


class PeerRejected(RuntimeError):
    pass


class Peer:
    def __init__(self, path, name, eva=False, clocked=False, retirement="native_presented", dialogue=False):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(3)
        self.socket.connect(str(path))
        self.name, self.boot, self.seq = name, "", 0
        self.clocked = clocked or dialogue
        self.pending = deque()
        hello = {"type": "eva_hello_dialogue", "clock": "linux_boottime_ns_v1", "dialogue_version": 2} if dialogue else {"type": "eva_hello_clocked", "clock": "linux_boottime_ns_v1"} if clocked else {"type": "eva_hello"} if eva else {
            "type": "hello", "host": {
                "id": name, "incarnation": 1, "surface_id": "test-surface",
                "retirement": retirement,
            },
        }
        try:
            self.send(hello)
            accepted = self.until("eva_clocked" if self.clocked else "accepted")
            self.boot = accepted["boot_id"]
            if dialogue:
                assert accepted["dialogue_version"] == 2
        except Exception:
            self.socket.close()
            raise

    def close(self):
        self.socket.close()

    def send(self, body):
        if self.clocked and body.get("type") == "audio":
            body = dict(body, type="audio_clocked", observed_at_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME))
        self.seq += 1
        envelope = {
            "protocol_version": 1, "event_id": f"{self.name}-{self.seq}",
            "source_id": self.name, "source_seq": self.seq, "boot_id": self.boot,
            "session_id": SESSION, "body": body,
        }
        raw = json.dumps(envelope).encode()
        self.socket.sendall(struct.pack(">I", len(raw)) + raw)

    def read(self, deadline):
        def exact(size):
            data = bytearray()
            while len(data) < size:
                self.socket.settimeout(max(0.001, deadline - time.monotonic()))
                chunk = self.socket.recv(size - len(data))
                if not chunk:
                    raise EOFError("daemon closed peer")
                data.extend(chunk)
            return bytes(data)
        size = struct.unpack(">I", exact(4))[0]
        if not 0 < size <= MAX_FRAME:
            raise AssertionError(f"invalid reply length {size}")
        return json.loads(exact(size))

    def until(self, kind, predicate=lambda _: True, timeout=3):
        for reply in list(self.pending):
            if reply["type"] == kind and predicate(reply):
                self.pending.remove(reply)
                return reply
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            reply = self.read(deadline)
            if kind in ("accepted", "eva_clocked") and reply["type"] == "rejected":
                raise PeerRejected(reply["reason"])
            if reply["type"] == kind and predicate(reply):
                return reply
            self.pending.append(reply)
        raise AssertionError(f"missing {kind}")

    def context(self, task=None, project=None, revision=1, pane="pane-a"):
        context = {
            "host_id": self.name, "pane_id": pane, "task_id": task,
            "project_id": project, "revision": revision,
        }
        self.send({"type": "context_observed", "context": context})
        return context

    def geometry(self, revision=1, safe=True):
        rect = dict(x=0.0, y=0.0, width=500.0, height=500.0)
        self.send(dict(type="geometry", revision=revision, viewport=rect,
                       candidates=[rect] if safe else [], exclusions=[]))

    def acquire(self):
        self.geometry()
        self.send({"type": "recall"})
        prepare = self.until("prepare")
        self.send(dict(type="prepared", epoch=prepare["epoch"]))
        return self.until("grant")["token"]

    def task(self, task, revision, status):
        self.send(dict(type="task_observation", task_id=task,
                       context_revision=revision, status=status))

    def pose(self, expected):
        return self.until("snapshot", lambda r: r["pose"] == expected)

    def reply_pose(self):
        # Ignore asynchronous old snapshots; Resync's response follows all
        # earlier operations on this ordered connection.
        self.pending.clear()
        self.send({"type": "resync"})
        deadline = time.monotonic() + 0.3
        latest = None
        while time.monotonic() < deadline:
            try:
                reply = self.read(deadline)
            except socket.timeout:
                break
            if reply["type"] == "snapshot":
                latest = reply["pose"]
        if latest is None:
            raise AssertionError("missing resync snapshot")
        return latest


class DaemonContracts(unittest.TestCase):
    def dialogue_history(self, count):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            path = self.profile / "dialogue-events.json"
            if path.exists():
                data = json.loads(path.read_text())
                if data["turns"] and len(data["turns"][0]["events"]) == count:
                    return data
            time.sleep(.01)
        self.fail("voice dialogue history did not reach expected event count")

    def test_voice_dialogue_result_settles_original_turn_without_restoring_audio(self):
        voice = Peer(self.path, "dialogue-voice", dialogue=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_acquire", session_id="activation-one"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="audio", turn_id="turn-one", state="thinking",
                        generated_samples=0, played_samples=None, interrupted=False))
        def emit(event, activation="activation-one", turn="turn-one"):
            voice.send(dict(type="voice_dialogue", voice_session_id=activation, turn_id=turn,
                            observed_at_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME), event=event))
        emit(dict(kind="input_committed", item_id="input-one"))
        emit(dict(kind="response_completed", response_id="response-one", phase="plan", status="completed"))
        emit(dict(kind="tool_call", response_id="response-one", call_id="call-one",
                  tool="eva_submit_plan", arguments_digest="a" * 64))
        result = dict(kind="tool_result", call_id="call-one", result_digest="b" * 64,
                      outcome="unknown", operations=[dict(operation_id="operation-one", outcome="unknown")])
        emit(result)
        data = self.dialogue_history(4)
        self.assertEqual(data["turns"][0]["events"][-1]["event"]["outcome"], "unknown")
        voice.send(dict(type="voice_release", session_id="activation-one"))
        voice.until("voice_released")
        voice.send(dict(type="voice_acquire", session_id="activation-two"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        result = dict(result, outcome="succeeded", operations=[dict(operation_id="operation-one", outcome="succeeded")])
        emit(result, activation="activation-two")
        self.assertEqual(voice.until("operation_error")["reason"], "voice_dialogue_activation_or_finished")
        emit(result)
        data = self.dialogue_history(5)
        self.assertEqual(data["turns"][0]["voice_session_id"], "activation-one")
        self.assertEqual(data["turns"][0]["events"][-1]["event"]["outcome"], "succeeded")
        self.assertTrue(self.history()["turns"][0]["entry"]["finished"])
        self.assertEqual(self.history()["turns"][0]["entry"]["end"], "resources_released")
        voice.send(dict(type="voice_release", session_id="activation-two"))
        voice.until("voice_released")
        before = (self.profile / "dialogue-events.json").read_bytes()
        self.stop(); voice.close(); self.start()
        self.assertEqual((self.profile / "dialogue-events.json").read_bytes(), before)
        for forbidden in ("transcript", "arguments\"", "pcm", "api_key"):
            self.assertNotIn(forbidden, before.decode())

    def test_voice_dialogue_extension_is_not_implied_by_clock_support(self):
        voice = Peer(self.path, "clock-only", clocked=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_dialogue", voice_session_id="activation", turn_id="turn",
                        observed_at_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                        event=dict(kind="input_committed", item_id="input")))
        self.assertEqual(voice.until("operation_error")["reason"], "voice_dialogue_not_negotiated_or_old_connection")
        self.assertFalse((self.profile / "dialogue-events.json").exists())

    def test_late_operation_receipt_keeps_its_registration_after_voice_end(self):
        voice=Peer(self.path,"operation-voice",dialogue=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_acquire",session_id="activation"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="audio",turn_id="turn",state="thinking",generated_samples=0,played_samples=None,interrupted=False))
        def emit(event):
            voice.send(dict(type="voice_dialogue",voice_session_id="activation",turn_id="turn",
                            observed_at_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),event=event))
        for event in [dict(kind="input_committed",item_id="input"),
                      dict(kind="response_completed",response_id="response",phase="plan",status="completed"),
                      dict(kind="tool_call",response_id="response",call_id="call",tool="eva_submit_plan",arguments_digest="a"*64),
                      dict(kind="operation_registered",call_id="call",operation_id="operation",plan_hash="b"*64,wm_instance_id="wm",request_digest="c"*64),
                      dict(kind="operation_settled",operation_id="operation",request_digest="c"*64,result_digest="d"*64,outcome="unknown")]:
            emit(event)
        self.dialogue_history(5)
        voice.send(dict(type="voice_release",session_id="activation"));voice.until("voice_released")
        emit(dict(kind="operation_settled",operation_id="operation",request_digest="f"*64,result_digest="e"*64,outcome="succeeded"))
        self.assertEqual(voice.until("operation_error")["reason"],"voice_dialogue_order_or_reference")
        emit(dict(kind="operation_settled",operation_id="operation",request_digest="c"*64,result_digest="e"*64,outcome="succeeded"))
        data=self.dialogue_history(6)
        self.assertEqual(data["schema"],2)
        self.assertEqual(data["turns"][0]["events"][-1]["event"]["outcome"],"succeeded")
        emit(dict(kind="operation_settled",operation_id="operation",request_digest="c"*64,result_digest="f"*64,outcome="failed"))
        self.assertEqual(voice.until("operation_error")["reason"],"voice_dialogue_order_or_reference")
        self.assertEqual(len(self.dialogue_history(6)["turns"][0]["events"]),6)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="eva-ipc-contract-")
        self.root = Path(self.temp.name)
        self.profile, self.path = self.root / "profile", self.root / "eva.sock"
        self.peers, self.process = [], None
        self.log = open(self.root / "daemon.log", "wb")
        # No ambient credentials, provider config, compositor policy or desktop
        # observer can enable devices/network in these fresh offline profiles.
        self.env = {k: v for k, v in os.environ.items() if not (
            k.startswith("EVA_COMPANION_") or k in (
                "SSH_CONNECTION", "SSH_TTY", "OPENAI_API_KEY"))}
        self.env.update(XDG_SESSION_ID=SESSION, EVA_COMPANION_SOCKET=str(self.path))
        self.addCleanup(self.cleanup)
        self.start()

    def start(self):
        self.process = subprocess.Popen([str(BINARY), str(self.profile)],
                                        env=self.env, stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail("daemon failed: " + (self.root / "daemon.log").read_text())
            if self.path.exists():
                probe = socket.socket(socket.AF_UNIX)
                try:
                    probe.connect(str(self.path))
                    return
                except OSError:
                    pass
                finally:
                    probe.close()
            time.sleep(0.01)
        self.fail("daemon startup deadline")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(3)

    def cleanup(self):
        for peer in self.peers:
            peer.close()
        self.stop()
        self.log.close()
        self.temp.cleanup()

    def peer(self, name, eva=False):
        peer = Peer(self.path, name, eva)
        self.peers.append(peer)
        return peer

    def memory_list(self, peer, context, scope):
        peer.send(dict(type="memory_list", context=context, scope=scope,
                       query="", before_id=None))
        return peer.until("memory_list")

    def propose(self, peer, context, change):
        peer.send(dict(type="memory_propose", context=context, change=change))
        return peer.until("memory_review")["review"]

    def approve(self, peer, context, review):
        peer.send(dict(type="memory_approve", context=context,
                       review_id=review["id"], digest=review["digest"]))
        return peer.until("memory_result")["status"]

    def history(self, predicate=lambda _: True):
        deadline = time.monotonic() + 3
        path = self.profile / "dialogue-index.json"
        while time.monotonic() < deadline:
            if path.exists():
                data = json.loads(path.read_text())
                if predicate(data):
                    return data
            time.sleep(.01)
        self.fail("durable dialogue observation deadline")

    def test_dialogue_metadata_survives_restart_without_transcript_or_replay(self):
        peer = Peer(self.path, "history", retirement="none")
        self.peers.append(peer)
        context = peer.context("build", "project")
        secret = "private-user-dialogue-not-for-storage"
        peer.send(dict(type="dialogue_start", turn_id="turn", context=context,
                       text=secret, approved_selection=None))
        self.assertEqual(peer.until("dialogue")["status"], "offline")
        data = self.history()
        record = data["turns"][0]
        self.assertTrue(record["entry"]["generated"])
        self.assertFalse(record["entry"]["displayed"])
        self.assertIsNone(record["entry"]["audio"])
        self.assertEqual(record["entry"]["publisher"]["source_id"], "history")
        peer.send(dict(type="dialogue_displayed", turn_id="turn"))
        data = self.history(lambda d: d["turns"][0]["entry"]["displayed"])
        self.assertNotIn(secret, (self.profile / "dialogue-index.json").read_text())
        old_boot = data["turns"][0]["boot_id"]
        peer.close()
        self.stop()
        self.start()
        peer = Peer(self.path, "history", retirement="none")
        self.peers.append(peer)
        context = peer.context("build", "project")
        peer.send(dict(type="dialogue_start", turn_id="turn", context=context,
                       text="fresh explicit request", approved_selection=None))
        self.assertEqual(peer.until("dialogue")["status"], "offline")
        data = self.history(lambda d: len(d["turns"]) == 2)
        self.assertEqual(data["turns"][0]["boot_id"], old_boot)
        self.assertNotEqual(data["turns"][1]["boot_id"], old_boot)
        self.assertFalse(data["turns"][1]["entry"]["displayed"])

    def test_voice_restart_retains_real_lease_but_history_restores_no_live_pose(self):
        voice = Peer(self.path, "history-voice", clocked=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_acquire", session_id="activation"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="audio", turn_id="voice-turn", state="speaking",
                        generated_samples=1000, played_samples=100, interrupted=False))
        data = self.history(lambda d: len(d["turns"]) == 1)
        self.assertFalse(data["turns"][0]["entry"]["finished"])
        self.stop()
        voice.close()
        self.start()
        data = self.history(lambda d: d["turns"][0]["recovered_after_restart"])
        entry = data["turns"][0]["entry"]
        self.assertEqual(entry["end"], "restarted_unknown")
        self.assertEqual(entry["audio"]["confirmed_played_samples"], 100)
        self.assertIsNone(entry["audio"]["state"])
        host = Peer(self.path, "after-restart", retirement="none")
        self.peers.append(host)
        context = host.context()
        host.send(dict(type="dialogue_start", turn_id="blocked", context=context,
                       text="must not take active voice route", approved_selection=None))
        self.assertEqual(host.until("dialogue")["status"], "eva_voice_route_active_or_recovery_blocked")
        voice = Peer(self.path, "history-voice", clocked=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_acquire", session_id="activation"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="voice_release", session_id="activation"))
        self.assertEqual(voice.until("voice_released")["session_id"], "activation")
        self.assertEqual(len(self.history()["turns"]), 1,
                         "historical release must not create a current playback turn")

    def test_corrupt_dialogue_index_preserves_terminal_service_without_reset(self):
        self.stop()
        path = self.profile / "dialogue-index.json"
        path.write_text('{"schema":999}')
        path.chmod(0o600)
        self.start()
        peer = self.peer("history-failure")
        context = peer.context()
        peer.send(dict(type="dialogue_start", turn_id="denied", context=context,
                       text="do not discard corrupt history", approved_selection=None))
        self.assertEqual(peer.until("dialogue")["status"], "dialogue_LocalHistoryUnavailable")
        peer.send(dict(type="resync"))
        peer.until("snapshot")
        self.assertIsNone(self.process.poll())
        self.assertEqual(path.read_text(), '{"schema":999}')

    def test_task_facts_follow_current_context_and_keep_per_task_revision(self):
        host = self.peer("tasks")
        host.acquire()
        host.context("build-a", "project-a")
        host.task("build-a", 10, "failed")
        host.pose("guard_failure")
        host.context("build-b", "project-b", 2, "pane-b")
        self.assertNotEqual(host.reply_pose(), "guard_failure",
                            "A's failure must not become B's current work fact")
        host.task("build-b", 20, "running")
        host.pose("look_at")
        host.task("build-a", 11, "failed")
        self.assertEqual(host.reply_pose(), "look_at",
                         "a background A receipt must not replace B's running fact")
        host.task("build-b", 19, "succeeded")
        self.assertEqual(host.until("operation_error")["reason"], "stale_task")
        host.context("build-a", "project-a", 3)
        host.pose("guard_failure")
        host.context(None, None, 4)
        self.assertNotEqual(host.reply_pose(), "guard_failure")
        history = self.history(lambda d: len(d["results"]) == 2)
        a = next(r for r in history["results"] if r["task_id"] == "build-a")
        self.assertEqual((a["project_id"], a["revision"], a["status"]),
                         ("project-a", 11, "failed"))

    def test_delayed_presented_preserves_preparing_and_exact_retirement(self):
        old = self.peer("old-body")
        token = old.acquire()
        target = self.peer("new-target")
        target.geometry()
        target.send(dict(type="recall"))
        prepare = target.until("prepare")
        old.send(dict(type="presented", token=token))
        self.assertEqual(old.until("operation_error")["reason"], "stale_presented")
        self.assertIsNone(self.process.poll(), "late Presented must not terminate the daemon")
        journal = json.loads((self.profile/"residence.json").read_text())
        self.assertEqual(journal["phase"], "preparing")
        self.assertEqual(journal["possible_body"], token)
        self.assertEqual(journal["target"]["id"], target.name)
        target.send(dict(type="prepared", epoch=prepare["epoch"]))
        self.assertEqual(old.until("revoke")["token"], token)
        # This fixture tests protocol ordering only, not native pixel removal.
        old.send(dict(type="retired", token=token, presentation_serial=1))
        self.assertEqual(old.until("retirement_accepted")["token"], token)
        replacement = target.until("grant")["token"]
        self.assertGreater(replacement["epoch"], token["epoch"])
        target.send(dict(type="presented", token=replacement))
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            journal = json.loads((self.profile/"residence.json").read_text())
            if journal["phase"] == "active":
                break
            time.sleep(.01)
        self.assertEqual(journal["phase"], "active")
        self.assertEqual(journal["possible_body"], replacement)
        self.assertIsNone(journal["target"])

    def preparation_geometry_retry(self, with_old_owner):
        owner = self.peer("prior-owner") if with_old_owner else None
        old_token = owner.acquire() if owner else None
        target = self.peer("geometry-target")
        target.geometry()
        target.send(dict(type="recall"))
        prepare = target.until("prepare")
        # Reproduce the native metadata/control race in a deterministic order.
        target.geometry(revision=2, safe=False)
        target.send(dict(type="prepared", epoch=prepare["epoch"]))
        self.assertEqual(target.until("operation_error")["reason"], "safe_geometry_required")
        state = json.loads((self.profile/"residence.json").read_text())
        self.assertEqual(state["phase"], "preparing")
        self.assertEqual(state["possible_body"], old_token)
        self.assertFalse(state["revoke_intent"], "unsafe target must not revoke an old body")
        target.geometry(revision=3, safe=True)
        retry = target.until("prepare")
        self.assertEqual(retry["epoch"], prepare["epoch"])
        target.send(dict(type="prepared", epoch=retry["epoch"]-1))
        self.assertEqual(target.until("operation_error")["reason"], "stale_prepare")
        target.send(dict(type="prepared", epoch=retry["epoch"]))
        if owner:
            self.assertEqual(owner.until("revoke")["token"], old_token)
            state = json.loads((self.profile/"residence.json").read_text())
            self.assertEqual(state["phase"], "awaiting_removal_proof")
            self.assertEqual(state["possible_body"], old_token)
            # Protocol fixture only; this is not native pixel removal evidence.
            owner.send(dict(type="retired", token=old_token, presentation_serial=1))
            owner.until("retirement_accepted")
        token = target.until("grant")["token"]
        self.assertEqual(token["host_id"], target.name)
        self.assertEqual(token["epoch"], retry["epoch"])
        self.assertIsNone(self.process.poll())

    def test_preparation_retries_after_safe_geometry_returns_without_old_owner(self):
        self.preparation_geometry_retry(False)

    def test_preparation_retries_without_releasing_old_owner_early(self):
        self.preparation_geometry_retry(True)

    def test_selection_requires_exact_one_use_consent_and_current_context(self):
        host = self.peer("selection")
        context = host.context()
        host.send(dict(type="context_access_requested", context=context,
                       text="synthetic selected error", source_event_id="selection-1",
                       captured_at_ms=int(time.time() * 1000)))
        evidence = host.until("context_access_review")["evidence"]
        def dialogue(turn, selection, ctx=context):
            host.send(dict(type="dialogue_start", turn_id=turn, context=ctx,
                           text="Explain the reviewed selection", approved_selection=selection))
            return host.until("dialogue")["status"]
        self.assertEqual(dialogue("unapproved", evidence), "selection_review_required")
        host.send(dict(type="context_access_granted", context=context,
                       consent_id=evidence["consent_id"]))
        host.until("ack")
        altered = {**evidence, "text": "different unreviewed text"}
        self.assertEqual(dialogue("altered", altered), "selection_review_required")
        self.assertEqual(dialogue("approved", evidence), "offline")
        self.assertEqual(dialogue("reused", evidence), "selection_review_required")
        host.context(revision=2, pane="pane-b")
        self.assertEqual(dialogue("late-origin", None), "stale_context")

    def test_memory_reviews_scope_isolation_archive_and_durable_delete(self):
        host = self.peer("memory")
        context = host.context("task-a", "project-a")
        scope = dict(kind="task", id="task-a")
        change = dict(operation="put", scope=scope, key="preference",
                      value="synthetic consented memory", source_event_id="explicit-1",
                      expected_revision=None, expires_at=None)
        review = self.propose(host, context, change)
        self.assertEqual(self.memory_list(host, context, scope)["entries"], [])
        self.assertEqual(self.approve(host, context, {**review, "digest": "0" * 64}),
                         "memory_stale_review")
        self.assertEqual(self.approve(host, context, review), "committed")
        entry = self.memory_list(host, context, scope)["entries"][0]
        other = host.context("task-b", "project-b", 2, "pane-b")
        host.send(dict(type="memory_list", context=other, scope=scope, query="", before_id=None))
        self.assertEqual(host.until("memory_result")["status"], "memory_scope_denied")
        host.send(dict(type="memory_scope_review_requested", context=other, scope=scope))
        access = host.until("memory_scope_review")
        host.send(dict(type="memory_scope_approve", context=other,
                       review_id=access["review_id"], digest=access["digest"]))
        self.assertEqual(host.until("memory_result")["status"],
                         "management_scope_granted_not_model_access")
        self.assertEqual(self.memory_list(host, other, scope)["entries"][0]["id"], entry["id"])
        host.send(dict(type="memory_use", context=other, scopes=[scope]))
        self.assertEqual(host.until("memory_result")["status"], "scope_or_context_denied")
        deletion = self.propose(host, other, dict(operation="delete", id=entry["id"],
                                                 expected_revision=entry["revision"]))
        self.assertEqual(self.approve(host, other, deletion), "committed")
        host.close()
        self.stop()
        self.start()
        reopened = self.peer("memory")
        original = reopened.context("task-a", "project-a")
        self.assertEqual(self.memory_list(reopened, original, scope)["entries"], [])

    def test_voice_terminal_frames_also_require_the_current_lease(self):
        voice = self.peer("voice-without-lease", eva=True)
        for state in ["idle", "stopped", "error", "speaking"]:
            voice.send(dict(type="audio", turn_id="unowned", state=state,
                            generated_samples=100, played_samples=20, interrupted=False))
            self.assertEqual(voice.until("operation_error")["reason"], "voice_permit_required")

    def test_legacy_voice_cannot_claim_clocked_audio(self):
        voice = self.peer("legacy-voice", eva=True)
        voice.send(dict(type="voice_acquire", session_id="legacy-activation"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="audio", turn_id="t", state="listening",
                        generated_samples=0, played_samples=None, interrupted=False))
        self.assertEqual(voice.until("operation_error")["reason"], "timestamped_audio_required")
        voice.send(dict(type="voice_release", session_id="legacy-activation"))
        voice.until("voice_released")

    def test_clocked_voice_rejects_delayed_and_future_observations(self):
        voice = Peer(self.path, "clocked-voice", eva=True, clocked=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_acquire", session_id="activation"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        stamp = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        time.sleep(.3)
        for value in [stamp, time.clock_gettime_ns(time.CLOCK_BOOTTIME) + 1_000_000_000]:
            voice.send(dict(type="audio_clocked", turn_id="stale", state="speaking",
                            generated_samples=1000, played_samples=100, interrupted=False,
                            observed_at_ns=value))
            self.assertEqual(voice.until("operation_error")["reason"], "audio_observation_stale_or_future")
        voice.send(dict(type="audio", turn_id="current", state="listening",
                        generated_samples=0, played_samples=None, interrupted=False))
        voice.send(dict(type="voice_context", session_id="activation", include_global_memory=False))
        self.assertEqual(voice.until("voice_context")["session_id"], "activation")
        voice.send(dict(type="voice_release", session_id="activation"))
        voice.until("voice_released")

    def test_voice_turn_cannot_be_rebound_to_a_later_activation(self):
        voice = Peer(self.path, "voice-owner", eva=True, clocked=True)
        self.peers.append(voice)
        voice.send(dict(type="voice_acquire", session_id="activation-one"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="audio", turn_id="old-turn", state="speaking",
                        generated_samples=100, played_samples=20, interrupted=False))
        voice.send(dict(type="voice_context", session_id="activation-one", include_global_memory=False))
        voice.until("voice_context")
        voice.send(dict(type="voice_release", session_id="activation-one"))
        voice.until("voice_released")
        voice.send(dict(type="voice_acquire", session_id="activation-two"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        voice.send(dict(type="audio", turn_id="old-turn", state="speaking",
                        generated_samples=100, played_samples=30, interrupted=False))
        self.assertEqual(voice.until("operation_error")["reason"], "audio_lease_binding")
        voice.send(dict(type="audio", turn_id="new-turn", state="listening",
                        generated_samples=0, played_samples=None, interrupted=False))
        voice.send(dict(type="voice_release", session_id="activation-one"))
        self.assertEqual(voice.until("operation_error")["reason"], "voice_lease_not_owned")
        voice.send(dict(type="voice_context", session_id="activation-two", include_global_memory=False))
        self.assertEqual(voice.until("voice_context")["session_id"], "activation-two")
        voice.send(dict(type="voice_release", session_id="activation-two"))
        voice.until("voice_released")

    def test_voice_lease_blocks_text_survives_restart_and_needs_exact_owner(self):
        host = self.peer("text")
        context = host.context()
        voice = self.peer("voice-owner", eva=True)
        voice.send(dict(type="voice_acquire", session_id="voice-turn"))
        self.assertTrue(voice.until("voice_permit")["granted"])
        host.send(dict(type="dialogue_start", turn_id="blocked-text", context=context,
                       text="synthetic offline request", approved_selection=None))
        self.assertEqual(host.until("dialogue")["status"],
                         "eva_voice_route_active_or_recovery_blocked")
        self.process.kill()
        self.process.wait(3)
        voice.close()
        host.close()
        self.start()
        wrong = self.peer("different-voice-owner", eva=True)
        wrong.send(dict(type="voice_acquire", session_id="new-voice-turn"))
        self.assertFalse(wrong.until("voice_permit")["granted"])
        wrong.send(dict(type="voice_release", session_id="voice-turn"))
        self.assertEqual(wrong.until("operation_error")["reason"], "voice_lease_not_owned")
        wrong.close()
        deadline = time.monotonic() + 2
        # Await actual acceptance after the old connection is torn down, not an
        # assumed teardown delay or a modification to the durable lease.
        while True:
            try:
                original = self.peer("voice-owner", eva=True)
                break
            except PeerRejected as error:
                if str(error) != "audio_owner_already_bound" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        original.send(dict(type="voice_release", session_id="voice-turn"))
        self.assertEqual(original.until("voice_released")["session_id"], "voice-turn")
        original.send(dict(type="voice_acquire", session_id="next-voice-turn"))
        self.assertTrue(original.until("voice_permit")["granted"])
        original.send(dict(type="voice_release", session_id="next-voice-turn"))
        original.until("voice_released")


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        failed = any(t is test for t, _ in self.failures + self.errors)
        self.records.append(dict(test=test.id(), status="failed" if failed else "passed",
                                 duration_ms=round((time.monotonic() - self.started) * 1000, 2)))
        super().stopTest(test)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    BINARY = args.binary.resolve(strict=True)
    # Kernel peer checks read the process-start environment, not os.environ.
    if f"XDG_SESSION_ID={SESSION}".encode() not in Path("/proc/self/environ").read_bytes().split(b"\0"):
        parser.error(f"launch with XDG_SESSION_ID={SESSION}")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DaemonContracts)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "schema": 1, "scope": __doc__,
            "binary_sha256": hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            "passed": result.wasSuccessful(), "tests": result.records,
        }, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)

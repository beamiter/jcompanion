"""Synthetic relay controls only; these tests supply no native evidence."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from native_retirement_proxy import Frames, Relay


def framed(packet):
    # Keep non-canonical spacing and Unicode to catch JSON re-serialization.
    body = json.dumps(packet, ensure_ascii=False, indent=1).encode()
    return struct.pack('!I', len(body)) + body


class RelayTests(unittest.TestCase):
    def test_fragmented_and_coalesced_frames_keep_original_bytes(self):
        packets = [{'body': {'type': 'retired', 'token': {'epoch': 8}}},
                   {'type': 'snapshot', 'text': '原始字节'}]
        originals = [framed(packet) for packet in packets]
        combined = b''.join(originals)
        for split in range(1, len(combined)):
            parser = Frames()
            actual = parser.feed(combined[:split]) + parser.feed(combined[split:])
            self.assertEqual(actual, list(zip(originals, packets)))
            self.assertFalse(parser.pending)

    def test_invalid_or_incomplete_lengths_are_never_forwardable(self):
        for length in [0, 65537, 0xffffffff]:
            with self.assertRaises(ValueError):
                Frames().feed(struct.pack('!I', length))
        parser = Frames()
        self.assertEqual(parser.feed(struct.pack('!I', 10) + b'{'), [])
        self.assertEqual(bytes(parser.pending), struct.pack('!I', 10) + b'{')

    def test_only_exact_source_ack_is_dropped_and_release_never_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relay = Relay(root, ['source', 'other'], 'source')
            token = {'host_id': 'source', 'epoch': 1, 'boot_id': 'original'}
            changed = dict(token, boot_id='different')

            def classify(label, direction, body):
                packet = {'body': body, 'source_seq': 4} if direction == 'client' else body
                wire = framed(packet)
                drop = relay.classify(label, 1, direction, wire, packet)
                # Classifying an existing frame must not mutate it or its packet.
                self.assertEqual(wire, framed(packet))
                return drop, hashlib.sha256(wire).hexdigest()

            self.assertFalse(classify('source', 'server', {'type': 'retirement_accepted', 'token': token})[0])
            self.assertFalse(classify('source', 'client', {'type': 'retired', 'token': token, 'presentation_serial': 7})[0])
            self.assertFalse(classify('source', 'client', {'type': 'retired', 'token': changed, 'presentation_serial': 8})[0])
            self.assertFalse(classify('other', 'server', {'type': 'retirement_accepted', 'token': token})[0])
            self.assertFalse(classify('source', 'server', {'type': 'retirement_accepted', 'token': changed})[0])
            dropped, wire_hash = classify('source', 'server', {'type': 'retirement_accepted', 'token': token})
            self.assertTrue(dropped)
            before = relay.sequence
            (root / 'release-acks').write_text('future replies only\n')
            self.assertEqual(relay.sequence, before)
            self.assertFalse(classify('source', 'server', {'type': 'retirement_accepted', 'token': token})[0])
            relay.log.close()
            rows = [json.loads(line) for line in (root / 'relay-events.jsonl').read_text().splitlines()]
            self.assertEqual([row['frame_sha256'] for row in rows if row['action'] == 'drop'], [wire_hash])
            self.assertEqual([row['index'] for row in rows], list(range(1, len(rows) + 1)))

    def test_content_is_forwardable_but_not_copied_into_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relay = Relay(root, ['source'], 'source')
            for kind in ['snapshot', 'host_metadata', 'dialogue_request', 'selection']:
                body = {'type': kind, 'private_text': 'DO_NOT_LOG_CONTENT', 'geometry': [1, 2, 3, 4]}
                packet = {'body': body, 'source_seq': 5}
                self.assertFalse(relay.classify('source', 1, 'client', framed(packet), packet))
            relay.log.close()
            text = (root / 'relay-events.jsonl').read_text()
            self.assertNotIn('DO_NOT_LOG_CONTENT', text)
            self.assertNotIn('geometry', text)


if __name__ == '__main__':
    unittest.main()

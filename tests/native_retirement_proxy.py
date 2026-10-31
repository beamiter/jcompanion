#!/usr/bin/env python3
"""Private byte-preserving fault relay for native retirement acceptance.

Forwards original length-prefixed frames. The only suppressed frames are exact
RetirementAccepted replies for the source GUI's first actual Retired request.
It never constructs, changes, duplicates or replays a protocol frame. Control
files can hold source reconnection and release future (never cached) replies.
Only opaque coordination/control metadata and frame hashes are logged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import select
import socket
import struct
import threading
import time


class Frames:
    def __init__(self):
        self.pending = bytearray()

    def feed(self, data):
        self.pending.extend(data)
        frames = []
        while len(self.pending) >= 4:
            length = struct.unpack('!I', self.pending[:4])[0]
            if not 0 < length <= 65536:
                raise ValueError('invalid original frame length')
            if len(self.pending) < length + 4:
                break
            frame = bytes(self.pending[:length + 4])
            del self.pending[:length + 4]
            frames.append((frame, json.loads(frame[4:])))
        return frames


class Relay:
    def __init__(self, root, labels, source):
        self.root, self.labels, self.source = root, labels, source
        self.lock = threading.Lock()
        self.first_token = None
        self.sequence = 0
        self.generation = {label: 0 for label in labels}
        self.log = (root / 'relay-events.jsonl').open('a', buffering=1)
        self.failed = False

    def event(self, **data):
        with self.lock:
            self.sequence += 1
            self.log.write(json.dumps(dict(index=self.sequence, monotonic=time.monotonic(), **data)) + '\n')

    def classify(self, label, generation, direction, frame, packet):
        body = packet['body'] if direction == 'client' else packet
        kind = body.get('type')
        with self.lock:
            if label == self.source and direction == 'client' and kind == 'retired' and self.first_token is None:
                self.first_token = body['token']
            drop = (label == self.source and direction == 'server' and kind == 'retirement_accepted'
                    and body['token'] == self.first_token and not (self.root / 'release-acks').exists())
        # Geometry, selection, dialogue and memory contents are never logged.
        safe = {key: body[key] for key in ['token', 'presentation_serial', 'connection_nonce',
                'boot_id', 'companion_id', 'host_id', 'incarnation', 'surface_id',
                'admission_epoch', 'reason'] if key in body}
        if kind == 'hello_with_features':
            safe['host'] = body['host']
        if kind in ['snapshot', 'host_metadata']:
            safe = {}
        self.event(label=label, connection=generation, direction=direction, kind=kind,
                   action='drop' if drop else 'forward', frame_sha256=hashlib.sha256(frame).hexdigest(),
                   frame_bytes=len(frame), source_seq=packet.get('source_seq') if direction == 'client' else None,
                   **safe)
        return drop

    def connection(self, label, client, generation):
        server = None
        try:
            while True:
                if label == self.source and (self.root / 'hold-source-reconnect').exists():
                    time.sleep(.05)
                    continue
                try:
                    server = socket.socket(socket.AF_UNIX)
                    server.settimeout(2)
                    server.connect(str(self.root / 'eva.sock'))
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    server.close()
                    time.sleep(.05)
            self.event(label=label, connection=generation, kind='connected', action='transport')
            client.settimeout(2)
            parsers = {client: Frames(), server: Frames()}
            while True:
                if label == self.source and (self.root / 'disconnect-source').exists():
                    (self.root / 'disconnect-source').unlink()
                    self.event(label=label, connection=generation, kind='controlled_disconnect', action='transport')
                    return
                readable, _, _ = select.select([client, server], [], [], .05)
                for stream in readable:
                    data = stream.recv(8192)
                    if not data:
                        return
                    direction = 'client' if stream is client else 'server'
                    target = server if stream is client else client
                    for frame, packet in parsers[stream].feed(data):
                        if not self.classify(label, generation, direction, frame, packet):
                            target.sendall(frame)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout) as error:
            self.event(label=label, connection=generation, kind='transport_closed', action='transport', error=type(error).__name__)
        except Exception as error:
            self.failed = True
            self.event(label=label, connection=generation, kind='relay_failure', action='error', error=repr(error))
        finally:
            client.close()
            if server is not None:
                server.close()
            self.event(label=label, connection=generation, kind='disconnected', action='transport')

    def run(self):
        listeners = {}
        for label in self.labels:
            path = self.root / ('relay-' + label + '.sock')
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(str(path))
            path.chmod(0o600)
            listener.listen(4)
            listeners[listener] = label
        (self.root / 'relay-ready').write_text('ready\n')
        while not (self.root / 'stop-relay').exists():
            readable, _, _ = select.select(list(listeners), [], [], .1)
            for listener in readable:
                label = listeners[listener]
                client, _ = listener.accept()
                self.generation[label] += 1
                if self.generation[label] > 32:
                    client.close()
                    raise RuntimeError('unexpected reconnect storm')
                threading.Thread(target=self.connection, args=(label, client, self.generation[label]), daemon=True).start()
        for listener in listeners:
            listener.close()
        return 1 if self.failed else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--label', action='append', required=True)
    args = parser.parse_args()
    if any('/' in label or '..' in label for label in args.label) or args.source not in args.label:
        parser.error('invalid private relay labels')
    raise SystemExit(Relay(args.root, args.label, args.source).run())

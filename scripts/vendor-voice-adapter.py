#!/usr/bin/env python3
"""Vendor the explicit clocked voice extension without changing public Git pins."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('workspace', type=Path)
parser.add_argument('--write', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
target = args.workspace / 'jwm/eva/vendor/companion-voice'
pin = '9aa569540091524d637a7115b64c587b9177a55b'
cargo = '''[package]
name = "companion-voice"
version = "0.1.0"
edition = "2021"
license = "MIT"
publish = false

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
libc = "0.2"
'''
for package in ['companion-client', 'companion-protocol']:
    cargo += f'{package} = {{ git = "https://github.com/beamiter/jcompanion.git", rev = "{pin}" }}\n'
files = {'src/lib.rs': (root/'crates/companion-voice/src/lib.rs').read_bytes(),
         'src/dialogue.rs': (root/'crates/companion-voice/src/dialogue.rs').read_bytes(),
         'LICENSE': (root/'LICENSE').read_bytes(), 'Cargo.toml': cargo.encode()}
manifest = dict(schema=1, feature='linux_boottime_ns_v1', dialogue_version=2, public_companion_base=pin,
                files_sha256={name: hashlib.sha256(value).hexdigest() for name, value in files.items()})
files['bundle.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
different = [name for name, value in files.items()
             if not (target/name).is_file() or (target/name).read_bytes() != value]
if args.write:
    for name in different:
        path = target/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[name])
else:
    assert not different, different
print(json.dumps(dict(files=len(files), changed=different, written=args.write)))

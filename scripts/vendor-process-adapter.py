#!/usr/bin/env python3
"""Freeze the shared PTY observer for GTK frontends, without changing Git pins.

The process modules have one canonical source in companion-host. This small
standalone package does not import the transport, protocol, renderer or daemon.
"""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('workspace', type=Path)
parser.add_argument('--write', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
prefix = 'vendor/companion-process/'
inputs = {
    prefix + 'Cargo.toml': b'''[package]
name = "companion-process"
version = "0.1.0"
edition = "2021"
license = "MIT"
publish = false

[dependencies]
libc = "0.2"

[dev-dependencies]
uuid = { version = "~1.26.0", features = ["v4"] }
''',
    prefix + 'src/lib.rs': b'pub mod pty_session;\npub mod shell_identity;\n',
    prefix + 'LICENSE': (root / 'LICENSE').read_bytes(),
    'tools/check-process-bundle.py': (root / 'scripts/check-process-bundle.py').read_bytes(),
    'src/gtk_process.rs': (root / 'adapters/gtk_process.rs').read_bytes(),
    'src/gtk_spawn.rs': (root / 'adapters/gtk_spawn.rs').read_bytes(),
}
for module in ['pty_session', 'shell_identity']:
    inputs[prefix + f'src/{module}.rs'] = (root / f'crates/companion-host/src/{module}.rs').read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
manifest = dict(schema=1, bundle='pty-process-v1', version='0.1.0',
                public_core_base='974ccad203375032fe87706caecab39ad516c238',
                scope='Local versioned process observer and GTK launch ownership. No protocol or presentation proof; no change to published Git bases.',
                files_sha256={name: digest(data) for name, data in sorted(inputs.items())})
inputs['vendor/process-adapter-bundle.json'] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
for app in ['forge', 'anvil']:
    target = args.workspace / app
    differences = [name for name, data in inputs.items()
                   if not (target / name).is_file() or (target / name).read_bytes() != data]
    if args.write:
        for name in differences:
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(inputs[name])
    else:
        assert not differences, (app, differences)
    print(json.dumps(dict(frontend=app, files=len(inputs), changed=len(differences), written=args.write,
                         bundle_manifest_sha256=digest(inputs['vendor/process-adapter-bundle.json']))))

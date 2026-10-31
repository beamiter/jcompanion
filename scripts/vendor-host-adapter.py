#!/usr/bin/env python3
"""Build/check a versioned in-repository host/protocol/client source bundle.

Public jterm_core/core/atlas Git pins remain fixed. No unversioned sibling
checkout is a frontend build input. This script never fetches or publishes.
"""
import argparse
import hashlib
import json
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('workspace',type=Path)
parser.add_argument('--write',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
# The overlay is versioned independently of its immutable public dependency base.
# Deriving this from HEAD would change dependency pins after committing the overlay.
base='9aa569540091524d637a7115b64c587b9177a55b'
remote='https://github.com/beamiter/jcompanion.git'
def git_dep(name):return f'{name} = {{ version = "0.1.0", git = "{remote}", rev = "{base}" }}\n'
def digest(value):return hashlib.sha256(value).hexdigest()
packages=['companion-host','companion-protocol','companion-client']
inputs={}
for package in packages:
 prefix=f'vendor/{package}/'
 for source in (root/'crates'/package/'src').rglob('*'):
  if source.is_file():inputs[prefix+'src/'+str(source.relative_to(root/'crates'/package/'src'))]=source.read_bytes()
 inputs[prefix+'LICENSE']=(root/'LICENSE').read_bytes()
 cargo=f'[package]\nname = "{package}"\nversion = "0.1.0"\nedition = "2021"\nlicense = "MIT"\npublish = false\n\n[dependencies]\n'
 if package=='companion-protocol':cargo+='serde = { version = "1", features = ["derive"] }\nserde_json = "1"\n'
 elif package=='companion-client':cargo+=git_dep('companion-protocol')+'serde = { version = "1", features = ["derive"] }\nserde_json = "1"\nlibc = "0.2"\n'
 else:
  cargo+=''.join(git_dep(p) for p in ['companion-protocol','companion-client','companion-core','eva-character-atlas'])
  cargo+='uuid = { version = "~1.26.0", features = ["v4"] }\nlibc = "0.2"\n'
 inputs[prefix+'Cargo.toml']=cargo.encode()
 inputs[prefix+'upstream-Cargo.toml']=(root/'crates'/package/'Cargo.toml').read_bytes()
 if (root/'crates'/package/'origin.json').exists():inputs[prefix+'origin.json']=(root/'crates'/package/'origin.json').read_bytes()
inputs['tools/check-host-bundle.py']=(root/'scripts/check-host-bundle.py').read_bytes()
core_base=json.loads((root/'crates/companion-host/origin.json').read_text())['origin_commit']
manifest=dict(schema=1,bundle='withdrawal-resume-v1',version='0.1.0',public_companion_base=base,public_core_base=core_base,
 scope='Exact versioned host/protocol/client source overlay with GTK frame identity and negotiated withdrawal resumption. Public core/atlas/jterm_core pins stay immutable. This is local reviewable source, not a published Git revision or installation.',
 files_sha256={name:digest(data) for name,data in sorted(inputs.items())})
for app in ['ember','frost','forge','anvil']:
 files=dict(inputs)
 if app in ['forge','anvil']:
  files['src/gtk_close.rs']=(root/'adapters/gtk_close.rs').read_bytes()
  files['src/gtk_presentation.rs']=(root/'adapters/gtk_presentation.rs').read_bytes()
  files['src/gtk_clock_fixture.rs']=(root/'adapters/gtk_clock_fixture.rs').read_bytes()
 local_manifest=dict(manifest,files_sha256={name:digest(data) for name,data in sorted(files.items())})
 files['vendor/host-adapter-bundle.json']=(json.dumps(local_manifest,sort_keys=True,indent=2)+'\n').encode()
 target=args.workspace/app
 differences=[name for name,data in files.items() if not (target/name).is_file() or (target/name).read_bytes()!=data]
 if args.write:
  for name in differences:p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(files[name])
 else:
  assert not differences,(app,differences)
 print(json.dumps(dict(frontend=app,files=len(files),changed=len(differences),written=args.write,bundle_manifest_sha256=digest(files['vendor/host-adapter-bundle.json']))))

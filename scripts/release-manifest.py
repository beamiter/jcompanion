#!/usr/bin/env python3
"""Read-only canonical family inventory; emit JSON to stdout outside source trees."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('workspace', type=Path)
args = parser.parse_args()
def git(root, *argv):
    return subprocess.check_output(['git', '-C', str(root), *argv])
def sha(data):
    return hashlib.sha256(data).hexdigest()
result = {'schema': 1, 'protocol_version': 1, 'scope': 'local snapshot, not publication or hardware acceptance', 'repositories': {}}
for name in ['jcompanion', 'jterm_core', 'anvil', 'forge', 'ember', 'frost', 'jwm', 'jagent']:
    root = args.workspace / name
    names = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0')
    files = {}
    for raw in sorted(set(names)):
        if not raw:
            continue
        rel = raw.decode()
        path = root / rel
        if path.is_file() and not path.is_symlink():
            files[rel] = sha(path.read_bytes())
    encoded = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    result['repositories'][name] = {
        'base_commit': git(root, 'rev-parse', 'HEAD').decode().strip(),
        'status': git(root, 'status', '--porcelain=v1', '--untracked-files=all').decode().splitlines(),
        'tracked_diff_sha256': sha(git(root, 'diff', '--binary', 'HEAD', '--')),
        'source_tree_sha256': sha(encoded), 'files_sha256': files,
    }
print(json.dumps(result, sort_keys=True, indent=2))

#!/usr/bin/env python3
"""Pin published family dependencies; never commits, fetches or installs anything."""
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('workspace', type=Path, help='parent of family checkouts')
parser.add_argument('--companion-rev', help='published full 40-character Git commit')
parser.add_argument('--core-rev', help='published full 40-character jterm_core commit')
parser.add_argument('--write', action='store_true', help='otherwise only report changes')
args = parser.parse_args()
for rev in [args.companion_rev, args.core_rev]:
    if rev is not None and not re.fullmatch('[0-9a-f]{40}', rev):
        parser.error('revisions must be full lowercase 40-character commit IDs')
packages = {}
if args.companion_rev:
    for name in ['companion-protocol', 'companion-client', 'companion-core', 'eva-character-atlas']:
        packages[name] = ('jcompanion', args.companion_rev)
if args.core_rev:
    packages['jterm_core'] = ('jterm_core', args.core_rev)
for repo in ['jterm_core', 'anvil', 'forge', 'ember', 'frost', 'jwm']:
    for path in sorted((args.workspace / repo).rglob('Cargo.toml')):
        if any(part in ['target', '.git', 'vendor'] for part in path.parts):
            continue
        original = path.read_text()
        lines = []
        for line in original.splitlines(keepends=True):
            match = re.match(r'([\w-]+)\s*=\s*\{(.*)\}(\s*)$', line)
            if match and match[1] in packages:
                remote, rev = packages[match[1]]
                body = match[2]
                body = re.sub(r'\b(?:path|git|rev|branch|tag)\s*=\s*"[^"]*"\s*,?\s*', '', body)
                body = body.strip().rstrip(',')
                suffix = f'git = "https://github.com/beamiter/{remote}.git", rev = "{rev}"'
                line = f'{match[1]} = {{ {body + ", " if body else ""}{suffix} }}{match[3]}'
            lines.append(line)
        updated = ''.join(lines)
        if updated != original:
            print(path.relative_to(args.workspace))
            if args.write:
                path.write_text(updated)
print('Refresh Cargo.lock with cargo metadata/build, review deny.toml and Nix hashes, and test exact pins before publishing.')

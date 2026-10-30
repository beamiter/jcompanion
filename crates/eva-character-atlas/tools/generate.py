from pathlib import Path
import json
from art import ART
root=Path(__file__).resolve().parents[1]
original=json.loads((root/'design/original-ascii-skins.json').read_text())
q=lambda s:json.dumps(s,ensure_ascii=False)
out='// Generated from tools/art.py: hand-authored implementation-derived artwork.\n'
out+='pub(crate) const ORIGINAL: [&str; 8] = [\n'+',\n'.join(q(x['ascii']) for x in original.values())+'];\n'
out+='pub(crate) const ART: [[&str; 6]; 8] = [\n'
for forms in ART: out+='[\n'+',\n'.join(q(a.strip('\n')) for a in forms)+'\n],\n'
out+='];\n'
(root/'src/art.rs').write_text(out)

"""Renders actual Rust-exported cell buffers, never reference raster artwork."""
from pathlib import Path
import json, html
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
frames=json.loads((ROOT/'qa/frames.json').read_text())
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',15)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',12)
title=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',22)
CW,CH=9,18
W,H=400,464
skins=list(dict.fromkeys(f['skin'] for f in frames))
def card(im,f,x,y):
 d=ImageDraw.Draw(im); d.rounded_rectangle((x+6,y+6,x+W-6,y+H-6),radius=12,fill='#101d27',outline='#2d4351')
 d.text((x+18,y+16),f["pose"],font=title,fill='#e3f3f4')
 for row,line in enumerate(f['lines']):
  for col,c in enumerate(line):
   if c!=' ':d.text((x+18+col*CW,y+42+row*CH),c,font=font,fill=tuple(f['palette'][f['inks'][row][col]]))
 d.text((x+18,y+H-27),f"{f['mode']} / t={f['time_ms']}ms / #{f['frame']} / seed42",font=small,fill='#8fadb9')
for skin in skins:
 chosen=[f for f in frames if f['skin']==skin and f['mode']=='Static']
 im=Image.new('RGB',(W*4,H*4+90),'#081219');d=ImageDraw.Draw(im)
 d.text((22,18),f'EVA / {skin.upper()} / 13 POSES',font=title,fill='#e7f7f5')
 d.text((22,51),'Implementation-derived glyph art / actual Rust cell output / not source animation',font=small,fill='#8fadb9')
 for i,f in enumerate(chosen):card(im,f,i%4*W,i//4*H+90)
 im.save(ROOT/f'qa/{skin}-poses.png')
im=Image.new('RGB',(W*4,H*2+90),'#081219');d=ImageDraw.Draw(im)
d.text((22,18),'EVA COMPANION / THE EIGHT BODIES',font=title,fill='#e7f7f5')
d.text((22,51),'One identity, eight skins. Handcrafted reference-derived ASCII. Rust output, Static, seed42.',font=small,fill='#8fadb9')
for i,skin in enumerate(skins):
 f=next(f for f in frames if f['skin']==skin and f['pose']=='idle' and f['mode']=='Static').copy();f['pose']=skin
 card(im,f,i%4*W,i//4*H+90)
im.save(ROOT/'qa/eight-skins.png')
# Self-contained contact gallery with all modes/frame durations, no external assets.
css='body{background:#081219;color:#e7f7f5;font:15px system-ui;margin:32px}section{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px}article{background:#101d27;padding:20px;border:1px solid #2d4351;border-radius:12px}pre{font:15px/18px monospace;white-space:pre}small{color:#9bb7c4}summary{cursor:pointer}h1{letter-spacing:.12em}'
content=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Eva native glyph atlas QA</title><style>'+css+'</style><h1>EVA / CHARACTER ATLAS</h1><p>Actual Rust-exported glyph cells. Implementation-derived artwork, not original animation frames. Each card is a static QA specimen, never a runtime extra body.</p>']
for skin in skins:
 content.append('<h2>'+skin+'</h2><section>')
 for f in [f for f in frames if f['skin']==skin and f['mode']=='Static']:
  rendered=''
  for y,line in enumerate(f['lines']):
   for x,c in enumerate(line):
    rgb=f['palette'][f['inks'][y][x]];rendered+=f'<span style="color:rgb{tuple(rgb)}">{html.escape(c)}</span>'
   rendered+='\n'
  content.append('<article><h3>'+f['pose']+'</h3><pre role="img" aria-label="'+html.escape(f['label'])+'">'+rendered+'</pre><small>Static / seed 42 / frame '+str(f['frame'])+'</small></article>')
 content.append('</section>')
content.append('<p>Full and Calm per-frame cell data and timestamps: <a href="frames.json">frames.json</a>. Original sketches and provenance are preserved separately in design/.</p></html>')
(ROOT/'qa/gallery.html').write_text(''.join(content))
print(f'Rendered {len(frames)} actual Rust frames; 8 pose sheets and overview.')
# Mood and motion sheets: pure evidence frames from exactly the same Rust API.
moods=json.loads((ROOT/'qa/moods.json').read_text())
for skin in skins:
 selected=[f for f in moods if f['skin']==skin]
 im=Image.new('RGB',(W*3,H*3+90),'#081219');d=ImageDraw.Draw(im)
 d.text((22,18),f'EVA / {skin.upper()} / OPTIONAL MOODS',font=title,fill='#e7f7f5')
 d.text((22,51),'Artistic expressions only; never inferred user emotions or authoritative task states.',font=small,fill='#8fadb9')
 for i,f in enumerate(selected):
  f=f.copy();f['pose']=f['mood'];card(im,f,i%3*W,i//3*H+90)
 im.save(ROOT/f'qa/{skin}-moods.png')
 selected=[f for f in frames if f['skin']==skin and f['mode']=='Full']
 im=Image.new('RGB',(W*5,90+H*((len(selected)+4)//5)),'#081219');d=ImageDraw.Draw(im)
 d.text((22,18),f'EVA / {skin.upper()} / FULL MOTION FRAMES',font=title,fill='#e7f7f5')
 d.text((22,51),'Deterministic action-relative times; independent poses, not a live multi-body scene.',font=small,fill='#8fadb9')
 for i,f in enumerate(selected):card(im,f,i%5*W,i//5*H+90)
 im.resize((1000,im.height//2)).save(ROOT/f'qa/{skin}-motion.png')

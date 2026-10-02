"""Write EditorialSelect Serif's glyph metrics for the runtime's arithmetic text
layout: advance and ink box per character (printable ASCII plus the Latin-1 and
punctuation range up to U+2026), GPOS pair kerning and the vertical metrics, all
in font units of 1000 per em. Run after the font changes, then inject.py.

usage: uv run --project ~/motion-expert/toolkit python metrics.py
"""
import json, os
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, '..', '..', 'assets', 'fonts', 'EditorialSelect-Serif.ttf')

f = TTFont(FONT)
upm = f['head'].unitsPerEm
assert upm == 1000, upm
cmap, hm, gs = f.getBestCmap(), f['hmtx'], f.getGlyphSet()
adv, ink = {}, {}
for cp, gn in sorted(cmap.items()):
    if cp < 32 or cp > 0x2026 or 127 <= cp < 160 and cp != 0xA0:
        continue
    ch = chr(cp)
    adv[ch] = hm[gn][0]
    bp = BoundsPen(gs); gs[gn].draw(bp)
    if bp.bounds and bp.bounds[2]:
        ink[ch] = [round(v) for v in bp.bounds]
rev = {gn: chr(cp) for cp, gn in cmap.items() if chr(cp) in adv}
kern = {}
for lk in f['GPOS'].table.LookupList.Lookup if 'GPOS' in f else []:
    for st in lk.SubTable:
        if getattr(st, 'Format', None) != 1 or not hasattr(st, 'PairSet'):
            continue
        for i, first in enumerate(st.Coverage.glyphs):
            for pv in st.PairSet[i].PairValueRecord:
                v = pv.Value1.XAdvance if pv.Value1 and hasattr(pv.Value1, 'XAdvance') else 0
                a, b = rev.get(first), rev.get(pv.SecondGlyph)
                if a and b and v:
                    kern[a + b] = v
os2, hh = f['OS/2'], f['hhea']
out = {'upm': upm, 'cap': os2.sCapHeight, 'x': os2.sxHeight, 'asc': hh.ascent, 'desc': hh.descent,
       'adv': adv, 'kern': kern, 'ink': ink}
json.dump(out, open(os.path.join(HERE, 'es-serif-metrics.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(len(adv), 'chars', len(ink), 'ink', len(kern), 'kern pairs')

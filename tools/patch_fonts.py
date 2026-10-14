"""One-off build step: graft ASCII punctuation + digits from Noto Sans into the Indic/Arabic Noto fonts
that lack them, so a script word followed by '.' or ',' can be typeset in ONE font (ReportLab cannot
mix fonts inside an unbroken word). Noto fonts are OFL-licensed and have no Reserved Font Name.
Usage (repo root): python tools/patch_fonts.py   (run once; idempotent)"""
import copy, glob, os
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rxora_pdf", "fonts")
CHARS = [chr(c) for c in range(0x21, 0x7F) if not chr(c).isalpha()]   # punctuation + digits

def patch(path, src_path):
    f, s = TTFont(path), TTFont(src_path)
    cmap = f.getBestCmap(); scmap = s.getBestCmap()
    missing = [c for c in CHARS if ord(c) not in cmap and ord(c) in scmap]
    if not missing:
        return 0
    order = f.getGlyphOrder()[:]; glyf, hmtx = f["glyf"], f["hmtx"]
    for ch in missing:
        sname = scmap[ord(ch)]; name = "rx_" + sname
        g = copy.deepcopy(s["glyf"][sname])
        if g.isComposite():
            raise RuntimeError(f"composite glyph {sname}")
        g.program = ttProgram.Program(); g.program.fromBytecode(b"")
        glyf.glyphs[name] = g; order.append(name)
        hmtx.metrics[name] = s["hmtx"].metrics[sname]
        for t in f["cmap"].tables:
            if t.isUnicode():
                t.cmap[ord(ch)] = name
    f.setGlyphOrder(order); glyf.glyphOrder = order
    for t in ("hdmx", "LTSH", "VDMX"):
        if t in f: del f[t]
    f.save(path)
    return len(missing)

for p in sorted(glob.glob(os.path.join(FONTS, "*.ttf"))):
    base = os.path.basename(p)
    if base.startswith("NotoSans-"):
        continue
    src = os.path.join(FONTS, "NotoSans-Bold.ttf" if "Bold" in base else "NotoSans-Regular.ttf")
    print(base, "+", patch(p, src), "glyphs")

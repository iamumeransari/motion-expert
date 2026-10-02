"""Splice the editorial-select runtime into every block, identically.

The runtime is the modules in this folder (00-core.js to 70-preset.js) wrapped in
one guarded IIFE that defines window.__esRuntime, with EditorialSelect Serif's
metrics (es-serif-metrics.json, from metrics.py) filled in. Every block carries a
byte-identical copy between the markers

    /* BEGIN es-runtime */ ... /* END es-runtime */

because a block must run alone on the storyboard canvas, and in a composed piece
the first copy in the document wins, so all copies must be the same version.
Change a module here, bump VERSION, run this, and re-prove the blocks.

Older kit regions (es-shared, es-select, es-camera between BEGIN/END markers, and
es-kit, es-cursor between :begin/:end markers) are replaced by the runtime; a
block with none gets the runtime at the top of its first <script>. Block code
then reaches the runtime as window.__esRuntime.<module>; the old globals
(__esShared, __esKit, __esSelect, __esCamera, __esCursor) stay defined as aliases
for harness files outside the skill.

usage: python3 inject.py [--check] [extra.html ...]
  no arguments: every library/*.html block listed in blocks.json, plus any extra
  files named (harness elements outside the skill); --check reports drift only.
"""
import json, os, re, sys

VERSION = "2.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.dirname(HERE)
STYLE = os.path.dirname(LIB)
MODULES = ["00-core.js", "20-shared.js", "30-kit.js", "40-select.js", "50-camera.js", "60-cursor.js", "70-preset.js"]
ALIASES = {"__esShared": "shared", "__esKit": "kit", "__esSelect": "select", "__esCamera": "camera", "__esCursor": "cursor"}


def runtime():
    metrics = open(os.path.join(HERE, "es-serif-metrics.json"), encoding="utf-8").read().strip()
    mods = "\n".join(open(os.path.join(HERE, m), encoding="utf-8").read().rstrip() + "\n" for m in MODULES)
    mods = mods.replace("__ES_SERIF_METRICS__", metrics)
    mods = "\n".join(("  " + l) if l.strip() else l for l in mods.split("\n"))
    alias = "\n".join(f"  window.{g} = window.{g} || window.__esRuntime.{m};" for g, m in ALIASES.items())
    return (f"  /* es-runtime {VERSION}. The editorial-select runtime, one copy per block and\n"
            f"     identical in all of them; the first copy in a document wins. Source and\n"
            f"     docs: library/_runtime/ (inject.py splices it, never edit a copy). */\n"
            f"  if (!window.__esRuntime) window.__esRuntime = (function () {{\n"
            f"    var R = {{ version: \"{VERSION}\" }};\n{mods}    return R;\n  }})();\n{alias}\n")


OLD = [re.compile(r"[ \t]*/\* BEGIN (es-shared|es-select|es-camera|es-runtime) \*/.*?/\* END \1 \*/[ \t]*\n?", re.S),
       re.compile(r"[ \t]*/\* (es-kit|es-cursor):begin \*/.*?/\* \1:end \*/[ \t]*\n?", re.S)]


def splice(text, body):
    region = "  /* BEGIN es-runtime */\n" + body + "  /* END es-runtime */\n"
    first = None
    for rx in OLD:
        m = rx.search(text)
        if m and (first is None or m.start() < first):
            first = m.start()
    for rx in OLD:
        text = rx.sub("\x00", text)
    if first is not None:
        i = text.index("\x00")
        text = text[:i] + region + text[i + 1:]
        text = text.replace("\x00", "")
    else:
        m = re.search(r"<script>\n", text)
        if not m:
            raise SystemExit("no <script> to carry the runtime")
        text = text[:m.end()] + region + text[m.end():]
    # block code reaches the runtime by its own name
    head, sep, tail = text.partition("/* END es-runtime */\n")
    for g, mod in ALIASES.items():
        tail = re.sub(r"window\." + g + r"\b", "window.__esRuntime." + mod, tail)
    return head + sep + tail


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    check = "--check" in sys.argv
    blocks = json.load(open(os.path.join(STYLE, "blocks.json")))["blocks"]
    files = [os.path.join(LIB, b + ".html") for b in blocks] + [os.path.abspath(a) for a in args]
    body = runtime()
    drift = 0
    for p in files:
        t = open(p, encoding="utf-8").read()
        n = splice(t, body)
        if n != t:
            drift += 1
            if not check:
                open(p, "w", encoding="utf-8").write(n)
        print(("drift " if check and n != t else "ok    " if n == t else "wrote ") + os.path.relpath(p, STYLE) if p.startswith(STYLE) else p)
    if check and drift:
        sys.exit(1)


if __name__ == "__main__":
    main()

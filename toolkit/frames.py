"""Frame sheets for reading a video by eye: contact sheets, per-cut strips, dense move
strips and frames at given timestamps. Labels are drawn with Pillow (this ffmpeg
build has no drawtext). Every mode decodes the video once, sequentially, through
ffmpeg at a constant frame rate, so frame k is the frame at k / fps.

  frames.py contact <video> --out sheet.png [--n 24] [--cols 6] [--width 270]
  frames.py cuts    <video> --fingerprint fp.json --out DIR [--before 2] [--after 4]
  frames.py moves   <video> --fingerprint fp.json --out DIR [--min-confidence low]
  frames.py at      <video> <t> [<t> ...] --out DIR [--width 540] [--sheet sheet.png]

Python: from frames import frames_at, sheet  (compare.py uses frames_at for
beat-matched side-by-side sheets).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent / "measure"))
from common import frames_at_times, probe  # noqa: E402

LABEL_H = 22
BG = (18, 18, 20)
FG = (235, 235, 235)
ACCENT = (255, 196, 64)


def _font(size=14):
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf",
              "/Library/Fonts/Arial Unicode.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fmt_t(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:06.3f}"


def frames_at(video, times, width=None, fps=None) -> list[Image.Image]:
    """PIL images of the frames at each timestamp (nearest frame at or before t)."""
    pr = probe(video)
    w, h = pr["width"], pr["height"]
    size = (width - width % 2, int(round(width * h / w / 2)) * 2) if width else (w, h)
    arrs = frames_at_times(video, list(times), size, gray=False, fps=fps or pr["fps"])
    return [Image.fromarray(a) for a in arrs]


def sheet(images, labels, cols, out, title=None, highlight=None):
    """Grid of tiles with a label bar under each; highlight = set of indices drawn
    with an accent label (e.g. the first frame after a cut)."""
    if not images:
        return None
    tw, th = images[0].size
    rows = math.ceil(len(images) / cols)
    top = 28 if title else 0
    canvas = Image.new("RGB", (cols * tw, top + rows * (th + LABEL_H)), BG)
    d = ImageDraw.Draw(canvas)
    f = _font(max(11, min(16, tw // 16)))
    if title:
        d.text((8, 6), title, fill=FG, font=_font(16))
    for i, (im, lab) in enumerate(zip(images, labels)):
        r, c = divmod(i, cols)
        x, y = c * tw, top + r * (th + LABEL_H)
        canvas.paste(im, (x, y))
        col = ACCENT if highlight and i in highlight else FG
        d.text((x + 4, y + th + 3), lab, fill=col, font=f)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, optimize=True)
    return str(out)


def tile_width(pr, target_h=320):
    return max(120, int(round(target_h * pr["width"] / pr["height"] / 2)) * 2)


def cmd_contact(a):
    pr = probe(a.video)
    dur = pr["duration"]
    times = [dur * (i + 0.5) / a.n for i in range(a.n)]
    w = a.width or tile_width(pr)
    ims = frames_at(a.video, times, w)
    out = sheet(ims, [fmt_t(t) for t in times], a.cols, a.out,
                title=f"{Path(a.video).name}  {dur:.2f}s  {pr['width']}x{pr['height']} @ {pr['fps']:.3f}")
    print(json.dumps({"sheet": out, "times": [round(t, 4) for t in times]}))


def _load_fp(path):
    fp = json.loads(Path(path).read_text())
    return fp


def cmd_cuts(a):
    pr = probe(a.video)
    fps = pr["fps"]
    fp = _load_fp(a.fingerprint)
    timing = fp["timing"] if "timing" in fp else fp
    events = [("cut", c, c) for c in timing.get("cuts", [])]
    if not a.hard_only:
        events += [(d.get("kind", "soft"), d["t0"], d["t1"]) for d in timing.get("dissolves", [])]
    events.sort(key=lambda e: e[1])
    w = a.width or tile_width(pr, 240)
    out = []
    for n, (kind, t0, t1) in enumerate(events, 1):
        k0 = int(round(t0 * fps))
        k1 = int(round(t1 * fps))
        if kind == "cut":
            idx = list(range(k0 - a.before, k0 + a.after + 1))
            hl = {a.before}
        else:
            idx = list(range(k0 - a.before, k1 + a.after + 1))
            if len(idx) > 24:
                idx = sorted(set(int(round(v)) for v in np.linspace(idx[0], idx[-1], 24)))
            hl = {i for i, k in enumerate(idx) if k0 <= k <= k1}
        idx = [k for k in idx if k >= 0]
        times = [k / fps for k in idx]
        ims = frames_at(a.video, times, w, fps)
        ref = k0
        labels = [f"{k - ref:+d}f {fmt_t(k / fps)}" for k in idx]
        p = Path(a.out) / f"{'cut' if kind == 'cut' else 'trans'}_{n:03d}_{t0:07.3f}s.png"
        sheet(ims, labels, min(len(ims), a.cols), p,
              title=f"{kind} at {fmt_t(t0)}" + (f" to {fmt_t(t1)}" if t1 != t0 else "") + "  (accent = new shot)")
        out.append({"kind": kind, "t0": t0, "t1": t1, "path": str(p)})
    print(json.dumps(out, indent=1))


def cmd_moves(a):
    pr = probe(a.video)
    fps = pr["fps"]
    fp = _load_fp(a.fingerprint)
    moves = fp["motion"]["moves"] if "motion" in fp else fp["moves"]
    rank = {"low": 0, "medium": 1, "high": 2}
    w = a.width or tile_width(pr, 240)
    out = []
    for n, mv in enumerate(moves, 1):
        if rank.get(mv.get("confidence", "low"), 0) < rank[a.min_confidence]:
            continue
        pad = a.pad
        # sample at 2x the source rate so no source frame is skipped, then keep one
        # tile per distinct frame
        step = 1 / (a.rate * fps)
        ts = np.arange(max(0.0, mv["t0"] - pad), mv["t1"] + pad + 1e-9, step)
        idx = sorted(set(int(math.floor(t * fps + 1e-6)) for t in ts))
        if len(idx) > a.max_frames:
            idx = sorted(set(int(round(v)) for v in np.linspace(idx[0], idx[-1], a.max_frames)))
        times = [k / fps for k in idx]
        ims = frames_at(a.video, times, w, fps)
        # outline the move region on each tile
        r = mv["region"]
        for im in ims:
            dr = ImageDraw.Draw(im)
            W, H = im.size
            dr.rectangle([r["x"] * W, r["y"] * H, (r["x"] + r["w"]) * W - 1, (r["y"] + r["h"]) * H - 1],
                         outline=ACCENT, width=2)
        kf = mv.get("keyframes", {})
        hl = {i for i, t in enumerate(times) if mv["t0"] <= t <= mv["t1"]}
        labels = []
        for t in times:
            tag = ""
            for name, kt in kf.items():
                if abs(t - kt) < 0.5 / fps:
                    tag = " " + name
            labels.append(f"{fmt_t(t)}{tag}")
        bez = ",".join(f"{v:.2f}" for v in mv.get("bezier", []))
        p = Path(a.out) / f"move_{n:03d}_{mv['t0']:07.3f}s_{mv['property']}.png"
        sheet(ims, labels, min(len(ims), a.cols), p,
              title=f"move {n}: {mv['property']} {mv['duration']:.2f}s  bezier({bez})  "
                    f"overshoot {mv.get('overshoot', 0):.2f}  err {mv.get('fit_error', 0):.3f}  {mv.get('confidence')}",
              highlight=hl)
        out.append({"move": n, "t0": mv["t0"], "path": str(p)})
    print(json.dumps(out, indent=1))


def cmd_at(a):
    pr = probe(a.video)
    times = [float(t) for t in a.times]
    ims = frames_at(a.video, times, a.width)
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    res = []
    for t, im in zip(times, ims):
        p = outdir / f"f_{t:08.3f}.png"
        im.save(p)
        res.append({"t": t, "path": str(p)})
    if a.sheet:
        sheet(ims, [fmt_t(t) for t in times], a.cols, a.sheet, title=Path(a.video).name)
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser(description="Contact sheets and frame strips")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("contact")
    c.add_argument("video"); c.add_argument("--out", required=True)
    c.add_argument("--n", type=int, default=24); c.add_argument("--cols", type=int, default=6)
    c.add_argument("--width", type=int)
    c.set_defaults(fn=cmd_contact)
    c = sub.add_parser("cuts")
    c.add_argument("video"); c.add_argument("--fingerprint", required=True); c.add_argument("--out", required=True)
    c.add_argument("--before", type=int, default=2); c.add_argument("--after", type=int, default=4)
    c.add_argument("--cols", type=int, default=12); c.add_argument("--width", type=int)
    c.add_argument("--hard-only", action="store_true")
    c.set_defaults(fn=cmd_cuts)
    c = sub.add_parser("moves")
    c.add_argument("video"); c.add_argument("--fingerprint", required=True); c.add_argument("--out", required=True)
    c.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium")
    c.add_argument("--rate", type=float, default=2.0, help="sampling rate as a multiple of source fps")
    c.add_argument("--pad", type=float, default=0.1); c.add_argument("--max-frames", type=int, default=48)
    c.add_argument("--cols", type=int, default=12); c.add_argument("--width", type=int)
    c.set_defaults(fn=cmd_moves)
    c = sub.add_parser("at")
    c.add_argument("video"); c.add_argument("times", nargs="+"); c.add_argument("--out", required=True)
    c.add_argument("--width", type=int, default=540); c.add_argument("--sheet"); c.add_argument("--cols", type=int, default=6)
    c.set_defaults(fn=cmd_at)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

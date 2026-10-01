"""Mechanical checks behind the reference board, used by toolkit/reference-board.py.

Data against picture (run on every build, they decide what is drawn):
  check_cuts   a cut marker must sit on the frame where the picture changes; a change
               one frame either side moves the marker, no change drops it
  check_moves  a move bar must bracket visible motion inside its region and is
               trimmed to the frames where the region moves; its region box must also
               hold most of the frame's motion; anything unverified is hidden by
               default on the board
  check_sfx    a sound marker must sit on an audible onset (within a frame); it snaps
               to an onset within 80 ms or is marked unverified

Board against source (`--verify`):
  sync_report  seeks every page in Chrome on both sides of every cut, identifies the
               source frame actually on screen by matching the screenshot against the
               source, and measures how far the overlay's clock runs ahead of the
               presented frame during playback
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "measure"))
from common import FFMPEG, analysis_size, load_frames, probe  # noqa: E402

LONG = 160          # analysis size, as cuts.py
CUT_FLOOR = 0.10    # share of pixels moving > 20 levels for a frame to count as a picture change
MOVE_THR = 10       # grey levels a region pixel must move frame to frame
MOVE_FLOOR = 0.02   # mean share of region pixels moving per frame inside the move span
MOVE_NET = 0.05     # share of region pixels that differ between the first and last frame of the span
MOVE_LOCAL = 2.0    # the box must move this many times more densely than a ring of picture around it
SFX_SNAP = 0.08     # seconds an onset may sit from the marker


def source_grey(video, fps, long_side=LONG):
    pr = probe(video)
    size = analysis_size(pr["width"], pr["height"], long_side)
    return load_frames(video, fps, size, gray=True)


def _diff_share(G, k, thr):
    return float((np.abs(G[k].astype(np.int16) - G[k - 1].astype(np.int16)) > thr).mean()) if k >= 1 else 0.0


def check_cuts(G, cuts, fps):
    """Returns [{t, status ok|moved|dropped, t_fixed, change}]"""
    n = len(G)
    Gb = np.stack([cv2.GaussianBlur(g, (3, 3), 0) for g in G])
    out = []
    for c in cuts:
        k = int(round(c * fps))
        ch = {j: _diff_share(Gb, j, 20) for j in range(max(1, k - 1), min(n, k + 2))}
        best = max(ch, key=lambda j: (ch[j], -abs(j - k)))
        if ch.get(k, 0) >= CUT_FLOOR and ch[k] >= ch[best] * 0.999:
            out.append(dict(t=c, status="ok", t_fixed=c, change=ch[k]))
        elif ch[best] >= CUT_FLOOR:
            out.append(dict(t=c, status="moved", t_fixed=best / fps, change=ch[best]))
        else:
            out.append(dict(t=c, status="dropped", t_fixed=None, change=ch.get(k, 0)))
    return out


def check_moves(G, moves, cuts, fps):
    """One dict per move. G should be at least 320 px wide so small elements (corner
    ticks, a cursor) cover enough pixels to measure. A bar is verified when its region
    visibly moves inside the span (mean share of region pixels changing by more than
    MOVE_THR per frame at least MOVE_FLOOR) and the motion goes somewhere (at least
    MOVE_NET of the region differs between the frame before the span and its last
    frame, which grain and compression shimmer on high-contrast edges never reach);
    its span is then trimmed to the frames where the region moves. A box is verified when the bar is and the motion is in the
    box rather than all around it: the box moves at least MOVE_LOCAL times as densely
    as a ring of picture around it (half the box size each side), or the box is near
    full frame. A camera drift moves the ring as much as the box, so its box (which
    only marks where flow peaked) fails, while a corner tick fading in beside a word
    that wipes on elsewhere passes. continues says the region keeps moving past the
    span within the same shot, so the bar is one stretch of a longer motion."""
    n, H, W = G.shape
    cut_f = sorted(int(round(c * fps)) for c in cuts)
    cutset = set(cut_f)
    cache = {}

    def diff(k):
        if k not in cache:
            cache[k] = np.abs(G[k].astype(np.int16) - G[k - 1].astype(np.int16)) > MOVE_THR
        return cache[k]

    out = []
    for m in moves:
        r = m["region"]
        x0, y0 = int(np.floor(r["x"] * W)), int(np.floor(r["y"] * H))
        x1, y1 = max(x0 + 1, int(np.ceil((r["x"] + r["w"]) * W))), max(y0 + 1, int(np.ceil((r["y"] + r["h"]) * H)))
        area = (x1 - x0) * (y1 - y0) / (W * H)
        f0, f1 = max(1, int(round(m["t0"] * fps))), min(n - 1, int(round(m["t1"] * fps)))
        lo = max([c for c in cut_f if c <= f0] + [1])
        hi = min([c for c in cut_f if c > f0] + [n]) - 1
        frames = [k for k in range(f0 + 1, min(max(f1, f0 + 1), hi) + 1) if k not in cutset]
        if not frames:
            out.append(dict(verified=False, box=False, reason="span lies on a cut", t0=m["t0"], t1=m["t1"],
                            level=0.0, conc=0.0, continues=False, trimmed=False))
            continue
        reg = {k: float(diff(k)[y0:y1, x0:x1].mean()) for k in frames}
        level = float(np.mean(list(reg.values())))
        # ring around the box, half its size (at least 4 px) each side
        px, py = max(4, (x1 - x0) // 2), max(4, (y1 - y0) // 2)
        X0, Y0, X1, Y1 = max(0, x0 - px), max(0, y0 - py), min(W, x1 + px), min(H, y1 + py)
        ring_n = (X1 - X0) * (Y1 - Y0) - (x1 - x0) * (y1 - y0)
        inner = sum(float(diff(k)[y0:y1, x0:x1].sum()) for k in frames)
        outer = sum(float(diff(k)[Y0:Y1, X0:X1].sum()) for k in frames) - inner
        dens_in = inner / (len(frames) * (x1 - x0) * (y1 - y0))
        dens_ring = outer / (len(frames) * ring_n) if ring_n > 0 else 0.0
        conc = dens_in / max(dens_ring, 1e-4)
        pad = max(2, int(round(0.25 * fps)))
        near = [k for k in list(range(max(lo + 1, f0 - pad + 1), f0 + 1)) + list(range(f1 + 1, min(hi, f1 + pad) + 1)) if k not in cutset]
        cont = bool(near) and float(np.mean([diff(k)[y0:y1, x0:x1].mean() for k in near])) >= max(MOVE_FLOOR, 0.6 * level)
        active = [k for k in frames if reg[k] >= MOVE_FLOOR]
        t0, t1 = m["t0"], m["t1"]
        if active:
            t0, t1 = (active[0] - 1) / fps, active[-1] / fps
        last = max(frames)
        net = float((np.abs(G[last, y0:y1, x0:x1].astype(np.int16) - G[f0, y0:y1, x0:x1].astype(np.int16)) > MOVE_THR).mean())
        verified = level >= MOVE_FLOOR and bool(active) and net >= MOVE_NET
        box = verified and (area >= 0.9 or ring_n <= 0 or dens_in >= MOVE_LOCAL * dens_ring)
        reason = None
        if not verified:
            reason = (f"region barely moves in the span ({level:.3f} of its pixels per frame)" if level < MOVE_FLOOR or not active
                      else f"region flickers but ends where it started ({net:.3f} of its pixels changed over the span)")
        elif not box:
            reason = f"moves, but the picture around the box moves as much ({dens_ring:.3f} against {dens_in:.3f}), so the box is not where the motion is"
        out.append(dict(verified=verified, box=box, reason=reason, t0=t0, t1=t1, level=level, conc=conc, net=net,
                        continues=cont, trimmed=verified and (abs(t0 - m["t0"]) > 0.5 / fps or abs(t1 - m["t1"]) > 0.5 / fps)))
    return out


def onset_env(video):
    """Onset strength of the mixed soundtrack at 22.05 kHz, hop 256 (11.6 ms)."""
    import librosa
    raw = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", str(video), "-vn", "-ac", "1", "-ar", "22050",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    y = np.frombuffer(raw, np.float32)
    env = librosa.onset.onset_strength(y=y, sr=22050, hop_length=256)
    times = librosa.frames_to_time(np.arange(len(env)), sr=22050, hop_length=256)
    return times, env


def check_sfx(video, events):
    if not events:
        return []
    times, env = onset_env(video)
    med = float(np.median(env))
    mad = float(np.median(np.abs(env - med))) + 1e-9
    peaks = [i for i in range(1, len(env) - 1) if env[i] >= env[i - 1] and env[i] > env[i + 1] and env[i] > med + 3 * mad]
    pt = times[peaks] if peaks else np.array([])
    out = []
    for e in events:
        if not len(pt):
            out.append(dict(status="dropped", t_fixed=None, off=None))
            continue
        j = int(np.argmin(np.abs(pt - e["t"])))
        off = float(pt[j] - e["t"])
        if abs(off) <= 1.0 / 24:      # within a frame: on the onset (onset strength peaks lag the attack)
            out.append(dict(status="ok", t_fixed=e["t"], off=off))
        elif abs(off) <= SFX_SNAP:
            out.append(dict(status="moved", t_fixed=float(pt[j]), off=off))
        else:
            out.append(dict(status="dropped", t_fixed=None, off=off))
    return out


# ---- board against source -------------------------------------------------------

def _page_data(p: Path, var: str):
    m = re.search(r"window\." + var + r" = (\{.*?\});</script>", p.read_text(), re.S)
    return json.loads(m.group(1)) if m else None


def _z(a):
    a = a - a.mean()
    return a / (np.sqrt((a * a).mean()) + 1e-6)


def sync_report(board: Path, video: str, fps: float, fp_cuts: list, drawn_cuts: list, out: Path, play_s=2.0):
    """Seek every page of the built board in Chrome and prove the picture matches the
    overlay. Seeks land a quarter into frames on both sides of every cut plus ten
    spread through each beat (eight on the overview); the screenshot of the <video>
    is matched by normalised correlation against the source frames within three of
    the expected one, and a seek is wrong only when the expected frame matches
    clearly worse than another (frames on twos and holds are identical to their
    neighbours, so a one-frame slip there is invisible and not counted). Playback is
    sampled every animation frame for the time the overlay draws against the
    presented frame's mediaTime. The data-source check compares the cuts every page
    draws with the cuts the fingerprint holds after the recorded corrections."""
    board = Path(board)
    pages = sorted(board.glob("[0-9][0-9]-*.html"))
    beats = {p.name: _page_data(p, "__beat") for p in pages if p.name != "00-overview.html"}
    ov = _page_data(board / "00-overview.html", "__ov")
    G = source_grey(video, fps).astype(np.float32)
    Z = [_z(g) for g in G]
    n = len(G)
    jobs, expect = [], {}
    for name, B in beats.items():
        f0 = int(round(B["a"] * fps))
        nf = int(round(B["b"] * fps)) - f0
        fr = set()
        for c in B["cuts"]:
            k = int(round(c * fps)) - f0
            fr.update([k - 1, k])
        fr.update(int(v) for v in np.linspace(0, nf - 1, 10))
        fr = sorted(f for f in fr if 0 <= f < nf)
        jobs.append({"file": name, "times": [(f + 0.25) / fps for f in fr]})
        expect[name] = [(f0 + f, (f0 + f) in {int(round(c * fps)) for c in B["cuts"]} or (f0 + f + 1) in {int(round(c * fps)) for c in B["cuts"]}) for f in fr]
    ofr = sorted(set(int(v) for v in np.linspace(0, n - 1, 8)) | {int(round(c * fps)) + d for c in (ov or {}).get("cuts", [])[:4] for d in (-1, 0)})
    ofr = [f for f in ofr if 0 <= f < n]
    jobs.append({"file": "00-overview.html", "times": [(f + 0.25) / fps for f in ofr]})
    expect["00-overview.html"] = [(f, False) for f in ofr]
    plays = [{"file": j["file"], "from": 0, "seconds": play_s} for j in jobs[:3]] + [{"file": "00-overview.html", "from": 10, "seconds": play_s}]
    out.mkdir(parents=True, exist_ok=True)
    job_p = out / "job.json"
    job_p.write_text(json.dumps({"board": str(board), "jobs": jobs, "play": plays, "out": str(out)}))
    subprocess.run(["node", str(HERE / "verify-sync.cjs"), str(job_p)], check=True, capture_output=True, text=True)
    sync = json.loads((out / "sync.json").read_text())

    H, W = G.shape[1:]
    rows, idx = [], {}
    for s in sync["seeks"]:
        i = idx.get(s["file"], 0)
        idx[s["file"]] = i + 1
        want, at_cut = expect[s["file"]][i]
        img = _z(cv2.resize(cv2.imread(s["png"], cv2.IMREAD_GRAYSCALE), (W, H), interpolation=cv2.INTER_AREA).astype(np.float32))
        sc = {q: float(((img - Z[q]) ** 2).mean()) for q in range(max(0, want - 3), min(n, want + 4))}
        best = min(sc, key=sc.get)
        wrong = sc[want] > sc[best] + 0.05 and sc[want] > 1.5 * sc[best]
        rows.append(dict(file=s["file"], t=s["t"], want=want, shown=best if wrong else want, wrong=wrong, at_cut=at_cut))
    wrong = [r for r in rows if r["wrong"]]
    offs = {}
    for r in wrong:
        offs[str(r["shown"] - r["want"])] = offs.get(str(r["shown"] - r["want"]), 0) + 1
    leads = np.array([(smp["overlay"] - smp["media"]) * fps for p in sync["plays"] for smp in p["samples"]] or [0.0])
    board_cuts = sorted({round(c, 4) for B in beats.values() for c in B["cuts"]})
    inner = sorted(round(c, 4) for c in drawn_cuts if any(B["a"] + 1e-3 < c < B["b"] - 1e-3 for B in beats.values()))
    return dict(
        seeks=len(rows), seeks_at_cuts=sum(r["at_cut"] for r in rows), wrong=len(wrong),
        wrong_at_cuts=sum(r["at_cut"] for r in wrong), offsets=offs, wrong_rows=wrong[:20],
        playback_lead_frames=dict(mean=float(leads.mean()), p90=float(np.percentile(leads, 90)), max=float(leads.max()),
                                  share_over_half_frame=float((leads > 0.5).mean()), samples=int(len(leads))),
        source=dict(fingerprint_cuts=len(fp_cuts), drawn_cuts=len(drawn_cuts),
                    overview_draws_them=[round(c, 4) for c in (ov or {}).get("cuts", [])] == [round(c, 4) for c in drawn_cuts],
                    beats_draw_them=board_cuts == inner),
        errors=sync.get("errors", []))

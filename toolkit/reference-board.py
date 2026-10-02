"""Build the canvas reference storyboard for a source video. It is made right after
fingerprinting and is the first thing Umer reviews in a capture: one overview frame
of the whole film plus one frame per beat that plays the beat's exact source frames
under a review overlay of shots, cuts, soft transitions, the music beat grid, the
motion energy curve, tracked moves and sound events.

  reference-board.py <slug> [--video V] [--fingerprint FP] [--grid music-beats.json]
                     [--spec beats.json] [--out DIR] [--name BOARD] [--beat-s 3]
                     [--register] [--verify]

Inputs, all defaulting to work/<slug>/:
  fingerprint.json   from measure/fingerprint.py (timing, motion, sound)
  music-beats.json   the beat grid (tempo_bpm, beats, downbeats); when it is missing
                     and the fingerprint heard music, music.py measure --beats-out
                     writes it first
  beats.json         the beats spec the capturing agent writes after reading the
                     strips; without it every beat is one cluster of shots

beats.json:
  {"title": "Ideogram 4.5 launch film",               film name on the overview
   "board_title": "Ideogram 4.5 reference, beat by beat",
   "summary": "The shape: ...",                        one paragraph on the overview
   "beats": [{"slug": "genre-cards", "title": "Genre word cards", "a": 0.0, "b": 3.2917,
              "feeling": "Range. ...",
              "shots": [{"a": 0.0, "b": 0.417, "tag": "Art", "text": "Art over a moon ..."}]}],
   "move_names": [{"t0": 0.0, "property": "position", "name": "Art corner tick nudges up"}],
   "soft_notes": [{"t0": 9.125, "note": "motion: The rushes through camera"}],
   "missed_cuts": [{"t": 22.1667, "why": "face to bottle on white"}]}
Times are source seconds. A shot whose start is a cut (or the beat start) is drawn as
a shot, any other as a phase inside a shot. Move names and soft notes attach to the
fingerprint's move or transition starting within one frame of t0 (and of the same
property when given), so they survive a re-fingerprint that renumbers moves. A missed
cut is drawn dashed amber until the fingerprint finds it, then it is dropped.

Every build checks the data against the picture before drawing it (lib/reference/
checks.py): a cut marker must sit on the frame where the picture changes (a change one
frame off moves it), a move bar must bracket visible motion in its region and is
trimmed to the frames where the region moves, a region box is drawn only when the
motion is inside it, and a sound marker must sit on an audible onset (snapped within
80 ms). What fails is not drawn: region boxes are off by default (B shows the
verified ones) and unverified moves and sounds appear only on U, hatched. Every
failure is listed in DIR/verify.json. --verify then proves the board shows what it
says: it seeks every page in Chrome on both sides of every cut, matches the frame on
screen against the source, measures how far the overlay runs ahead of the picture
during playback, checks the pages draw the fingerprint's cuts, adds that to
verify.json and exits 1 on any mismatch.

Writes DIR (default work/<slug>/board): 00-overview.html, NN-<slug>.html per beat,
board.json, lib/ (overlay.css, sb.css, sb.js from toolkit/lib), clips/ (a
frame-accurate clip per beat and full.mp4 with sound, tracked in clips.json) and
thumbs/. Only files whose content changed are rewritten, so a board already on the
canvas keeps its comments. --register runs ~/storyboard-canvas/bin/canvas add on the
folder under the board name (default <slug>-reference).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIB = HERE / "lib"
sys.path.insert(0, str(HERE / "measure"))
sys.path.insert(0, str(LIB / "reference"))
import checks  # noqa: E402
from common import FFMPEG, FFPROBE, sha256  # noqa: E402

CANVAS = Path.home() / "storyboard-canvas" / "bin" / "canvas"
SFX_COLORS = {"pop": "#39d98a", "click": "#4cc9f0", "other": "#adb5bd", "sub-drop": "#b388ff",
              "chime": "#ffd166", "impact": "#ff4d6d", "whoosh": "#f78c6b"}
SPARE = ["#e0aaff", "#90e0ef", "#caffbf", "#ffc6ff", "#fdffb6"]


def log(*a):
    print(*a, file=sys.stderr)


def write_if_changed(p: Path, text: str) -> bool:
    if p.exists() and p.read_text() == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return True


def copy_if_changed(src: Path, dst: Path) -> bool:
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def frame_count(video: str, fps: float, duration: float) -> int:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                          "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip()
    try:
        return int(out)
    except ValueError:
        return int(duration * fps + 1e-6)


def nb_frames(path: Path) -> int | None:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    try:
        return int(out.strip())
    except ValueError:
        return None


# ---- wording ----------------------------------------------------------------

def curve_words(bz, over):
    x1, y1, x2, y2 = bz
    early, late = y1 - x1, y2 - x2
    if early > 0.25 and late > -0.15:
        w = "ease-out, fast start soft land"
    elif early < -0.2 and late > 0.2:
        w = "ease-in-out"
    elif early < -0.2:
        w = "ease-in, slow start"
    elif early > 0.25:
        w = "fast start, late lift"
    else:
        w = "near linear"
    if over and over >= 0.1:
        w += f", {round(over * 100)}% overshoot"
    return f"{w} ({','.join(('%.2f' % v).rstrip('0').rstrip('.') or '0' for v in bz)})"


def energy_label(v):
    if v < 0.03:
        return "calm", "#8fb0ff"
    if v < 0.07:
        return "medium", "#39d98a"
    if v < 0.13:
        return "high", "#ffd166"
    return "peak", "#ff4d6d"


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ---- spec ---------------------------------------------------------------------

def norm_shot(s):
    if isinstance(s, (list, tuple)):
        a, b, tag, text = (list(s) + [None, None, "", ""])[:4]
        return {"a": float(a), "b": float(b), "tag": tag or "", "text": text or ""}
    return {"a": float(s["a"]), "b": float(s["b"]), "tag": s.get("tag", ""), "text": s.get("text", "")}


def shot_bounds(timing):
    """Shot boundaries the way cuts.py counts them: hard cuts plus the midpoint of
    each soft transition that does not join a cut."""
    b = [(c, "cut") for c in timing.get("cuts", [])]
    b += [((x["t0"] + x["t1"]) / 2, "soft") for x in timing.get("dissolves", []) if "joins_cut" not in x]
    return sorted(b)


def cluster_beats(timing, end, fps, beat_s):
    """No spec: one beat per cluster of consecutive shots, closed once it reaches
    beat_s seconds or at a soft transition (a scene change), a short tail merging
    into the beat before it."""
    edges = [(0.0, "start")] + [x for x in shot_bounds(timing) if 0 < x[0] < end] + [(end, "end")]
    shots = [(a, b, kind) for (a, kind), (b, _) in zip(edges[:-1], edges[1:]) if b - a > 0.5 / fps]
    beats, cur = [], []
    for i, (a, b, kind) in enumerate(shots):
        if cur and (kind == "soft" or cur[-1][1] - cur[0][0] >= beat_s):
            beats.append(cur)
            cur = []
        cur.append((a, b, kind))
    if cur:
        if beats and cur[-1][1] - cur[0][0] < beat_s / 3:
            beats[-1] += cur
        else:
            beats.append(cur)
    out, k = [], 0
    for n, grp in enumerate(beats, 1):
        sh = []
        for a, b, _ in grp:
            k += 1
            sh.append({"a": a, "b": b, "tag": f"s{k:02d}", "text": f"shot {k}, {round((b - a) * fps)} frames"})
        out.append({"slug": f"beat-{n:02d}", "title": f"Shots {k - len(grp) + 1} to {k}" if len(grp) > 1 else f"Shot {k}",
                    "a": grp[0][0], "b": grp[-1][1], "feeling": "", "shots": sh})
    return out


def match_by_t0(items, entries, fps, prop_key=None):
    """Attach each entry (with t0, optional property) to the item starting within one
    frame of it; one item per entry, nearest first. Returns {item index: entry} and
    the entries that found nothing."""
    tol = 1.0 / fps + 1e-3
    taken, out, lost = set(), {}, []
    for e in entries:
        cands = []
        for i, it in enumerate(items):
            if i in taken or abs(it["t0"] - float(e["t0"])) > tol:
                continue
            if prop_key and e.get("property") and it.get(prop_key) != e["property"]:
                continue
            cands.append((abs(it["t0"] - float(e["t0"])), abs(it.get("t1", 0) - float(e.get("t1", it.get("t1", 0)))), i))
        if cands:
            i = min(cands)[2]
            taken.add(i)
            out[i] = e
        else:
            lost.append(e)
    return out, lost


# ---- media --------------------------------------------------------------------

def encode_clips(video, out, beats, fps, total, src_sha):
    """One clip per beat at source size without sound, plus full.mp4 at 1280 wide with
    sound, frame-accurate (input seek a quarter frame early so rounding never pulls in
    the previous frame, then an exact frame count). clips.json remembers what each
    file holds so a rebuild re-encodes only what moved; an existing clip from before
    the manifest is adopted when its frame count matches."""
    cdir = out / "clips"
    cdir.mkdir(parents=True, exist_ok=True)
    man_p = cdir / "clips.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {}
    jobs = []
    for n, b in enumerate(beats, 1):
        f0 = int(round(b["a"] * fps))
        nf = max(1, int(round(b["b"] * fps)) - f0)
        jobs.append((f"b{n:02d}.mp4", {"src": src_sha, "f0": f0, "n": nf, "kind": "beat"}))
    jobs.append(("full.mp4", {"src": src_sha, "f0": 0, "n": total, "kind": "full"}))
    made = 0
    for name, want in jobs:
        p = cdir / name
        if man.get(name) == want and p.exists():
            continue
        if name not in man and p.exists() and nb_frames(p) == want["n"]:
            man[name] = want  # adopt a clip built before the manifest existed
            continue
        cmd = [FFMPEG, "-v", "error", "-y", "-nostdin"]
        if want["kind"] == "beat":
            cmd += ["-ss", f"{max(0.0, (want['f0'] - 0.25) / fps):.6f}", "-i", video, "-frames:v", str(want["n"]), "-an",
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(p)]
        else:
            cmd += ["-i", video, "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(p)]
        subprocess.run(cmd, check=True)
        man[name] = want
        made += 1
    for stale in set(man) - {j[0] for j in jobs}:
        (cdir / stale).unlink(missing_ok=True)
        man.pop(stale)
    write_if_changed(man_p, json.dumps(man, indent=1, sort_keys=True) + "\n")
    return made


def make_thumbs(video, out, beats, fps):
    tdir = out / "thumbs"
    tdir.mkdir(parents=True, exist_ok=True)
    man_p = tdir / "thumbs.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {}
    for n, b in enumerate(beats, 1):
        s = b["shots"][len(b["shots"]) // 2] if b["shots"] else {"a": b["a"], "b": b["b"]}
        t = round((s["a"] + s["b"]) / 2, 4)
        name = f"b{n:02d}.jpg"
        if man.get(name) == t and (tdir / name).exists():
            continue
        subprocess.run([FFMPEG, "-v", "error", "-y", "-nostdin", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                        "-vf", "scale=480:-2", "-q:v", "4", str(tdir / name)], check=True)
        man[name] = t
    write_if_changed(man_p, json.dumps(man, indent=1, sort_keys=True) + "\n")


def ensure_grid(grid: Path, video: str, fp: dict, work: Path) -> dict | None:
    if grid.exists():
        return json.loads(grid.read_text())
    music = ((fp.get("sound") or {}).get("music") or {})
    if not music.get("present"):
        return None
    log(f"no beat grid at {grid}; measuring it with music.py")
    try:
        subprocess.run([sys.executable, str(HERE / "music.py"), "measure", video, "--out", str(work / "music.json"),
                        "--beats-out", str(grid)], check=True)
        return json.loads(grid.read_text())
    except Exception as e:  # the board is still useful without a grid
        log(f"beat grid unavailable ({e}); building without it")
        return None


# ---- build --------------------------------------------------------------------

def build(a):
    work = Path(a.work or ROOT / "work" / a.slug).resolve()
    fp_path = Path(a.fingerprint or work / "fingerprint.json")
    fp = json.loads(fp_path.read_text())
    src = fp["source"]
    video = a.video or (src["path"] if Path(src["path"]).exists() else str(work / "source.mp4"))
    if not Path(video).exists():
        sys.exit(f"source video not found: {video}")
    fps = float(src["fps"])
    total = frame_count(video, fps, src["duration"])
    END = total / fps
    out = Path(a.out or work / "board").resolve()
    out.mkdir(parents=True, exist_ok=True)

    spec_p = Path(a.spec or work / "beats.json")
    spec = json.loads(spec_p.read_text()) if spec_p.exists() else None
    timing = fp.get("timing") or {}
    motion = fp.get("motion") or {}
    sound = fp.get("sound") or {}
    if spec:
        beats = [dict(b, shots=[norm_shot(s) for s in b.get("shots", [])]) for b in spec["beats"]]
    else:
        beats = cluster_beats(timing, END, fps, a.beat_s)
        log(f"no beats spec at {spec_p}; {len(beats)} beats, one per cluster of shots")
    spec = spec or {}

    grid = ensure_grid(Path(a.grid or work / "music-beats.json"), video, fp, work)
    downs = set(round(t, 4) for t in (grid or {}).get("downbeats", []))
    music_beats = [dict(t=t, down=round(t, 4) in downs) for t in (grid or {}).get("beats", [])]
    bpm = (grid or {}).get("tempo_bpm") or (sound.get("music") or {}).get("tempo_bpm")

    fp_cuts = timing.get("cuts", [])
    G = checks.source_grey(video, fps, 320)
    cut_v = checks.check_cuts(G, fp_cuts, fps)
    cuts = sorted(c["t_fixed"] for c in cut_v if c["t_fixed"] is not None)
    tol = 1.0 / fps + 1e-3
    missed_all = spec.get("missed_cuts", [])
    missed = [m for m in missed_all if not any(abs(c - m["t"]) <= tol for c in cuts)]
    if len(missed) < len(missed_all):
        log(f"{len(missed_all) - len(missed)} of {len(missed_all)} missed cuts are now in the fingerprint and drawn solid")
    soft = [dict(x) for x in timing.get("dissolves", [])]
    notes, lost_notes = match_by_t0(soft, spec.get("soft_notes", []), fps)
    for i, x in enumerate(soft):
        x["note"] = notes[i]["note"] if i in notes else None
    for e in lost_notes:
        log(f"soft note at {e['t0']} matches no transition in the fingerprint: {e['note']}")
    holds = timing.get("holds", [])
    ev = motion.get("energy") or {"hz": 10, "values": []}
    energy = [dict(t=i / ev["hz"], v=v) for i, v in enumerate(ev["values"])]
    moves = motion.get("moves", [])
    move_v = checks.check_moves(G, moves, cuts, fps)
    del G
    named, lost_names = match_by_t0(moves, spec.get("move_names", []), fps, prop_key="property")
    for e in lost_names:
        log(f"move name at {e['t0']} {e.get('property', '')} matches no move in the fingerprint: {e['name']}")
    sfx_raw = sound.get("events") or []
    sfx_v = checks.check_sfx(video, sfx_raw)
    sfx = []
    for e, v in zip(sfx_raw, sfx_v):
        sfx.append(dict(e, t=v["t_fixed"] if v["t_fixed"] is not None else e["t"], ok=v["status"] != "dropped",
                        moved=v["status"] == "moved", t_orig=e["t"]))
    sfx_ok = [e for e in sfx if e["ok"]]
    classes = sorted({e["class"] for e in sfx})
    colors = dict(SFX_COLORS)
    for i, c in enumerate(k for k in classes if k not in colors):
        colors[c] = SPARE[i % len(SPARE)]

    def tc(t):
        f = round(t * fps)
        return f"{f // round(fps)}:{f % round(fps):02d}"

    means = []
    for b in beats:
        vs = [e["v"] for e in energy if b["a"] <= e["t"] < b["b"]]
        means.append(sum(vs) / max(1, len(vs)))
    order = sorted(range(len(beats)), key=lambda i: -means[i])

    frames_meta = [dict(file="00-overview.html", title=f"Overview, the whole {round(END)}s", duration=round(END, 3),
                        notes=f"All {len(beats)} beats to scale with the fingerprint energy curve, every cut and transition, "
                              "and sound-effect density per second.")]
    tpl = (LIB / "reference" / "frame.html").read_text()
    written = []
    for n, b in enumerate(beats, 1):
        A, Z = b["a"], b["b"]
        mv = []
        for i, m in enumerate(moves):
            if A - 1e-3 <= m["t0"] < Z - 1e-3:
                name = named[i]["name"] if i in named else m["property"]
                mid = f"m{i:02d}"
                v = move_v[i]
                mv.append(dict(id=mid, name=name, prop=m["property"], conf=m["confidence"], t0=v["t0"], t1=v["t1"],
                               ok=v["verified"], box=v["box"], why=v["reason"], trimmed=v["trimmed"],
                               keys={k: v for k, v in (m.get("keyframes") or {}).items() if k in ("peak", "land")},
                               curve=curve_words(m["bezier"], m.get("overshoot")) if m.get("bezier") else "no curve fitted",
                               region=m["region"], label=f"{mid} {m['property']}: {name}"))
        lab, col = energy_label(means[n - 1])
        pts = [e for e in energy if A - 0.1 <= e["t"] <= Z + 0.1]
        shots = []
        for s in b["shots"]:
            is_cut = abs(s["a"] - A) < 0.6 / fps or any(abs(s["a"] - c) < 0.6 / fps for c in cuts) \
                or any(abs(s["a"] - m["t"]) < 0.6 / fps for m in missed)
            shots.append(dict(s, cut=is_cut))
        data = dict(n=n, total=len(beats), slug=b["slug"], title=b["title"], a=A, b=Z, fps=fps, bpm=bpm,
                    feeling=b.get("feeling", ""), energyMean=means[n - 1], energyLabel=lab, energyColor=col,
                    energyRank=f"{ordinal(order.index(n - 1) + 1)} busiest of {len(beats)}",
                    energyScale=max(0.15, max((p["v"] for p in pts), default=0.15)), energy=pts, shots=shots,
                    cuts=[c for c in cuts if A + 1e-3 < c < Z - 1e-3],
                    missed=[m for m in missed if A + 1e-3 < m["t"] < Z - 1e-3],
                    soft=[d for d in soft if d["t1"] > A and d["t0"] < Z],
                    holds=[d for d in holds if d["t1"] > A and d["t0"] < Z],
                    beats=[x for x in music_beats if A <= x["t"] < Z], moves=mv,
                    sfx=[dict(t=e["t"], cls=e["class"], level=round(e.get("level_db_rel_vo", 0.0), 1), bound=e.get("bound_move"),
                              ok=e["ok"], moved=e["moved"]) for e in sfx if A <= e["t"] < Z],
                    sfxColors=colors)
        fname = f"{n:02d}-{b['slug']}.html"
        page = (tpl.replace("{{TITLE}}", html.escape(b["title"])).replace("{{SCENE}}", b["slug"])
                .replace("{{CLIP}}", f"clips/b{n:02d}.mp4").replace("{{DATA}}", json.dumps(data, separators=(",", ":"))))
        if write_if_changed(out / fname, page):
            written.append(fname)
        shot_lines = "; ".join(f"{tc(s['a'])} {s['text']}" for s in b["shots"])
        n_bad = sum(1 for m in mv if not m["ok"])
        move_lines = ("; ".join(f"{m['id']} {m['name']} ({tc(m['t0'])}, {round((m['t1'] - m['t0']) * fps)}f, {m['conf']})"
                                for m in mv if m["ok"]) or "none verified") + (f" ({n_bad} unverified hidden)" if n_bad else "")
        feel = (b.get("feeling") + " ") if b.get("feeling") else ""
        frames_meta.append(dict(file=fname, title=b["title"], duration=round(Z - A, 4),
                                notes=f"src {tc(A)} to {tc(Z)}, {round((Z - A) * fps)}f, energy {lab}. {feel}"
                                      f"Shots: {shot_lines}. Moves: {move_lines}."))

    # stale beat frames from an earlier spec (only files this tool wrote)
    keep = {m["file"] for m in frames_meta}
    for p in out.glob("[0-9][0-9]-*.html"):
        if p.name not in keep and "window.__beat" in p.read_text():
            p.unlink()
            log(f"removed stale frame {p.name}")

    for f in (LIB / "overlay.css", LIB / "reference" / "sb.css", LIB / "reference" / "sb.js"):
        copy_if_changed(f, out / "lib" / f.name)
    made = encode_clips(video, out, beats, fps, total, src.get("sha256") or sha256(video))
    make_thumbs(video, out, beats, fps)

    lands = list(cuts) + [m["keyframes"]["land"] for m in moves if (m.get("keyframes") or {}).get("land") is not None]
    near = sum(1 for e in sfx_ok if lands and min(abs(e["t"] - x) for x in lands) <= 0.25)
    top = max(classes, key=lambda c: (sum(1 for e in sfx_ok if e["class"] == c), c)) if sfx_ok else None
    music = sound.get("music") or {}
    speech = fp.get("delivery") is not None
    if not src.get("has_audio"):
        audio = "silent"
    elif speech and music.get("present"):
        audio = f"voice over music at {round(bpm)} BPM" if bpm else "voice over music"
    elif speech:
        audio = "voice, no music"
    elif music.get("present"):
        audio = f"music only at {round(bpm)} BPM" if bpm else "music only"
    else:
        audio = "sound without music or speech"
    film_title = spec.get("title") or a.slug
    ms = motion.get("move_stats") or {}
    ov = dict(end=END, fps=fps, spec=bool(spec), summary=spec.get("summary"),
              film=dict(title=film_title, size=f"{src['width']}x{src['height']}",
                        fps=round(fps, 3) if fps % 1 else int(fps), audio=audio),
              beats=[dict(n=n, title=b["title"], a=b["a"], b=b["b"], energy=energy_label(means[n - 1])[0],
                          color=energy_label(means[n - 1])[1], shots=len(b["shots"])) for n, b in enumerate(beats, 1)],
              energy=energy, cuts=cuts, missed=missed, soft=soft,
              peaks=(motion.get("energy_stats") or {}).get("peak_times", []),
              sfx=[dict(t=e["t"], cls=e["class"]) for e in sfx_ok], sfxColors=colors,
              beatsGrid=[x["t"] for x in music_beats if x["down"]],
              stats=dict(cuts=len(cuts), missed=len(missed), soft=len(soft), moves=len(moves), high=ms.get("high_confidence", 0),
                         verified=sum(1 for v in move_v if v["verified"]),
                         sfx=len(sfx_ok), top_cls=top, top_n=sum(1 for e in sfx_ok if e["class"] == top), near=near,
                         bpm=round(bpm) if bpm else None, median_shot=(timing.get("shot_length") or {}).get("median") or END,
                         on_beat=music.get("cuts_on_beat_share")))
    ovt = ((LIB / "reference" / "overview.html").read_text()
           .replace("{{TITLE}}", html.escape(frames_meta[0]["title"])).replace("{{DATA}}", json.dumps(ov, separators=(",", ":"))))
    if write_if_changed(out / "00-overview.html", ovt):
        written.append("00-overview.html")
    board = dict(title=spec.get("board_title") or f"{film_title} reference, beat by beat", size="1920x1080", fps=round(fps, 3) if fps else 24, frames=frames_meta)
    write_if_changed(out / "board.json", json.dumps(board, indent=1) + "\n")
    report = dict(
        fingerprint=dict(path=str(fp_path.resolve()), sha256=sha256(fp_path), cuts=len(fp_cuts)),
        cuts=dict(checked=len(cut_v), moved=[c for c in cut_v if c["status"] == "moved"], dropped=[c for c in cut_v if c["status"] == "dropped"]),
        moves=dict(checked=len(move_v), bars_verified=sum(v["verified"] for v in move_v), boxes_verified=sum(v["box"] for v in move_v),
                   trimmed=[dict(id=f"m{i:02d}", t0=moves[i]["t0"], t1=moves[i]["t1"], to=[round(v["t0"], 4), round(v["t1"], 4)])
                            for i, v in enumerate(move_v) if v["trimmed"]],
                   unverified=[dict(id=f"m{i:02d}", t0=moves[i]["t0"], t1=moves[i]["t1"], property=moves[i]["property"],
                                    confidence=moves[i]["confidence"], why=v["reason"]) for i, v in enumerate(move_v) if not v["verified"]],
                   box_hidden=[dict(id=f"m{i:02d}", why=v["reason"]) for i, v in enumerate(move_v) if v["verified"] and not v["box"]]),
        sfx=dict(checked=len(sfx), moved=[dict(t=e["t_orig"], to=round(e["t"], 4), cls=e["class"]) for e in sfx if e["moved"]],
                 dropped=[dict(t=e["t_orig"], cls=e["class"]) for e in sfx if not e["ok"]]))
    if a.verify:
        rep = checks.sync_report(out, video, fps, fp_cuts, cuts, work / "verify-sync")
        report["sync"] = rep
    write_if_changed(out / "verify.json", json.dumps(checks_json(report), indent=1) + "\n")
    log(f"{out}: {len(frames_meta)} frames, {len(written)} rewritten, {made} clips encoded, {len(cuts)} cuts "
        f"({len(report['cuts']['moved'])} moved, {len(report['cuts']['dropped'])} dropped), {len(missed)} missed, {len(soft)} soft, "
        f"{len(moves)} moves ({report['moves']['bars_verified']} verified, {len(report['moves']['trimmed'])} trimmed, "
        f"{report['moves']['boxes_verified']} boxes), {len(sfx)} sound events ({len(report['sfx']['moved'])} snapped, "
        f"{len(report['sfx']['dropped'])} hidden), {len(named)} moves named")
    failed = False
    if a.verify:
        r = report["sync"]
        lead = r["playback_lead_frames"]
        src_ok = r["source"]["overview_draws_them"] and r["source"]["beats_draw_them"]
        log(f"verify: {r['seeks']} seeks ({r['seeks_at_cuts']} beside cuts), {r['wrong']} show the wrong frame {r['offsets'] or ''}; "
            f"playback overlay lead mean {lead['mean']:.2f} frames, max {lead['max']:.2f}; "
            f"pages draw the fingerprint's cuts: {'yes' if src_ok else 'NO'}; page errors {len(r['errors'])}")
        failed = bool(r["wrong"] or lead["max"] > 0.5 or not src_ok or r["errors"])
    if a.register:
        name = a.name or f"{a.slug}-reference"
        url = subprocess.run([str(CANVAS), "add", str(out), "--name", name], capture_output=True, text=True, check=True).stdout.strip()
        print(url)
    else:
        print(out)
    if failed:
        sys.exit(1)


def checks_json(x):
    """Round floats for a stable verify.json."""
    if isinstance(x, dict):
        return {k: checks_json(v) for k, v in x.items()}
    if isinstance(x, list):
        return [checks_json(v) for v in x]
    if isinstance(x, float):
        return round(x, 4)
    return x


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--work", help="work folder (default work/<slug>)")
    ap.add_argument("--video", help="source video (default the fingerprint's source path, else work/<slug>/source.mp4)")
    ap.add_argument("--fingerprint")
    ap.add_argument("--grid", help="beat grid JSON (default work/<slug>/music-beats.json)")
    ap.add_argument("--spec", help="beats spec (default work/<slug>/beats.json)")
    ap.add_argument("--out", help="board folder (default work/<slug>/board)")
    ap.add_argument("--name", help="canvas board name (default <slug>-reference)")
    ap.add_argument("--beat-s", type=float, default=3.0, help="target beat length when there is no spec")
    ap.add_argument("--register", action="store_true", help="register the folder on the storyboard canvas")
    ap.add_argument("--verify", action="store_true", help="prove in Chrome that every page shows the frame its overlay claims")
    build(ap.parse_args())


if __name__ == "__main__":
    main()

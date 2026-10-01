"""Sound plan: place a style's sound effects and music bed under a new piece.

  sound-plan.py <scene-plan.json> --style-dir DIR --out sfx-plan.json
                [--music bed.mp3] [--beats beats.json] [--snap-beats 0.06] [--vo vo.mp3]

Reads the style's DIR/sound/palette.json (sfx.py palette) and the scene plan. Every
move becomes anchors at its start, peak-velocity and landing keyframes, and every
scene boundary after the first is a cut anchor. A move's property and keyframes
come from props.tweens when the move is grammar-composed (tween at and units in the
style's timing unit, peak velocity from the named easing's bezier), otherwise from
palette.move_map[name] when the capture recorded it, otherwise from the move name
and a four-unit default, flagged as estimated.

Which moves get a sound follows the binding rules: each rule carries the share of
that property's moves that had a sound in the source (coverage), and placement uses
error diffusion over the piece so the share is met without randomness. A property
the source never sounded, or a novel move, takes the style's dominant rule at the
source's overall sounded share. The event is placed at keyframe + offset_s, or for a
peak-aligned rule so the clip's own peak lands where the source's did. The density
cap keeps every 10 s window under the source's density_per_10s plus a quarter, and
drops the least-supported events first.

Gain is computed, not guessed: the source level relative to its reference (the voice
when it had one, else the bed) is reproduced against this piece's voice-over, or bed,
measured the same way sound.py measures (50 ms peak power of the clip, p90 of 50 ms
power over speech for the voice), so gain_db is what build-composition.mjs applies to
the clip. The bed's gain keeps the source's bed-to-voice loudness offset, and the
duck is the source's measured duck.

Output is what toolkit/lib/sfx.mjs reads:
  {"events": [{"clip", "t", "gain_db", "pan", "class", "move": "<scene>/<move>@<target>", ...}],
   "music": {"clip", "gain_db", "duck_db_under_vo"}, "stats": {...}}
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "measure"))
sys.path.insert(0, str(HERE))
import sound as S  # noqa: E402
from common import dumps, pct  # noqa: E402

TIME_REF = re.compile(r"^(word|beat|downbeat):(\d+)([+-]\d*\.?\d+)?$")
PROP_OF = {"x": "translate", "y": "translate", "xPercent": "translate", "yPercent": "translate",
           "scale": "scale", "scaleX": "scale", "scaleY": "scale", "opacity": "opacity", "autoAlpha": "opacity",
           "rotation": "rotate", "rotate": "rotate", "clipPath": "mask-wipe", "webkitClipPath": "mask-wipe",
           "filter": "opacity"}
NAME_HINTS = [("wipe", "mask-wipe"), ("mask", "mask-wipe"), ("reveal", "mask-wipe"), ("slide", "translate"),
              ("rise", "translate"), ("push", "translate"), ("drop", "translate"), ("enter", "translate"),
              ("whip", "translate"), ("pan", "translate"), ("scale", "scale"), ("zoom", "scale"), ("pop", "scale"),
              ("punch", "scale"), ("slam", "scale"), ("fade", "opacity"), ("blur", "opacity"), ("spin", "rotate"),
              ("rotate", "rotate"), ("tilt", "rotate"), ("type", "opacity"), ("count", "opacity")]


# ----------------------------------------------------------------------------- timing

def bezier_peak(b) -> float:
    """Progress share at which a cubic-bezier easing moves fastest."""
    if not (isinstance(b, (list, tuple)) and len(b) == 4):
        return 0.3
    x1, y1, x2, y2 = b
    s = np.linspace(0, 1, 401)
    bx = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
    by = 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s ** 2 * y2 + s ** 3
    v = np.gradient(by) / np.maximum(np.gradient(bx), 1e-6)
    return float(bx[int(np.argmax(v))])


def resolve_t(t, words, beats) -> float:
    if isinstance(t, (int, float)):
        return float(t)
    m = TIME_REF.match(str(t))
    if not m:
        raise SystemExit(f"cannot resolve time {t!r}")
    off = float(m.group(3) or 0)
    i = int(m.group(2))
    if m.group(1) == "word":
        return float(words[i]["start"]) + off
    lst = (beats or {}).get("beats" if m.group(1) == "beat" else "downbeats") or []
    if i >= len(lst):
        raise SystemExit(f"{t!r} needs a beat grid with at least {i + 1} entries (--beats)")
    return float(lst[i]) + off


def anchors_of(plan: dict, style: dict, beats) -> list:
    tokens = style.get("tokens", {})
    unit = (tokens.get("timing", {}).get("unit_ms") or 100) / 1000.0
    eases = tokens.get("easings", {})
    mm = style.get("move_map", {})
    words = (plan.get("vo") or {}).get("words") or []
    out = []
    for si, sc in enumerate(plan["scenes"]):
        if si > 0:
            out.append({"t": float(sc["start"]), "key": "cut", "property": "cut", "move": None, "novel": False,
                        "estimated": False})
        for mv in sc.get("moves", []):
            t0 = resolve_t(mv["t"], words, beats)
            props = mv.get("props") or {}
            ref = f"{sc['id']}/{mv['name']}@{mv['target']}"
            est = False
            if props.get("tweens"):
                prop_counts = {}
                starts, ends, peaks = [], [], []
                for tw in props["tweens"]:
                    keys = set((tw.get("to") or {}).keys()) | set((tw.get("from") or {}).keys())
                    for k in keys:
                        if k in PROP_OF:
                            prop_counts[PROP_OF[k]] = prop_counts.get(PROP_OF[k], 0) + 1
                    a = t0 + unit * float(tw.get("at", 0) or 0)
                    d = unit * float(tw.get("units", 1) or 1)
                    starts.append(a)
                    ends.append(a + d)
                    peaks.append(a + d * bezier_peak(eases.get(tw.get("ease"))))
                prop = max(prop_counts, key=prop_counts.get) if prop_counts else "opacity"
                kf = {"start": min(starts), "peak": peaks[int(np.argmin(starts))], "land": max(ends)}
            else:
                info = mm.get(mv["name"], {})
                prop = info.get("property") or next((p for h, p in NAME_HINTS if h in mv["name"]), "translate")
                dur = float(info.get("duration_s") or props.get("duration") or unit * float(props.get("units", 4)))
                pk = float(info.get("peak_frac", 0.3))
                est = "duration_s" not in info
                kf = {"start": t0, "peak": t0 + pk * dur, "land": t0 + dur}
            for key, t in kf.items():
                out.append({"t": t, "key": key, "property": prop, "move": ref, "novel": bool(mv.get("novel")),
                            "estimated": est, "override": mv.get("sfx")})
    out.sort(key=lambda a: (a["t"], a["key"]))
    return out


# ----------------------------------------------------------------------------- levels

def load(path) -> np.ndarray:
    import sfx
    return sfx.load(path)


def p90_50ms(x: np.ndarray, gate_db: float | None = 30.0) -> float:
    """p90 of 50 ms power in sound.py's mel units, over frames within gate_db of the
    loudest (speech frames for a voice-over)."""
    fb, _ = S.mel_bank()
    M = fb @ (S.power_spec(x[:, 0]) + S.power_spec(x[:, 1]))
    w = max(1, int(0.05 * S.FPS))
    p = np.convolve(M.sum(0), np.ones(w) / w, "same")
    db = 10 * np.log10(p + 1e-14)
    if gate_db is not None:
        p = p[db > db.max() - gate_db]
    return float(10 * np.log10(np.percentile(p, 90) + 1e-14))


def peak_50ms(x: np.ndarray) -> float:
    fb, _ = S.mel_bank()
    M = fb @ (S.power_spec(x[:, 0]) + S.power_spec(x[:, 1]))
    w = max(1, int(0.05 * S.FPS))
    return float(10 * np.log10(np.convolve(M.sum(0), np.ones(w) / w, "same").max() + 1e-14))


# ----------------------------------------------------------------------------- placement

def choose_rule(prop: str, key: str, rules: list, dominant: dict | None):
    cands = [r for r in rules if r["move_property"] == prop and r["key"] == key]
    return cands[0] if cands else None


def plan_sounds(plan_path: str, style_dir: str, out: str, music: str | None, beats_path: str | None,
                snap: float, vo_path: str | None) -> dict:
    planp = Path(plan_path).resolve()
    plan = json.loads(planp.read_text())
    sd = Path(style_dir).resolve()
    pal = json.loads((sd / "sound" / "palette.json").read_text())
    style = {"tokens": json.loads((sd / "tokens.json").read_text()) if (sd / "tokens.json").exists() else {},
             "move_map": pal.get("move_map", {})}
    beats = None
    bp = beats_path or ((plan.get("music") or {}).get("beats") if isinstance((plan.get("music") or {}).get("beats"), str) else None)
    if bp:
        bpp = Path(bp) if Path(bp).is_absolute() or Path(bp).exists() else planp.parent / bp
        beats = json.loads(bpp.read_text())
    elif isinstance((plan.get("music") or {}).get("beats"), dict):
        beats = plan["music"]["beats"]
    anchors = anchors_of(plan, style, beats)
    rules = pal["binding_rules"]
    dur = float(plan["duration"])
    # which properties the source sounded, and how often
    n_moves = pal.get("moves_seen", {})
    sounded_share = (sum(r["n"] for r in rules) / max(1, sum(n_moves.values()))) if n_moves else 0.3
    dominant = max(rules, key=lambda r: r["n"]) if rules else None
    # one decision per move (and per cut): the best-supported rule among its keyframes
    by_move = {}
    for a in anchors:
        k = a["move"] or f"cut@{a['t']:.4f}"
        by_move.setdefault(k, []).append(a)
    acc = {}
    events, skipped = [], []
    for k, group in sorted(by_move.items(), key=lambda kv: min(a["t"] for a in kv[1])):
        prop = group[0]["property"]
        ov = group[0].get("override")
        if ov is False:
            skipped.append({"move": k, "reason": "plan sets sfx: false"})
            continue
        opts = [(r, a) for a in group for r in rules if r["move_property"] == prop and r["key"] == a["key"]]
        novel = any(a["novel"] for a in group)
        if opts:
            r, a = max(opts, key=lambda ra: (ra[0]["n"], -["cut", "land", "start", "peak"].index(ra[1]["key"])))
            cov = r.get("coverage") or sounded_share
            origin_rule = "rule"
        elif dominant is not None and prop != "cut":
            # unseen property or novel move: the style's dominant sound, bound by its key
            key = dominant["key"] if dominant["key"] != "cut" else "land"
            a = next((x for x in group if x["key"] == key), group[0])
            r = dominant
            cov = sounded_share
            origin_rule = "dominant"
        else:
            continue
        acc[prop] = acc.get(prop, 0.0) + min(1.0, cov)
        if acc[prop] < 0.5:
            skipped.append({"move": k, "reason": f"coverage {cov:.2f} for {prop}"})
            continue
        acc[prop] -= 1.0
        events.append({"anchor": a, "rule": r, "origin_rule": origin_rule, "novel": novel})

    # clips, timing and gain
    import sfx
    vo_audio = vo_path or (plan.get("vo") or {}).get("audio")
    if vo_audio and not Path(vo_audio).is_absolute():
        vo_audio = str(planp.parent / vo_audio)
    level_ref = pal.get("level_ref", "vo")
    vo_ref = p90_50ms(load(vo_audio)) if vo_audio and Path(vo_audio).exists() else None
    bed = music_choice(sd, music)
    bed_gain, bed_ref = None, None
    src_music = pal.get("music") or {}
    src_vo = pal.get("vo") or {}
    if bed:
        bx = load(bed["clip"])
        bed_lufs = S.lufs(bx)
        if vo_audio and Path(vo_audio).exists() and src_music.get("lufs") is not None and src_vo.get("lufs") is not None:
            vo_lufs = S.lufs(load(vo_audio))
            bed_gain = (src_music["lufs"] - src_vo["lufs"]) + vo_lufs - bed_lufs
        elif src_music.get("lufs") is not None:
            bed_gain = src_music["lufs"] - bed_lufs
        else:
            bed_gain = -18.0
        bed_gain = float(min(12.0, bed_gain))
        bed_ref = p90_50ms(bx, gate_db=None) + bed_gain
    ref_db = vo_ref if (level_ref == "vo" and vo_ref is not None) else (bed_ref if bed_ref is not None else vo_ref)
    placed = []
    cache = {}
    for e in events:
        r, a = e["rule"], e["anchor"]
        cls = r["class"]
        if cls not in cache:
            try:
                cache[cls] = sfx.pick(str(sd), r["move_property"], cls, None)
            except SystemExit:
                cache[cls] = None
        pk = cache[cls]
        if pk is None:
            skipped.append({"move": a["move"], "reason": f"no clip for class {cls}; run sfx.py generate {sd} --class {cls}"})
            continue
        x = load(pk["clip"])
        prof = sfx.analyse(x)
        if r.get("align") == "peak" and r.get("peak_offset_s") is not None:
            t = a["t"] + r["peak_offset_s"] - prof["attack_ms"] / 1000.0
        else:
            t = a["t"] + (r.get("offset_s") or 0.0)
        snapped = False
        if beats and snap > 0 and beats.get("beats"):
            bt = np.array(beats["beats"])
            j = int(np.argmin(np.abs(bt - t)))
            if abs(bt[j] - t) <= snap:
                t, snapped = float(bt[j]), True
        tgt_lvl = r.get("level_db_rel_vo")
        if tgt_lvl is None:
            tgt_lvl = (pal["classes"].get(cls, {}).get("target") or {}).get("level_db_rel_vo")
        gain = 0.0
        if tgt_lvl is not None and ref_db is not None:
            gain = float(min(12.0, tgt_lvl + ref_db - peak_50ms(x)))
        ov = a.get("override") if isinstance(a.get("override"), dict) else None
        placed.append({"clip": pk["clip"], "t": max(0.0, min(dur - 0.01, t)), "gain_db": gain,
                       "pan": float(r.get("pan") if r.get("pan") is not None else pk.get("pan") or 0.0),
                       "class": cls, "move": a["move"], "key": a["key"], "origin": pk["origin"],
                       "rule": f"{r['move_property']}/{r['class']}/{r['key']}", "rule_n": r["n"],
                       "binding": e["origin_rule"], "novel": e["novel"], "snapped": snapped,
                       "estimated_keyframes": a["estimated"], **({"override": True} if ov else {})})
    placed.sort(key=lambda e: e["t"])
    placed, dropped = density_cap(placed, pal["density_per_10s"], dur)
    res = {"events": [{k: v for k, v in e.items()} for e in placed],
           "music": ({"clip": bed["clip"], "gain_db": bed_gain,
                      "duck_db_under_vo": (src_music.get("duck_db_under_vo") or 0.0) if vo_audio else 0.0,
                      "from": bed["from"]} if bed else None),
           "level_ref": level_ref, "ref_db": ref_db,
           "stats": {"anchors": len(anchors), "moves": len(by_move), "placed": len(placed),
                     "density_per_10s": len(placed) / dur * 10, "target_density_per_10s": pal["density_per_10s"],
                     "dropped_by_density": dropped, "skipped": skipped,
                     "sounded_share_source": sounded_share}}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(dumps(res))
    return res


def density_cap(ev: list, density: float, dur: float):
    cap = max(1, int(math.ceil(density * 1.25)))
    keep = list(ev)
    dropped = []
    changed = True
    while changed:
        changed = False
        for i, e in enumerate(keep):
            win = [x for x in keep if e["t"] <= x["t"] < e["t"] + 10.0]
            if len(win) > cap:
                worst = min(win, key=lambda x: (x["rule_n"], -x["t"]))
                keep.remove(worst)
                dropped.append({"t": worst["t"], "class": worst["class"], "move": worst["move"]})
                changed = True
                break
    # never two of one class within 60 ms
    out = []
    for e in keep:
        if out and e["class"] == out[-1]["class"] and e["t"] - out[-1]["t"] < 0.06:
            dropped.append({"t": e["t"], "class": e["class"], "move": e["move"]})
            continue
        out.append(e)
    return out, dropped


def music_choice(sd: Path, music: str | None):
    if music:
        return {"clip": str(Path(music).resolve()), "from": "--music"}
    g = sd / "sound" / "music" / "generated.json"
    if g.exists():
        best = json.loads(g.read_text())["best"]
        return {"clip": str((g.parent / best).resolve()), "from": "sound/music/generated.json"}
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--style-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--music", help="bed file; default the best in <style>/sound/music/generated.json")
    ap.add_argument("--beats", help="beat grid JSON (music.py writes one per bed)")
    ap.add_argument("--snap-beats", type=float, default=0.0, help="snap events within this many seconds to a beat")
    ap.add_argument("--vo", help="voice-over file when the plan's vo.audio is not set yet")
    a = ap.parse_args()
    r = plan_sounds(a.plan, a.style_dir, a.out, a.music, a.beats, a.snap_beats, a.vo)
    s = r["stats"]
    print(f"{s['placed']} events, {s['density_per_10s']:.1f}/10s against {s['target_density_per_10s']:.1f}, "
          f"{len(s['dropped_by_density'])} dropped by density, {len(s['skipped'])} moves left silent -> {a.out}")


if __name__ == "__main__":
    main()

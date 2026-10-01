#!/usr/bin/env python3
"""Imagery for styles whose look depends on photographs: on-subject stills in the
source's photographic look, graded into tolerance and cut out so HyperFrames can
layer type between subject and background and do all the motion.

  prompt   <style-dir> --subject "..." --shot close [--look editorial] [--room behind]
  generate <style-dir> --subject "..." --shot close --n 4 --size 1920x1080 --out <dir>
  generate --resume <dir>
  score    <candidates-dir> --style-dir <dir> [--look editorial] [--shot close]
  grade    <image> --style-dir <dir> [--look editorial] --out <graded.png>
  matte    <image> --out <dir> [--engine auto|local|fal]
  compose  --bg bg.png --fg fg.png --text "Word" --out still.png
  plates-from-source <style-dir> --shots 12,19 --out <dir> [--matte]

A style's imagery lives in <style>/imagery.json (from toolkit/measure/imagery.py)
and <style>/references/imagery.md (the written look, shot recipes and the source
content that never crosses). See toolkit/IMAGERY.md for the method.

Python runs through `uv run --project ~/motion-expert/toolkit python toolkit/imagery.py`.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "measure"))
from common import FFMPEG, dumps, frames_at_times, probe  # noqa: E402

# measure/imagery.py shares this file's name, so it is loaded by path.
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("measure_imagery", HERE / "measure" / "imagery.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

HF = ["npx", "-y", "hyperframes@0.8.101"]
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
DERIVED = re.compile(r"(graded|fg|bg|bg-clean|mask|still|sheet|composite)", re.I)

# fal endpoints, newest first. Ideogram v4.5 takes no reference image, so a style
# reference (aesthetic only, never content) routes to Ideogram v3, whose image_urls
# are documented as style references. Flux 2 Pro is the fallback when Ideogram
# fails for a reason other than the account.
IDEOGRAM = "ideogram/v4.5"
IDEOGRAM_STYLE_REF = "fal-ai/ideogram/v3"
FLUX = "fal-ai/flux-2-pro"
BIREFNET = "fal-ai/birefnet/v2"
V45_SIZES = ["1024x1024", "1024x3072", "1120x896", "1152x2944", "1152x864", "1248x3328", "1248x832", "1280x3072",
             "1280x720", "1280x800", "1296x3168", "1440x2560", "1440x2880", "1440x720", "1600x2560", "1664x2496",
             "1728x2304", "1792x2240", "2048x2048", "2240x1792", "2304x1728", "2496x1664", "2560x1440", "2560x1600",
             "2880x1440", "2944x1152", "3072x1024", "3072x1280", "3168x1296", "3328x1248", "720x1280", "720x1440",
             "800x1280", "832x1248", "864x1152", "896x1120"]


def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_env() -> dict:
    env = {}
    for p in (ROOT / ".env", Path.home() / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def read_rgb(path) -> np.ndarray:
    im = Image.open(path)
    from PIL import ImageOps
    im = ImageOps.exif_transpose(im).convert("RGB")
    return np.asarray(im).copy()


def write_rgb(path, rgb: np.ndarray):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(path)


# ====================================================================== style

class Style:
    """A style's imagery: imagery.json profile(s) plus references/imagery.md."""

    def __init__(self, style_dir: str, look: str | None = None):
        self.dir = Path(style_dir).resolve()
        cands = [self.dir / "imagery.json", self.dir / "references" / "imagery.json"]
        jp = next((p for p in cands if p.exists()), None)
        if not jp:
            die(f"no imagery.json in {self.dir} (run toolkit/measure/imagery.py --out {self.dir}/imagery.json)")
        self.json_path = jp
        self.data = json.loads(jp.read_text())
        looks = self.data.get("looks") or {}
        if look:
            if look not in looks:
                die(f"look '{look}' not in {jp.name}; it has {sorted(looks)}")
            self.look_name, self.profile = look, looks[look]
        else:
            self.look_name, self.profile = "all", self.data.get("look")
        if not self.profile:
            die(f"{jp} has no look profile")
        md = self.dir / "references" / "imagery.md"
        self.md = md.read_text() if md.exists() else ""
        self.sections = parse_md(self.md)

    def shots(self):
        idx = set(self.profile.get("shots") or [])
        return [s for s in self.data["shots"] if not idx or s["index"] in idx]

    def frame_path(self, shot) -> Path:
        return self.json_path.parent / shot["frame"]

    def never(self) -> list[str]:
        return [t for t in bullets(self.sections.get("never", "")) if t]

    def recipes(self) -> dict:
        return self.sections.get("shots_sub", {})


def strip_placeholders(text: str) -> str:
    return re.sub(r"\{\{[^}]*\}\}", "", text).strip()


def parse_md(md: str) -> dict:
    """## sections by lowercased heading; ### subsections under ## Shots."""
    out, cur, sub = {}, None, None
    shots = {}
    for line in md.splitlines():
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        h3 = re.match(r"^###\s+(.+?)\s*$", line)
        if h2 and not line.startswith("###"):
            cur, sub = h2.group(1).strip().lower(), None
            out[cur] = ""
            continue
        if h3 and cur == "shots":
            sub = h3.group(1).strip().lower()
            shots[sub] = ""
            continue
        if cur is None:
            continue
        if sub is not None:
            shots[sub] += line + "\n"
        else:
            out[cur] += line + "\n"
    out = {k: strip_placeholders(v) for k, v in out.items()}
    out["shots_sub"] = {k: strip_placeholders(v) for k, v in shots.items() if strip_placeholders(v)}
    return out


def bullets(text: str) -> list[str]:
    return [re.sub(r"^[-*]\s+", "", l).strip() for l in text.splitlines() if re.match(r"^\s*[-*]\s+", l)]


# ====================================================================== words

HUES = [(0, "magenta-pink"), (20, "rose"), (45, "peach"), (70, "amber"), (95, "olive-yellow"), (135, "green"),
        (190, "teal"), (240, "blue"), (290, "violet"), (330, "magenta"), (360, "magenta-pink")]


def hue_name(a, b) -> str:
    ang = math.degrees(math.atan2(b, a)) % 360
    name = HUES[0][1]
    for start, n in HUES:
        if ang >= start:
            name = n
    return name


def tint_words(a, b, zone) -> str | None:
    if a is None or b is None:
        return None
    c = math.hypot(a, b)
    if c < 3:
        return f"neutral {zone}"
    strength = "a faint" if c < 6 else "a soft" if c < 11 else "a clear"
    return f"{strength} {hue_name(a, b)} tint in the {zone}"


def colour_name(lab) -> str:
    L, a, b = lab
    c = math.hypot(a, b)
    light = "near-black" if L < 15 else "deep" if L < 35 else "mid" if L < 60 else "light" if L < 80 else "pale"
    if c < 6:
        tone = "warm grey" if b > 2 else "cool grey" if b < -2 else "grey"
        return tone if light in ("mid",) else f"{light} {tone}" if light not in ("near-black",) else "near-black"
    mood = "dusty" if c < 20 else "muted" if c < 32 else "saturated"
    return f"{light} {mood} {hue_name(a, b)}"


def lens_for(scale: str) -> str:
    return {"extreme-close": "100mm macro-portrait lens", "close": "85mm portrait lens",
            "medium": "50mm lens", "wide": "35mm lens", "extreme-wide": "24mm lens"}.get(scale, "50mm lens")


def look_words(style: Style, scale: str) -> dict:
    """Numbers to the words a photographer would use. Every threshold is written
    against the measures in measure/imagery.py so a reader can check the wording."""
    f = style.profile["features"]
    med = lambda k: f[k]["median"] if k in f else None  # noqa: E731
    w = {}
    tints = [t for t in (tint_words(med("grade.shadows_a"), med("grade.shadows_b"), "shadows"),
                         tint_words(med("grade.mids_a"), med("grade.mids_b"), "midtones"),
                         tint_words(med("grade.highlights_a"), med("grade.highlights_b"), "highlights")) if t]
    con = med("tone.contrast") or 0.22
    contrast = "low, flat contrast" if con < 0.17 else "gentle contrast" if con < 0.25 else "punchy contrast"
    bp, wp = med("tone.black_point") or 10, med("tone.white_point") or 240
    blacks = "milky lifted blacks" if bp > 24 else "softly lifted blacks" if bp > 13 else "rich deep blacks"
    whites = "rolled-off creamy highlights" if wp < 226 else "soft highlights" if wp < 242 else "clean bright whites"
    chroma = med("sat.chroma_mean") or 12
    sat = "muted, desaturated colour" if chroma < 12 else "natural colour" if chroma < 20 else "rich saturated colour"
    w["grade"] = f"{sat} with {contrast}, {blacks} and {whites}; " + ", ".join(tints)
    pal = style.profile.get("palette") or []
    w["palette"] = "palette of " + ", ".join(colour_name(p["lab"]) for p in pal[:5]) if pal else ""
    g = med("grain.amount")
    gs = med("grain.size") or 1.2
    if g is None or g < 0.15:
        w["grain"] = "clean, grainless"
    else:
        w["grain"] = ("fine" if gs < 1.4 else "medium" if gs < 2 else "coarse") + " 35mm film grain, shot on film"

    by = style.profile.get("by_scale", {})
    sc = by.get(scale) or {}
    keys = style.profile.get("light_keys", {})
    key = max(keys, key=keys.get) if keys else "mid"
    dirs = style.profile.get("light_directions", {})
    direction = sc.get("light_direction") or (max(dirs, key=dirs.get) if dirs else "frontal")
    shots = [s for s in style.shots() if s["comp"]["scale"] == scale] or style.shots()
    sc_con = float(np.median([s["light"]["subject_contrast"] for s in shots])) if shots else 30
    # subject_contrast on skin or the subject: the pilot's soft window light reads
    # 34 to 64, a hard sun slash 79.
    quality = "soft diffused" if sc_con < 40 else "soft directional" if sc_con < 65 else "hard"
    keyw = {"high": "bright high-key", "mid": "natural mid-key", "low": "moody low-key"}[key]
    side = {"from left": "from the left", "from right": "from the right", "from above": "from above",
            "from below": "from below", "frontal": "from the front"}[direction]
    w["light"] = f"{keyw} exposure, {quality} light falling {side}"

    fs = sc.get("focus_share", med("focus.focus_share") or 0.4)
    dof = ("very shallow depth of field, background melting into soft blur" if fs < 0.3 else
           "shallow depth of field, background gently out of focus" if fs < 0.45 else
           "moderate depth of field, background slightly soft" if fs < 0.65 else "deep focus, everything sharp")
    w["lens"] = f"{lens_for(scale)}, {dof}"

    x = sc.get("x", med("comp.x") or 0.5)
    hr = sc.get("headroom", med("comp.headroom") or 0.15)
    place = "subject centred in the frame" if 0.4 <= x <= 0.6 else \
        ("subject on the left third" if x < 0.4 else "subject on the right third")
    head = ("cropped tight at the top edge" if hr < 0.06 else "with little headroom" if hr < 0.14
            else "with modest headroom" if hr < 0.24 else "with generous headroom")
    scale_words = {"extreme-close": "extreme close-up", "close": "close-up", "medium": "medium shot",
                   "wide": "wide shot", "extreme-wide": "extreme wide establishing shot"}.get(scale, scale)
    w["composition"] = f"{scale_words}, {place} {head}, 16:9 frame"
    return w


ROOM = {
    "behind": "uncluttered plain background directly behind and above the subject, leaving clear space where a "
              "large headline can sit behind the subject",
    "left": "clean empty space on the left half of the frame",
    "right": "clean empty space on the right half of the frame",
    "top": "clean empty space across the top third of the frame",
}


def scale_of(style: Style, shot: str | None) -> str | None:
    """The shot scale a shot name means: itself when it is a scale, else the
    `scale:` line of its recipe under ## Shots."""
    if not shot:
        return None
    rec = style.recipes().get(shot.lower(), "")
    m = re.match(r"^scale:\s*([\w-]+)", rec) if rec else None
    sc = m.group(1) if m else shot
    return sc if sc in style.profile.get("by_scale", {}) else None


def build_prompt(style: Style, subject: str, shot: str, room: str | None = None) -> dict:
    recipes = style.recipes()
    recipe = recipes.get(shot.lower(), "")
    scale = shot
    m = re.match(r"^scale:\s*([\w-]+)\s*$", recipe.splitlines()[0]) if recipe else None
    if m:
        scale = m.group(1)
        recipe = "\n".join(recipe.splitlines()[1:]).strip()
    if scale not in ("extreme-close", "close", "medium", "wide", "extreme-wide"):
        scale = "close" if "close" in scale else "medium"
    w = look_words(style, scale)
    # "## Look <name>" overrides "## Look" for that named look group.
    look_para = style.sections.get(f"look {style.look_name}", style.sections.get("look", ""))
    parts = [subject.strip().rstrip(".")]
    if recipe:
        parts.append(" ".join(recipe.split()))
    parts += [w["composition"], w["lens"], w["light"]]
    if look_para:
        parts.append(" ".join(look_para.split()))
    parts += [f"Colour grade: {w['grade']}", w["palette"], w["grain"]]
    if room:
        parts.append(ROOM.get(room, room))
    avoid = bullets(style.sections.get("avoid", "")) or ["text", "lettering", "logos", "watermarks"]
    parts.append("No " + ", no ".join(a.rstrip(".") for a in avoid))
    parts = [p.strip().rstrip(".") for p in parts if p.strip()]
    prompt = ". ".join(p[0].upper() + p[1:] for p in parts) + "."
    banned = [t for t in style.never() if re.search(r"\b" + re.escape(t) + r"\b", prompt, re.I)]
    return {"prompt": prompt, "subject": subject, "shot": shot, "scale": scale, "look": style.look_name,
            "room": room, "words": w, "banned_hits": banned}


# ====================================================================== fal

class NoCredits(Exception):
    """The account cannot run the job (no credit, or the key was refused). The job
    stays queued for --resume."""


class FalError(Exception):
    pass


def fal_key() -> str:
    k = os.environ.get("FAL_KEY") or load_env().get("FAL_KEY")
    if not k:
        die("FAL_KEY missing from ~/motion-expert/.env and ~/.env")
    return k


def fal_run(model: str, args: dict, timeout=600) -> dict:
    """Submit to the fal queue and wait. Raises NoCredits on an account or balance
    refusal (401, 402, 403, or a body naming balance, credit or billing) and
    FalError on anything else."""
    import requests
    h = {"Authorization": f"Key {fal_key()}", "Content-Type": "application/json"}

    def check(r):
        if r.status_code < 300:
            return
        body = r.text[:600]
        if r.status_code == 401:
            raise NoCredits(f"fal: key rejected ({r.status_code}: {body})")
        if r.status_code in (402, 403) or re.search(r"balance|credit|billing|locked|payment", body, re.I):
            raise NoCredits(f"fal: no credits ({r.status_code}: {body})")
        raise FalError(f"fal {model} {r.status_code}: {body}")
    r = requests.post(f"https://queue.fal.run/{model}", headers=h, json=args, timeout=60)
    check(r)
    sub = r.json()
    status_url, resp_url = sub["status_url"], sub["response_url"]
    t0 = time.time()
    while True:
        s = requests.get(status_url, headers=h, timeout=60)
        check(s)
        st = s.json()
        if st.get("status") == "COMPLETED":
            break
        if time.time() - t0 > timeout:
            raise FalError(f"fal {model} timed out after {timeout}s ({sub.get('request_id')})")
        time.sleep(2)
    res = requests.get(resp_url, headers=h, timeout=120)
    check(res)
    out = res.json()
    out["_request_id"] = sub.get("request_id")
    out["_metrics"] = st.get("metrics")
    return out


def download(url: str, dest: Path):
    import requests
    if url.startswith("data:"):
        dest.write_bytes(base64.b64decode(url.split(",", 1)[1]))
        return
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)


def data_uri(path: Path, long_side=1280) -> str:
    rgb = read_rgb(path)
    rgb = M.resize_long(rgb, long_side)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def v45_size(w: int, h: int) -> str:
    """The smallest supported v4.5 size at the same aspect that covers w x h, else
    the closest aspect."""
    sizes = [tuple(map(int, s.split("x"))) for s in V45_SIZES]
    same = [s for s in sizes if abs(s[0] / s[1] - w / h) < 0.01 and s[0] >= w and s[1] >= h]
    if same:
        s = min(same, key=lambda s: s[0] * s[1])
    else:
        s = min(sizes, key=lambda s: (abs(math.log((s[0] / s[1]) / (w / h))), -s[0] * s[1]))
    return f"{s[0]}x{s[1]}"


def job_args(model: str, prompt: str, seed: int, size: tuple[int, int], style_refs: list[str] | None,
             quality: str) -> dict:
    w, h = size
    if model == IDEOGRAM:
        vw, vh = map(int, v45_size(w, h).split("x"))
        return {"prompt": prompt, "seed": seed, "num_images": 1, "image_size": {"width": vw, "height": vh},
                "quality": quality, "enable_prompt_expansion": False}
    if model == IDEOGRAM_STYLE_REF:
        return {"prompt": prompt, "seed": seed, "num_images": 1, "image_size": {"width": w, "height": h},
                "rendering_speed": "QUALITY" if quality == "high" else "BALANCED", "style": "REALISTIC",
                "expand_prompt": False, "image_urls": style_refs or [],
                "negative_prompt": "text, lettering, logo, watermark"}
    return {"prompt": prompt, "seed": seed, "image_size": {"width": w, "height": h}, "output_format": "png",
            "safety_tolerance": "2"}


def run_jobs(out: Path) -> int:
    """Run every queued job in out/jobs.json. Returns the number still queued."""
    jf = out / "jobs.json"
    jobs = json.loads(jf.read_text())
    for job in jobs["jobs"]:
        if job["status"] == "done":
            continue
        chain = [job["model"]] + [m for m in job.get("fallbacks", []) if m != job["model"]]
        for model in chain:
            args = job["args"] if model == job["model"] else job_args(
                model, job["prompt"], job["seed"], tuple(job["size"]), None, job.get("quality", "high"))
            try:
                t0 = time.time()
                res = fal_run(model, args)
            except NoCredits as e:
                job["status"] = "queued"
                job["error"] = str(e)
                jf.write_text(dumps(jobs))
                print(str(e).split(" (")[0], file=sys.stderr)
                print(f"queued {sum(j['status'] != 'done' for j in jobs['jobs'])} job(s) in {jf}; "
                      f"run `imagery.py generate --resume {out}` once the account has credit", file=sys.stderr)
                return sum(j["status"] != "done" for j in jobs["jobs"])
            except FalError as e:
                job.setdefault("errors", []).append(str(e))
                print(f"{job['id']}: {model} failed, {'trying fallback' if model != chain[-1] else 'giving up'}: {e}",
                      file=sys.stderr)
                continue
            raw = out / f"{job['id']}.raw.png"
            download(res["images"][0]["url"], raw)
            rgb = read_rgb(raw)
            w, h = job["size"]
            if rgb.shape[1] != w or rgb.shape[0] != h:
                # cover-fit to the exact frame, then Lanczos
                im = Image.fromarray(rgb)
                s = max(w / im.width, h / im.height)
                im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
                l, t = (im.width - w) // 2, (im.height - h) // 2
                im = im.crop((l, t, l + w, t + h))
                rgb = np.asarray(im)
            final = out / f"{job['id']}.png"
            write_rgb(final, rgb)
            raw.unlink(missing_ok=True)
            side = {"id": job["id"], "model": model, "seed": res.get("seed", job["seed"]), "prompt": job["prompt"],
                    "args": {k: v for k, v in args.items() if k != "image_urls"},
                    "style_refs": job.get("style_ref_frames"), "subject": job["subject"], "shot": job["shot"],
                    "look": job["look"], "size": job["size"], "request_id": res.get("_request_id"),
                    "inference_s": (res.get("_metrics") or {}).get("inference_time"),
                    "wall_s": round(time.time() - t0, 1), "file": final.name}
            (out / f"{job['id']}.json").write_text(dumps(side))
            job.update(status="done", file=final.name, model_used=model, error=None)
            jf.write_text(dumps(jobs))
            print(f"{job['id']}: {model} seed {side['seed']} -> {final}", file=sys.stderr)
            break
        else:
            job["status"] = "failed"
            jf.write_text(dumps(jobs))
    return sum(j["status"] != "done" for j in jobs["jobs"])


# ====================================================================== score

def candidates_in(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXTS and not DERIVED.search(p.stem)
                  and not p.name.endswith(".raw.png"))


def sidecar(p: Path) -> dict:
    j = p.with_suffix(".json")
    return json.loads(j.read_text()) if j.exists() else {}


def label(img: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    except OSError:
        f = ImageFont.load_default()
    tw = d.textlength(text, font=f)
    d.rectangle([0, 0, tw + 12, 26], fill=(0, 0, 0))
    d.text((6, 3), text, fill=(255, 220, 0), font=f)
    return img


def sheet(rows: list[list[tuple[Image.Image, str]]], dest: Path, tile=(480, 270)):
    cols = max(len(r) for r in rows)
    out = Image.new("RGB", (tile[0] * cols, tile[1] * len(rows)), (0, 0, 0))
    for j, row in enumerate(rows):
        for i, (im, text) in enumerate(row):
            t = im.convert("RGB").copy()
            t.thumbnail(tile)
            out.paste(label(t, text), (i * tile[0], j * tile[1]))
    out.save(dest, quality=88)


def cmd_score(a):
    style = Style(a.style_dir, a.look)
    d = Path(a.candidates)
    rows = []
    for p in candidates_in(d):
        sc = sidecar(p)
        shot = a.shot or sc.get("shot")
        m = M.measure_image(read_rgb(p))
        dist = M.distance(m, style.profile, scale=scale_of(style, shot))
        rows.append({"file": p.name, "shot": shot, "distance": dist["distance"], "inside": dist["inside"],
                     "of": dist["of"], "kind": m["kind"], "scale": m["comp"]["scale"],
                     "worst": sorted(((k, v["z"]) for k, v in dist["features"].items() if v["z"] > 0),
                                     key=lambda kv: -kv[1])[:5],
                     "features": dist["features"]})
    rows.sort(key=lambda r: r["distance"])
    res = {"style": str(style.dir), "look": style.look_name, "ranked": rows}
    (d / "score.json").write_text(dumps(res))
    print(f"look '{style.look_name}', {len(rows)} candidate(s), lower is closer:")
    for r in rows:
        worst = ", ".join(f"{k} {z:.1f}" for k, z in r["worst"])
        print(f"  {r['distance']:.3f}  {r['inside']}/{r['of']} in band  {r['file']}  ({r['scale']})  worst: {worst}")
    src = [(Image.open(style.frame_path(s)), f"source shot {s['index']}") for s in style.shots()[:4]]
    cands = [(Image.open(d / r["file"]), f"{r['file']}  d={r['distance']:.2f}") for r in rows[:4]]
    sheet([src, cands], d / "sheet.jpg")
    print(f"wrote {d / 'score.json'} and {d / 'sheet.jpg'} (top row source frames, bottom row candidates)")


# ====================================================================== grade

ZONES = (("shadows", 16.5), ("mids", 49.5), ("highlights", 83.0))
MAX_TINT = 9.0  # Lab a*/b* units per zone


def zone_weights(L: np.ndarray) -> list[np.ndarray]:
    """Smooth shadow, midtone and highlight weights over L (0-100), summing to 1."""
    ws = [np.exp(-((L - c) / 18.0) ** 2) for _, c in ZONES]
    tot = sum(ws) + 1e-6
    return [w / tot for w in ws]


def l_curve(cand: np.ndarray, targ: np.ndarray, strength: float):
    """A smooth monotone curve on Lab L (0-100) taking the candidate's L
    percentiles toward the target's. Ends (1st, 5th, 95th, 99th) move fully, the
    middle halfway, because mid-grey is mostly the subject's own brightness and
    dragging it to the source's median would relight the scene. PCHIP keeps it
    monotone without the kinks a piecewise-linear curve bands on skin."""
    from scipy.interpolate import PchipInterpolator
    s = np.array([1.0, 1.0, 0.7, 0.5, 0.5, 0.5, 0.7, 1.0, 1.0])[: len(cand)] * strength
    move = s * (targ - cand)
    # The curve may lift blacks and roll off whites freely, but it may only stretch
    # them a little: a still with no true white has its brightest skin there, and
    # stretching that to the source's white point blows it out in blotches.
    lo_room = np.array([4, 4, 6, 8, 8, 8, 6, 4, 4])[: len(cand)]
    n = len(cand)
    for i in range(n):
        if i >= n // 2 + 1:      # upper percentiles: brightening is a stretch
            move[i] = min(move[i], lo_room[i])
        elif i < n // 2:         # lower percentiles: darkening is a stretch
            move[i] = max(move[i], -lo_room[i])
        else:
            move[i] = float(np.clip(move[i], -lo_room[i], lo_room[i]))
    # Percentiles that crowd together (a flat backdrop fills the 25th to 90th of
    # a portrait) would give the curve a cliff between them, and skin crossing
    # that cliff posterises. Control points closer than 3 L are merged, and every
    # move shrinks together until no segment's slope leaves 0.7 to 1.4.
    xs0 = np.concatenate([[0.0], cand, [100.0]])
    mv0 = np.concatenate([[0.0], move, [0.0]])
    xs, mv = [xs0[0]], [mv0[0]]
    for x, m_ in zip(xs0[1:], mv0[1:]):
        if x - xs[-1] < 3.0 and x < 100.0:
            mv[-1] = (mv[-1] + m_) / 2 if len(xs) > 1 else mv[-1]
            continue
        xs.append(x)
        mv.append(m_)
    xs, mv = np.array(xs), np.array(mv)
    for _ in range(30):
        ys = xs + mv
        slope = np.diff(ys) / np.maximum(1e-6, np.diff(xs))
        if slope.min() >= 0.7 and slope.max() <= 1.4:
            break
        mv *= 0.85
    ys = np.maximum.accumulate(xs + mv)
    if xs[-1] < 100.0:
        xs, ys = np.append(xs, 100.0), np.append(ys, 100.0)
    return PchipInterpolator(xs, ys)


def apply_grade(rgb: np.ndarray, curve, deltas: dict, sat_k: float) -> np.ndarray:
    """Tone on L, chroma scale, then zone tints, all in Lab, back to sRGB."""
    lab = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)
    if curve is not None:
        lab[..., 0] = np.clip(curve(lab[..., 0]), 0, 100)
    L = lab[..., 0]
    lab[..., 1] *= sat_k
    lab[..., 2] *= sat_k
    for (zone, _), w in zip(ZONES, zone_weights(L)):
        lab[..., 1] += w * deltas[zone][0]
        lab[..., 2] += w * deltas[zone][1]
    out = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB) * 255.0
    return np.clip(out, 0, 255)


def grain_field(shape, size_px: float, seed: int, chroma: float) -> np.ndarray:
    """Unit-deviation luma grain with the given correlation size, plus a weaker
    chroma component, as an H x W x 3 offset field. Seeded, so deterministic."""
    rng = np.random.default_rng(seed)
    h, w = shape[:2]
    sigma = max(0.0, (size_px - 0.9) * 0.9)

    def field():
        n = rng.standard_normal((h, w)).astype(np.float32)
        if sigma > 0.05:
            n = cv2.GaussianBlur(n, (0, 0), sigma)
        return n / (n.std() + 1e-6)
    lum = field()
    out = np.repeat(lum[..., None], 3, axis=2)
    if chroma > 0:
        c1, c2 = field(), field()
        k = 0.35 * min(1.0, chroma)
        out[..., 0] += k * c1
        out[..., 2] += k * c2
    return out


def encode_roundtrip(rgb: np.ndarray, crf: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    with tempfile.TemporaryDirectory() as td:
        src, mp4, back = Path(td) / "a.png", Path(td) / "a.mp4", Path(td) / "b.png"
        write_rgb(src, rgb)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", str(mp4)],
                       check=True)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(mp4), "-frames:v", "1", str(back)], check=True)
        out = read_rgb(back)
    if out.shape[:2] != (h, w):
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC)
    return out


def cmd_grade(a):
    style = Style(a.style_dir, a.look)
    prof = style.profile
    feats = prof["features"]
    src = Path(a.image)
    rgb0 = M.standard(read_rgb(src)).astype(np.float32)
    shot = a.shot or sidecar(src).get("shot")
    scale = scale_of(style, shot)
    m0 = M.measure_image(rgb0.astype(np.uint8))
    before = M.distance(m0, prof, scale=scale)

    # 1. tone curve on L, 2. split toning and saturation, closed loop: measure,
    #    correct the remaining error in each zone and in mean chroma, damped.
    curve = None
    if prof.get("L_curve") and m0["tone"].get("L_pcts"):
        curve = l_curve(np.array(m0["tone"]["L_pcts"]), np.array(prof["L_curve"]), a.strength)
    deltas = {z: [0.0, 0.0] for z, _ in ZONES}
    sat_k = 1.0
    for _ in range(4):
        graded = apply_grade(rgb0, curve, deltas, sat_k)
        m = M.measure_image(graded.astype(np.uint8))
        for z, _c in ZONES:
            for i, ch in enumerate("ab"):
                key = f"grade.{z}_{ch}"
                cur = m["grade"].get(f"{z}_{ch}")
                if key in feats and cur is not None:
                    deltas[z][i] += 0.8 * a.strength * (feats[key]["median"] - cur)
                    # A grade nudges a tint; a swing past MAX_TINT is a recolour,
                    # which is the prompt's job, and it tears skin when forced.
                    deltas[z][i] = float(np.clip(deltas[z][i], -MAX_TINT, MAX_TINT))
        tc, cc = feats["sat.chroma_mean"]["median"], m["sat"]["chroma_mean"]
        if cc > 1e-3:
            sat_k *= float(np.clip((tc / cc) ** (0.8 * a.strength), 0.85, 1.18))
        sat_k = float(np.clip(sat_k, 0.35, 1.6))
    rgb = apply_grade(rgb0, curve, deltas, sat_k)

    # 3. grain, calibrated through an encode round trip so the grain that survives
    #    the render's encode is the grain the source measured.
    gstat = feats.get("grain.amount")
    amp = 0.0
    if gstat and not a.no_grain:
        target = gstat["median"]
        size = feats.get("grain.size", {}).get("median", 1.2)
        seed = int(hashlib.sha256(src.read_bytes()).hexdigest()[:8], 16)
        field = grain_field(rgb.shape, size, seed, prof.get("grain_chroma", 0.6))

        def measured(A):
            img = np.clip(rgb + A * field, 0, 255).astype(np.uint8)
            if a.encode_crf >= 0:
                img = encode_roundtrip(img, a.encode_crf)
            return M.grain_of(img, M.to_lab(img))["amount"] or 0.0
        lo, hi = 0.0, 12.0
        base = measured(0.0)
        # A still noisier than the source is cleaned first (non-local means, the
        # lightest strength that brings it inside the band), then grain is added.
        denoise_h = 0
        if base > gstat["band"][1]:
            # capped at 4: stronger non-local means smears skin into plastic
            # blotches, which reads worse than grain a little over the band.
            for h_ in (2, 3, 4):
                den = cv2.fastNlMeansDenoisingColored(rgb.astype(np.uint8), None, h_, h_, 5, 15).astype(np.float32)
                img = den.astype(np.uint8)
                g_ = M.grain_of(encode_roundtrip(img, a.encode_crf) if a.encode_crf >= 0 else img,
                                M.to_lab(img))["amount"] or 0.0
                denoise_h = h_
                if g_ <= gstat["band"][1]:
                    break
            rgb = den
            base = measured(0.0)
        if base < target:
            for _ in range(9):
                mid = (lo + hi) / 2
                if measured(mid) < target:
                    lo = mid
                else:
                    hi = mid
            amp = (lo + hi) / 2
        rgb = np.clip(rgb + amp * field, 0, 255)

    out_rgb = rgb.astype(np.uint8)
    final = out_rgb if a.encode_crf < 0 else encode_roundtrip(out_rgb, a.encode_crf)
    m1 = M.measure_image(final)
    after = M.distance(m1, prof, scale=scale)
    out = Path(a.out)
    write_rgb(out, out_rgb)
    rep = {"input": str(src), "output": str(out), "look": style.look_name, "strength": a.strength,
           "tone": "PCHIP curve on Lab L, ends to target, mids halfway", "zone_deltas_ab": deltas, "saturation_k": sat_k,
           "grain_amplitude": amp, "denoise_h": denoise_h if gstat and not a.no_grain else 0, "grain_measured_after_encode": a.encode_crf >= 0, "encode_crf": a.encode_crf,
           "before": {"distance": before["distance"], "inside": before["inside"], "of": before["of"]},
           "after": {"distance": after["distance"], "inside": after["inside"], "of": after["of"]},
           "features_after": after["features"]}
    out.with_suffix(".json").write_text(dumps(rep))
    print(f"distance {before['distance']:.3f} ({before['inside']}/{before['of']} in band) -> "
          f"{after['distance']:.3f} ({after['inside']}/{after['of']}); grain amplitude {amp:.2f}; wrote {out}")
    outside = [(k, v) for k, v in after["features"].items() if not v["inside"]]
    for k, v in outside:
        print(f"  still outside: {k} {v['value']:.2f} vs band [{v['band'][0]:.2f}, {v['band'][1]:.2f}]")


# ====================================================================== matte

def fringe_share(rgb: np.ndarray, solid: np.ndarray) -> float:
    """Share of the matte's inner edge band (12 px inside the edge) whose colour
    matches the local background just outside it (Delta E under 6): background
    the matte kept, typically a chunk between loose hair or under a handle."""
    lab = M.to_lab(rgb)
    outside = (1 - solid).astype(np.float32)
    ring = cv2.dilate(solid, np.ones((51, 51), np.uint8)).astype(np.float32) * outside
    num = cv2.GaussianBlur(lab * ring[..., None], (0, 0), 20)
    den = cv2.GaussianBlur(ring, (0, 0), 20)[..., None] + 1e-6
    local_bg = num / den
    inner = solid.astype(bool) & ~cv2.erode(solid, np.ones((25, 25), np.uint8)).astype(bool)
    if inner.sum() < 100:
        return 0.0
    de = np.linalg.norm(lab - local_bg, axis=2)
    return float((de[inner] < 6).mean())


def dropped_focus(rgb: np.ndarray, solid: np.ndarray) -> float:
    """The largest in-focus pocket inside the matte's convex hull but outside the
    matte, as a share of the matte's area. The local model segments people only,
    so an object a person holds against themselves (in focus, in a concavity of
    the person) is cut away; out-of-focus background in the same pockets, and a
    pocket whose colour matches the surface just outside the hull (Delta E under
    6, a table continuing under a spout), do not count. Heuristic: on the pilot a
    held bottle read 8.6 from its surroundings and table pockets under a teapot
    about 4."""
    small = M.resize_long(rgb, 480)
    h, w = small.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 0.8)
    lap = cv2.GaussianBlur(np.abs(cv2.Laplacian(g, cv2.CV_32F)), (0, 0), 4)
    m = cv2.resize(solid, (w, h), interpolation=cv2.INTER_NEAREST)
    if m.sum() < 50:
        return 0.0
    inside_level = float(np.median(lap[m.astype(bool)]))
    sharp = lap > 0.6 * inside_level
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = np.zeros_like(m)
    for c in cnts:
        cv2.fillPoly(hull, [cv2.convexHull(c)], 1)
    pocket = (hull.astype(bool) & ~m.astype(bool) & sharp).astype(np.uint8)
    pocket = cv2.morphologyEx(pocket, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(pocket, 8)
    # A pocket that matches the surface just outside the hull is that surface
    # continuing (a table under a spout), not something the subject holds.
    labc = M.to_lab(small)
    ring = cv2.dilate(hull, np.ones((31, 31), np.uint8)).astype(bool) & ~hull.astype(bool)
    biggest = 0
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area <= biggest:
            continue
        comp = lab == i
        near = cv2.dilate(comp.astype(np.uint8), np.ones((61, 61), np.uint8)).astype(bool) & ring
        if near.sum() > 20:
            de = float(np.linalg.norm(labc[comp].mean(0) - labc[near].mean(0)))
            if de < 6:
                continue
        biggest = area
    return float(biggest / m.sum())


def matte_quality(alpha: np.ndarray, rgb: np.ndarray | None = None) -> dict:
    a = alpha.astype(np.float32) / 255.0
    solid = (a > 0.5).astype(np.uint8)
    cov = float(solid.mean())
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
    areas = sorted((int(s[cv2.CC_STAT_AREA]) for s in stats[1:]), reverse=True)
    total = sum(areas) or 1
    big = [x for x in areas if x > 0.001 * solid.size]
    inv = (1 - solid).astype(np.uint8)
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(inv, 8)
    h, w = solid.shape
    holes = 0
    for i in range(1, n2):
        x, y, ww, hh, area = st2[i]
        if x > 0 and y > 0 and x + ww < w and y + hh < h and area > 0.0005 * solid.size:
            holes += 1
    edge = cv2.morphologyEx(solid, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)).astype(bool)
    soft = (a > 0.05) & (a < 0.95)
    band = cv2.dilate(edge.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    soft_share = float(soft[band].mean()) if band.any() else 0.0
    cnts, _ = cv2.findContours(solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    rag = None
    if cnts:
        c = max(cnts, key=cv2.contourArea)
        per = cv2.arcLength(c, True)
        sm = cv2.GaussianBlur(solid.astype(np.float32), (0, 0), 6) > 0.5
        cs, _ = cv2.findContours(sm.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if cs:
            rag = float(per / max(1.0, cv2.arcLength(max(cs, key=cv2.contourArea), True)))
    largest = areas[0] / total if areas else 0.0
    fringe = fringe_share(rgb, solid) if rgb is not None else None
    dropped = dropped_focus(rgb, solid) if rgb is not None else None
    problems = []
    if dropped is not None and dropped > 0.04:
        problems.append(f"an in-focus pocket {dropped:.0%} the size of the matte sits inside its outline but was "
                        "cut away, probably an object the subject holds (the local model segments people only; "
                        "use --engine fal)")
    if fringe is not None and fringe > 0.15:
        problems.append(f"background kept along {fringe:.0%} of the inner edge")
    if cov < 0.01:
        problems.append("almost nothing kept")
    if cov > 0.92:
        problems.append("almost everything kept")
    if largest < 0.85:
        problems.append(f"subject split: largest piece is {largest:.0%} of the matte")
    if len(big) > 3:
        problems.append(f"{len(big)} separate pieces")
    if rag and rag > 1.6:
        problems.append(f"ragged edge (perimeter {rag:.2f}x its smoothed outline)")
    verdict = "poor" if (cov < 0.01 or cov > 0.92 or largest < 0.6) else ("fair" if problems else "good")
    return {"coverage": cov, "pieces": len(big), "largest_piece_share": largest, "holes": holes,
            "edge_soft_share": soft_share, "raggedness": rag, "fringe_share": fringe, "dropped_focus": dropped,
            "problems": problems,
            "verdict": verdict}


def matte_local(img: Path, out_png: Path) -> None:
    r = subprocess.run(HF + ["remove-background", str(img), "-o", str(out_png)], capture_output=True, text=True)
    if r.returncode != 0 or not out_png.exists():
        raise RuntimeError(f"hyperframes remove-background failed: {r.stderr[-600:] or r.stdout[-600:]}")


def matte_fal(img: Path, out_png: Path) -> None:
    res = fal_run(BIREFNET, {"image_url": data_uri(img, 2048), "model": "General Use (Heavy)",
                             "operating_resolution": "2048x2048", "output_format": "png", "refine_foreground": True})
    download(res["image"]["url"], out_png)


def cmd_matte(a):
    img = Path(a.image)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rgb = read_rgb(img)
    h, w = rgb.shape[:2]
    tried = []
    engines = ["local", "fal"] if a.engine == "auto" else [a.engine]
    chosen, alpha, q = None, None, None
    for eng in engines:
        tmp = out / f"_matte-{eng}.png"
        try:
            (matte_local if eng == "local" else matte_fal)(img, tmp)
        except NoCredits as e:
            tried.append({"engine": eng, "error": str(e).split(" (")[0]})
            continue
        except Exception as e:  # noqa: BLE001
            tried.append({"engine": eng, "error": str(e)[:300]})
            continue
        rgba = Image.open(tmp).convert("RGBA")
        if rgba.size != (w, h):
            rgba = rgba.resize((w, h), Image.LANCZOS)
        al = np.asarray(rgba)[..., 3]
        qq = matte_quality(al, rgb)
        tried.append({"engine": eng, **qq})
        tmp.unlink(missing_ok=True)
        rank = {"good": 2, "fair": 1, "poor": 0}
        if chosen is None or rank[qq["verdict"]] > rank[q["verdict"]]:
            chosen, alpha, q = eng, al, qq
        if qq["verdict"] == "good":
            break
    if alpha is None:
        die("no matte engine produced a result: " + json.dumps(tried))
    fg = np.dstack([rgb, alpha])
    Image.fromarray(fg, "RGBA").save(out / "fg.png")
    Image.fromarray(rgb).save(out / "bg.png")
    Image.fromarray(alpha).save(out / "mask.png")
    # A clean plate for parallax: the subject region filled from its surroundings.
    # Telea inpainting is soft over large areas, which is acceptable only because
    # the cutout covers all but the few percent of the hole that parallax reveals.
    hole = cv2.dilate((alpha > 8).astype(np.uint8), np.ones((15, 15), np.uint8))
    small = 960 / max(h, w)
    sm = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (int(w * small), int(h * small)), interpolation=cv2.INTER_AREA)
    hm = cv2.resize(hole, (int(w * small), int(h * small)), interpolation=cv2.INTER_NEAREST)
    filled = cv2.inpaint(sm, hm, 9, cv2.INPAINT_TELEA)
    filled = cv2.resize(filled, (w, h), interpolation=cv2.INTER_CUBIC)
    clean = np.where(hole[..., None] > 0, cv2.cvtColor(filled, cv2.COLOR_BGR2RGB), rgb)
    Image.fromarray(clean.astype(np.uint8)).save(out / "bg-clean.png")
    rep = {"image": str(img), "engine": chosen, "quality": q, "tried": tried, "size": [w, h],
           "files": {"fg": "fg.png", "bg": "bg.png", "bg_clean": "bg-clean.png", "mask": "mask.png"},
           "notes": "bg.png is the untouched still: stack it under the type and fg.png on top and the subject "
                    "occludes the type exactly while both plates move together. bg-clean.png has the subject "
                    "inpainted (soft) for parallax, where fg and bg move apart."}
    (out / "matte.json").write_text(dumps(rep))
    print(f"{chosen}: {q['verdict']}, coverage {q['coverage']:.1%}, {q['pieces']} piece(s), "
          f"largest {q['largest_piece_share']:.0%}, holes {q['holes']}, edge soft {q['edge_soft_share']:.0%}, "
          f"raggedness {q['raggedness'] or 0:.2f}, fringe {q['fringe_share'] or 0:.0%}, "
          f"dropped focus {q['dropped_focus'] or 0:.0%}" + (f"; {'; '.join(q['problems'])}" if q["problems"] else ""))
    for t in tried:
        if "error" in t:
            print(f"  {t['engine']}: {t['error']}")
    print(f"wrote fg.png, bg.png, bg-clean.png, mask.png in {out}")


# ====================================================================== compose

def find_font(name: str | None) -> str:
    if name and Path(name).exists():
        return name
    for p in ["~/.cache/hyperframes/fonts/instrument-serif", "/System/Library/Fonts/Supplemental/Georgia.ttf"]:
        p = Path(p).expanduser()
        if p.is_dir():
            fs = sorted(x for x in p.rglob("*") if x.suffix.lower() in (".ttf", ".otf") and "italic" not in x.name.lower())
            if fs:
                return str(fs[0])
        elif p.exists():
            return str(p)
    die("no serif font found; pass --font")


def cmd_compose(a):
    bg = Image.open(a.bg).convert("RGBA")
    fg = Image.open(a.fg).convert("RGBA").resize(bg.size, Image.LANCZOS)
    W, H = bg.size
    layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = ImageFont.truetype(find_font(a.font), int(a.size * H))
    box = d.textbbox((0, 0), a.text, font=font, anchor="ls")
    tw = box[2] - box[0]
    x = a.x * W - tw / 2
    y = a.y * H
    col = tuple(int(a.color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    d.text((x, y), a.text, font=font, fill=col, anchor="ls")
    out = Image.alpha_composite(bg, layer)
    if not a.front:
        out = Image.alpha_composite(out, fg)
    out.convert("RGB").save(a.out, quality=92)
    print(f"wrote {a.out}: bg, '{a.text}' ({Path(find_font(a.font)).name}), "
          f"{'no fg (type in front)' if a.front else 'fg cutout on top'}")


# ====================================================================== plates-from-source

def cmd_plates_from_source(a):
    style = Style(a.style_dir)
    video = a.video or style.data["source"]["path"]
    if not Path(video).exists():
        die(f"source video not found at {video}; pass --video")
    want = M.parse_ranges(a.shots)
    shots = [s for s in style.data["shots"] if s["index"] in want]
    if not shots:
        die("none of those shot indices exist in imagery.json")
    pr = probe(video)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = frames_at_times(video, [s["frame_t"] for s in shots], (pr["width"], pr["height"]), gray=False,
                             fps=pr["fps"])
    made = []
    for s, rgb in zip(shots, frames):
        name = f"calibration-only-shot-{s['index']:02d}.png"
        write_rgb(out / name, rgb)
        made.append({"shot": s["index"], "t": s["frame_t"], "file": name})
        if a.matte:
            ns = argparse.Namespace(image=str(out / name), out=str(out / f"calibration-only-shot-{s['index']:02d}"),
                                    engine=a.engine)
            cmd_matte(ns)
    marker = {"calibration_only": True, "never_ship": True, "source": video,
              "why": "Source frames rebuild the replica so the loop can prove the motion and layering match the "
                     "source. They are the source's content and never enter a novel piece; build a novel piece's "
                     "plates with generate, score, grade and matte.",
              "plates": made}
    (out / "CALIBRATION-ONLY.json").write_text(dumps(marker))
    print(f"wrote {len(made)} calibration-only plate(s) to {out}; never use them in a shipped piece")


# ====================================================================== cli

def cmd_prompt(a):
    style = Style(a.style_dir, a.look)
    p = build_prompt(style, a.subject, a.shot, a.room)
    if p["banned_hits"]:
        die(f"refused: the prompt names source content {p['banned_hits']} listed under Never in references/imagery.md", 2)
    if a.json:
        print(dumps(p), end="")
    else:
        print(p["prompt"])


def cmd_generate(a):
    if a.resume:
        out = Path(a.resume)
        if not (out / "jobs.json").exists():
            die(f"no jobs.json in {out}")
        left = run_jobs(out)
        sys.exit(3 if left else 0)
    if not (a.style_dir and a.subject and a.shot and a.out):
        die("generate needs <style-dir> --subject --shot --out (or --resume <dir>)")
    style = Style(a.style_dir, a.look)
    p = build_prompt(style, a.subject, a.shot, a.room)
    if p["banned_hits"]:
        die(f"refused: the prompt names source content {p['banned_hits']}", 2)
    w, h = map(int, a.size.lower().split("x"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    refs, ref_frames = None, None
    model = a.model or (IDEOGRAM_STYLE_REF if a.style_ref else IDEOGRAM)
    if a.style_ref:
        idx = M.parse_ranges(a.style_ref)
        shots = [s for s in style.data["shots"] if s["index"] in idx]
        ref_frames = [s["frame"] for s in shots]
        refs = [data_uri(style.frame_path(s), 1024) for s in shots]
    seed0 = a.seed if a.seed is not None else int(hashlib.sha256(p["prompt"].encode()).hexdigest()[:6], 16)
    jobs = []
    for i in range(a.n):
        seed = seed0 + i
        jobs.append({"id": f"cand-{i + 1:02d}", "status": "queued", "model": model,
                     "fallbacks": [FLUX] if not a.no_fallback else [], "prompt": p["prompt"], "seed": seed,
                     "size": [w, h], "quality": a.quality, "subject": a.subject, "shot": a.shot,
                     "look": style.look_name, "style_ref_frames": ref_frames,
                     "args": job_args(model, p["prompt"], seed, (w, h), refs, a.quality)})
    (out / "jobs.json").write_text(dumps({"style": str(style.dir), "prompt": p, "jobs": jobs}))
    (out / "prompt.txt").write_text(p["prompt"] + "\n")
    if a.queue_only:
        print(f"queued {len(jobs)} job(s) on {model} in {out / 'jobs.json'}; run `imagery.py generate --resume {out}`",
              file=sys.stderr)
        sys.exit(3)
    left = run_jobs(out)
    sys.exit(3 if left else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def style_args(p, positional=True):
        if positional:
            p.add_argument("style_dir", nargs="?")
        p.add_argument("--look", help="named look group in imagery.json (default: the union profile)")

    p = sub.add_parser("prompt", help="build a generation prompt from the style's imagery profile")
    style_args(p)
    p.add_argument("--subject", required=True)
    p.add_argument("--shot", required=True, help="close, medium, wide, extreme-close, or a recipe under ## Shots")
    p.add_argument("--room", help="behind, left, right or top: keep space for type")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_prompt)

    p = sub.add_parser("generate", help="generate candidate stills on fal")
    style_args(p)
    p.add_argument("--subject")
    p.add_argument("--shot")
    p.add_argument("--room")
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--size", default="1920x1080")
    p.add_argument("--out")
    p.add_argument("--seed", type=int)
    p.add_argument("--quality", default="medium", choices=["low", "medium", "high"],
                   help="Ideogram v4.5 tier: $0.03, $0.06, $0.22 per image on fal (Oct 2026)")
    p.add_argument("--model", help=f"override the endpoint (default {IDEOGRAM})")
    p.add_argument("--style-ref", help="shot indices to pass as STYLE references (routes to Ideogram v3)")
    p.add_argument("--no-fallback", action="store_true")
    p.add_argument("--resume", help="run the queued jobs in this folder")
    p.add_argument("--queue-only", action="store_true", help="write jobs.json and stop without calling fal")
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("score", help="rank candidates by distance to the look profile")
    p.add_argument("candidates")
    p.add_argument("--style-dir", required=True)
    p.add_argument("--look")
    p.add_argument("--shot")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("grade", help="pull one still into the look's tolerance")
    p.add_argument("image")
    p.add_argument("--style-dir", required=True)
    p.add_argument("--look")
    p.add_argument("--shot")
    p.add_argument("--out", required=True)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--encode-crf", type=int, default=18, help="x264 CRF for the grain round trip; -1 skips it")
    p.add_argument("--no-grain", action="store_true")
    p.set_defaults(fn=cmd_grade)

    p = sub.add_parser("matte", help="cut the subject out: fg.png, bg.png, bg-clean.png")
    p.add_argument("image")
    p.add_argument("--out", required=True)
    p.add_argument("--engine", default="auto", choices=["auto", "local", "fal"])
    p.set_defaults(fn=cmd_matte)

    p = sub.add_parser("compose", help="Pillow proof of the layering: bg, a word, fg")
    p.add_argument("--bg", required=True)
    p.add_argument("--fg", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--font")
    p.add_argument("--size", type=float, default=0.32, help="cap size as a share of frame height")
    p.add_argument("--x", type=float, default=0.5)
    p.add_argument("--y", type=float, default=0.62, help="baseline as a share of frame height")
    p.add_argument("--color", default="#ffffff")
    p.add_argument("--front", action="store_true", help="type in front (no fg), for comparison")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_compose)

    p = sub.add_parser("plates-from-source", help="calibration-only plates from the source's clean frames")
    p.add_argument("style_dir")
    p.add_argument("--shots", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--video")
    p.add_argument("--matte", action="store_true")
    p.add_argument("--engine", default="local", choices=["auto", "local", "fal"])
    p.set_defaults(fn=cmd_plates_from_source)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

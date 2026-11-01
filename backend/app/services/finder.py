"""Shot finder: for every shot in a list, search all analysed footage.

Two approaches (compared in docs/research_note.md):

- "baseline": plain CLIP. Cosine similarity between each frame and the shot description, best
  frame wins, window centred on it. No scenes, no quality, no look-alike handling.
- "hybrid" (default):
    1. Each frame is classified against *all* shots of the list, every shot's look-alike
       negatives and a few generic background classes (softmax over CLIP logits). A frame only
       scores high for a shot if it fits that shot better than every alternative explanation.
    2. Candidate windows of the shot's length slide inside detected scenes (never across a cut);
       window score = mean frame probability, weighted by measured quality (sharp/bright/steady).
    3. needs_audio shots must be confirmed by the speech transcript (keyword match with word
       timestamps); a visual look-alike without the spoken line is reported as missing.
    4. Shots are assigned greedily by confidence so two shots never use the same moment.
    5. Below the confidence threshold a shot is reported "missing" with the closest candidate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from app.core.config import settings
from app.pipeline.analyze import load_arrays, overall_quality

# Generic "none of the above" classes. Blur and darkness are deliberately NOT here: the measured
# quality score already handles them, and a "dark photo" class would wrongly reject dim but
# correct scenes (stage shows, evening events).
BACKGROUND = [
    "a random everyday scene",
    "a close-up of an object on a table",
    "an empty room",
]
LOGIT_SCALE = 100.0
NEG_MARGIN = 0.015  # cosine margin a look-alike needs before it suppresses a shot
_NEGATION = re.compile(r"\b(no|not|without|never|nobody|isn't|aren't|empty of)\b|n't\b", re.I)


@dataclass
class FootageFile:
    asset_id: str
    filename: str
    duration: float
    scenes: list[dict]
    transcript: dict
    t_c: np.ndarray
    emb: np.ndarray
    t_q: np.ndarray
    sharpness: np.ndarray
    brightness: np.ndarray
    stability: np.ndarray

    @classmethod
    def load(cls, asset_id: str, filename: str, analysis: dict) -> "FootageFile | None":
        arr = load_arrays(asset_id)
        if arr is None:
            return None
        return cls(asset_id, filename, analysis.get("duration", 0.0), analysis.get("scenes", []),
                   analysis.get("transcript", {}), arr["t_c"], arr["emb"].astype(np.float32),
                   arr["t_q"], arr["sharpness"], arr["brightness"], arr["stability"])

    def quality(self, a: float, b: float) -> dict:
        m = (self.t_q >= a) & (self.t_q <= b)
        if not m.any():
            m = np.abs(self.t_q - (a + b) / 2) == np.abs(self.t_q - (a + b) / 2).min()
        s, br, st = (float(x[m].mean()) for x in (self.sharpness, self.brightness, self.stability))
        return {"sharpness": round(s, 3), "brightness": round(br, 3), "stability": round(st, 3),
                "overall": overall_quality(s, br, st)}


@dataclass
class Candidate:
    file: FootageFile
    start: float
    end: float
    visual: float
    quality: dict
    score: float
    query: str = ""
    audio_text: str = ""
    notes: list[str] = field(default_factory=list)
    scene: float = -1.0  # start of the scene (take) this window belongs to

    def same_scene(self, other: "Candidate") -> bool:
        return self.file.asset_id == other.file.asset_id and self.scene == other.scene and self.scene >= 0

    def as_dict(self, with_quality: bool = True) -> dict:
        d = {"file": self.file.filename, "start": round(self.start, 2), "end": round(self.end, 2),
             "confidence": round(float(self.score), 3)}
        if with_quality:
            d["quality"] = self.quality
        d["reason"] = reason_text(self)
        return d


def _quality_words(q: dict) -> str:
    words = []
    words.append("sharp" if q["sharpness"] >= 0.6 else "soft focus" if q["sharpness"] >= 0.35 else "blurry")
    words.append("well lit" if q["brightness"] >= 0.8 else "dim" if q["brightness"] >= 0.45 else "too dark")
    words.append("steady" if q["stability"] >= 0.7 else "a little shaky" if q["stability"] >= 0.45 else "shaky")
    return ", ".join(words)


def reason_text(c: Candidate) -> str:
    parts = []
    if c.audio_text:
        parts.append(f"Heard: “{c.audio_text}”")
    if c.query:
        parts.append(f"looks like “{c.query}”")
    parts.append(_quality_words(c.quality))
    parts.extend(c.notes)
    text = "; ".join(parts)
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------- text side
def _prompts(q: str) -> list[str]:
    q = q.strip().rstrip(".")
    return [f"a photo of {q[0].lower() + q[1:]}", f"a video frame showing {q[0].lower() + q[1:]}"]


class _TextCache:
    """Encodes every prompt once, in one batch (text encoding dominated search time)."""

    def __init__(self, clip):
        self.clip, self.vecs = clip, {}

    def prime(self, texts: list[str]) -> None:
        todo = list(dict.fromkeys(p for t in texts for p in _prompts(t) if p not in self.vecs))
        for i in range(0, len(todo), 64):
            chunk = todo[i:i + 64]
            for p, v in zip(chunk, self.clip.encode_texts(chunk)):
                self.vecs[p] = v

    def encode_texts(self, prompts: list[str]) -> np.ndarray:
        missing = [p for p in prompts if p not in self.vecs]
        if missing:
            for p, v in zip(missing, self.clip.encode_texts(missing)):
                self.vecs[p] = v
        return np.stack([self.vecs[p] for p in prompts])


def _encode_mean(clip, texts: list[str]) -> np.ndarray:
    e = clip.encode_texts([p for t in texts for p in _prompts(t)])
    v = e.mean(axis=0)
    return v / np.linalg.norm(v)


def build_text_bank(clip, shots: list[dict]) -> dict:
    """Per-shot class sets: all shots compete with each other, plus that shot's own look-alike
    negatives and generic background classes. A shot's negatives never penalise other shots
    (an LLM may list another shot's subject as a look-alike)."""
    clip = _TextCache(clip)
    clip.prime([t for s in shots for t in [s["name"], s["description"] or s["name"]]
                + (s.get("visual_queries") or []) + (s.get("negative_queries") or [])] + BACKGROUND)
    shot_vecs, query_vecs, neg_vecs = [], [], []
    for s in shots:
        # Name + description (what the customer/planner wrote) carry half the weight; the LLM's
        # extra visual queries add coverage but can be generic, so they never dominate.
        core = list(dict.fromkeys([s["name"], s["description"] or s["name"]]))
        extra = [q for q in (s.get("visual_queries") or []) if q not in core]
        v = _encode_mean(clip, core)
        if extra:
            v = 0.5 * v + 0.5 * _encode_mean(clip, extra)
        shot_vecs.append(v / np.linalg.norm(v))
        queries = core + extra
        query_vecs.append((queries, clip.encode_texts([_prompts(q)[0] for q in queries])))
    shot_mat = np.stack(shot_vecs)
    for i, s in enumerate(shots):
        # CLIP cannot read negation: "empty street with no café" matches an empty café street.
        negs = [t for t in s.get("negative_queries", []) if not _NEGATION.search(t)]
        vecs = [_encode_mean(clip, [t]) for t in negs]
        # Drop a negative that is really describing another shot of this list.
        others = np.delete(shot_mat, i, axis=0)
        vecs = [v for v in vecs if others.size == 0 or float((others @ v).max()) < 0.9]
        neg_vecs.append(np.stack(vecs) if vecs else np.zeros((0, shot_mat.shape[1]), np.float32))
    bg = np.stack([_encode_mean(clip, [t]) for t in BACKGROUND])
    return {"shots": shot_mat, "negatives": neg_vecs, "background": bg, "queries": query_vecs}


def shot_probabilities(bank: dict, emb: np.ndarray) -> np.ndarray:
    """(frames, shots) probability that each frame shows each shot rather than anything else."""
    n = bank["shots"].shape[0]
    shot_logits = LOGIT_SCALE * (emb @ bank["shots"].T)
    bg_logits = LOGIT_SCALE * (emb @ bank["background"].T)
    out = np.zeros((emb.shape[0], n), np.float32)
    for i in range(n):
        # A look-alike only counts against the shot when it fits the frame clearly better.
        neg = LOGIT_SCALE * (emb @ bank["negatives"][i].T - NEG_MARGIN)
        logits = np.concatenate([shot_logits, neg, bg_logits], axis=1)
        logits -= logits.max(axis=1, keepdims=True)
        p = np.exp(logits)
        out[:, i] = p[:, i] / p.sum(axis=1)
    return out


# ---------------------------------------------------------------- audio side
_WORD = re.compile(r"[a-z0-9']+")


def _norm_words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def find_audio(footage: list[FootageFile], keywords: list[str]) -> list[dict]:
    """Transcript segments containing a keyword phrase. Keywords are in priority order (the
    first one is the line the customer asked for), so earlier keywords rank higher."""
    hits = []
    kw = [k for k in (_norm_words(k) for k in keywords) if k]
    for f in footage:
        for seg in f.transcript.get("segments", []):
            words = _norm_words(seg["text"])
            best, best_rank = 0.0, len(kw)
            for rank, k in enumerate(kw):
                n = len(k)
                for i in range(len(words) - n + 1):
                    window = words[i:i + n]
                    match = sum(1 for a, b in zip(window, k) if a == b or (len(b) > 4 and a.startswith(b[:-1]))) / n
                    if match > best + 1e-9 or (abs(match - best) < 1e-9 and rank < best_rank):
                        best, best_rank = match, rank
            if best >= 0.99 or (best >= 0.75 and len(kw[best_rank]) > 1):
                hits.append({"file": f, "seg": seg, "match": best, "rank": best_rank})
    hits.sort(key=lambda h: (-h["match"], h["rank"], -h["seg"].get("confidence", 0)))
    return hits


def _sentence_span(f: FootageFile, seg: dict) -> tuple[float, float]:
    """The matched segment plus the speech that directly follows it (gaps < 0.6 s), so the
    clip starts on the requested line and doesn't cut the speaker off mid-thought."""
    segs = f.transcript.get("segments", [])
    i = segs.index(seg)
    a, b = seg["start"], seg["end"]
    j = i + 1
    while j < len(segs) and segs[j]["start"] - b < 0.6 and segs[j]["end"] - a < 8:
        b = segs[j]["end"]
        j += 1
    return a, b


# ---------------------------------------------------------------- main search
def _windows(f: FootageFile, length: float, step: float = 0.5):
    for sc in f.scenes or [{"start": 0.0, "end": f.duration}]:
        a, b = sc["start"], sc["end"]
        # Trim a few frames at cuts so a clip never flashes the neighbouring scene.
        a, b = a + 0.1, b - 0.1
        if b - a <= length:
            yield sc, a, b
            continue
        t = a
        while t + length <= b + 1e-6:
            yield sc, t, t + length
            t += step


def _best_query(bank: dict, shot_idx: int, emb: np.ndarray) -> str:
    queries, qv = bank["queries"][shot_idx]
    sims = emb @ qv.T  # (frames, queries)
    return queries[int(sims.mean(axis=0).argmax())]


def frame_scores(bank: dict, footage: list[FootageFile]) -> dict[str, np.ndarray]:
    """(frames, shots) score per file = relative fit (softmax vs. every other explanation)
    x absolute fit (how close the frame is to the strongest match for that shot anywhere in
    the footage). The softmax alone saturates: a weak match still wins if nothing else fits,
    e.g. milk poured into iced coffee for a latte-art shot."""
    sims = {f.asset_id: f.emb @ bank["shots"].T for f in footage}
    all_sims = np.concatenate(list(sims.values()), axis=0)
    top = np.percentile(all_sims, 99, axis=0)  # per shot
    out = {}
    for f in footage:
        rel = shot_probabilities(bank, f.emb)
        gate = 1.0 / (1.0 + np.exp(-(sims[f.asset_id] - (top - GATE_MARGIN)) / GATE_SOFTNESS))
        out[f.asset_id] = rel * gate
    return out


GATE_MARGIN = 0.035   # cosine distance below the shot's best match where the score halves
GATE_SOFTNESS = 0.008


def search_hybrid(shots: list[dict], footage: list[FootageFile], clip, progress: Callable[[float, str], None]):
    bank = build_text_bank(clip, shots)
    probs = frame_scores(bank, footage)

    per_shot: list[list[Candidate]] = []
    for i, shot in enumerate(shots):
        progress(0.1 + 0.6 * i / max(1, len(shots)), f"Searching for “{shot['name']}”")
        L = float(shot["target_seconds"])
        cands: list[Candidate] = []
        for f in footage:
            pf = probs[f.asset_id][:, i]
            per_scene: dict[float, list[Candidate]] = {}
            for sc, a, b in _windows(f, L):
                m = (f.t_c >= a) & (f.t_c <= b)
                if not m.any():
                    continue
                vis = float(pf[m].mean())
                q = f.quality(a, b)
                score = vis * (0.55 + 0.45 * q["overall"])
                per_scene.setdefault(sc["start"], []).append(Candidate(f, a, b, vis, q, score, scene=sc["start"]))
            # Keep the best window of each scene plus up to two non-overlapping runners-up, so a
            # long take can serve two shots (e.g. "regulars smiling" and the spoken thank-you).
            picked: list[Candidate] = []
            for wins in per_scene.values():
                chosen: list[Candidate] = []
                for c in sorted(wins, key=lambda c: c.score, reverse=True):
                    if len(chosen) == 3:
                        break
                    if all(min(c.end, o.end) - max(c.start, o.start) <= 0 for o in chosen):
                        chosen.append(c)
                picked.extend(chosen)
            for c in picked:
                m = (f.t_c >= c.start) & (f.t_c <= c.end)
                c.query = _best_query(bank, i, f.emb[m])
                if c.end - c.start < L - 0.25:
                    c.notes.append(f"only {c.end - c.start:.1f}s available in this take")
                if c.quality["overall"] < settings.min_quality:
                    c.notes.append("weak take (quality)")
                cands.append(c)

        if shot.get("needs_audio"):
            cands = _apply_audio(shot, footage, probs, i, cands)
        cands.sort(key=lambda c: c.score, reverse=True)
        per_shot.append(cands)
    return per_shot


def _apply_audio(shot, footage, probs, i, visual_cands: list[Candidate]) -> list[Candidate]:
    keywords = shot.get("audio_keywords") or re.findall(r"['\"]([^'\"]+)['\"]", shot["description"]) or [shot["name"]]
    hits = find_audio(footage, keywords)
    out = []
    L = float(shot["target_seconds"])
    for h in hits[:3]:
        f, seg = h["file"], h["seg"]
        a, b = _sentence_span(f, seg)
        spoken = " ".join(s["text"] for s in f.transcript.get("segments", []) if s["start"] >= a - 0.01 and s["end"] <= b + 0.01)
        a = max(0.0, a - 0.3)
        b = min(f.duration, max(b + 0.3, a + L))
        m = (f.t_c >= a) & (f.t_c <= b)
        vis = float(probs[f.asset_id][m, i].mean()) if m.any() else 0.0
        q = f.quality(a, b)
        conf = (0.55 + 0.35 * h["match"] * min(1.0, seg.get("confidence", 0.7) / 0.7)
                + 0.10 * min(1.0, vis * 3) - 0.04 * h["rank"])
        c = Candidate(f, a, b, vis, q, min(0.99, conf), audio_text=spoken or seg["text"])
        if vis < 0.15:
            c.notes.append("speaker not clearly visible on screen (found by audio)")
        out.append(c)
    # Visual-only matches cannot prove the line was said: keep them as low-confidence suggestions.
    for c in visual_cands:
        c.score *= 0.4
        c.notes.append("visual guess only, required speech not heard here")
    return out + visual_cands


def _overlaps(c: Candidate, taken: list[Candidate]) -> bool:
    return any(c.file.asset_id == t.file.asset_id and min(c.end, t.end) - max(c.start, t.start) > 0.5 for t in taken)


def assign(shots: list[dict], per_shot: list[list[Candidate]], threshold: float) -> list[dict]:
    """Greedy global assignment by confidence; no moment used twice; honest 'missing'."""
    chosen: dict[int, Candidate] = {}
    taken: list[Candidate] = []
    pairs = sorted(((c.score, i, c) for i, cs in enumerate(per_shot) for c in cs), key=lambda x: -x[0])
    for score, i, c in pairs:
        if i in chosen or score < threshold or _overlaps(c, taken):
            continue
        chosen[i] = c
        taken.append(c)

    results = []
    for i, shot in enumerate(shots):
        cs = per_shot[i]
        if i in chosen:
            best = chosen[i]
            # Only alternatives an editor could plausibly use; near-zero matches are noise.
            alts = [c for c in cs if c is not best and not _same_take(c, best) and not c.same_scene(best)
                    and c.score >= threshold / 2]
            alts = _dedupe(alts)[:2]
            results.append({"shot_id": shot["shot_id"], "status": "found", "best": best.as_dict(),
                            "alternatives": [a.as_dict(with_quality=True) for a in alts]})
        else:
            top = cs[0] if cs else None
            if top is None:
                why = "No footage analysed"
            elif shot.get("needs_audio") and not top.audio_text:
                kws = ", ".join(f"“{k}”" for k in (shot.get("audio_keywords") or [])[:3])
                why = (f"Required speech not found in any transcript (searched for {kws or 'the line'}); "
                       f"closest visual candidate scored {top.score:.2f}")
            elif top.score >= threshold:
                why = f"Best matching moment is already used by another shot; next best scored {top.score:.2f}"
            else:
                why = f"No moment above the confidence threshold ({threshold:.2f}); closest candidate scored {top.score:.2f}"
            suggestions = [c.as_dict() for c in _dedupe(cs)[:2] if c.score >= 0.05]
            results.append({"shot_id": shot["shot_id"], "status": "missing", "best": None,
                            "alternatives": [], "reason": why, "suggestions": suggestions})
    return results


def _same_take(a: Candidate, b: Candidate) -> bool:
    return a.file.asset_id == b.file.asset_id and min(a.end, b.end) - max(a.start, b.start) > 0


def _dedupe(cs: list[Candidate]) -> list[Candidate]:
    """One candidate per take: drops overlapping windows and other windows of the same scene."""
    out: list[Candidate] = []
    for c in cs:
        if not any(_same_take(c, o) or c.same_scene(o) for o in out):
            out.append(c)
    return out


# ---------------------------------------------------------------- baseline
def search_baseline(shots: list[dict], footage: list[FootageFile], clip, threshold: float = 0.22) -> list[dict]:
    results = []
    for shot in shots:
        t = _encode_mean(clip, [shot["description"] or shot["name"]])
        best = None
        for f in footage:
            sims = f.emb @ t
            k = int(sims.argmax())
            if best is None or sims[k] > best[0]:
                best = (float(sims[k]), f, float(f.t_c[k]))
        L = float(shot["target_seconds"])
        if best is None or best[0] < threshold:
            results.append({"shot_id": shot["shot_id"], "status": "missing", "best": None, "alternatives": [],
                            "reason": f"Best cosine {best[0] if best else 0:.2f} below {threshold}"})
            continue
        sim, f, tc = best
        a = max(0.0, min(tc - L / 2, f.duration - L))
        c = Candidate(f, a, min(f.duration, a + L), sim, f.quality(a, a + L), sim, query=shot["description"])
        results.append({"shot_id": shot["shot_id"], "status": "found", "best": c.as_dict(), "alternatives": []})
    return results


# ---------------------------------------------------------------- entry point
def find_shots(shots: list[dict], footage: list[FootageFile], approach: str = "hybrid",
               progress: Callable[[float, str], None] = lambda p, m: None,
               threshold: float | None = None) -> list[dict]:
    from app.providers.vision import get_clip

    clip = get_clip()
    shots = sorted(shots, key=lambda s: s.get("order", 0))
    if approach == "baseline":
        return search_baseline(shots, footage, clip)
    per_shot = search_hybrid(shots, footage, clip, progress)
    progress(0.8, "Assigning best takes")
    return assign(shots, per_shot, settings.missing_threshold if threshold is None else threshold)


def build_timeline(shots: list[dict], results: list[dict]) -> list[dict]:
    by_id = {r["shot_id"]: r for r in results}
    timeline = []
    for s in sorted(shots, key=lambda s: s.get("order", 0)):
        r = by_id.get(s["shot_id"])
        if r and r["status"] == "found":
            b = r["best"]
            timeline.append({"order": len(timeline) + 1, "shot_id": s["shot_id"], "name": s["name"],
                             "file": b["file"], "start": b["start"], "end": b["end"],
                             "needs_audio": bool(s.get("needs_audio"))})
    return timeline

"""Shot planner: free-text brief -> structured shot list.

Each shot also carries *search hints* the shot finder uses: positive visual queries, look-alike
negatives that must NOT be accepted, and audio keywords for moments that are heard, not seen.
Hints are generated for any shot list (including ones loaded from a file) via `enrich_shots`.
"""
from __future__ import annotations

import re
from typing import Any

from app.providers.llm import LLMResult, get_llm

PLAN_SYSTEM = """You are a senior video producer planning a short social-media edit.
Turn the customer's brief into an ordered shot list. Rules:
- Only include moments the customer actually asked for or clearly implied. Never invent
  people, props, events or locations that are not in the brief.
- One shot per distinct moment the customer mentions. NEVER add filler shots to reach the
  length (no "enjoying the atmosphere", "B-roll", "closing logo" unless asked); if there are
  few moments, make each shot longer instead.
- Keep the exact order in which the moments appear in the brief; only move a moment if the
  customer explicitly says where it goes (e.g. "start with", "end with").
- Descriptions use only details from the brief: do not add signs, logos, props, decorations
  or people the customer did not mention.
- target_seconds per shot: usually 2-6 s (up to 10 s when there are only a few moments), and
  the total must equal the requested length (±1 s). Give more time to moments the customer
  emphasised.
- Style words ("warm", "professional", "not blurry") are quality requirements, not shots.
- needs_audio = true only if the moment can only be identified by what is said or heard
  (e.g. a specific spoken line). Otherwise false.
- For every shot also write search hints for an AI that scans raw footage with a CLIP
  image-text model and a speech transcript:
  - visual_queries: 3 short, concrete descriptions of what the frame looks like. Lead with the
    DISTINCTIVE visual element that proves it is this shot (e.g. latte art: "a heart pattern
    in the foam of a latte"), not generic objects that also appear in other shots.
  - negative_queries: 2-3 visually similar scenes that would be WRONG: the same objects without
    the key action, earlier/later steps of the same process, or a similar-looking event
    (e.g. latte art: "milk being steamed in a metal jug", "milk poured into an iced coffee
    glass", "a plain cup of coffee"). Never describe another shot of this list.
  - audio_keywords: words/phrases that would be spoken, most important first
    (only when needs_audio, else []).
  Hints describe only what is visible, never absence or negation (not "street with no café",
  "owner not speaking"), and never add details the brief doesn't give: say "glasses" or
  "drinks", not "coffee cups" or "champagne", unless the brief says which.
- brief_quote: the exact words copied from the brief that this shot comes from.
- placement: "start" or "end" only if the customer explicitly says so, else "auto".
Return JSON: {"style": str, "total_seconds": number, "shots": [{"shot_id": "A1", "name": str,
"description": str, "target_seconds": number, "order": int, "needs_audio": bool,
"brief_quote": str, "placement": str,
"visual_queries": [str], "negative_queries": [str], "audio_keywords": [str]}]}"""

ENRICH_SYSTEM = """You help an AI search raw video footage for the shots of an edit.
For each shot write search hints for a CLIP image-text model and a speech transcript:
- visual_queries: 3 short, concrete descriptions of the frame. Lead with the DISTINCTIVE visual
  element that proves it is this shot (e.g. latte art: "a heart pattern in the foam of a
  latte"), not generic objects that also appear in other shots.
- negative_queries: 2-3 visually similar scenes that would be WRONG: the same objects without
  the key action, earlier/later steps of the same process, or a similar-looking event
  (e.g. latte art: "milk being steamed in a metal jug", "a plain cup of coffee").
  Never describe another shot of the list.
- audio_keywords: words likely spoken in the moment, most important first, if needs_audio is
  true, else [].
Hints describe only what is visible, never absence or negation (not "street with no café"),
and never add details the shot description doesn't give.
If needs_audio is missing, set it true only when the shot can only be identified by speech/sound.
Return JSON: {"shots": [{"shot_id": str, "needs_audio": bool, "visual_queries": [str],
"negative_queries": [str], "audio_keywords": [str]}]}"""


# ---------------------------------------------------------------- rule-based fallback
# (keyword trigger, name, description, visual queries, negatives, audio keywords, weight)
_RULES: list[tuple[str, str, str, list[str], list[str], list[str], float]] = [
    (r"\boutside|exterior|storefront|street|where we are|entrance\b", "Exterior",
     "Wide shot of the venue from outside so people see where it is.",
     ["exterior of a cafe from the street", "outdoor seating on a street", "street view of a shopfront"],
     ["restaurant dining room interior"], [], 1.0),
    (r"coffee being made|espresso|barista|brew|coffee machine", "Coffee being made",
     "Espresso being made at the coffee machine.",
     ["espresso pouring from a coffee machine", "barista using an espresso machine", "coffee extraction close-up"],
     ["tea poured into a glass cup", "french press on a table"], [], 1.0),
    (r"latte art", "Latte art close-up",
     "Close-up of milk being poured into a coffee to create latte art.",
     ["latte art being poured into a cup", "milk poured making a heart pattern in coffee", "close-up of latte art"],
     ["milk poured into iced coffee glass", "steamed milk in a jug"], [], 1.3),
    (r"customer|guests?\b|people enjoying|crowd", "Happy customers",
     "Customers chatting and smiling at a table inside the venue.",
     ["happy customers chatting at a cafe table", "people smiling and laughing in a cafe", "friends drinking coffee together"],
     ["concert crowd with raised hands", "very dark bar"], [], 1.2),
    (r"pastr|cake|croissant|bakery|food|dessert", "Pastry display",
     "A slow look across the pastries in the display case.",
     ["pastries in a bakery display case", "croissants on display behind glass", "cafe counter with pastries"],
     ["close-up of a single cookie", "coffee beans"], [], 1.0),
    (r"welcom|speech|say|says|announce", "Welcome speech",
     "The host welcomes everyone; use the moment they actually say the welcome line.",
     ["person speaking to guests", "host giving a welcome speech", "owner talking to the camera"],
     ["people chatting silently"], ["welcome", "thank you for coming", "grand opening"], 1.4),
    (r"ribbon", "Ribbon cutting",
     "The ribbon being cut at the entrance to open the venue.",
     ["cutting a ribbon with scissors", "ribbon cutting ceremony at a door", "red ribbon being cut"],
     ["scissors on a table"], [], 1.0),
    (r"toast|cheers|raise .*glass|celebrat", "Celebration toast",
     "Guests raise their glasses together for a toast.",
     ["people raising glasses for a toast", "friends clinking champagne glasses", "group cheers with drinks"],
     ["concert crowd raising hands", "person drinking alone"], [], 1.0),
    (r"product|menu|dish|signature", "Product hero shot",
     "A clean hero shot of the featured product.",
     ["product close-up on a table", "featured dish beautifully plated", "hero shot of the product"],
     [], [], 1.0),
    (r"team|staff|crew", "Team",
     "The team at work or posing together.",
     ["staff team smiling together", "employees working behind the counter", "team portrait"],
     [], [], 1.0),
]


def _parse_length(brief: str, default: float) -> float:
    m = re.search(r"(\d{1,3})\s*-?\s*(?:second|sec|s\b)", brief, re.I)
    return float(m.group(1)) if m else default


def _distribute(weights: list[float], total: float) -> list[float]:
    raw = [w / sum(weights) * total for w in weights]
    hi = max(6.0, min(10.0, total / max(1, len(weights)) + 2))
    secs = [max(1.5, min(hi, round(r * 2) / 2)) for r in raw]
    # Nudge the longest shots until the sum matches the target.
    diff = round((total - sum(secs)) * 2) / 2
    i = 0
    while abs(diff) >= 0.5 and i < 100:
        idx = max(range(len(secs)), key=lambda k: raw[k] - secs[k]) if diff > 0 else \
            max(range(len(secs)), key=lambda k: secs[k] - raw[k])
        step = 0.5 if diff > 0 else -0.5
        if 1.5 <= secs[idx] + step <= hi:
            secs[idx] += step
            diff -= step
        i += 1
    return secs


def plan_rule_based(brief: str, target_seconds: float) -> dict:
    text = brief.lower()
    found: list[tuple[int, tuple]] = []
    for rule in _RULES:
        m = re.search(rule[0], text)
        if m:
            found.append((m.start(), rule))
    found.sort(key=lambda x: x[0])
    # "End with ..." should be last.
    end_m = re.search(r"end(?:ing)? with ([^.!]+)", text)
    if end_m:
        tail = [f for f in found if re.search(f[1][0], end_m.group(1))]
        found = [f for f in found if f not in tail] + tail
    if not found:
        # Generic fallback: one shot per sentence of the brief.
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", brief) if len(s.split()) > 3][:8]
        found = [(0, (None, f"Shot {i+1}", s, [s], [], [], 1.0)) for i, s in enumerate(sentences)]
    secs = _distribute([r[6] for _, r in found], target_seconds)
    shots = []
    for i, ((_, r), s) in enumerate(zip(found, secs), start=1):
        shots.append({
            "shot_id": f"A{i}", "name": r[1], "description": r[2], "target_seconds": s,
            "order": i, "needs_audio": bool(r[5]), "visual_queries": r[3],
            "negative_queries": r[4], "audio_keywords": r[5],
        })
    return {"style": "", "total_seconds": sum(secs), "shots": shots}


# ---------------------------------------------------------------- public API
def _normalise(shots: list[dict], prefix: str = "A") -> list[dict]:
    out = []
    for i, s in enumerate(sorted(shots, key=lambda s: s.get("order", 0) or 0), start=1):
        out.append({
            "shot_id": str(s.get("shot_id") or f"{prefix}{i}"),
            "name": str(s.get("name", f"Shot {i}")).strip(),
            "description": str(s.get("description", "")).strip(),
            "target_seconds": float(s.get("target_seconds", 3) or 3),
            "order": i,
            "needs_audio": bool(s.get("needs_audio", False)),
            "visual_queries": [q for q in s.get("visual_queries", []) if q][:5],
            "negative_queries": [q for q in s.get("negative_queries", []) if q][:5],
            "audio_keywords": [q for q in s.get("audio_keywords", []) if q][:6],
        })
    return out


def _quote_position(brief: str, quote: str) -> int | None:
    """Where in the brief a shot's source quote appears (exact, else best word overlap)."""
    norm = lambda t: " ".join(re.findall(r"[a-z0-9']+", t.lower()))
    b, q = norm(brief), norm(quote or "")
    if not q:
        return None
    i = b.find(q)
    if i >= 0:
        return i
    # Fuzzy: median position of the quote's distinctive words (ignores stray common words).
    words = [w for w in q.split() if len(w) > 4]
    hits = sorted(m.start() for w in words for m in [re.search(rf"\b{re.escape(w)}", b)] if m)
    if not hits or len(hits) < max(1, len(words) // 2):
        return None
    return hits[len(hits) // 2]


def _ground(brief: str, raw: list[dict], target_seconds: float) -> list[dict]:
    """Enforce in code what an LLM may not obey: brief order, exact total length, and a
    'grounded' flag for shots whose source text cannot be found in the brief."""
    items = []
    for k, s in enumerate(raw):
        pos = _quote_position(brief, s.get("brief_quote", ""))
        placement = (s.get("placement") or "auto").lower()
        rank = -1 if placement == "start" else (10**9 if placement == "end" else (pos if pos is not None else 10**8 + k))
        items.append((rank, k, s, pos is not None))
    items.sort(key=lambda x: (x[0], x[1]))
    ordered = []
    for i, (_r, _k, s, grounded) in enumerate(items, start=1):
        ordered.append({**s, "shot_id": f"A{i}", "order": i, "grounded": grounded})
    secs = _distribute([max(0.5, float(s.get("target_seconds") or 3)) for s in ordered], target_seconds)
    for s, sec in zip(ordered, secs):
        s["target_seconds"] = sec
    return ordered


def plan_shots(brief: str, target_seconds: float) -> tuple[dict, LLMResult | None]:
    """Returns ({source, style, shots}, llm_result_or_None)."""
    target_seconds = _parse_length(brief, target_seconds)
    llm = get_llm()
    if llm:
        try:
            res = llm.complete_json(PLAN_SYSTEM, f"Requested length: {target_seconds:g} seconds.\n\nBrief:\n{brief}")
            raw = _ground(brief, res.data.get("shots", []), target_seconds)
            shots = _normalise(raw)
            for s, r in zip(shots, raw):
                s["brief_quote"], s["grounded"] = r.get("brief_quote", ""), r["grounded"]
            if shots:
                return {"source": "ai", "model": res.model, "style": res.data.get("style", ""),
                        "shots": shots}, res
        except Exception as exc:
            print(f"[planner] LLM failed ({exc}); using rules")
    plan = plan_rule_based(brief, target_seconds)
    return {"source": "rules", "model": "rule-based", "style": "", "shots": _normalise(plan["shots"])}, None


def _rule_hints(shot: dict) -> dict:
    text = f"{shot['name']} {shot['description']}".lower()
    for rule in _RULES:
        if re.search(rule[0], text):
            return {"visual_queries": rule[3], "negative_queries": rule[4],
                    "audio_keywords": rule[5] if shot.get("needs_audio") else []}
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", shot["description"])
    return {"visual_queries": [shot["description"] or shot["name"]], "negative_queries": [],
            "audio_keywords": quoted if shot.get("needs_audio") else []}


def enrich_shots(shots: list[dict]) -> tuple[list[dict], LLMResult | None]:
    """Fill in missing search hints for shots (e.g. a reference list loaded from CSV)."""
    shots = _normalise(shots)
    todo = [s for s in shots if not s["visual_queries"]]
    if not todo:
        return shots, None
    llm, res = get_llm(), None
    hints: dict[str, Any] = {}
    if llm:
        try:
            payload = [{k: s[k] for k in ("shot_id", "name", "description", "needs_audio")} for s in todo]
            res = llm.complete_json(ENRICH_SYSTEM, f"Shots:\n{payload}")
            hints = {h["shot_id"]: h for h in res.data.get("shots", []) if "shot_id" in h}
        except Exception as exc:
            print(f"[planner] enrich via LLM failed ({exc}); using rules")
    for s in todo:
        h = hints.get(s["shot_id"]) or _rule_hints(s)
        s["visual_queries"] = list(h.get("visual_queries") or [s["description"]])[:5]
        s["negative_queries"] = list(h.get("negative_queries") or [])[:5]
        if "needs_audio" in h and not s.get("_needs_audio_given"):
            s["needs_audio"] = bool(h["needs_audio"]) or s["needs_audio"]
        s["audio_keywords"] = list(h.get("audio_keywords") or [])[:6] if s["needs_audio"] else []
    return shots, res

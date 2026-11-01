"""Score shot-finder results against the hand-labelled ground truth (docs/ground_truth.json).

Per shot:
- correct     found inside a correct take (>= 80 % of the clip inside a 'good'/'ok' segment),
              or correctly reported missing; for audio shots the clip must contain the key line
- best take   chose a 'good' take (not merely 'ok') when one exists
- bad take    chose a take labelled 'bad' (blurry/dark)
- distractor  chose a look-alike labelled 'distractor'
- purity      % of the chosen clip that lies inside a correct segment (timestamp accuracy)
- start error for the audio shot: seconds between clip start and the start of the spoken line

    python scripts/evaluate.py deliverables/results_reference_hybrid.json [more files...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT = json.loads((ROOT / "docs" / "ground_truth.json").read_text(encoding="utf-8"))


def _overlap(f, a, b, segs) -> float:
    return sum(max(0.0, min(b, e) - max(a, s)) for sf, s, e in segs if sf == f)


def concept_for(shot_id: str, name: str) -> list[str]:
    if shot_id in GT["shots"]:
        return [shot_id]
    for pattern, ids in GT["ai_shot_mapping"]["rules"]:
        if re.search(pattern, name.lower()):
            return ids
    return []


def score_shot(res: dict, concepts: list[str]) -> dict:
    gts = [GT["shots"][c] for c in concepts]
    present = any(g["present"] for g in gts)
    out = {"present": present, "status": res["status"], "correct": False, "best_take": None,
           "bad_take": False, "distractor": False, "purity": None, "start_error": None}
    if res["status"] != "found" or not res.get("best"):
        out["correct"] = not present
        return out
    b = res["best"]
    f, a, e = b["file"], b["start"], b["end"]
    dur = max(1e-6, e - a)
    good = [tuple(s) for g in gts for s in g.get("good", [])]
    ok = [tuple(s) for g in gts for s in g.get("ok", [])]
    in_good, in_ok = _overlap(f, a, e, good), _overlap(f, a, e, ok)
    out["purity"] = round(min(1.0, (in_good + in_ok) / dur), 3)
    out["bad_take"] = _overlap(f, a, e, [tuple(s) for g in gts for s in g.get("bad", [])]) / dur > 0.5
    out["distractor"] = _overlap(f, a, e, [tuple(s) for g in gts for s in g.get("distractor", [])]) / dur > 0.5
    audio = next((g for g in gts if g.get("audio")), None)
    if audio:
        kf, ks, ke = audio["key_moment"]
        out["correct"] = f == kf and a <= ks + 0.3 and e >= ke - 0.3
        out["start_error"] = round(abs(a - ks), 2) if f == kf else None
    else:
        out["correct"] = present and out["purity"] >= 0.8
    if out["correct"]:
        out["best_take"] = in_good / dur >= 0.8 if good else True
    return out


def evaluate(path: Path, shot_names: dict[str, str] | None = None) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for res in doc["shots"]:
        name = (shot_names or {}).get(res["shot_id"], res["shot_id"])
        concepts = concept_for(res["shot_id"], name)
        if not concepts:
            rows.append({"shot_id": res["shot_id"], "name": name, "unmapped": True})
            continue
        rows.append({"shot_id": res["shot_id"], "name": name, "concepts": concepts, **score_shot(res, concepts)})
    scored = [r for r in rows if not r.get("unmapped")]
    found_present = [r for r in scored if r["present"] and r["status"] == "found"]
    summary = {
        "file": path.name, "shots": len(scored),
        "correct": sum(r["correct"] for r in scored),
        "accuracy": round(sum(r["correct"] for r in scored) / max(1, len(scored)), 3),
        "missing_correct": sum(1 for r in scored if not r["present"] and r["status"] == "missing"),
        "missing_total": sum(1 for r in scored if not r["present"]),
        "false_missing": sum(1 for r in scored if r["present"] and r["status"] == "missing"),
        "false_positive": sum(1 for r in scored if not r["present"] and r["status"] == "found"),
        "best_take": sum(1 for r in scored if r["best_take"]),
        "bad_takes": sum(r["bad_take"] for r in scored),
        "distractors": sum(r["distractor"] for r in scored),
        "mean_purity": round(sum(r["purity"] for r in found_present) / max(1, len(found_present)), 3),
        "audio_start_error_s": next((r["start_error"] for r in scored if r["start_error"] is not None), None),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted((ROOT / "deliverables").glob("results_*.json"))
    names = {}
    ai = ROOT / "deliverables" / "ai_shot_list.json"
    if ai.exists():
        names = {s["shot_id"]: s["name"] for s in json.loads(ai.read_text(encoding="utf-8"))["shots"]}
    report = {}
    for p in paths:
        r = evaluate(p, names if "_ai_" in p.name else None)
        report[p.stem] = r
        s = r["summary"]
        print(f"\n{p.name}: {s['correct']}/{s['shots']} correct ({s['accuracy']:.0%}) | missing ok {s['missing_correct']}/{s['missing_total']}"
              f" | false-missing {s['false_missing']} | false-positive {s['false_positive']} | best take {s['best_take']}"
              f" | bad takes {s['bad_takes']} | look-alikes {s['distractors']} | purity {s['mean_purity']:.0%}"
              f" | audio start err {s['audio_start_error_s']}s")
        for row in r["rows"]:
            if row.get("unmapped"):
                print(f"   {row['shot_id']:4} {row['name'][:34]:34} (no ground-truth concept)")
                continue
            mark = "OK " if row["correct"] else "BAD"
            extra = []
            if row["bad_take"]: extra.append("bad take")
            if row["distractor"]: extra.append("look-alike")
            if row["best_take"] is False: extra.append("weaker take")
            print(f"   {mark} {row['shot_id']:4} {row['name'][:34]:34} {row['status']:8} purity={row['purity']} {' '.join(extra)}")
    out = ROOT / "docs" / "evaluation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

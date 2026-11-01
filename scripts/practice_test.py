"""Generalisation check on the 4 practice clips (never used for tuning).

Each practice clip's title becomes a shot; two shots that are NOT in the clips are added
(ribbon cutting, a dog on a beach). A shot is correct when it is found in its own clip, and the
two absent shots must come back as "missing".

    python scripts/practice_test.py
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline.analyze import analyze_video  # noqa: E402
from app.services.finder import FootageFile, find_shots  # noqa: E402
from app.services.planner import enrich_shots  # noqa: E402

PRACTICE = ROOT / "OnSpotly_Intern_Assignment" / "02_Resources" / "practice"


def main() -> None:
    rows = list(csv.DictReader(open(PRACTICE / "practice_clips.csv", encoding="utf-8")))
    footage, t0 = [], time.time()
    for r in rows:
        aid = "practice_" + Path(r["file"]).stem
        an = analyze_video(aid, PRACTICE / r["file"], lambda p, m: None)
        footage.append(FootageFile.load(aid, r["file"], an))
    print(f"analysed {len(rows)} practice clips in {time.time() - t0:.0f}s")
    shots = [{"shot_id": f"P{i}", "name": r["title"], "description": r["description"].split(". This video")[0] + ".",
              "target_seconds": 3, "order": i, "expect": r["file"]} for i, r in enumerate(rows, start=1)]
    shots += [{"shot_id": "X1", "name": "Ribbon cutting", "description": "A ribbon being cut with scissors at a shop entrance.",
               "target_seconds": 3, "order": 5, "expect": None},
              {"shot_id": "X2", "name": "Dog on a beach", "description": "A dog running along a sandy beach.",
               "target_seconds": 3, "order": 6, "expect": None}]
    enriched, _ = enrich_shots([{k: v for k, v in s.items() if k != "expect"} for s in shots])
    results = find_shots(enriched, footage)
    ok = 0
    for s, r in zip(shots, results):
        got = r["best"]["file"] if r["best"] else None
        good = got == s["expect"]
        ok += good
        print(f"  {'OK ' if good else 'BAD'} {s['shot_id']} {s['name'][:40]:40} expected={s['expect'] or 'missing'}  got={got or 'missing'}"
              f"  conf={r['best']['confidence'] if r['best'] else r['reason'].split('scored ')[-1]}")
    print(f"practice: {ok}/{len(shots)} correct")


if __name__ == "__main__":
    main()

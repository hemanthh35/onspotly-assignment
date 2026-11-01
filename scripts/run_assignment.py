"""End-to-end run of the OnSpotly assignment through the platform's public API.

Creates a project from brief.md, uploads all footage, plans an AI shot list, imports the
reference shot list, runs the shot finder on both (hybrid + baseline), renders the edit from
the reference list and downloads every deliverable into deliverables/.

    python scripts/run_assignment.py --api http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "OnSpotly_Intern_Assignment" / "02_Resources"
OUT = ROOT / "deliverables"


def wait(api: str, job_id: str) -> dict:
    last = ""
    while True:
        j = requests.get(f"{api}/jobs/{job_id}").json()
        msg = f"  [{j['kind']}] {j['progress'] * 100:5.1f}%  {j['message']}"
        if msg != last:
            print(msg, flush=True)
            last = msg
        if j["status"] in ("done", "failed"):
            if j["status"] == "failed":
                raise RuntimeError(j["error"])
            return j
        time.sleep(1.5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--project", help="reuse an existing, already analysed project id")
    args = ap.parse_args()
    api = args.api.rstrip("/") + "/api/v1"
    OUT.mkdir(exist_ok=True)
    t0 = time.time()

    brief = (RES / "brief.md").read_text(encoding="utf-8").split("**This brief")[0].split("\n", 1)[1]
    brief = brief.replace("> ", "").replace("**", "").replace('"', "").strip()
    if args.project:
        p = requests.get(f"{api}/projects/{args.project}").json()
        analyze = next(j for j in p["jobs"] if j["kind"] == "analyze" and j["status"] == "done")
        print("reusing project", p["id"])
    else:
        p = requests.post(f"{api}/projects", json={"name": "Bean & Bloom grand opening", "brief": brief,
                                                   "target_seconds": 30, "aspect_ratio": "16:9"}).json()
        print("project", p["id"])
        files = sorted((RES / "footage").glob("*.mp4"))
        r = requests.post(f"{api}/projects/{p['id']}/assets",
                          files=[("files", (f.name, open(f, "rb"), "video/mp4")) for f in files]).json()
        print("uploaded", [a["filename"] for a in r["assets"]], f"({time.time() - t0:.0f}s)")
        analyze = wait(api, r["job_id"])

    ai = requests.post(f"{api}/projects/{p['id']}/shot-lists/plan").json()
    print("AI shot list:", ai["meta"], [s["name"] for s in ai["shots"]])
    ref = requests.post(f"{api}/projects/{p['id']}/shot-lists/import", data={"name": "OnSpotly reference shot list"},
                        files={"file": ("reference_shot_list.csv", open(RES / "reference_shot_list.csv", "rb"))}).json()

    runs = {}
    for label, sl in (("reference", ref), ("ai", ai)):
        for approach in ("hybrid", "baseline"):
            j = wait(api, requests.post(f"{api}/shot-lists/{sl['id']}/find", json={"approach": approach}).json()["job_id"])
            runs[(label, approach)] = j["result"]["run_id"]
            print(f"{label}/{approach}: found {j['result']['found']}/{j['result']['total']} in {j['wall_seconds']:.1f}s")

    # Shot lists as JSON.
    (OUT / "ai_shot_list.json").write_text(json.dumps(
        {"source": ai["source"], "model": ai["meta"].get("model"), "brief": brief, "shots": ai["shots"]}, indent=2, ensure_ascii=False), encoding="utf-8")
    for (label, approach), run_id in runs.items():
        doc = requests.get(f"{api}/runs/{run_id}/download/results").content
        (OUT / f"results_{label}_{approach}.json").write_bytes(doc)

    # Edited video + editor files from the reference list (hybrid).
    run_id = runs[("reference", "hybrid")]
    for kind, name in (("json", "clip_list_reference.json"), ("csv", "clip_list_reference.csv"),
                       ("edl", "rough_cut_reference.edl"), ("fcpxml", "rough_cut_reference.fcpxml")):
        (OUT / name).write_bytes(requests.get(f"{api}/runs/{run_id}/download/{kind}").content)
    j = wait(api, requests.post(f"{api}/runs/{run_id}/render", json={"aspect": "16:9"}).json()["job_id"])
    (OUT / "edited_video_reference.mp4").write_bytes(requests.get(f"{api}/exports/{j['result']['export_id']}/download").content)
    print(f"rendered {j['result']['duration']}s in {j['wall_seconds']:.1f}s")

    # Same for the AI list, plus a vertical reel for Instagram.
    run_ai = runs[("ai", "hybrid")]
    (OUT / "clip_list_ai.json").write_bytes(requests.get(f"{api}/runs/{run_ai}/download/json").content)
    j = wait(api, requests.post(f"{api}/runs/{run_ai}/render", json={"aspect": "9:16", "crossfade": 0.3}).json()["job_id"])
    (OUT / "edited_video_ai_9x16.mp4").write_bytes(requests.get(f"{api}/exports/{j['result']['export_id']}/download").content)

    timing = {"analysis_seconds": analyze["wall_seconds"], "analysis_cpu_seconds": analyze["cpu_seconds"],
              "analysis_peak_ram_mb": analyze["peak_rss_mb"], "analysis_steps": analyze["steps"],
              "end_to_end_seconds": round(time.time() - t0, 1), "project_id": p["id"],
              "runs": {f"{k[0]}_{k[1]}": v for k, v in runs.items()}}
    (OUT / "processing_time.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
    print(json.dumps(timing, indent=2))


if __name__ == "__main__":
    main()

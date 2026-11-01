"""OnSpotly technical blueprint: an Excalidraw deck (one frame per slide).

Every number on these slides was measured in this project (research note, evaluation.json,
job metrics). Anything not verified is labelled as such.

    python scripts/blueprint/build_blueprint.py   ->  docs/architecture/onspotly_blueprint.excalidraw
"""
from __future__ import annotations

from pathlib import Path

from xd import INK, MUTED, RED, Scene

W, H, GAP = 1920, 1080, 220
OUT = Path(__file__).resolve().parents[2] / "docs" / "architecture" / "onspotly_blueprint.excalidraw"
GREEN, VIOLET, BLUE, ORANGE = "#2f9e44", "#6741d9", "#1971c2", "#f08c00"

s = Scene()
_slide = 0


def slide(title, sub, nxt=None):
    global _slide
    _slide += 1
    s.frame(0, (_slide - 1) * (H + GAP), W, H, f"{_slide:02d} · {title}")
    s.text(80, 52, f"{_slide:02d}", 24, RED)
    s.text(128, 40, title, 46, INK)
    s.text(80, 112, sub, 22, MUTED, w=1760)
    s.line(80, 158, 1840, 158, color="#e9ecef", width=2)
    s.text(80, 1036, "OnSpotly · Smart Rough Cut · technical blueprint", 15, MUTED)
    if nxt:
        s.text(1500, 1036, f"next → {nxt}", 15, MUTED, w=340, align="right")


# =============================================================== 01 · Overview
slide("Smart Rough Cut", "A customer's brief becomes a timed rough cut, found automatically in messy raw footage.",
      "02 System architecture")
s.text(80, 190, "Brief → shot list → find the shots → edit → export", 40, INK, w=1760)
flow = [("Brief\ncustomer's own words", "proc"), ("Shot list\ngpt-4.1 + code guardrails", "ai"),
        ("Find shots\nCLIP · Whisper · quality", "ai"), ("Edit\ntimeline · music · title", "proc"),
        ("Export\nMP4 · JSON · CSV · EDL", "good")]
prev = None
for i, (lbl, kind) in enumerate(flow):
    b = s.box(80 + i * 352, 280, 300, 120, lbl, kind, size=22)
    if prev:
        s.arrow(prev, b, sides="rl")
    prev = b
tiles = [("8 / 8", "reference shots correct (hybrid)\nplain-CLIP baseline: 5 / 8", "good"),
         ("0", "shots faked: the ribbon cutting\nis reported missing, not forced", "proc"),
         ("326 s", "to analyse 231 s of footage\non a 6-core laptop CPU, no GPU", "proc")]
for i, (big, cap, kind) in enumerate(tiles):
    x = 80 + i * 592
    s.box(x, 470, 552, 220, "", kind)
    s.text(x + 32, 494, big, 72, RED if i == 0 else INK)
    s.text(x + 32, 600, cap, 22, "#495057", w=490)
s.text(80, 740, "Legend", 22, INK)
legend = [("Process", "proc"), ("AI model", "ai"), ("Data / storage", "data"), ("Decision", "decision"),
          ("External / optional", "ext"), ("Result OK", "good"), ("Problem / missing", "bad")]
for i, (lbl, kind) in enumerate(legend):
    shape = "diamond" if kind == "decision" else "rectangle"
    s.box(80 + i * 250, 780, 220, 70, lbl, kind, size=18, shape=shape)
s.text(80, 900, "Numbers are measured against my hand labels of the footage (docs/ground_truth.json, scripts/evaluate.py).\n"
       "Anything not verified is marked \"est.\" or \"not tested\".", 18, MUTED, w=1760)

# =============================================================== 02 · Architecture
slide("System architecture", "Each row is one path through the system. Every external service has a local fallback.",
      "03 Video analysis pipeline")
cols = [(80, 250, "CLIENT"), (380, 330, "API · FastAPI /api/v1"), (760, 300, "CORE SERVICES"),
        (1110, 290, "PROVIDERS"), (1450, 390, "EXTERNAL  ↳ FALLBACK")]
for x, w, name in cols:
    s.text(x, 180, name, 18, RED, w=w)
rows = [230, 350, 470, 590, 710]
api = ["POST /shot-lists/plan\n+ import · edit", "POST /shot-lists/{id}/find", "/projects · /assets\nupload → analyse job",
       "/runs · /exports\ntimeline · mix · render", "/admin\nlogin · dashboard"]
core = [("Planner\nbrief → shot list", "ai"), ("Finder\nhybrid shot search", "ai"),
        ("Job runner\nthreads · progress · metering", "proc"), ("Exporter\nFFmpeg · EDL · FCPXML", "proc"),
        ("Tracking\ncost · activity", "proc")]
prov = [("LLM", "ai"), ("Vision · CLIP", "ai"), ("Compute\nOpenCV · CLIP · Whisper", "proc"), ("Storage", "data"),
        ("Database\nSQLAlchemy", "data")]
ext = ["OpenAI gpt-4.1\n↳ rule-based planner", "OpenCLIP ViT-B/16 weights\nlocal CPU · CUDA if present",
       "Colab T4 worker (Cloudflare tunnel)\n↳ local CPU", "Supabase Storage · bucket media\n↳ local disk",
       "Supabase Postgres (eu-west-2)\n↳ SQLite"]
studio = s.box(80, 230, 250, 440, "Studio\nReact 19 · Vite\n\nprojects · footage · shot list · editor · export · versions", "proc", size=19)
admin = s.box(80, 710, 250, 100, "Admin\nReact · Recharts", "proc", size=19)
for i, y in enumerate(rows):
    a = s.box(380, y, 330, 100, api[i], "proc", size=18)
    c = s.box(760, y, 300, 100, core[i][0], core[i][1], size=18)
    p = s.box(1110, y, 290, 100, prov[i][0], prov[i][1], size=18)
    e = s.box(1450, y, 390, 100, ext[i], "ext", size=18)
    client = admin if i == 4 else studio
    s.arrow(client, a, sides="rl", start=(330, y + 50) if i < 4 else None)
    s.arrow(a, c, sides="rl")
    s.arrow(c, p, sides="rl")
    s.arrow(p, e, sides="rl")
s.box(80, 860, 860, 130, "Why providers: OpenAI, Supabase and Colab are optional. Without keys the platform runs offline "
      "(SQLite + local disk + rules + CPU) in two commands. Swapping a service = one new provider class.", "note", size=19, align="left")
s.box(980, 860, 860, 130, "Jobs: queued → running → done / failed. Every step records wall time, CPU (incl. FFmpeg) and peak RAM "
      "→ cost records → admin dashboard. Interrupted jobs are marked failed on restart.", "note", size=19, align="left")

# =============================================================== 03 · Analysis pipeline
slide("Video analysis pipeline", "Runs once per uploaded file and is cached. Same code on the laptop CPU or a Colab GPU.",
      "04 Shot planning & fallback")
up = s.box(80, 220, 220, 110, "Upload\nvideos or a .zip", "proc")
st = s.box(350, 220, 250, 110, "Store\nSupabase bucket + local cache", "data")
pr = s.box(650, 220, 230, 110, "ffprobe\nduration · fps · audio?", "proc")
dec = s.box(930, 200, 240, 150, "Colab GPU selected?", "decision", shape="diamond", size=19)
colab = s.box(1260, 175, 300, 90, "Colab worker\nupload · poll · download", "ext")
local = s.box(1260, 325, 300, 90, "Local CPU", "proc")
s.arrow(up, st)
s.arrow(st, pr)
s.arrow(pr, dec)
s.arrow(dec, colab, "yes", sides="rl", start=(1170, 250), end=(1260, 220), via=[(1215, 250), (1215, 220)])
s.arrow(dec, local, "no", sides="rl", start=(1170, 300), end=(1260, 370), via=[(1215, 300), (1215, 370)])
s.arrow(colab, local, "unreachable → fall back", sides="rr", color=RED, dashed=True, via=[(1620, 220), (1620, 370)])
grp = s.box(60, 470, 1800, 360, "", "group")
s.text(80, 482, "ANALYSIS · identical on CPU or GPU", 18, MUTED, w=600)
s.arrow(local, grp, sides="bt", end=(1410, 470))
sc = s.box(80, 590, 250, 130, "Scenes\nPySceneDetect\nAdaptiveDetector", "proc")
dp = s.box(380, 590, 230, 130, "One decode pass\nOpenCV", "proc")
q = s.box(660, 520, 380, 150, "Quality @ 6 fps\nsharpness = Laplacian variance\nbrightness = mean luma\nstability = camera-motion jitter", "proc", size=18)
cl = s.box(660, 690, 380, 120, "Frames @ 2 fps → 224 px\nOpenCLIP ViT-B/16 embeddings", "ai", size=18)
wh = s.box(1090, 590, 330, 130, "Whisper small\nwords + timestamps\n(voice activity filter)", "ai", size=18)
ca = s.box(1470, 590, 330, 130, "Cache\n.npz arrays + JSON summary in DB", "data", size=18)
s.arrow(sc, dp)
s.arrow(dp, q, sides="rl")
s.arrow(dp, cl, sides="rl")
s.arrow(q, wh, sides="rl")
s.arrow(cl, wh, sides="rl")
s.arrow(wh, ca)
s.box(80, 860, 560, 140, "Take quality\n= 0.45 sharp + 0.35 bright + 0.20 steady\ngreen ≥ 0.75 · yellow ≥ 0.50 · red < 0.50", "note", size=19, align="left")
s.box(680, 860, 560, 140, "Measured on the café footage: blurry latte pour → sharpness 0.00, dark bar → brightness 0.00. "
      "Analysis: 326 s for 231 s of footage (raw file 244 s), peak RAM 1.6 GB.", "note", size=19, align="left")
s.box(1280, 860, 560, 140, "Why motion jitter: smooth pans are fine, handheld shake is not. A latte take scoring 0.01 looked like a bug; "
      "measuring its motion showed it really is handheld.", "note", size=19, align="left")

# =============================================================== 04 · Shot planning
slide("Shot planning & fallback", "The LLM proposes, code enforces. Any shot list works: AI, rule-based, imported or hand-made.",
      "05 Hybrid shot finder")
br = s.box(80, 230, 220, 110, "Customer brief", "proc", size=22)
k = s.box(360, 200, 240, 170, "OpenAI key set?", "decision", shape="diamond")
gpt = s.box(680, 200, 380, 170, "gpt-4.1 · JSON · temperature 0\nshots + brief_quote + placement + search hints", "ai", size=19)
guard = s.box(1120, 180, 400, 210, "Guardrails in code\n① order by where each quote appears in the brief\n② rescale to the exact target length\n③ flag shots not found in the brief\n④ renumber A1…An", "good", size=18, align="left")
rules = s.box(680, 450, 380, 120, "Rule-based planner\nkeyword rules · one shot per sentence fallback", "proc", size=19)
lst = s.box(1580, 230, 260, 160, "Editable shot list\nrename · retime · add · delete · drag · audio toggle", "data", size=18)
s.arrow(br, k)
s.arrow(k, gpt, "yes", sides="rl")
s.arrow(k, rules, "no", sides="bl", end=(680, 510), via=[(480, 510)])
s.arrow(gpt, guard, sides="rl")
s.arrow(gpt, rules, "API error → rules", sides="bt", color=RED, dashed=True)
s.arrow(guard, lst, sides="rl")
s.arrow(rules, lst, sides="rb", via=[(1710, 510)])
imp = s.box(80, 650, 260, 110, "Import a list\nreference CSV / JSON", "proc")
hint = s.box(400, 620, 240, 170, "Has search hints?", "decision", shape="diamond", size=19)
enr = s.box(700, 650, 380, 110, "Write hints\nLLM, or rule hints offline", "ai", size=19)
s.arrow(imp, hint)
s.arrow(hint, enr, "no", sides="rl")
s.arrow(enr, lst, sides="rb", end=(1780, 390), via=[(1780, 705)])
s.arrow(hint, lst, "yes", sides="bb", end=(1820, 390), via=[(520, 830), (1820, 830)])
s.box(1120, 600, 400, 200, "Search hints per shot\nvisual queries (what the frame looks like)\nlook-alikes to reject\naudio keywords, most important first", "note", size=18, align="left")
s.box(80, 880, 860, 120, "Why guardrails: from the prompt alone, gpt-4.1 moved the ribbon cutting to 2nd place and returned 34 s for a 30 s brief.",
      "bad", size=19, align="left")
s.box(980, 880, 860, 120, "Hint hygiene: negations (\"street with no café\") are dropped because CLIP can't read \"no\"; "
      "look-alikes that describe another shot are dropped (similarity ≥ 0.9).", "note", size=19, align="left")

# =============================================================== 05 · Hybrid finder
slide("Hybrid shot finder", "CLIP for meaning · OpenCV for quality · Whisper for speech · rules for honesty.",
      "06 AI models & stack")
a1 = s.box(80, 190, 440, 80, "One shot from the list", "proc", size=20)
a2 = s.box(80, 310, 440, 110, "Text bank\nname + description 50% · LLM queries 50%", "proc", size=19)
a3 = s.box(80, 460, 440, 110, "Frame score\nrelative fit × absolute gate", "ai", size=19)
a4 = s.box(80, 610, 440, 110, "Windows inside each scene\nshot length · 0.5 s step · best 3 non-overlapping", "proc", size=18)
a5 = s.box(80, 760, 440, 110, "Window score\nvisual × (0.55 + 0.45 × quality)", "proc", size=19)
for x_, y_ in ((a1, a2), (a2, a3), (a3, a4), (a4, a5)):
    s.arrow(x_, y_, sides="bt")
na = s.box(600, 735, 250, 170, "Needs audio?", "decision", shape="diamond")
s.arrow(a5, na, sides="rl")
tr = s.box(600, 520, 250, 110, "Transcript search\nkeywords in priority order", "ai", size=18)
s.arrow(na, tr, "spoken shot", sides="tb")
lh = s.box(920, 495, 230, 160, "Line heard?", "decision", shape="diamond")
s.arrow(tr, lh, sides="rl")
on = s.box(1220, 520, 300, 110, "Clip starts on the line\n+ the rest of the sentence", "good", size=18)
s.arrow(lh, on, "yes", sides="rl")
vg = s.box(920, 330, 230, 110, "Visual guesses × 0.4\n\"speech not heard\"", "bad", size=17)
s.arrow(lh, vg, "no", sides="tb")
vis = s.box(920, 765, 230, 110, "Visual candidates\n(normal shot)", "proc", size=18)
s.arrow(na, vis, "normal shot", sides="rl")
asg = s.box(1220, 765, 300, 110, "Greedy assignment\nbest first · no moment used twice", "proc", size=18)
s.arrow(vis, asg, sides="rl")
s.arrow(on, asg, sides="bt")
s.arrow(vg, asg, sides="rt", end=(1250, 765), via=[(1188, 385), (1188, 700), (1250, 700)])
th = s.box(1580, 735, 260, 170, "Score ≥ 0.25?", "decision", shape="diamond")
s.arrow(asg, th, sides="rl")
fd = s.box(1580, 520, 260, 120, "FOUND\nbest + up to 2 other takes", "good", size=18)
ms = s.box(1580, 930, 260, 90, "MISSING + reason\n+ closest candidates", "bad", size=17)
s.arrow(th, fd, "yes", sides="tb")
s.arrow(th, ms, "no", sides="bt")
s.box(1220, 190, 620, 170, "Why hybrid: CLIP alone always picks something, can't hear and ignores blur (5/8). A vision LLM on every frame "
      "is slow and needs the internet. Classic CV alone can't tell latte art from iced coffee. Together: 8/8.", "warn", size=18, align="left")
s.box(600, 930, 540, 90, "Relative = softmax vs every other shot, own look-alikes (−0.015 margin), background. "
      "Absolute = closeness to the shot's best match anywhere.", "note", size=16, align="left")
s.box(1160, 930, 400, 90, "Plain-CLIP baseline: best single frame, window centred, cosine ≥ 0.22. No scenes, quality or audio.",
      "ext", size=16, align="left")

# =============================================================== 06 · Models & stack
slide("AI models & technology stack", "Four engines with one job each, plus the libraries and tools around them.",
      "07 Render, export & versions")
cards = [
    ("OpenAI gpt-4.1", "cloud · optional", "IN  brief or shot names\nOUT shot list, look-alikes, audio keywords\nJSON mode · temperature 0\nFallback: rule-based planner", "ai"),
    ("OpenCLIP ViT-B/16", "laion2b · local", "IN  frames @ 2 fps + text\nOUT 512-d embeddings → similarity\nCPU here · CUDA on Colab\nOpen source, works offline", "ai"),
    ("Whisper small", "faster-whisper · local", "IN  audio track\nOUT words + timestamps\nint8 on CPU · fp16 on GPU\nGPU library error → CPU", "ai"),
    ("PySceneDetect + OpenCV", "classic CV · not AI", "IN  frames @ 6 fps\nOUT scenes · sharpness · brightness · stability\nFast, explainable, deterministic", "data"),
]
for i, (name, where, body, kind) in enumerate(cards):
    x = 80 + i * 440
    s.box(x, 185, 410, 300, "", kind)
    s.text(x + 24, 205, name, 26, INK, w=370)
    s.text(x + 24, 244, where, 17, VIOLET if kind == "ai" else BLUE, w=370)
    s.text(x + 24, 290, body, 18, "#343a40", w=370)
lanes = [
    ("FRONTEND · Studio + Admin", [("React 19", "UI"), ("Vite 8", "dev server · build"), ("Tailwind 4", "styling · mobile"),
     ("React Router 7", "pages · ?tab · ?run"), ("TanStack Query 5", "fetch · job polling"), ("dnd-kit", "drag to reorder"),
     ("Recharts 3", "admin charts"), ("lucide · sonner", "icons · toasts")]),
    ("BACKEND · Python 3.11", [("FastAPI + Uvicorn", "REST API · server"), ("Pydantic", "request validation"),
     ("SQLAlchemy 2", "ORM · Postgres/SQLite"), ("psycopg 3", "Postgres driver"), ("supabase-py", "storage bucket"),
     ("openai", "gpt-4.1 calls"), ("PyTorch + open_clip", "CLIP runtime"), ("faster-whisper", "speech to text")]),
    ("", [("PySceneDetect", "scene cuts"), ("OpenCV", "frames · quality"), ("NumPy", "scoring maths"),
     ("Pillow", "CLIP image input"), ("psutil", "CPU/RAM metering"), ("requests", "Colab worker client"),
     ("python-multipart", "file uploads"), ("python-dotenv", ".env settings")]),
    ("TOOLS & SERVICES", [("FFmpeg 9", "cut · join · mix · title"), ("Supabase", "Postgres + Storage"),
     ("Google Colab T4", "optional free GPU"), ("cloudflared", "worker tunnel"), ("Conda", "Python env + FFmpeg"),
     ("Node 22", "builds the web apps"), ("Git / GitHub", "repo · notebook source"), ("Excalidraw", "this blueprint")]),
]
y = 520
for title, chips in lanes:
    if title:
        s.text(80, y, title, 17, RED, w=600)
        y += 30
    for j, (name, purpose) in enumerate(chips):
        s.box(80 + j * 220, y, 205, 66, f"{name}\n{purpose}", "proc", size=16, pad=8)
    y += 80

# =============================================================== 07 · Render & versions
slide("Render, export & versions", "The editor saves a cut + its mix; a render job turns it into a numbered, named version.",
      "08 Data, jobs & cost")
steps = [("Editor timeline\nV1 clips · A1 music · T1 title", "proc"), ("Save\ncut + mix", "data"),
         ("Render job\n5-stage progress screen", "proc"), ("① Cut clips", "proc"), ("② Join", "proc"),
         ("③ Finish", "proc"), ("Upload\nSupabase Storage", "data"), ("Version vN\nreadable file name", "good")]
bx = []
for i, (lbl, kind) in enumerate(steps):
    b = s.box(80 + i * 224, 200, 196, 120, lbl, kind, size=17, pad=10)
    if bx:
        s.arrow(bx[-1], b, sides="rl")
    bx.append(b)
s.box(752, 360, 644, 170, "① per clip: trim · scale/crop to 16:9, 9:16, 1:1 or 4:5 · 30 fps · clip volume (auto / manual / mute)\n"
      "② concat (hard cuts) or xfade + acrossfade (0.3 / 0.6 s)\n"
      "③ title in the last N s · music: start offset, loop, duck to 20% under dialogue, fade-out, limiter", "note", size=16, align="left")
hub = s.box(80, 560, 1170, 70, "Download for editor · generated on demand from the saved cut, no render needed", "proc", size=18)
s.arrow(bx[1], hub, sides="bt", end=(402, 560))
files = ["Clip list\nJSON · CSV", "EDL\nCMX3600 · 30 fps", "FCPXML 1.9\nResolve · Final Cut", "Results JSON\nOnSpotly's format"]
for i, f in enumerate(files):
    fx = 80 + i * 300
    fb = s.box(fx, 680, 270, 90, f, "data", size=17)
    s.arrow(hub, fb, sides="bt", start=(fx + 135, 630), end=(fx + 135, 680))
rec = s.box(1420, 560, 420, 100, "Export record\nversion · cut · format · music · title · size", "data", size=17)
s.arrow(bx[-1], rec, sides="bt", start=(1746, 320), end=(1746, 560))
vp = s.box(1420, 700, 420, 110, "Versions page\ngrouped by day · filter by cut · 6 per page · play · download · delete", "proc", size=17)
s.arrow(rec, vp, sides="bt")
s.box(1420, 840, 420, 80, "Bean-and-Bloom-grand-opening_\nAI-shot-list_16x9_v10_2026-11-02.mp4", "note", size=15)
s.box(80, 820, 1300, 170, "Verified in real renders: the title shows only in the last 3 s · music loops and fades out · music ducks under the welcome line "
      "and the speech carries it · 0 black frames · a 25 s cut renders in about 21–26 s plus 7–13 s upload · FFmpeg CPU is now metered "
      "(about 90 CPU-seconds per render). Not tested: importing the EDL/FCPXML into DaVinci or Premiere.", "note", size=18, align="left")

# =============================================================== 08 · Data, jobs & cost
slide("Data, jobs & cost", "One project holds everything; every job is metered and turned into cost lines.",
      "09 Development journey")
s.text(80, 180, "DATA MODEL", 18, RED, w=500)
proj = s.box(400, 470, 280, 120, "Project\nname · brief · length · format", "dark", size=18)
asset = s.box(80, 475, 260, 110, "Asset\nvideo or music · analysis JSON", "data", size=17)
shotl = s.box(400, 240, 280, 110, "ShotList\nshots + search hints (JSON)", "data", size=17)
job = s.box(400, 710, 280, 110, "Job\nkind · status · progress · steps", "data", size=17)
run = s.box(740, 475, 280, 110, "FinderRun · a cut\nresults · timeline · mix", "data", size=17)
exp = s.box(740, 710, 280, 110, "Export · a version\nfile name · options · downloads", "data", size=17)
s.arrow(proj, asset, "1:n", sides="lr", size=14)
s.arrow(proj, shotl, "1:n", sides="tb", size=14)
s.arrow(proj, job, "1:n", sides="bt", size=14)
s.arrow(proj, run, "1:n", sides="rl", size=14)
s.arrow(run, exp, "1:n", sides="bt", size=14)
s.arrow(shotl, run, "searched by", sides="rt", end=(880, 475), via=[(880, 295)], size=14)
s.text(80, 920, "Flexible structures (shots, results, timeline, mix) are JSON, so new fields need no migration; "
       "anything aggregated (status, cost, time) is a real column.", 17, MUTED, w=940)
s.text(1100, 180, "JOB LIFECYCLE", 18, RED, w=500)
qd = s.box(1100, 220, 170, 70, "queued", "proc", shape="ellipse", size=18)
rn = s.box(1340, 220, 170, 70, "running", "warn", shape="ellipse", size=18)
dn = s.box(1580, 160, 170, 70, "done", "good", shape="ellipse", size=18)
fl = s.box(1580, 280, 170, 70, "failed", "bad", shape="ellipse", size=18)
s.arrow(qd, rn, sides="rl")
s.arrow(rn, dn, sides="rl")
s.arrow(rn, fl, sides="rl")
s.text(1100, 370, "Server restart → running jobs marked failed (\"interrupted\"). Progress written ~every 0.7 s.", 16, MUTED, w=740)
m = s.box(1100, 450, 340, 120, "Each job step\nwall time · CPU incl. FFmpeg · peak RAM", "proc", size=17)
cr = s.box(1500, 450, 340, 120, "CostRecord\ncompute · LLM · storage · egress", "data", size=17)
ad = s.box(1500, 640, 340, 140, "Admin dashboard\nspend · cost per video · processing stats · heatmap · feed", "proc", size=17)
ev = s.box(1100, 640, 340, 140, "ActivityEvent\nuploads · runs · renders · fallbacks · downloads", "data", size=17)
s.arrow(m, cr, sides="rl")
s.arrow(cr, ad, sides="bt")
s.arrow(ev, ad, sides="rl")
s.box(1100, 830, 740, 160, "Prices are estimates, editable in .env: vCPU-hour $0.048 · storage $0.021/GB-month · egress $0.09/GB · "
      "gpt-4.1 $2 / $8 per 1M tokens. Measured: the whole café project ≈ $0.05, mostly gpt-4.1 tokens.", "note", size=17, align="left")

# =============================================================== 09 · Journey
slide("Development journey", "Each problem was found by running on real footage, measured, then fixed. In order.",
      "10 Evaluation")
items = [
    ("Espresso shot stolen", "An LLM look-alike for latte art said \"espresso\". Look-alikes now only count against their own shot."),
    ("Iced coffee chosen as latte art", "The softmax saturated. Added an absolute-similarity gate; customer words outweigh LLM phrasing."),
    ("Welcome clip began mid-speech", "Audio keywords ranked by priority: the clip starts on \"Welcome to Bean and Bloom\"."),
    ("Planner reordered the brief, 34 s", "Order taken from the brief quote and the length rescaled, both in code."),
    ("\"Street with no café\" killed a match", "CLIP can't read negation: negated look-alikes dropped, plus a 0.015 margin."),
    ("Stability 0.01: a bug?", "Measured the camera motion: the take really is handheld. The metric was kept."),
    ("Shot search ~33 s", "Batched CLIP text encoding: 7.5 s once the model is loaded."),
    ("Render CPU logged as 0.1 s", "FFmpeg child processes now metered: about 90 CPU-s per render."),
    ("Preview froze in a background tab", "requestAnimationFrame replaced by a timer clock."),
    ("One take served only one shot", "Keep the best 3 non-overlapping windows per scene (found via the Golden Crust test)."),
    ("\"Dark photo\" class punished dim scenes", "Removed; the quality score already handles darkness. Applause still missed."),
]
s.line(80, 545, 1840, 545, color=INK, width=3)
for i, (prob, fix) in enumerate(items):
    up_ = i % 2 == 0
    x = 80 + (i // 2) * 300 + (0 if up_ else 150)
    y = 200 if up_ else 600
    s.box(x, y, 280, 290, "", "proc")
    s.text(x + 18, y + 16, f"{i + 1:02d}", 18, MUTED)
    s.text(x + 18, y + 44, prob, 19, RED, w=244)
    s.text(x + 18, y + 120, fix, 17, GREEN, w=244)
    cx = x + 140
    s.line(cx, y + 290 if up_ else 545, cx, 545 if up_ else y, color=MUTED, width=1)
    s.box(cx - 9, 536, 18, 18, "", "brand", shape="ellipse")
s.text(80, 930, "Red = problem found by running on real footage   ·   Green = the fix that shipped", 18, MUTED, w=1000)

# =============================================================== 10 · Evaluation
slide("Evaluation", "Hand labels → automatic scoring → a check on clips the system never saw while tuning.",
      "11 Limits & next steps")
ev_steps = ["Hand-label every scene\ncontact sheets every 2 s + transcript", "ground_truth.json\ngood · ok · bad · look-alike per shot",
            "Run both lists × both approaches\nthrough the public API", "scripts/evaluate.py\nscores every results file",
            "Generalisation check\n4 unseen practice clips + 2 absent shots"]
prev = None
for i, lbl in enumerate(ev_steps):
    b = s.box(80, 190 + i * 160, 440, 120, lbl, "data" if i in (1, 3) else "proc", size=18)
    if prev:
        s.arrow(prev, b, sides="bt")
    prev = b
s.box(580, 190, 560, 300, "Metrics\ncorrect = ≥ 80% of the clip inside a correct take, or correctly reported missing\n"
      "spoken shot = the clip must contain the key line\npurity = share of the clip inside a correct take\n"
      "also counted: bad takes, look-alikes, false positives, start error of the spoken line", "note", size=18, align="left")
s.box(1180, 190, 660, 300, "Read with care: the thresholds were tuned on the café footage, so 8/8 is a best case. The practice clips "
      "were never used for tuning; that 5/6 is the honest number. Also checked: the steady latte take beat the handheld one; "
      "blurry and dark takes were never chosen; no look-alike was chosen.", "warn", size=18, align="left")
hdr = ["Shot list · approach", "Correct", "Absent shot", "Purity", "Spoken line"]
cw = [380, 160, 220, 160, 340]
rows_ = [
    (["Reference · hybrid", "8 / 8", "missing ✓", "97%", "0.3 s from start"], "good"),
    (["Reference · plain CLIP", "5 / 8", "faked ✗", "80%", "111.6 s off"], "bad"),
    (["AI list · hybrid", "7 / 7", "missing ✓", "98%", "0.3 s from start"], "good"),
    (["AI list · plain CLIP", "4 / 7", "faked ✗", "90%", "not found"], "bad"),
    (["Practice clips (unseen) · hybrid", "5 / 6", "2 / 2 ✓", "–", "applause missed (0.19)"], "warn"),
]
ty = 540
x = 580
for j, h_ in enumerate(hdr):
    s.box(x, ty, cw[j], 56, h_, "dark", size=18, radius=False)
    x += cw[j]
for r, (cells, kind) in enumerate(rows_):
    x = 580
    for j, c in enumerate(cells):
        s.box(x, ty + 56 + r * 64, cw[j], 64, c, kind if j == 0 else "proc", size=18, radius=False, width=1)
        x += cw[j]

# =============================================================== 11 · Limits & future
slide("Limits, trade-offs & next steps", "What it does not do yet, what we traded, and where it goes next.")
s.text(80, 185, "TRADE-OFFS", 20, ORANGE, w=500)
s.text(690, 185, "KNOWN GAPS", 20, RED, w=500)
s.text(1300, 185, "NEXT · WITH 2 MORE WEEKS", 20, GREEN, w=540)
trade = ["Strict threshold: never fakes a shot ⇄ a correct take can fall under it when hints are off",
         "CPU only: free and offline ⇄ about 0.7× realtime analysis", "LLM search hints: work for any brief ⇄ least predictable part",
         "Supabase in London: managed ⇄ ~190 ms per query from India", "Preview plays hard cuts: instant ⇄ fades only in the export"]
gaps = ["Thresholds tuned on one footage set", "Colab worker tested with a local stand-in, not on real Colab",
        "EDL / FCPXML not imported into DaVinci or Premiere", "No automated test suite",
        "Reference cut is 25 s: list is 28 s and the ribbon shot is missing", "No user accounts; not deployed online"]
nxt = ["Benchmark 20–50 real projects; calibrate per shot type", "Second opinion: small vision model says yes/no on close calls",
       "Action models (X-CLIP) for \"ribbon being cut\", \"glasses raised\"", "J/L-cuts: lay a spoken line over the best visual",
       "GPU / ONNX CLIP, adaptive sampling, Redis job queue", "Smart vertical crop that follows faces", "Accounts + a database region near users"]
for i, t in enumerate(trade):
    s.box(80, 230 + i * 150, 560, 120, t, "warn", size=19, align="left")
for i, t in enumerate(gaps):
    s.box(690, 230 + i * 125, 560, 100, t, "bad", size=19, align="left")
prev = None
for i, t in enumerate(nxt):
    b = s.box(1300, 230 + i * 110, 540, 84, f"{i + 1}  {t}", "good", size=18, align="left")
    if prev:
        s.arrow(prev, b, sides="bt")
    prev = b

OUT.parent.mkdir(parents=True, exist_ok=True)
s.save(OUT)
print(f"wrote {OUT} · {_slide} slides · {len(s.els)} elements")

# OnSpotly Studio · Smart Rough Cut

**Customer brief → AI shot list → AI finds the shots in raw footage → editable rough cut → MP4 + editor files.**

A small but complete platform: upload any footage (files or a zip), paste any brief, and get a
timed rough cut that an editor can fine-tune or download as a finished video. Nothing is
hard-coded to the café assignment; it is the first project the platform was run on.

| | |
|---|---|
| **Studio** (`/`) | Projects · footage upload & analysis · AI shot planner with an editable list · shot finder · editor screen (preview, drag to reorder, trim, swap takes, honest "missing") · exports |
| **Admin** (`/admin`) | KPIs, spend over time, per-video cost analysis (processing time, CPU, RAM, tokens, storage, egress), processing statistics, activity heatmap, finder-quality histograms, activity feed, system health |
| **Outputs** | Edited MP4 (16:9 / 9:16 / 1:1 / 4:5, optional fades, end title, background music) · clip list JSON + CSV · CMX3600 EDL · FCPXML · shot-finder results JSON in OnSpotly's format |

## Results (measured against my hand labels of the footage)

| Shot list | Hybrid finder (mine) | Plain-CLIP baseline |
|---|---|---|
| OnSpotly reference list (8 shots) | **8 / 8 correct**, ribbon cutting reported missing (not in footage), 97 % timestamp purity | 5 / 8 (fakes the ribbon cutting, misses the spoken welcome) |
| My AI shot list (7 shots) | **7 / 7 correct** | 4 / 7 |
| Unseen practice clips (4 + 2 absent shots) | 5 / 6 (applause clip missed) | n/a |

No blurry, dark or look-alike take was chosen; the spoken welcome line is found within 0.3 s.
Thresholds were tuned on the café footage, so the practice-clip score is the honest number for new footage.
Details: [docs/research_note.md](docs/research_note.md) · scored by `scripts/evaluate.py` against `docs/ground_truth.json`.

## Run it (2 commands)

Requirements: **Python 3.11+** and **FFmpeg** on PATH. The web apps are already built (`frontend/dist`,
`admin/dist`), so Node.js is only needed if you change the frontend code.

```bash
pip install -r requirements.txt
python run.py
```

Open **http://localhost:8000** (Studio) and **http://localhost:8000/admin** (Admin).
`run.py` builds both web apps on first start, then serves the API and the apps from one process.
The first analysis downloads the CLIP (~600 MB) and Whisper-small (~480 MB) weights.

With conda (what I used): `conda create -n onspotly -c conda-forge python=3.11 ffmpeg` then the two commands above.

### Configuration (optional, `.env`)

Copy `.env.example` to `.env`. **Everything is optional**; the platform falls back gracefully:

| Setting | When set | When empty |
|---|---|---|
| `DATABASE_URL` | Supabase Postgres (session pooler URI) | local SQLite in `data/` |
| `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | Supabase Storage bucket `media` (created automatically) | local disk in `data/storage` |
| `OPENAI_API_KEY` (+ `OPENAI_MODEL`, default `gpt-4.1`) | AI shot planner + search hints | rule-based planner (keyword rules) |
| `ADMIN_PASSWORD` | admin dashboard requires login | admin is open (local dev) |
| `PRICE_*` | unit prices used by the cost tracker | sensible defaults |

### Optional: free GPU analysis on Google Colab

Analysis (CLIP + Whisper) is the slow step on a CPU. To offload it to a free Colab T4:

1. Upload [`notebooks/colab_gpu_worker.ipynb`](notebooks/colab_gpu_worker.ipynb) to https://colab.research.google.com
2. `Runtime → Change runtime type → T4 GPU`, then `Runtime → Run all`
3. Copy the printed **Worker URL** + **token** into Studio → **Settings** (the CPU/GPU badge in the header) →
   *Google Colab GPU* → *Test connection* → *Save*

The notebook runs the same analysis code (`backend/app/worker.py`) behind a free Cloudflare
tunnel, protected by the random token. If the Colab session ends, jobs fall back to local CPU
automatically (logged in the admin activity feed). Each analysed file shows a `Colab GPU` or `CPU` chip.

### Reproduce the assignment deliverables

With the server running:

```bash
python scripts/run_assignment.py --api http://localhost:8000
```

```bash
python scripts/evaluate.py
```

The first command creates the project through the public API, uploads the footage, plans the AI
shot list, imports the reference list, runs both finder approaches on both lists, renders the
videos and writes everything to `deliverables/`. The second scores all results against my
hand labels in `docs/ground_truth.json`.

## How it works

```
brief ──► Shot planner (gpt-4.1 → JSON; brief-grounded order + exact length enforced in code; rule fallback)
              │  each shot: name, description, target_seconds, order, needs_audio,
              │  + search hints: visual queries, look-alike negatives, audio keywords
              ▼
footage ─► Analysis (once per file, cached)
              PySceneDetect scenes · OpenCV quality @6 fps (sharpness = Laplacian variance,
              brightness, stability = jitter of phase-correlation camera motion) ·
              OpenCLIP ViT-B/16 embeddings @2 fps · faster-whisper word timestamps
              ▼
           Shot finder ("hybrid")
              1. per frame: softmax over [all shots + this shot's look-alikes + background]
                 × gate on closeness to the shot's strongest match anywhere in the footage
              2. windows of the shot's length slide inside scenes (never across a cut)
              3. score = visual fit × (0.55 + 0.45 × take quality)
              4. needs_audio shots must be confirmed in the transcript (keyword → word timestamps)
              5. greedy global assignment: no moment used twice
              6. below threshold → "missing" + reason + closest candidates (never forced)
              ▼
           Editor screen → timeline (order, trims, swaps) → FFmpeg render + JSON/CSV/EDL/FCPXML
```

More detail, measured results and failures: **[docs/research_note.md](docs/research_note.md)**.

**Technical blueprint (11-slide Excalidraw deck):** [`docs/architecture/onspotly_blueprint.excalidraw`](docs/architecture/onspotly_blueprint.excalidraw)
(open at https://excalidraw.com → menu → Open). Covers architecture, analysis pipeline, shot planning,
hybrid finder, models & stack, rendering & versions, data/jobs/cost, development journey, evaluation and
limits. Regenerate with `python scripts/blueprint/build_blueprint.py`.

## Project structure

```
backend/app/
  api/v1/        projects.py (projects, uploads, shot lists, runs, exports, jobs) · admin.py (analytics)
  core/          config.py (settings, prices, provider selection)
  db/            SQLAlchemy models + session (Postgres or SQLite)
  providers/     storage (Supabase/local) · llm (OpenAI) · vision (OpenCLIP) · speech (Whisper)
                 · compute (local CPU or remote GPU worker)
  worker.py      standalone analysis worker (run on Colab GPU via notebooks/colab_gpu_worker.ipynb)
  pipeline/      analyze.py (scenes, quality, embeddings, transcript)
  services/      planner · finder · exporter · tracking (cost + activity)
  workers/       jobs.py (background jobs, timings, resource usage) · handlers.py
frontend/        React + Vite + Tailwind (Studio, mobile-first)
admin/           React + Vite + Tailwind + Recharts (Admin dashboard)
scripts/         run_assignment.py · evaluate.py
docs/            research note, ground truth labels, evaluation, comparison, AI-use note
deliverables/    shot lists, results (both lists × both approaches), clip lists, EDL, FCPXML
```

Swapping a provider (another LLM, S3 instead of Supabase, a bigger vision model) means adding one
class in `providers/`; new pipeline steps plug into `pipeline/` and are metered automatically by
the job runner.

## Submission documents

- [docs/research_note.md](docs/research_note.md): approaches, measured accuracy, failures, next steps, processing time
- [docs/shot_list_comparison.md](docs/shot_list_comparison.md): AI shot list vs reference
- [docs/ai_use.md](docs/ai_use.md): AI tools used and what I checked myself
- `deliverables/`: AI shot list JSON, results for both lists, clip lists, EDL/FCPXML (videos are shared by link)

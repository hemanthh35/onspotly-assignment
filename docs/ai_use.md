# AI-use note

**Coding assistant.** I built this with **Claude Code (Anthropic)** as a pair-programmer. It
drafted most of the code (FastAPI backend, analysis pipeline, shot finder, exporters, both React
apps), the evaluation script and first drafts of these documents, while I set the requirements,
architecture and stack (React + Vite, FastAPI, Supabase Postgres + Storage, an admin dashboard
with cost analysis). Everything was run on my machine and checked against the real footage, not
assumed to work. Things that were checked and fixed along the way:

- the hybrid finder first stole the espresso shot because an LLM-written look-alike ("espresso
  shot being pulled") penalised every shot; look-alikes were made per-shot;
- latte art was confused with "milk poured into iced coffee"; I measured raw CLIP similarities
  per query, found the softmax was hiding the gap, and added the absolute-similarity gate;
- the welcome clip started on the second sentence; audio keywords are now ranked by priority;
- the planner reordered the brief and returned 34 s instead of 30 s; order and length are now
  enforced in code using a quote from the brief for every shot;
- a stability score of 0.01 on a latte-art take looked like a bug, but measuring the camera
  motion showed that take really is handheld/shaky, so the metric was kept.

I labelled the footage myself (`docs/ground_truth.json`) by watching contact sheets and reading
the transcript, and all accuracy numbers come from `scripts/evaluate.py` against those labels.

**AI inside the product.** OpenAI **gpt-4.1** plans the shot list and writes search hints
(optional, with a rule-based fallback); **OpenCLIP ViT-B/16** (open source) matches frames to
text; **faster-whisper small** (open source) transcribes speech. Both open-source models run
on CPU.

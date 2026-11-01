# Research note: Smart Rough Cut

## 1. Problem and approach

Input: a free-text brief and unlabelled footage (one 206.7 s raw file with 19 scenes in random
order, plus 3 short uploads). Output: a timed, ordered clip list and a rough cut. The footage
is deliberately messy: look-alike scenes (iced-coffee pour vs. latte art, concert crowd vs.
toast, cookie close-up vs. pastry case), unusable takes (a blurry latte pour, a far too dark
bar scene, a handheld latte pour), a moment that can only be *heard* (the welcome line plays
over a French-press shot, and the owner is never on screen), and a shot that is not in the
footage at all (ribbon cutting).

### Approaches considered

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **Plain CLIP**: embed frames, cosine vs. shot text, take the best frame | fast, simple, open source, CPU | no notion of "wrong but similar", no quality, forces a match for absent shots | kept as **baseline** |
| **Vision-language captions** (Moondream/SmolVLM/BLIP) per keyframe, then text matching | rich explanations | 5-20× slower on CPU, captions lose detail, still needs thresholds | rejected for time on CPU; noted as future work |
| **Cloud vision LLM** (GPT-4o on keyframes) | strongest reasoning | paid, must work offline per the rules, latency | optional future provider |
| **Hybrid (chosen)**: CLIP + per-shot contrastive scoring + scene windows + measured quality + speech transcript | handles look-alikes, bad takes, audio moments and absent shots explicitly; ~7 s per search once analysed | more moving parts and thresholds | **main approach** |

### What the hybrid finder does

1. **Analysis once per file** (cached): PySceneDetect scenes; quality at 6 fps:
   *sharpness* = Laplacian variance (log-scaled), *brightness* = mean luma with penalties for
   dark or blown-out frames, *stability* = jitter (change in frame-to-frame camera motion from
   phase correlation, so smooth pans score well and handheld shake doesn't); OpenCLIP ViT-B/16
   embeddings at 2 fps; faster-whisper word timestamps.
2. **Search hints**: the LLM writes, per shot, 3 visual queries, 2-3 look-alikes to reject and
   audio keywords. This works for *any* shot list, including the reference CSV, which has no hints.
3. **Frame score** = *relative fit* (softmax over all shots of the list + this shot's look-alikes +
   generic background classes) × *absolute fit* (a sigmoid gate on how close the frame is to the
   strongest match for this shot anywhere in the footage). The softmax alone saturates: milk
   poured into iced coffee "won" latte art because nothing else fitted better.
4. **Windows** of the shot's target length slide inside scenes (never across a cut);
   score = mean frame score × (0.55 + 0.45 × take quality).
5. **Audio shots** (`needs_audio`) must be confirmed by a keyword in the transcript; the clip
   starts on the requested line and runs to the end of the spoken thought. A visual look-alike
   without the line is only a low-confidence suggestion.
6. **Greedy global assignment** by confidence (no moment used twice); below the threshold
   (0.25) a shot is **missing** with the reason and closest candidates, never forced.

## 2. Measured results

I labelled every scene of every file by hand (`docs/ground_truth.json`, from contact sheets
every 2 s plus the transcript) and scored the results with `scripts/evaluate.py`. A shot counts
as correct if ≥ 80 % of the chosen clip lies inside a correct take (for the audio shot, the clip
must contain the spoken key line), or if it is correctly reported missing. *Purity* = share of the
chosen clip inside a correct segment (timestamp accuracy).

| Shot list · approach | Correct | Absent shot handled | False positives | Bad / look-alike takes | Purity | Welcome-line start error |
|---|---|---|---|---|---|---|
| **Reference · hybrid** | **8 / 8 (100 %)** | ✅ ribbon = missing | 0 | 0 / 0 | **97 %** | **0.3 s** (deliberate lead-in) |
| Reference · baseline | 5 / 8 (62 %) | ❌ invented a ribbon | 1 | 0 / 0 | 80 % | 111.6 s (wrong place) |
| **AI list · hybrid** | **7 / 7 (100 %)** | ✅ | 0 | 0 / 0 | **98 %** | 0.3 s |
| AI list · baseline | 4 / 7 (57 %) | ❌ | 1 (+1 false "missing") | 0 / 0 | 90 % | welcome line not found |

Specific checks: of the two sharp latte-art takes the steady one (174-188 s) was chosen over
the handheld one; the blurry (34-44 s) and dark (68-78 s) takes were never chosen; none of the
look-alikes (iced-coffee pour, steaming milk, cookies, concert crowd, tea pour) were chosen;
the welcome clip is 58.15-63.15 s and contains "Welcome to Bean and Bloom. Thank you so much for
coming to our grand opening today."

**Generalisation check on unseen clips** (`scripts/practice_test.py`, the 4 practice clips were
never used for tuning; their titles become shots and two absent shots are added): **5 / 6 correct**.
Coffee pour, pastry and smiling friends were found in the right clip, and "ribbon cutting" and
"dog on a beach" were correctly reported missing (score 0.00). **Failure:** "Applauding at the
end of a stage show" scored 0.19 < 0.25 and was reported missing; the clip is dark stage footage
and the quality weighting pushed a correct match under the threshold.

## 3. What failed or is weak (honestly)

- **Thresholds were tuned on this footage.** The 100 % above is on data I iterated on. The
  practice set is the honest number for unseen footage, and it already shows the trade-off:
  a stricter threshold avoids faked shots but can drop correct dark or low-quality takes.
  The fix is calibration on a labelled set of 20-50 real projects, ideally per shot type.
- **LLM-written hints are a risk.** Early versions failed because the LLM wrote negations
  ("street with no café"; CLIP cannot read "no"), listed another shot as a look-alike, or added
  details not in the brief ("coffee cups" for a champagne toast). I now filter negations, apply
  look-alikes only to their own shot with a margin, weight the customer's words above the LLM's,
  and prompt against invented detail, but the hints remain the least predictable part.
- **The planner needed code-level guardrails.** gpt-4.1 reordered the brief and returned 34 s for
  a 30 s request; order (via a quote from the brief per shot) and length are now enforced in code.
  It also merges "coffee being made + latte art" into one shot where the reference splits them
  (see `shot_list_comparison.md`).
- **The audio shot has no visual of the speaker.** It is found correctly, but the picture is a
  French press. The reason says "speaker not clearly visible", and an editor might prefer to lay
  the audio over another shot (J-cut), which the platform does not automate yet.
- **Length.** The reference list adds up to 28 s and one shot is missing, so the cut is 25 s;
  the editor has a "Fit to 30s" button that extends clips proportionally inside their scenes.
- **CPU speed.** Analysis runs at about 0.7× realtime (326 s for 231 s of footage), dominated by
  CLIP and the frame scan of the long file.

## 4. With two more weeks

1. Build a labelled benchmark (20-50 projects) and calibrate thresholds per shot type; report
   precision/recall curves instead of one operating point.
2. Add a **second-opinion verifier** for low-margin decisions: a small VLM (Moondream/SmolVLM)
   or an optional GPT-4o vision call on 3 keyframes answering "is this latte art: yes/no?".
3. **Temporal models**: action-level matching (X-CLIP / VideoMAE) for moments like a ribbon being
   *cut* or glasses being *raised*, instead of single frames.
4. **Audio-visual editing**: J/L-cuts so a spoken line can play over the best visual, audio
   ducking and beat-synced cuts with music.
5. **Speed**: GPU or ONNX/OpenVINO CLIP, adaptive frame sampling (dense only near scene
   changes), parallel analysis per file, and a Redis/Celery worker queue for scale.
6. **Smart vertical crop** that follows faces and subjects instead of a centre crop.

## 5. Processing time and machine

Machine: **AMD Ryzen 5 5600H (6 cores / 12 threads), 16 GB RAM, no GPU (CPU only)**, Windows 11,
Python 3.11. Database and storage on Supabase (eu-west-2).

| Step | Wall time | CPU time | Peak RAM |
|---|---|---|---|
| Analysis of all 4 files (230.9 s of footage) | **326 s** (raw file 244 s, uploads 23-29 s each) | 488 s | 1.6 GB |
| Search hints (gpt-4.1) | 2-13 s | ~0 | - |
| Shot search, one list (hybrid) | 17 s with the model loaded (38 s on the first search after start, which includes loading CLIP; now pre-loaded at start-up) | 24 s | 1.3 GB |
| Shot search (baseline) | 2.4 s | 4 s | - |
| Render 25 s MP4 (FFmpeg) + upload to Supabase | 21-26 s render + 7-13 s upload | - | - |
| Whole assignment, both lists × both approaches + 2 renders | ~10 min end to end | | |

The first run also downloads the model weights (CLIP ~600 MB, Whisper-small ~480 MB).
Measured platform cost for the whole assignment project (admin dashboard, estimated at cloud
prices): about **$0.05**, mostly gpt-4.1 tokens (~7 k tokens ≈ $0.04), with compute ≈ $0.008,
storage ≈ $0.001 and egress ≈ $0.002.

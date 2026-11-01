# OnSpotly — Intern Assignment: "Smart Rough Cut"

&nbsp;

---

## 1\. About OnSpotly

OnSpotly lets people book a nearby creator who shoots, edits and delivers social-media videos within minutes. Our next big step is an AI layer that understands what the customer wants, plans the shots, finds the right moments in the footage, and builds the edit automatically.

This assignment is a small, real version of that problem:

**Customer brief → AI plans the shot list → (creator shoots) → AI finds the shots in the footage → rough cut \+ clip list for the editor**

## 2\. The scenario

A creator just filmed the **grand opening of "Bean & Bloom", a small café**. They uploaded:

- **one long raw video** (about 3.5 minutes) with everything they shot, in no particular order, and  
- **3 extra short clips** uploaded separately.

The customer wants a **30-second Instagram reel**. All they gave us is a short **brief** in their own words (in `02_Resources/brief.md`).

Your job: **build a small app that turns the brief into a shot list, finds the right moments in the footage for each shot, cuts them into clips with timestamps, puts them in order, and lets an editor either fine-tune the cut or download a ready-made edited video.**

Real footage is messy. Not everything the customer asked for is guaranteed to be there, and not every take is usable. Your system should handle that honestly.

## 3\. What we give you

Everything is in `02_Resources` — start with `00_START_HERE.md`.

| File | What it is |
| :---- | :---- |
| `brief.md` | The customer's request, in their words — **the main input** |
| `reference_shot_list.json` / `.csv` | The shot list **our** planning step produced for this brief. Use it to test your shot finder and to compare with your own list. |
| `footage/raw_footage.mp4` | The long raw video (no labels, no timestamps given) |
| `footage/upload_01–03.mp4` | Extra clips uploaded separately |
| `practice/` | 4 practice clips **with titles and descriptions** to test your ideas |
| `output_format_example.json` | The structure we'd like your results in |
| `CREDITS_AND_LICENSES.md` | Where the clips come from (all free to use) |

You may also test with your own sample videos.

## 4\. What to build

A **proof of concept is fine**, but it must run end to end.

### Must have

1. **AI shot planner (brief → shot list).**  
   - Read the free-text brief and use AI to produce a **structured shot list**: `shot_id`, `name`, `description`, `target_seconds`, `order`, and `needs_audio` (true if the moment can only be found by what is said or heard).  
   - The list should follow the brief, add up to about the target length, and **not invent** things the customer did not ask for.  
   - The user can **edit** the shot list in the app (rename, change length, add or remove a shot) before searching.  
   - Free / open-source models are fine; a simple rule-based fallback is allowed if no model is available — tell us which you used.  
2. **AI shot finder.** It must work on **any** shot list loaded into the app (yours or ours). For every shot, search **all** the footage and return:  
   - the best matching clip: **file, start time, end time** (in seconds)  
   - a **confidence score** and a **short reason** ("close-up of a cup, milk being poured into it")  
   - a simple **quality score** (e.g. sharpness, brightness, stability)  
   - up to **2 alternative** options  
   - **"missing"** if the shot is not in the footage — do not force a match  
3. **Editor screen (web UI).**  
   - One row/card per shot, in order  
   - **Preview** the selected clip  
   - **Reorder** the shots  
   - Show what's missing  
4. **Two outputs.**  
   - **"Download edited video"**: an MP4 that joins the selected clips in order (about 30 seconds). FFmpeg is fine.  
   - **"Download for editor"**: the clip list with timestamps (JSON or CSV) so a human editor can rebuild or fine-tune the cut.  
5. **README** that lets us run it in 1–2 commands.

### Nice to have (extra credit)

- Trim start/end on screen; swap to an alternative  
- An edit file for professional editors (EDL / FCPXML) for Premiere or DaVinci  
- Background processing with a progress status  
- Comparing **two approaches** for shot finding with measured numbers

## 5\. Rules

- Free, open-source models running on a normal laptop are enough (CPU is OK). Free API tiers are allowed as an optional extra, but the app must still work without them.  
- **Any tech stack.** For example React/Next.js for the UI, Python (FastAPI) or Java (Spring Boot) for the backend, any database (SQLite is fine).  
- **Using AI coding tools is allowed and encouraged.** You must understand and be able to explain every part of your submission.  
- **Report how long processing takes** on your machine (and your machine's CPU/RAM/GPU).  
- If something is not possible in the time, **tell us** — a clear plan or a small prototype for that part still earns credit.

## 6\. What to submit

email us with:

1. **GitHub repository link** (public)  
2. **Demo video** (max 5 minutes): brief in → shot list → shots found → editor screen → both downloads (share drive link \- with anyone can view permission)  
3. **Your AI-made shot list** (JSON) and a **short comparison with our reference shot list**: what matched, what you missed, what you added, and why  
4. **Shot-finder results for BOTH shot lists** (yours and our reference), in the output format — plus the **edited video** and **clip list file** made from the reference list  
5. **Research note** (1–2 pages, PDF or Markdown in the repo):  
   - Approaches you considered and **why** you chose yours  
   - **How well it works, measured**: label the footage yourself (what is where), then report how many shots your system found correctly and how close the timestamps are  
   - What failed or what is weak, and what you would do with 2 more weeks  
   - Processing time and machine used  
6. **AI-use note** (a short paragraph): which AI tools you used, for what, and what you checked or fixed yourself

## 7\. How we evaluate

| Area | Weight |
| :---- | :---- |
| Shot list from the brief (covers the brief, sensible lengths, nothing invented, editable) | 10% |
| Finds the right shots (correct moments, good timestamps, good takes) | 25% |
| Handles real-world mess (missing shots, look-alike shots, bad takes) | 15% |
| Research note: measured results, honest failures, clear thinking | 15% |
| Editor screen: usable, clear, preview/reorder/edit | 15% |
| Outputs: edited video \+ editor file both work | 10% |
| Engineering, README, demo and AI-use honesty | 10% |

Strong research with an honest, partly working system beats a flashy demo that only works on the happy path.

## 8\. Next step

Shortlisted candidates get a **45-minute call**: walk us through your solution, run it on a new brief, and debug one case together.

Good luck — we're excited to see how you think. **The OnSpotly team**
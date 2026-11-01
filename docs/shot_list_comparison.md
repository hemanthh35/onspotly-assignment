# My AI shot list vs. OnSpotly's reference list

My planner: **gpt-4.1**, JSON output, with two rules enforced in code because the model did not
follow them reliably from the prompt alone: (1) every shot must quote the words of the brief
it comes from, and shots are sorted by where that quote appears (unless the brief says "start
with"/"end with"); (2) durations are rescaled to exactly the requested length. A shot whose quote
cannot be found in the brief is flagged "not in brief?" in the editor.
File: [`deliverables/ai_shot_list.json`](../deliverables/ai_shot_list.json).

| # | Reference (8 shots, 28 s) | My AI list (7 shots, 30 s) | |
|---|---|---|---|
| 1 | S1 Café exterior · 3 s | A1 Café Exterior · 4 s | ✅ match |
| 2 | S2 Barista making coffee · 3 s | A2 Coffee Making & Latte Art · 6 s | ⚠️ merged |
| 3 | S3 Latte art close-up · 4 s | (part of A2) | ⚠️ merged |
| 4 | S4 Happy customers · 4 s | A3 Happy Customers · 4 s | ✅ match |
| 5 | S5 Pastry display · 3 s | A4 Pastries Close-Up · 4 s | ✅ match |
| 6 | S6 Owner welcomes guests · 5 s | A5 Owner Welcoming · 4 s, **needs_audio = true** | ✅ match |
| 7 | S7 Ribbon cutting · 3 s | A6 Ribbon Cutting · 4 s | ✅ match |
| 8 | S8 Celebration toast · 3 s | A7 Group Toast · 4 s | ✅ match |

**Shot-finder outcome on my list** (`deliverables/results_ai_hybrid.json`): 7/7 correct. A1 alley
with outdoor seating (112.1-116.1 s), A2 the steady latte-art take (180.0-186.0 s), A3 customers
(145.4-149.4 s), A4 pastry case (166.0-170.0 s), A5 the spoken welcome line (58.15-62.71 s), A6
ribbon cutting reported **missing**, A7 champagne toast (189.0-193.0 s).

Note: the LLM's wording changes a little between runs (e.g. "Café exterior at grand opening" vs
"Café Exterior"), but the structure (7 shots, this order, 30 s, welcome = audio) was identical in
every run I made.

**What matched.** All eight moments of the brief are covered, in the same order as the
reference, with the same ending. The welcome shot is correctly marked `needs_audio` (the brief
says "use the bit where I actually say welcome"), and nothing was invented: no extra
"atmosphere" or logo shots, and every shot traces back to a quote from the brief.

**What I missed / did differently.** The model treats "show our coffee being made, especially
the latte art" as one moment (6 s) where the reference splits it into espresso (S2) + latte
art (S3). Both readings are defensible, but the reference split is better for an edit: two
shorter shots give more energy, and they are found in different takes (espresso machine vs.
pour). The shot finder copes with the merge: it picks the latte-art take for A2, so the
espresso moment is simply not in my cut. My durations are a little longer (4 s vs 3 s) because I
fill the requested 30 s exactly while the reference adds up to 28 s.

**What I added.** Nothing beyond the brief. Small wording liberties ("raising their cups",
"inside the café") appear in some descriptions; they do not change what the finder searches for
because the finder weights the shot name and the customer's words above extra phrasing.

**Why the planner is built this way.** An editor needs a list that is faithful to the customer
more than a creative one. The "quote from the brief" requirement turns "don't invent things"
into something the code can check, and the editor screen keeps the human in charge: rename,
re-time, split (add a shot), delete or reorder before searching.

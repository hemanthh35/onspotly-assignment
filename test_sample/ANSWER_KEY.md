# Answer key: what the platform SHOULD find

Don't look at this until you have run the test. Then compare.

## What is in the footage

`golden_crust_raw_footage.mp4` (34 s, shots in random order):

| Time | What it shows | Notes |
|---|---|---|
| 0 – 8 s | Audience applauding at a stage show | dark stage lighting, the "applause" shot |
| 8 – 15 s | Freshly baked pastries, **blurry and too dark** | ❌ bad take, should NOT be picked |
| 15 – 26 s | Friends smiling at the camera; at **~16.5 s** a voice says *"Thank you all for coming! Happy first anniversary to Golden Crust Bakery..."* | happy regulars **and** the spoken thank-you |
| 26 – 34 s | Coffee being poured into a cup | the opening shot |

`golden_crust_upload_01.mp4` (8 s): the same pastries, **sharp and bright**. ✅ good take.

## Expected result per shot

| Shot in the brief | Expected | What it tests |
|---|---|---|
| Coffee being poured | raw **26–34 s** | normal visual match |
| Freshly baked pastries | **upload_01** (sharp), *not* raw 8–15 s | picks the good take over the blurry/dark one |
| Happy regulars smiling | raw **15–26 s** | visual match |
| Owner says thank you | raw **~16.2 s onward**, marked *found by audio*, reason quotes "Thank you all for coming…" | finding a moment by sound (Whisper) |
| Free cupcakes for kids | **MISSING**: not in the footage | honesty, never fakes a shot |
| Crowd applauding | raw **0–8 s**, *or* reported missing | known weakness (see below) |

Note on the applause shot: this is a known weakness. The visual match is strong (about 0.93 per
frame), but the AI-written look-alikes for it (e.g. "performers acting on stage") are too close to
applause itself and pull the score under the 0.25 threshold, so it is usually reported missing,
sometimes with no candidates listed. That's an honest miss, not a crash.

The "regulars" and "thank you" shots come from the same take (15–26 s). The finder never uses the
same moment twice, so it gives them different, non-overlapping parts of that take, or uses the rest
of the take for the second one.

## Pass criteria
- Shot list follows the brief's order and adds up to 20 s, with the thank-you shot marked *found by audio*.
- Cupcakes reported **missing** (not faked).
- Pastries come from **upload_01**, not the blurry raw take.
- Thank-you clip contains the spoken line.
- Render works: 9:16 MP4 with music/title if you add them.

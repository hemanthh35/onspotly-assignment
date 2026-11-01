# START HERE — how to use these resources

## 1. Read the task
`../01_ASSIGNMENT_TASK.md` explains what to build and what to submit.

## 2. Understand what the customer wants
- `brief.md` — the customer's request in their own words. **This is the main input**: your AI shot planner turns it into a shot list.
- `reference_shot_list.json` (or `.csv`) — the shot list **our** planning step produced from the same brief, **in order**, with a target length for each (IDs `S1` … `S8`).
  Use it to (a) test your shot finder and (b) compare with the list your own AI makes. Submit shot-finder results for **both** lists.

## 3. Practice first (`practice/`)
4 short clips **with a title and description** in `practice/practice_clips.csv`.
Use them to try your matching ideas and check your quality scores before running on the real footage.

## 4. The real footage (`footage/`)
| File | Length | Notes |
|---|---|---|
| `raw_footage.mp4` | 206.7 s | Everything the creator filmed, in random order. No labels or timestamps are provided. |
| `upload_01.mp4` | 13.2 s | Extra clip uploaded separately by the creator. |
| `upload_02.mp4` | 8.0 s | Extra clip uploaded separately by the creator. |
| `upload_03.mp4` | 3.0 s | Extra clip uploaded separately by the creator. |

All videos: 1280×720, 30 fps, H.264 MP4 with an AAC audio track. Some parts have sound that matters.

Realistic notes:
- Shots are **not** in the customer's order and there are clips the customer didn't ask for.
- Some moments look similar to what the customer asked for but are **not** the right shot.
- Some takes are not usable (quality). Pick the best one.
- Not everything in the shot list is guaranteed to exist. If a shot isn't there, say so.

## 5. Output format
`output_format_example.json` shows the structure we'd like for your results
(the numbers in it are **made up** — they are only an example of the format).
Times are **in seconds from the start of each file**.

## 6. Tools you might find useful (all free)
FFmpeg · OpenCV · PySceneDetect · open-source image–text or vision–language models · open-source speech-to-text.
You choose — and tell us why in your research note.

## 7. Licenses
See `CREDITS_AND_LICENSES.md`. Please use these files only for this assignment.

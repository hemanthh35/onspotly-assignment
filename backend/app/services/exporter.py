"""Outputs: rendered MP4 (FFmpeg), clip list JSON/CSV, CMX3600 EDL, FCPXML, results JSON."""
from __future__ import annotations

import csv
import io
import json
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import psutil

from app.core.config import FFMPEG

FPS = 30
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720), "4:5": (720, 900)}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def machine_info() -> str:
    cpu = platform.processor() or platform.machine()
    try:
        import subprocess as sp
        if platform.system() == "Windows":
            name = sp.run(["powershell", "-NoProfile", "-c", "(Get-CimInstance Win32_Processor).Name"],
                          capture_output=True, text=True, timeout=10).stdout.strip()
            cpu = name or cpu
    except Exception:
        pass
    ram = round(psutil.virtual_memory().total / 2**30)
    return f"{cpu}, {psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads, {ram} GB RAM, no GPU (CPU only)"


_child_cpu = threading.local()


def child_cpu_seconds() -> float:
    """CPU seconds used by FFmpeg subprocesses started from the current thread."""
    return getattr(_child_cpu, "total", 0.0)


def _run(cmd: list[str]) -> None:
    proc = psutil.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    cpu, err = 0.0, []
    reader = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)
    reader.start()
    while proc.poll() is None:
        try:
            t = proc.cpu_times()
            cpu = t.user + t.system
        except psutil.Error:
            pass
        time.sleep(0.2)
    reader.join(timeout=5)
    _child_cpu.total = child_cpu_seconds() + cpu
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {''.join(err)[-1500:]}")


def _ff_path(p: Path | str) -> str:
    """Path escaped for use inside an FFmpeg filter argument."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _has_audio(path: Path) -> bool:
    from app.pipeline.analyze import probe
    return probe(path)["has_audio"]


def render_mp4(clips: list[dict], sources: dict[str, Path], out: Path, *, aspect: str = "16:9",
               crossfade: float = 0.0, title: str = "", music: Path | None = None,
               music_volume: float = 0.5, progress: Callable[[float, str], None] = lambda p, m: None) -> dict:
    """clips: [{file, start, end, needs_audio}] in order. Returns {duration, size_bytes}."""
    if not clips:
        raise ValueError("Nothing to render: the timeline is empty")
    W, H = SIZES.get(aspect, SIZES["16:9"])
    work = out.parent / f"_{out.stem}_parts"
    work.mkdir(parents=True, exist_ok=True)
    seg_paths, durs = [], []
    # When music is added, original sound is ducked except for shots that need their audio.
    for i, c in enumerate(clips):
        progress(0.05 + 0.6 * i / len(clips), f"Cutting clip {i + 1}/{len(clips)}")
        src = sources[c["file"]]
        dur = max(0.2, float(c["end"]) - float(c["start"]))
        vol = 1.0 if (music is None or c.get("needs_audio")) else 0.12
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"fps={FPS},format=yuv420p,setsar=1")
        seg = work / f"seg_{i:03d}.mp4"
        cmd = [FFMPEG, "-y", "-ss", f"{c['start']:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]
        if _has_audio(src):
            cmd += ["-filter_complex", f"[0:v]{vf}[v];[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol}[a]",
                    "-map", "[v]", "-map", "[a]"]
        else:
            cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
                    "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                "-ar", "48000", "-shortest", str(seg)]
        _run(cmd)
        seg_paths.append(seg)
        durs.append(dur)

    progress(0.7, "Joining clips")
    joined = work / "joined.mp4"
    xf = min(crossfade, min(durs) / 3) if crossfade > 0 and len(seg_paths) > 1 else 0
    if xf <= 0:
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in seg_paths))
        _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
        total = sum(durs)
    else:
        inputs = [x for p in seg_paths for x in ("-i", str(p))]
        fv, fa, offset = "[0:v]", "[0:a]", 0.0
        parts = []
        for k in range(1, len(seg_paths)):
            offset += durs[k - 1] - xf
            parts.append(f"{fv}[{k}:v]xfade=transition=fade:duration={xf:.2f}:offset={offset:.3f}[v{k}]")
            parts.append(f"{fa}[{k}:a]acrossfade=d={xf:.2f}[a{k}]")
            fv, fa = f"[v{k}]", f"[a{k}]"
        _run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(parts), "-map", fv, "-map", fa,
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(joined)])
        total = sum(durs) - xf * (len(durs) - 1)

    progress(0.85, "Finishing")
    vf_final, inputs, af = [], ["-i", str(joined)], None
    if title:
        font = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
        txt = work / "title.txt"
        txt.write_text(title, encoding="utf-8")
        fontarg = f"fontfile='{_ff_path(font)}':" if font else ""
        size = int(min(W, H) * 0.075)
        t0 = max(0.0, total - 3.0)
        vf_final.append(
            f"drawtext={fontarg}textfile='{_ff_path(txt)}':fontcolor=white:fontsize={size}:"
            f"box=1:boxcolor=0xE11D2E@0.85:boxborderw={size // 3}:x=(w-text_w)/2:y=h*0.78:"
            f"enable='gte(t,{t0:.2f})':alpha='min(1,(t-{t0:.2f})/0.4)'")
    if music is not None:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        fade_at = max(0.0, total - 1.5)
        # Duck the music to 20 % while a shot that needs its own audio plays (e.g. a spoken line).
        starts = [sum(durs[:k]) - k * xf for k in range(len(durs))]
        spans = [(starts[k], starts[k] + durs[k]) for k, c in enumerate(clips) if c.get("needs_audio")]
        duck = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans)
        vol = f"volume='{music_volume}*if({duck},0.2,1)':eval=frame" if duck else f"volume={music_volume}"
        af = (f"[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,{vol},afade=t=out:st={fade_at:.2f}:d=1.5[m];"
              f"[0:a][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    cmd = [FFMPEG, "-y", *inputs]
    if af or vf_final:
        fc = []
        if vf_final:
            fc.append(f"[0:v]{','.join(vf_final)}[v]")
        if af:
            fc.append(af)
        cmd += ["-filter_complex", ";".join(fc), "-map", "[v]" if vf_final else "0:v", "-map", "[a]" if af else "0:a"]
        cmd += ["-c:v", "libx264" if vf_final else "copy", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", str(out)]
    _run(cmd)
    for p in work.iterdir():
        p.unlink(missing_ok=True)
    work.rmdir()
    progress(1.0, "Render complete")
    return {"duration": round(total, 2), "size_bytes": out.stat().st_size}


# ---------------------------------------------------------------- clip lists
def clip_rows(clips: list[dict]) -> list[dict]:
    rows, t = [], 0.0
    for i, c in enumerate(clips, start=1):
        d = round(float(c["end"]) - float(c["start"]), 3)
        rows.append({"order": i, "shot_id": c.get("shot_id", ""), "name": c.get("name", ""),
                     "file": c["file"], "start": round(float(c["start"]), 3), "end": round(float(c["end"]), 3),
                     "duration": d, "timeline_in": round(t, 3), "timeline_out": round(t + d, 3),
                     "needs_audio": bool(c.get("needs_audio"))})
        t += d
    return rows


def clip_list_json(project: str, clips: list[dict], aspect: str) -> str:
    rows = clip_rows(clips)
    return json.dumps({"project": project, "fps": FPS, "aspect_ratio": aspect,
                       "total_seconds": round(sum(r["duration"] for r in rows), 3),
                       "clips": rows}, indent=2)


def clip_list_csv(clips: list[dict]) -> str:
    rows = clip_rows(clips)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["order"])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _tc(seconds: float, offset_hours: int = 0) -> str:
    f = int(round(seconds * FPS)) + offset_hours * 3600 * FPS
    return f"{f // (3600 * FPS):02d}:{f // (60 * FPS) % 60:02d}:{f // FPS % 60:02d}:{f % FPS:02d}"


def edl(project: str, clips: list[dict]) -> str:
    """CMX3600 EDL, 30 fps non-drop, record timeline starting at 01:00:00:00."""
    lines = [f"TITLE: {project[:60]}", "FCM: NON-DROP FRAME", ""]
    for r in clip_rows(clips):
        lines.append(f"{r['order']:03d}  AX       AA/V  C        {_tc(r['start'])} {_tc(r['end'])} "
                     f"{_tc(r['timeline_in'], 1)} {_tc(r['timeline_out'], 1)}")
        lines.append(f"* FROM CLIP NAME: {r['file']}")
        if r["name"]:
            lines.append(f"* COMMENT: {r['shot_id']} {r['name']}")
        lines.append("")
    return "\n".join(lines)


def fcpxml(project: str, clips: list[dict], sources: dict[str, Path], durations: dict[str, float],
           size: tuple[int, int] = (1280, 720)) -> str:
    """FCPXML 1.9 (Final Cut Pro, DaVinci Resolve, Premiere via import)."""
    from xml.sax.saxutils import escape, quoteattr

    def r(sec: float) -> str:
        return f"{int(round(sec * FPS))}/{FPS}s"

    files = list(dict.fromkeys(c["file"] for c in clips))
    ids = {f: f"r{i + 2}" for i, f in enumerate(files)}
    assets = "\n".join(
        f'    <asset id="{ids[f]}" name={quoteattr(f)} start="0s" duration="{r(durations.get(f, 0))}" '
        f'hasVideo="1" hasAudio="1" format="r1" audioSources="1" audioChannels="2">\n'
        f'      <media-rep kind="original-media" src={quoteattr(Path(sources[f]).resolve().as_uri())}/>\n'
        f'    </asset>' for f in files)
    rows = clip_rows(clips)
    spine = "\n".join(
        f'            <asset-clip ref="{ids[x["file"]]}" name={quoteattr(x["name"] or x["file"])} '
        f'offset="{r(x["timeline_in"])}" start="{r(x["start"])}" duration="{r(x["duration"])}" format="r1"/>'
        for x in rows)
    total = r(sum(x["duration"] for x in rows))
    W, H = size
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1" name="FFVideoFormat{H}p{FPS}" frameDuration="1/{FPS}s" width="{W}" height="{H}"/>
{assets}
  </resources>
  <library>
    <event name={quoteattr(project)}>
      <project name={quoteattr(project + ' - rough cut')}>
        <sequence format="r1" duration="{total}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
{spine}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""


def results_document(project: str, source_files: list[str], results: list[dict], timeline: list[dict],
                     processing: dict) -> str:
    """Shot-finder results in OnSpotly's requested output format."""
    tl = [{"order": i + 1, "shot_id": c["shot_id"], "file": c["file"], "start": c["start"], "end": c["end"]}
          for i, c in enumerate(timeline)]
    return json.dumps({"project": project, "source_files": source_files, "shots": results,
                       "timeline": tl, "processing": processing}, indent=2, ensure_ascii=False)

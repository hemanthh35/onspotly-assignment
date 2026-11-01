"""Tiny Excalidraw scene builder: crisp shapes, bound labels, bound arrows, frames (slides)."""
from __future__ import annotations

import json
import random

FONT = 2          # Helvetica: crisp, readable on a projector
CHAR_W = 0.53     # average glyph width as a fraction of font size (Helvetica, mixed case)
LINE_H = 1.25

INK, MUTED, WHITE = "#1e1e1e", "#868e96", "#ffffff"
RED = "#e03131"

KINDS = {
    #            fill        stroke      dashed  text
    "proc":     ("#ffffff", "#1e1e1e", False, INK),
    "ai":       ("#e5dbff", "#6741d9", False, INK),
    "data":     ("#e7f5ff", "#1971c2", False, INK),
    "decision": ("#fff3bf", "#f08c00", False, INK),
    "ext":      ("#f8f9fa", "#868e96", True, INK),
    "good":     ("#d3f9d8", "#2f9e44", False, INK),
    "bad":      ("#ffe3e3", "#e03131", False, INK),
    "warn":     ("#fff3bf", "#f08c00", False, INK),
    "note":     ("#f8f9fa", "#f8f9fa", False, "#495057"),
    "dark":     ("#1e1e1e", "#1e1e1e", False, WHITE),
    "brand":    ("#e03131", "#e03131", False, WHITE),
    "group":    ("transparent", "#adb5bd", True, MUTED),
}


def wrap(text: str, width: float, size: int) -> list[str]:
    per_line = max(4, int(width / (size * CHAR_W)))
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = f"{line} {word}".strip()
            if len(cand) <= per_line or not line:
                line = cand
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


class Scene:
    def __init__(self):
        self.els: list[dict] = []
        self._n = 0
        self.frame_id: str | None = None
        self.ox = self.oy = 0
        random.seed(7)

    # ------------------------------------------------------------- basics
    def _id(self, p="e"):
        self._n += 1
        return f"{p}{self._n}"

    def _base(self, typ, x, y, w, h, **kw):
        el = {
            "id": kw.pop("id", None) or self._id(typ[0]), "type": typ,
            "x": x + self.ox, "y": y + self.oy, "width": w, "height": h, "angle": 0,
            "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
            "groupIds": [], "frameId": self.frame_id, "roundness": None,
            "seed": random.randint(1, 2**31), "version": 1, "versionNonce": random.randint(1, 2**31),
            "isDeleted": False, "boundElements": [], "updated": 1, "link": None, "locked": False,
        }
        el.update(kw)
        self.els.append(el)
        return el

    def _text_el(self, x, y, w, h, text, size, color, align="left", valign="top", container=None):
        return self._base("text", x, y, w, h, strokeColor=color, text=text, originalText=text,
                          fontSize=size, fontFamily=FONT, textAlign=align, verticalAlign=valign,
                          containerId=container, lineHeight=LINE_H, autoResize=True, strokeWidth=1)

    # ------------------------------------------------------------- frames
    def frame(self, x, y, w, h, name):
        self.frame_id = None
        self.ox = self.oy = 0
        f = self._base("frame", x, y, w, h, name=name, strokeWidth=2, strokeColor="#bbb",
                       backgroundColor="transparent")
        self.frame_id = f["id"]
        self.ox, self.oy = x, y
        # white slide background
        self.box(0, 0, w, h, "", kind="proc", stroke="transparent", radius=False)
        return f

    # ------------------------------------------------------------- shapes
    def box(self, x, y, w, h, label="", kind="proc", size=20, align="center", shape="rectangle",
            stroke=None, fill=None, color=None, radius=True, dashed=None, width=2, pad=14):
        fill_, stroke_, dashed_, color_ = KINDS[kind]
        fill, stroke, color = fill or fill_, stroke or stroke_, color or color_
        dashed = dashed_ if dashed is None else dashed
        inner_w = (w - 2 * pad) * (0.58 if shape == "diamond" else 1)
        lines = wrap(label, inner_w, size) if label else []
        need = len(lines) * size * LINE_H + 2 * pad + (h * 0.45 if shape == "diamond" else 0)
        h = max(h, need)
        el = self._base(shape, x, y, w, h, strokeColor=stroke, backgroundColor=fill,
                        strokeStyle="dashed" if dashed else "solid", strokeWidth=width,
                        roundness={"type": 3} if (radius and shape == "rectangle") else
                        ({"type": 2} if shape != "rectangle" else None))
        if label:
            txt = "\n".join(lines)
            th = len(lines) * size * LINE_H
            t = self._text_el(x + (w - inner_w) / 2, y + (h - th) / 2, inner_w, th, txt, size, color,
                              align=align, valign="middle", container=el["id"])
            el["boundElements"].append({"type": "text", "id": t["id"]})
        el["_box"] = (x, y, w, h)
        return el

    def text(self, x, y, text, size=20, color=INK, w=None, align="left"):
        w = w or max(len(l) for l in text.split("\n")) * size * CHAR_W + 8
        lines = wrap(text, w, size)
        h = len(lines) * size * LINE_H
        return self._text_el(x, y, w, h, "\n".join(lines), size, color, align=align)

    def line(self, x1, y1, x2, y2, color=MUTED, width=2, dashed=False):
        return self._base("line", x1, y1, x2 - x1, y2 - y1, strokeColor=color, strokeWidth=width,
                          strokeStyle="dashed" if dashed else "solid",
                          points=[[0, 0], [x2 - x1, y2 - y1]], lastCommittedPoint=None,
                          startBinding=None, endBinding=None, startArrowhead=None, endArrowhead=None)

    # ------------------------------------------------------------- arrows
    @staticmethod
    def _anchor(b, side):
        x, y, w, h = b
        return {"r": (x + w, y + h / 2), "l": (x, y + h / 2), "t": (x + w / 2, y), "b": (x + w / 2, y + h)}[side]

    def arrow(self, a, b, label=None, sides=None, color=INK, dashed=False, via=None, size=16,
              start=None, end=None, head="arrow"):
        """a/b: elements returned by box(). sides: e.g. 'rl' (from a's right to b's left).
        start/end: explicit (x, y) slide coordinates to override anchors. via: elbow points."""
        ba, bb = a["_box"], b["_box"]
        if not sides:
            ax, ay = ba[0] + ba[2] / 2, ba[1] + ba[3] / 2
            bx, by = bb[0] + bb[2] / 2, bb[1] + bb[3] / 2
            if abs(bx - ax) >= abs(by - ay):
                sides = "rl" if bx > ax else "lr"
            else:
                sides = "bt" if by > ay else "tb"
        p0 = start or self._anchor(ba, sides[0])
        p1 = end or self._anchor(bb, sides[1])
        pts = [p0] + (via or []) + [p1]
        rel = [[px - p0[0], py - p0[1]] for px, py in pts]
        xs, ys = [p[0] for p in rel], [p[1] for p in rel]
        el = self._base("arrow", p0[0], p0[1], max(xs) - min(xs), max(ys) - min(ys),
                        strokeColor=color, strokeStyle="dashed" if dashed else "solid", strokeWidth=2,
                        roundness={"type": 2} if not via else None, points=rel, lastCommittedPoint=None,
                        startBinding={"elementId": a["id"], "focus": 0, "gap": 4},
                        endBinding={"elementId": b["id"], "focus": 0, "gap": 4},
                        startArrowhead=None, endArrowhead=head, elbowed=False)
        a["boundElements"].append({"type": "arrow", "id": el["id"]})
        b["boundElements"].append({"type": "arrow", "id": el["id"]})
        if label:
            mid = rel[len(rel) // 2] if via else [(rel[0][0] + rel[-1][0]) / 2, (rel[0][1] + rel[-1][1]) / 2]
            lines = wrap(label, 260, size)
            lw = max(len(l) for l in lines) * size * CHAR_W + 6
            lh = len(lines) * size * LINE_H
            t = self._text_el(p0[0] + mid[0] - lw / 2, p0[1] + mid[1] - lh / 2, lw, lh,
                              "\n".join(lines), size, color, align="center", valign="middle", container=el["id"])
            el["boundElements"].append({"type": "text", "id": t["id"]})
        return el

    # ------------------------------------------------------------- output
    def save(self, path):
        for e in self.els:
            e.pop("_box", None)
        doc = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
               "elements": self.els, "appState": {"viewBackgroundColor": "#f1f3f5", "gridSize": None},
               "files": {}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)

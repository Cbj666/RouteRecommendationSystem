"""把 P06 的前端原型图换成"无水体/无绿植"的干净版；文件被 WPS 占用时退回到同目录新文件。"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from pptx import Presentation

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "presentation" / "G7项目设计-2026113.pptx"
SHOT = ROOT / "presentation" / "前端原型图.png"
ALT = ROOT / "presentation" / "G7项目设计-2026113-新原型.pptx"


def walk(shapes):
    for sh in shapes:
        if sh.shape_type == 6:
            yield from walk(sh.shapes)
        else:
            yield sh


def build(src: Path, dst: Path) -> None:
    p = Presentation(str(src))
    slide = p.slides[5]
    pics = [sh for sh in walk(slide.shapes) if sh.shape_type == 13]
    tgt = max(pics, key=lambda s: s.width * s.height)
    l, t, w, h = tgt.left, tgt.top, tgt.width, tgt.height
    tgt._element.getparent().remove(tgt._element)
    slide.shapes.add_picture(str(SHOT), l, t, w, h)
    p.save(str(dst))


for attempt in range(1, 4):
    try:
        build(DECK, DECK)
        print(f"OK 已写回 {DECK.name}（第 {attempt} 次尝试）")
        break
    except PermissionError:
        print(f"占用中（第 {attempt} 次）…")
        time.sleep(8)
else:
    build(DECK, ALT)
    print(f"WPS 仍占用，已另存为 {ALT.name}")

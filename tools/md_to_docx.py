# -*- coding: utf-8 -*-
"""Convert a Markdown spec into a simple, editable .docx.

Supports the subset used by our docs: headings, paragraphs, bullet lists,
GFM tables and fenced code blocks. Not a full Markdown engine.

Usage:
    python tools/md_to_docx.py docs/项目说明书-v4.0.md docs/项目说明书-v4.0.docx
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
MONO_FONT = "Consolas"


def set_font(run, name: str, size: float | None = None, bold: bool = False) -> None:
    run.font.name = name
    run.font.bold = bold
    if size:
        run.font.size = Pt(size)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def add_paragraph(doc, text: str, style: str | None = None, indent: bool = True):
    p = doc.add_paragraph(style=style)
    if indent:
        p.paragraph_format.first_line_indent = Pt(21)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.35
    # inline `code` and **bold**
    for tok in re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", text):
        if not tok:
            continue
        if tok.startswith("`") and tok.endswith("`"):
            r = p.add_run(tok[1:-1])
            set_font(r, MONO_FONT, 9.5)
            r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        elif tok.startswith("**") and tok.endswith("**"):
            r = p.add_run(tok[2:-2])
            set_font(r, BODY_FONT, 10.5, bold=True)
        else:
            r = p.add_run(tok)
            set_font(r, BODY_FONT, 10.5)
    return p


def add_table(doc, rows: list[list[str]]) -> None:
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j in range(cols):
            cell = table.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            txt = row[j] if j < len(row) else ""
            run = p.add_run(txt.replace("`", ""))
            set_font(run, BODY_FONT, 9, bold=(i == 0))
            if i == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/项目说明书-v4.0.md")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else src.with_suffix(".docx"))
    lines = src.read_text(encoding="utf-8").splitlines()

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = BODY_FONT
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run("\n".join(block))
            set_font(run, MONO_FONT, 9)
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            rows = []
            header = [c.strip() for c in line.strip("|").split("|")]
            rows.append(header)
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            add_table(doc, rows)
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1:
                p = doc.add_heading(level=0)
                run = p.add_run(text)
                set_font(run, HEAD_FONT, 20, bold=True)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p = doc.add_heading(level=min(level - 1, 4))
                run = p.add_run(text)
                set_font(run, HEAD_FONT, 14 - (level - 2) * 1.5, bold=True)
            i += 1
            continue

        if line.startswith("- ") or line.startswith("* "):
            add_paragraph(doc, line[2:], style="List Bullet", indent=False)
            i += 1
            continue

        if re.match(r"^\d+\.\s+", line):
            add_paragraph(doc, re.sub(r"^\d+\.\s+", "", line), style="List Number", indent=False)
            i += 1
            continue

        if line.strip() in ("---", "***"):
            doc.add_paragraph()
            i += 1
            continue

        if line.strip():
            add_paragraph(doc, line.strip())
        i += 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dst)
    print(f"wrote {dst} ({dst.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

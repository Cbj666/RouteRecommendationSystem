# -*- coding: utf-8 -*-
"""Dump a docx draft to text with style info, for reading the user's notes."""
import sys
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_block_items(parent):
    from docx.oxml.ns import qn
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)


def main(path):
    doc = Document(path)
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style = block.style.name if block.style is not None else ""
            print(f"[{style}] {text}")
        else:
            print("=== TABLE ===")
            for row in block.rows:
                cells = []
                for c in row.cells:
                    cells.append(" / ".join(p.text.strip() for p in c.paragraphs if p.text.strip()))
                print(" | ".join(cells))
            print("=== END TABLE ===")


if __name__ == "__main__":
    main(sys.argv[1])

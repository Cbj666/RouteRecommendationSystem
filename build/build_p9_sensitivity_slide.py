# -*- coding: utf-8 -*-
"""Rebuild PPT page 9 as a single-slide sensitivity-test explainer.

Usage:
    <bundled python> build/build_p9_sensitivity_slide.py
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "presentation" / "G7项目设计-2026113.pptx"
OUT = ROOT / "presentation" / "P9-敏感性检验.pptx"

FONT = "微软雅黑"
GREEN = RGBColor(0x1A, 0x5C, 0x46)
INK = RGBColor(0x1F, 0x2A, 0x26)
GRAY = RGBColor(0x5F, 0x6F, 0x68)
LIGHT = RGBColor(0xEA, 0xF2, 0xEE)
PALE = RGBColor(0xF5, 0xF9, 0xF7)
MID = RGBColor(0x8F, 0xB5, 0xA4)
AMBER = RGBColor(0xC2, 0x7A, 0x2C)
AMBER_PALE = RGBColor(0xF8, 0xEF, 0xE4)
LINE = RGBColor(0xD8, 0xE4, 0xDD)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def set_font(run, size: float, bold: bool = False, color: RGBColor = INK) -> None:
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find(qn("a:ea"))
    if ea is None:
        ea = rpr.makeelement(qn("a:ea"), {})
        rpr.append(ea)
    ea.set("typeface", FONT)


def textbox(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str = "",
    size: float = 10,
    bold: bool = False,
    color: RGBColor = INK,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    line_spacing: float = 1.0,
    wrap: bool = True,
):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.word_wrap = wrap
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    p.line_spacing = line_spacing
    if text:
        run = p.add_run()
        run.text = text
        set_font(run, size, bold, color)
    return shape


def add_runs(paragraph, runs) -> None:
    for text, size, bold, color in runs:
        run = paragraph.add_run()
        run.text = text
        set_font(run, size, bold, color)


def rect(slide, x: float, y: float, w: float, h: float, fill, line=None, shape=MSO_SHAPE.RECTANGLE, radius=None):
    shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.75)
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        shp.adjustments[0] = radius
    return shp


def hline(slide, x1: float, y: float, x2: float, color=LINE, width: float = 0.75, dash=None):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y), Inches(x2), Inches(y))
    conn.line.color.rgb = color
    conn.line.width = Pt(width)
    if dash is not None:
        conn.line.dash_style = dash


def vline(slide, x: float, y1: float, y2: float, color=LINE, width: float = 0.75, dash=None):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y1), Inches(x), Inches(y2))
    conn.line.color.rgb = color
    conn.line.width = Pt(width)
    if dash is not None:
        conn.line.dash_style = dash


def add_step(slide, n: int, y: float, title: str, body: str) -> None:
    circ = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.66), Inches(y + 0.02), Inches(0.30), Inches(0.30))
    circ.fill.solid()
    circ.fill.fore_color.rgb = GREEN
    circ.line.fill.background()
    tf = circ.text_frame
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(n)
    set_font(r, 9.5, True, WHITE)

    textbox(slide, 1.10, y - 0.01, 3.75, 0.24, title, 10.6, True, GREEN)
    textbox(slide, 1.10, y + 0.25, 3.82, 0.50, body, 9.2, False, GRAY, line_spacing=1.12)


def build() -> None:
    prs = Presentation(str(SRC))
    sld_ids = list(prs.slides._sldIdLst)
    keep = 8
    for i, sld_id in enumerate(sld_ids):
        if i == keep:
            continue
        r_id = sld_id.get(qn("r:id"))
        prs.part.drop_rel(r_id)
        prs.slides._sldIdLst.remove(sld_id)

    slide = prs.slides[0]

    # Keep the deck's header/footer groups, change only the page title.
    for shape in slide.shapes:
        if shape.name == "header":
            for child in shape.shapes:
                if child.has_text_frame:
                    if "调参与检验" in child.text:
                        child.text_frame.paragraphs[0].runs[0].text = "08 · 权重检验"
                    elif "权重的三轮" in child.text:
                        child.text_frame.paragraphs[0].runs[0].text = "换掉权重，排序还稳吗？"

    # Remove old content, keep header and footer.
    for shape in list(slide.shapes):
        if shape.name not in {"header", "footer"}:
            shape._element.getparent().remove(shape._element)

    # Lead-in line.
    textbox(
        slide,
        0.66,
        1.72,
        12.0,
        0.22,
        "同一张 91,203 段评分表，只换权重；16 组方案全量重算，不抽样。",
        9.5,
        False,
        GRAY,
    )

    # ---------------- Left: method ----------------
    textbox(slide, 0.66, 1.98, 4.3, 0.20, "测试设计", 9.5, True, MID)
    textbox(slide, 0.66, 2.18, 4.35, 0.28, "一次只动一个变量", 15, True, INK)

    vline(slide, 0.81, 2.58, 5.60, color=LINE, width=1.0)

    add_step(
        slide,
        1,
        2.55,
        "固定基准",
        "六维权重 W₀ = .25 / .25 / .15 / .10 / .05 / .15；先算 91,203 段 baseline 分。",
    )
    add_step(
        slide,
        2,
        3.35,
        "造 16 组",
        "6 维 × 0.8/1.2 = 12 组单维扰动；再加 4 组整组换权。",
    )
    add_step(
        slide,
        3,
        4.15,
        "全量重算",
        "每组重算 91,203 段；权重先归一化，保证仍在同一把 0–100 的尺上。",
    )
    add_step(
        slide,
        4,
        4.95,
        "两把尺子",
        "Spearman 秩相关 ρ 看全样本排序；前 10% 重合看用户真正会点开的名单。",
    )

    # Method note.
    rect(slide, 0.66, 5.78, 4.35, 0.38, PALE, line=None)
    textbox(
        slide,
        0.80,
        5.84,
        4.08,
        0.28,
        "16 × 91,203 ≈ 146 万次打分；只换权重，不改 GIS 子分。",
        8.6,
        False,
        GRAY,
        anchor=MSO_ANCHOR.MIDDLE,
    )

    # ---------------- Right: results ----------------
    textbox(slide, 5.30, 1.98, 4.0, 0.20, "结果", 9.5, True, MID)
    textbox(slide, 5.30, 2.18, 7.3, 0.28, "12 组几乎重合，4 组开始分叉", 15, True, INK)

    textbox(slide, 5.30, 2.58, 4.0, 0.18, "单维 ±20% · 12 组", 8.8, False, GRAY)

    # Matrix: 6 dimensions x 2 directions.
    mx, my = 5.30, 2.80
    cw = [1.12, 1.16, 1.16]
    hh, rh = 0.24, 0.22
    headers = ["维度", "×0.8", "×1.2"]
    rows = [
        ("安全", "0.9951", "0.9969"),
        ("绿化", "0.9941", "0.9958"),
        ("坡度", "0.9982", "0.9982"),
        ("过街", "0.9959", "0.9963"),
        ("设施", "0.9995", "0.9995"),
        ("空气", "0.9989", "0.9989"),
    ]
    x = mx
    for j, head in enumerate(headers):
        rect(slide, x, my, cw[j], hh, GREEN)
        textbox(slide, x, my + 0.01, cw[j], hh - 0.02, head, 8.6, True, WHITE, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
        x += cw[j]
    for i, row in enumerate(rows):
        y = my + hh + i * rh
        fill = PALE if i % 2 == 0 else WHITE
        x = mx
        for j, cell in enumerate(row):
            rect(slide, x, y, cw[j], rh, fill)
            textbox(
                slide,
                x,
                y,
                cw[j],
                rh,
                cell,
                8.9,
                j == 0,
                INK if j == 0 else GRAY,
                PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER,
                MSO_ANCHOR.MIDDLE,
            )
            x += cw[j]

    # Callout next to matrix.
    textbox(slide, 9.05, 2.78, 3.55, 0.50, "0.9941", 25, True, GREEN)
    textbox(slide, 9.05, 3.24, 3.55, 0.20, "12 组最低 Spearman ρ", 8.8, False, GRAY)
    textbox(slide, 9.05, 3.50, 3.55, 0.20, "前 10% 重合 92.6% – 97.6%", 9.2, True, INK)
    textbox(
        slide,
        9.05,
        3.78,
        3.55,
        0.55,
        "6 维 × 2 方向；每次只动 1 维，其余 5 维不变。",
        8.6,
        False,
        GRAY,
        line_spacing=1.10,
    )

    # Alternatives header.
    textbox(slide, 5.30, 4.50, 4.0, 0.18, "整组换权 · 4 组", 8.8, False, GRAY)
    textbox(slide, 5.30, 4.70, 1.2, 0.16, "方案", 7.5, False, MID)
    textbox(slide, 6.55, 4.70, 3.0, 0.16, "Spearman ρ（横轴 0.85–1.00）", 7.5, False, MID)
    textbox(slide, 10.55, 4.70, 0.85, 0.16, "ρ", 7.5, True, MID, PP_ALIGN.CENTER)
    textbox(slide, 11.35, 4.70, 1.1, 0.16, "前 10%", 7.5, False, MID, PP_ALIGN.CENTER)

    bar_x, bar_w = 6.55, 3.90
    base, span = 0.85, 0.15
    # Grid + tick labels.
    for tick in (0.85, 0.90, 0.95, 1.00):
        tx = bar_x + (tick - base) / span * bar_w
        is_gate = abs(tick - 0.90) < 1e-9
        vline(slide, tx, 4.86, 6.08, color=AMBER if is_gate else LINE, width=0.9, dash=MSO_LINE_DASH_STYLE.DASH if is_gate else None)
        textbox(
            slide,
            tx - 0.28,
            4.86,
            0.56,
            0.16,
            f"{tick:.2f}",
            7.2,
            is_gate,
            AMBER if is_gate else GRAY,
            PP_ALIGN.CENTER,
        )

    alts = [
        ("AHP 型", 0.9834, 0.8641, GREEN),
        ("舒适优先", 0.8995, 0.7450, MID),
        ("地形优先", 0.8628, 0.7348, MID),
        ("全等权", 0.8849, 0.6257, AMBER),
    ]
    for i, (name, rho, top, color) in enumerate(alts):
        by = 5.08 + i * 0.25
        if name == "全等权":
            rect(slide, 5.22, by - 0.02, 7.45, 0.24, AMBER_PALE)
        rect(slide, bar_x, by + 0.035, bar_w, 0.14, LIGHT)
        length = max((rho - base) / span * bar_w, 0.03)
        rect(slide, bar_x, by + 0.035, length, 0.14, color)
        textbox(slide, 5.30, by, 1.18, 0.22, name, 9.0, True if name == "全等权" else False, INK, anchor=MSO_ANCHOR.MIDDLE)
        textbox(slide, 10.55, by, 0.85, 0.22, f"{rho:.4f}", 8.9, True, color if name == "全等权" else INK, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
        textbox(
            slide,
            11.35,
            by,
            1.18,
            0.22,
            f"{top*100:.1f}%",
            8.4,
            name == "全等权",
            AMBER if name == "全等权" else GRAY,
            PP_ALIGN.CENTER,
            MSO_ANCHOR.MIDDLE,
        )

    # ---------------- Bottom conclusion ----------------
    rect(slide, 0.66, 6.22, 12.0, 0.58, LIGHT)
    p = textbox(slide, 0.86, 6.25, 11.62, 0.24, "", 9.2, False, INK, anchor=MSO_ANCHOR.MIDDLE)
    para = p.text_frame.paragraphs[0]
    add_runs(
        para,
        [
            ("结论  ", 9.2, True, GREEN),
            ("单维 ±20%：ρ ≥ 0.9941、前 10% ≥ 92.6%；", 9.2, False, INK),
            ("整组换权：ρ 0.8628–0.9834、前 10% 最低 62.6%。", 9.2, False, INK),
            ("  权重数值不敏感，维度区分度才敏感——先修维度，再调权重。", 9.2, True, GREEN),
        ],
    )
    textbox(
        slide,
        0.86,
        6.50,
        11.62,
        0.18,
        "注：「AHP 型」只是相近权重的敏感性情景，不是真跑 AHP；ρ < 0.90 需单独说明。",
        7.6,
        False,
        GRAY,
    )

    # Speaker notes: the full method in prose.
    notes = (
        "这页只讲敏感性检验的方法，不逐条念 16 个数字。\n"
        "基准权重 W0 = .25/.25/.15/.10/.05/.15。12 组单维：每次只把一维乘 0.8 或 1.2，其余五维不变；"
        "4 组整组换权：全等权（各 .1583）、AHP 型（.32/.27/.17/.09/.05/.10）、"
        "舒适优先（.20/.35/.30/.05/.05/.05）、地形优先（.20/.20/.40/.10/.05/.05）。\n"
        "每组都把权重归一化后重算 91,203 段得分，再和 baseline 比两个指标："
        "Spearman 秩相关看全样本排序，前 10% 重合（9,120 段）看推荐名单。16 组共约 146 万次打分，没有抽样。\n"
        "单维 12 组 ρ .9941–.9995，前 10% 重合 92.6%–97.6%；整组 4 组 ρ .8628–.9834，前 10% 62.6%–86.4%。"
        "平均分位移只有 −2.56 到 +7.65 分，看起来不大；但前 10% 名单换掉 26%–37%，所以只看平均分会漏掉问题。"
        "全等权 ρ .8849 看着还行，但前 10% 只剩 62.6%，因为设施维度区分度低，等权把它从 5% 放大到 16.7%。\n"
        "所以结论是：权重数值不敏感，维度区分度才敏感；先修维度，再调权重。"
        "AHP 型只是相近权重的敏感性情景，不是真跑 AHP，也没有一致性检验。"
    )
    slide.notes_slide.notes_text_frame.text = notes

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(OUT)


if __name__ == "__main__":
    build()

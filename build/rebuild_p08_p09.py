"""重做 P08（六维评价：全部算子公式）与 P09（权重如何定 + 检验）。

直接改写 presentation 里的 pptx：只动第 8、9 页，保留页眉页脚，其余 11 页不碰。
文字用原生文本框（可在 WPS 里继续改），公式用 mathtext 图片。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image as PILImage
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
PPTX = ROOT / "presentation" / "项目展示-runroute-20261030.pptx"
FIMG = ROOT / "build" / "proto" / "assets" / "p8"

INK = RGBColor(0x1F, 0x2A, 0x26)
SUB = RGBColor(0x5F, 0x6F, 0x68)
PRIMARY = RGBColor(0x1A, 0x5C, 0x46)
CARD = RGBColor(0xF4, 0xF8, 0xF5)
LINE = RGBColor(0xD9, 0xE3, 0xDD)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)



FORMULAS = {
    "f_safety": r"$s_{\mathrm{safe}}=\mathrm{clip}\!\left(R(\mathrm{fclass})-15\,\mathbf{1}[d<50]-10\,\mathbf{1}[d<20],\ 0,\ 100\right)$",
    "f_green": r"$s_{\mathrm{green}}=0.7\left[100(1-e^{-2.5S})\right]+0.3\left[\mathrm{clip}(100(1-d/1500))\right]$",
    "f_slope": r"$s_{\mathrm{slope}}=\mathrm{clip}\!\left(100\left(1-\frac{i}{10}\right),0,100\right)$",
    "f_cross": r"$s_{\mathrm{cross}}=\mathrm{clip}\!\left(100-7\,n_{200},\ 0,\ 100\right)$",
    "f_air": r"$s_{\mathrm{air}}=\mathrm{clip}\!\left(100\cdot\frac{40-\mathrm{NO_2}}{30},\ 0,\ 100\right)$",
    "f_fac": r"$s_{\mathrm{fac}}=100\,e^{-d/500}$",
    "f_score": r"$\mathrm{score}=\sum_{i=1}^{6} w_i\, s_i$",
}


def render_formulas() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"mathtext.fontset": "stix", "font.family": "STIXGeneral"})
    FIMG.mkdir(parents=True, exist_ok=True)
    for name, tex in FORMULAS.items():
        fig = plt.figure(figsize=(9, 1.6))
        fig.patch.set_alpha(0)
        fig.text(0.005, 0.5, tex, fontsize=26, color="#1F2A26", va="center")
        fig.savefig(FIMG / f"{name}.png", dpi=300, transparent=True,
                    bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)


def tb(slide, l, t, w, h, lines, size=11, color=INK, bold=False,
       align=PP_ALIGN.LEFT, line_spacing=1.35, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = "Microsoft YaHei"
    return box


def rect(slide, l, t, w, h, fill=CARD, line=None):
    from pptx.enum.shapes import MSO_SHAPE
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    return sh


def pic(slide, name, l, t, max_w, max_h):
    path = FIMG / f"{name}.png"
    with PILImage.open(path) as im:
        aspect = im.width / im.height
    w = min(max_w, max_h * aspect)
    h = w / aspect
    slide.shapes.add_picture(str(path), Inches(l), Inches(t), Inches(w), Inches(h))
    return w


def clear_content(slide, keep: set[str]) -> None:
    for sh in list(slide.shapes):
        if sh.name in keep:
            continue
        sh._element.getparent().remove(sh._element)


CARDS = [
    ("安全", "0.25", "f_safety", [
        "按道路等级查表 R：footway 95、residential 70、主干道 18–10；",
        "距主干道 <50 m 再扣 15 分、<20 m 再扣 10 分。",
        "衡量与机动车同行的风险。"]),
    ("绿化", "0.25", "f_green", [
        "S = 0.8×树冠覆盖率 + 0.2×绿地覆盖率；",
        "前项边际递减（遮蔽有饱和），后项按 1500 m 截断。",
        "衡量遮阴与接触绿地的感觉。"]),
    ("坡度", "0.15", "f_slope", [
        "i 为路段平均坡度（%），每 1% 扣 10 分，≥10% 记 0。",
        "衡量体力负担；10% 以上基本跑不动。",
        "城区 90% 路段在此项接近满分，区分度低。"]),
    ("过街", "0.10", "f_cross", [
        "n₂₀₀ = 200 m 内交叉口数，每处扣 7 分，14 处归零。",
        "衡量节奏被打断的频率——跑步要连续，不是连通。",
        "与步行研究方向相反，是我们主动做的分歧。"]),
    ("空气", "0.15", "f_air", [
        "NO₂ = 10 µg/m³（WHO 2021 年均）→ 100 分；",
        "NO₂ = 40 µg/m³（GB 3095 二级）→ 0 分，中间线性。",
        "1 km 年均网格，只做区域校正。"]),
    ("设施", "0.05", "f_fac", [
        "d 为到最近运动场馆的距离，500 m 为衰减常数。",
        "d=0 时 100 分，500 m 时 37 分，1 km 时 14 分。",
        "衡量补给与休整的便利；高德 POI，远城偏稀。"]),
]


def build_p08(slide) -> None:
    clear_content(slide, {"header", "footer"})
    W, H, GAP = 3.86, 1.66, 0.18
    X0, Y0 = 0.66, 1.76
    for i, (name, w, img, lines) in enumerate(CARDS):
        x = X0 + (i % 3) * (W + GAP)
        y = Y0 + (i // 3) * (H + GAP)
        rect(slide, x, y, W, H)
        tb(slide, x + 0.16, y + 0.12, 1.6, 0.26, [name], size=13, bold=True, color=PRIMARY)
        tb(slide, x + W - 1.16, y + 0.15, 1.0, 0.22, [f"权重 {w}"], size=9, color=SUB,
           align=PP_ALIGN.RIGHT)
        pic(slide, img, x + 0.16, y + 0.46, W - 0.34, 0.34)
        tb(slide, x + 0.16, y + 0.90, W - 0.32, 0.70, lines, size=8.4, color=SUB, line_spacing=1.26)

    by = 5.26
    rect(slide, X0, by, 12.0, 1.02, fill=RGBColor(0xEE, 0xF5, 0xF1))
    w = pic(slide, "f_score", X0 + 0.26, by + 0.24, 2.0, 0.52)
    tx = X0 + 0.26 + w + 0.30
    tb(slide, tx, by + 0.14, 12.0 - (tx - X0) - 0.3, 0.78, [
        "总分 = 六项子分各自的 0–100 分加权求和。权重合计 0.95（沿用上一版口径），",
        "所以总分上限是 95 而不是 100；按 40 / 55 / 70 / 85 分五档，实测最高 79.8 分。",
    ], size=10.5, color=INK, line_spacing=1.34)

    tb(slide, X0, 6.42, 12.0, 0.20, [
        "文献：指标分层参照刘信知、孙帅（2025）；树冠用卫星覆盖率而非街景绿视率，"
        "两者相关 r = 0.617（高时雨、骆杰轩，2026），是本维度已知局限。"
    ], size=8.5, color=SUB)


def build_p09(slide) -> None:
    clear_content(slide, {"header", "footer"})
    rounds = [
        ("第一轮 · 定顺序", [
            "先按「哪一维最影响跑步体感」排序，给出一组初值：",
            "安全 0.30 / 绿化 0.25 / 坡度 0.20 / 过街 0.10 / 设施 0.10。",
            "这一步只排序，不定数。"]),
        ("第二轮 · 定标尺", [
            "把每一维的端点挂到公开标准上，而不是凭感觉定：",
            "坡度 10% 记极陡、NO₂ 用 WHO 10 / 国标 40、",
            "绿地 1500 m 截断、设施 500 m 衰减。"]),
        ("第三轮 · 按数据修正", [
            "设施中位只有 3 分、且与空气负相关 −0.66，0.10 → 0.05；",
            "坡度中位 88 分、区分度低，0.20 → 0.15；安全 0.30 → 0.25；",
            "省出的 0.15 全部给新加的空气维。"]),
    ]
    y = 1.80
    for title, lines in rounds:
        rect(slide, 0.66, y + 0.04, 0.05, 0.86, fill=PRIMARY)
        tb(slide, 0.84, y, 5.6, 0.28, [title], size=13, bold=True, color=PRIMARY)
        tb(slide, 0.84, y + 0.34, 5.9, 0.72, lines, size=9.8, color=SUB, line_spacing=1.32)
        y += 1.16

    # 右：权重对照表
    tx, ty, tw = 7.30, 1.80, 5.30
    tb(slide, tx, ty - 0.04, tw, 0.24, ["权重是怎么变的"], size=10, color=SUB)
    rows = [("维度", "初始", "最终"), ("安全", "0.30", "0.25"), ("绿化", "0.25", "0.25"),
            ("坡度", "0.20", "0.15"), ("过街", "0.10", "0.10"), ("设施", "0.10", "0.05"),
            ("空气", "—", "0.15"), ("合计", "0.95", "0.95")]
    rh = 0.30
    for i, (a, b, c) in enumerate(rows):
        yy = ty + 0.26 + i * rh
        if i == 0:
            rect(slide, tx, yy - 0.04, tw, rh, fill=PRIMARY)
            col = WHITE
            bold = True
        else:
            if i % 2 == 0:
                rect(slide, tx, yy - 0.04, tw, rh, fill=CARD)
            col = INK
            bold = i == len(rows) - 1
        tb(slide, tx + 0.14, yy, 1.6, 0.22, [a], size=10, color=col, bold=bold)
        tb(slide, tx + 1.7, yy, 1.2, 0.22, [b], size=10, color=col, bold=bold)
        tb(slide, tx + 2.9, yy, 1.2, 0.22, [c], size=10, color=col, bold=bold)

    tb(slide, 0.66, 5.42, 12.0, 0.28, ["怎么检验：同一张 9.1 万段评分表，用 16 组权重重算，比较排序是否变化"],
       size=10, color=SUB)
    rect(slide, 0.66, 5.76, 12.0, 0.90, fill=RGBColor(0xEE, 0xF5, 0xF1))
    tb(slide, 0.92, 5.92, 5.5, 0.72, [
        "单维 ±20% 扰动（12 组）：Spearman ≥ 0.9941",
        "整组换权（4 组）：AHP 型 0.9834 / 舒适优先 0.8995 / 地形优先 0.8628",
    ], size=9.8, color=INK, line_spacing=1.36)
    tb(slide, 6.9, 5.92, 5.5, 0.72, [
        "全部等权 1/6：掉到 0.8849（前 10% 只重合 0.63）",
        "结论：分数对「权重取多少」不敏感，对「维度有没有区分度」敏感。",
    ], size=9.8, color=INK, line_spacing=1.36)

    tb(slide, 0.66, 6.76, 11.0, 0.18, [
        "文献：定权思路参照吉实（2025）的 AHP + 专家咨询；本文未做一致性检验，用 16 组敏感性检验替代。"
    ], size=8.5, color=SUB)


def main() -> None:
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "formulas"):
        render_formulas()
        print("formulas done")
        if mode == "formulas":
            return
    p = Presentation(str(PPTX))
    build_p08(p.slides[7])
    build_p09(p.slides[8])
    p.save(str(PPTX))
    print("saved", PPTX.name)


if __name__ == "__main__":
    main()

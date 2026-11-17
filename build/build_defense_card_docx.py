# -*- coding: utf-8 -*-
"""Build a two-topic defense card for P7 (GIS) and P9 (weights)."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "G7答辩底气卡-P7-P9.docx"

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
GREEN = RGBColor(0x1F, 0x4E, 0x3D)
INK = RGBColor(0x22, 0x22, 0x22)
GRAY = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0x99, 0x99, 0x99)
ACCENT = RGBColor(0x2E, 0x6B, 0x55)
PALE = "EEF4F0"
PALE2 = "F7FAF8"


def set_east_asia(obj, name: str) -> None:
    obj.font.name = name
    element = obj.element
    rpr = element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:eastAsia", "w:ascii", "w:hAnsi"):
        rfonts.set(qn(attr), name)


def style_font(style, name: str, size: float, bold: bool = False, color=None) -> None:
    set_east_asia(style, name)
    style.font.size = Pt(size)
    style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def cell_text(cell, text: str, size: float = 9, bold: bool = False, color=INK) -> None:
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = 1.05
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color
    set_east_asia(run, BODY_FONT)


def keep_row_together(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    tr_pr.append(cant)


def add_table(doc, headers, rows, widths, header_fill="1F4E3D") -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.allow_autofit = False
    for i, width in enumerate(widths):
        table.columns[i].width = Cm(width)
    hdr = table.rows[0]
    keep_row_together(hdr)
    tr_pr = hdr._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tr_pr.append(tbl_header)
    for i, text in enumerate(headers):
        cell = hdr.cells[i]
        cell.width = Cm(widths[i])
        shade_cell(cell, header_fill)
        cell_text(cell, text, 9, True, RGBColor(0xFF, 0xFF, 0xFF))
    for r_idx, row_data in enumerate(rows):
        row = table.add_row()
        keep_row_together(row)
        for i, text in enumerate(row_data):
            cell = row.cells[i]
            cell.width = Cm(widths[i])
            if r_idx % 2 == 1:
                shade_cell(cell, PALE2)
            cell_text(cell, text, 9)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_body(doc, text: str, bold_prefix: str | None = None) -> None:
    p = doc.add_paragraph(style="CardBody")
    if bold_prefix and text.startswith(bold_prefix):
        run = p.add_run(bold_prefix)
        run.bold = True
        text = text[len(bold_prefix):]
    p.add_run(text)


def add_bullet(doc, text: str, num: str | None = None) -> None:
    p = doc.add_paragraph(style="CardBullet")
    p.paragraph_format.left_indent = Cm(0.0 if num else 0.55)
    p.paragraph_format.first_line_indent = Cm(-0.55 if num else 0.0)
    if num:
        p.add_run(num).bold = True
    # bold **...**
    for idx, part in enumerate(text.split("**")):
        if not part:
            continue
        run = p.add_run(part)
        run.bold = (idx % 2 == 1)


def add_qa(doc, q: str, a: str) -> None:
    p = doc.add_paragraph(style="CardQA")
    p.paragraph_format.space_before = Pt(3)
    q_run = p.add_run("问：" + q)
    q_run.bold = True
    q_run.font.color.rgb = GREEN
    add_body(doc, "答：" + a)


def add_note_box(doc, lines) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Cm(16.6)
    cell = table.rows[0].cells[0]
    cell.width = Cm(16.6)
    shade_cell(cell, PALE)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        for idx, part in enumerate(line.split("**")):
            if not part:
                continue
            run = p.add_run(part)
            run.font.size = Pt(9.5)
            run.bold = (idx % 2 == 1)
            set_east_asia(run, BODY_FONT)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_bottom_border(paragraph, color: str = "C9D8CF", size: int = 6) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_text = OxmlElement("w:t")
    fld_text.text = "1"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(fld_text)
    run._r.append(fld_end)
    run.font.size = Pt(8)
    run.font.color.rgb = LIGHT
    set_east_asia(run, BODY_FONT)


def h1(doc, text: str) -> None:
    p = doc.add_paragraph(style="CardH1")
    p.add_run(text)
    add_bottom_border(p)


def h2(doc, text: str) -> None:
    p = doc.add_paragraph(style="CardH2")
    p.add_run(text)


def build() -> Path:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.0)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(2.2)
    sec.right_margin = Cm(2.2)
    sec.footer_distance = Cm(1.0)

    styles = doc.styles
    normal = styles["Normal"]
    style_font(normal, BODY_FONT, 10.5, color=INK)
    normal.paragraph_format.line_spacing = 1.28
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(3)

    body = styles.add_style("CardBody", 1)
    body.base_style = normal
    style_font(body, BODY_FONT, 10.5, color=INK)
    body.paragraph_format.first_line_indent = Cm(0.74)
    body.paragraph_format.line_spacing = 1.3
    body.paragraph_format.space_after = Pt(3)

    bullet = styles.add_style("CardBullet", 1)
    bullet.base_style = normal
    style_font(bullet, BODY_FONT, 10.5, color=INK)
    bullet.paragraph_format.line_spacing = 1.25
    bullet.paragraph_format.space_after = Pt(2)

    qa = styles.add_style("CardQA", 1)
    qa.base_style = normal
    style_font(qa, BODY_FONT, 10.5, color=INK)
    qa.paragraph_format.space_before = Pt(4)
    qa.paragraph_format.space_after = Pt(0)
    qa.paragraph_format.keep_with_next = True

    h1s = styles.add_style("CardH1", 1)
    h1s.base_style = normal
    style_font(h1s, HEAD_FONT, 15, True, GREEN)
    h1s.paragraph_format.space_before = Pt(6)
    h1s.paragraph_format.space_after = Pt(8)
    h1s.paragraph_format.keep_with_next = True

    h2s = styles.add_style("CardH2", 1)
    h2s.base_style = normal
    style_font(h2s, HEAD_FONT, 11.5, True, ACCENT)
    h2s.paragraph_format.space_before = Pt(9)
    h2s.paragraph_format.space_after = Pt(3)
    h2s.paragraph_format.keep_with_next = True

    # Footer
    footer = sec.footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fp.add_run("G7 · P7/P9 答辩底气卡    ")
    r.font.size = Pt(8)
    r.font.color.rgb = LIGHT
    set_east_asia(r, BODY_FONT)
    add_page_field(fp)

    # Kicker + title
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_before = Pt(0)
    kicker.paragraph_format.space_after = Pt(4)
    r = kicker.add_run("G7 项目 · 答辩底气卡")
    r.font.size = Pt(9)
    r.bold = True
    r.font.color.rgb = ACCENT
    set_east_asia(r, HEAD_FONT)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(2)
    r = title.add_run("P7 GIS 数据处理：一页讲透")
    r.font.size = Pt(19)
    r.bold = True
    r.font.color.rgb = GREEN
    set_east_asia(r, HEAD_FONT)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(9)
    r = sub.add_run("把五套来源不同、分辨率不同的数据，压成一张 91,203 行的路段表")
    r.font.size = Pt(10.5)
    r.font.color.rgb = GRAY
    set_east_asia(r, BODY_FONT)

    add_note_box(doc, [
        "**先记三句话：**",
        "1. 这一页的主语不是 Python，是数据流：五套原始数据，最后都要落到同一条路段的一行记录上。",
        "2. 矢量和栅格是两种算法：距离、计数取路段中点；坡度、树冠沿路段顶点做长度加权。",
        "3. 存储用 WGS84，算长度和坡度先投影到 EPSG:32650；否则武汉东西向会被算短。",
    ])

    h2(doc, "六步管线：每一步的输入、操作、输出")
    add_table(
        doc,
        ["阶段", "输入", "关键操作", "输出"],
        [
            ["采集", "OSM / SRTM / WorldCover / 高德 / CHAP", "下载、解压、按市界过滤", "12.4 GB 原始数据"],
            ["统一", "OSM 道路", "25 类可步行道路；市界外扩 2 km；投影 32650 算 length_m；中点 in_boundary；1e-6 度去重", "91,203 段 / 47,051 km；979,351 节点 / 2,075,761 条有向边"],
            ["取指标", "栅格 + 矢量", "坡度、树冠、空气、设施、过街、安全", "每段一行原始指标"],
            ["归一化", "六个原始指标", "六条公式压到 0–100", "6 个 0–100 子分"],
            ["加权", "6 个子分", "W = .25/.25/.15/.10/.05/.15", "score + grade"],
            ["落表", "全部字段", "只读 GeoPackage", "27 字段 / 44.7 MB"],
        ],
        [2.4, 4.2, 6.0, 4.0],
    )

    h2(doc, "三个必须会解释的计算")
    add_bullet(doc, "投影：WGS84 的度不是米。武汉纬度约 30.5°，1° 经度只有约 96 km；不投影，东西向会被系统性算短。长度、坡度都在 EPSG:32650 里算，算完再存回 WGS84。", "①")
    add_bullet(doc, "平滑：SRTM 30 m 原始逐像元差分，会把建筑、树冠当成地形，城区中位坡度假到 2.66%，最大 533%。先做 σ=150 m 的高斯平滑，约 4.86 个像元，再求梯度；平滑后中位 1.19%、p90 3.27%。平滑不是美化，是去掉非地形噪声。", "②")
    add_bullet(doc, "窗口：WorldCover 10 m 先降采样到 20 m，再做 6×6 的 uniform_filter，约 120 m 窗口。因为人感受到的是这一段路周围的树荫，不是脚下那一个像素。输出 tree_share，均值 21.7%、中位 13.3%，武大 44%、磨山 87%。", "③")

    h2(doc, "三个坑，被问到就这样讲")
    add_bullet(doc, "WorldCover 拼接错位：rasterio 的 boundless=True 返回的是整幅 bbox，不是瓦片局部；按偏移贴回，后一幅会把前一幅覆盖成 0。症状很好认：武大、磨山 tree_share=0，远山反而 100%。正确做法是 1:1 合成，只用大于 0 的像元。", "坑 1 ")
    add_bullet(doc, "SRTM 假坡度：不平滑就差分，城区中位 2.66%，甚至 5%–7%。必须先平滑再求梯度。", "坑 2 ")
    add_bullet(doc, "高德 QPS 限流：失败响应不能写进缓存，否则重跑会当成有效结果跳过；后来改成 0.45 秒间隔加指数退避。", "坑 3 ")

    doc.add_page_break()

    h2(doc, "六个追问（P7）")
    add_qa(doc, "WorldCover 到底是 4 幅还是 6 幅？PPT 写 6 幅。",
           "实际是 4 幅：N27E111、N27E114、N30E111、N30E114，代码里 TILES 就是这四个。PPT 上是笔误，我按实际 4 幅讲。")
    add_qa(doc, "1,056 段空气缺失怎么办？",
           "这些段落在 CHAP 有效网格外或取值为 nodata；用城市中位补，占全部路段约 1.2%，不改变区域结论。")
    add_qa(doc, "只有 10 个监测站，凭什么做逐段空气？",
           "不能做逐段。AQICN 全市只有 10 个站，3 km 缓冲只覆盖 12.7% 的路段；所以用 CHAP 1 km 年均网格，只做区域校正，不声称能分辨同一条街两侧。同圈层不同道路只差 0.2–1.8 µg/m³，圈层间差 9.9。")
    add_qa(doc, "距离为什么用路段中点，而不是整条路段？",
           "中点是一个代表点，计算便宜、口径统一；对超长路段是简化，会低估沿线变化。坡度和树冠没有偷这个懒，它们是沿路段顶点做长度加权。这个局限我们在文档里承认。")
    add_qa(doc, "200 米过街数具体怎么数？",
           "以路段中点为圆心、200 米为半径，数图里度≥3 的顶点个数，不是数 OSM 的 crossing 标签。10 km/h 跑 200 米约 72 秒，这是一次绕行过街的时间尺度。实际中位 6 个、p75 18 个、p90 43 个。")
    add_qa(doc, "树冠为什么不用街景绿视率？",
           "中国街景 API 拿不到，做不了；WorldCover 是实测地表覆盖，但只认成片林荫，单排行道树常常不足一个像元。我们和街景绿视率的相关只有 r=0.617，这是清楚的短板，不藏着。")

    add_note_box(doc, [
        "**P7 一句话收尾：**",
        "“这页看起来是六个步骤，核心其实只有一句：把五套不同坐标系、不同分辨率的数据，压到同一条路段的一行记录上；后面所有评分和路线，都只读这张表。”",
    ])

    doc.add_page_break()

    # ---------------- P9 ----------------
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_before = Pt(0)
    kicker.paragraph_format.space_after = Pt(4)
    r = kicker.add_run("G7 项目 · 答辩底气卡")
    r.font.size = Pt(9)
    r.bold = True
    r.font.color.rgb = ACCENT
    set_east_asia(r, HEAD_FONT)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(2)
    r = title.add_run("P9 权重调整：一页讲透")
    r.font.size = Pt(19)
    r.bold = True
    r.font.color.rgb = GREEN
    set_east_asia(r, HEAD_FONT)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(9)
    r = sub.add_run("权重不是拍脑袋，是“排序—标尺—按数据修正—敏感性检验”")
    r.font.size = Pt(10.5)
    r.font.color.rgb = GRAY
    set_east_asia(r, BODY_FONT)

    add_note_box(doc, [
        "**先记三句话：**",
        "1. 权重没有唯一正确答案；我们追求的是排序稳健、口径透明，不是算出一个真理。",
        "2. 先定顺序，再定每一维的 0 和 100 怎么来，最后按数据分布修正。",
        "3. 真正敏感的是维度有没有区分度；权重 ±20% 基本不改排序，等权反而把失效的设施维度放大。",
    ])

    h2(doc, "三轮：从初值到最终权重")
    add_table(
        doc,
        ["轮次", "做什么", "结果"],
        [
            ["第一轮", "按体感重要性排序、给初值", "安全 .30 / 绿化 .25 / 坡度 .20 / 过街 .10 / 设施 .10，合计 .95"],
            ["第二轮", "给每一维定端点、定标尺", "空气 10/40；坡度 0/10%；绿化 0–1 + 1500 m；安全 8–95 + 50/20 m；过街 0/15；设施 0/500 m"],
            ["第三轮", "按实际分布修正", "坡度 .15、设施 .05、安全 .25；各让 .05 给空气；最终 .25/.25/.15/.10/.05/.15"],
        ],
        [1.8, 5.0, 9.8],
    )

    h2(doc, "“端点挂公开标准”到底对应什么")
    add_table(
        doc,
        ["维度", "数据", "端点 / 计算", "依据", "实际分布"],
        [
            ["空气", "CHAP NO₂ 年均", "10→100，40→0，线性", "WHO 2021 + GB 3095—2012 二级（唯一公开标准）", "中位 23.8，12.3–31.6"],
            ["坡度", "slope_mean_pct", "0→100，10%→0，线性", "跑步经验阈值（不是国标）", "中位 1.19，p90 3.27，76%≤2%"],
            ["绿化", "tree_share / green_share，d_green", "S=0.8 树冠+0.2 绿地；100(1−e^(−2.5S))；1500 m 线性归零", "规划服务半径 + 工程参数", "树冠中位 13.3%，绿地中位 470 m"],
            ["安全", "fclass，d_main", "查表 8–95；<50 m 扣 15；<20 m 扣 10", "道路分级 + 路侧暴露缓冲", "中位 56，p10 0，p90 90"],
            ["过街", "cross_200m", "100−7n；14 个剩 2 分，15 个归零", "分布反推", "中位 6，p75 18，p90 43"],
            ["设施", "d_fac", "100e^(−d/500)；500 m→37", "步行服务半径", "中位 1,760 m，41.6% 为 0"],
        ],
        [1.4, 3.8, 5.4, 4.2, 3.0],
    )

    add_note_box(doc, [
        "**这里必须说实话：** PPT 上“每一维的端点挂到公开标准”说得有点满。真正挂公开标准的只有空气；坡度是跑步经验，绿化/设施是规划服务半径，安全是道路分级，过街是从分布反推的工程锚点。被追问时不要硬说都是国标。",
    ])

    h2(doc, "三个降权动作：每一个都有数据证据")
    add_table(
        doc,
        ["维度", "数据证据", "动作", "理由"],
        [
            ["坡度", "中位 88.1；42.2%≥90；76%≤2%", ".20→.15", "几乎人人高分，区分度低，还会整体抬高总分"],
            ["设施", "中位 3.0；41.6% 为 0；与空气相关 −0.663", ".10→.05", "失效维度；中心城设施密但空气差，两个高权会互相抵消"],
            ["安全", "道路等级查表，是代理指标；与过街都指向人车冲突", ".30→.25", "仍是第一梯队，但不该一家独大；让 .05 给空气"],
        ],
        [1.6, 6.6, 2.4, 6.0],
    )

    h2(doc, "16 组敏感性检验：结论不是“权重随便定”")
    add_table(
        doc,
        ["检验", "Spearman / 前 10% 重合", "说明"],
        [
            ["12 组单维 ×0.8 / ×1.2", "0.9941–0.9995 / 0.926–0.976", "排序几乎不变"],
            ["AHP 型整组替换", "0.9834 / 0.864", "只作为情景，不是真跑 AHP"],
            ["舒适优先", "0.8995 / 0.745", "换权重后仍较高"],
            ["地形优先", "0.8628 / 0.735", "下降但可接受"],
            ["全等权", "0.8849 / 0.626", "设施被放大到 1/6，排序明显变差"],
        ],
        [5.2, 5.6, 6.0],
    )

    add_body(doc, "结论：权重加减 20% 基本不改排序；真正敏感的是维度有没有区分度。全等权把失效的设施维度抬到六分之一，排序立刻掉。所以我们的原则是：先修维度，再调权重。")

    doc.add_page_break()

    h2(doc, "六个追问（P9）")
    add_qa(doc, "权重是不是拍脑袋？",
           "不是。顺序来自体感重要性和文献；端点来自公开标准、规划参数、道路分级和跑步经验；第三轮按 91,203 条路段的实际分布修正；最后用 16 组敏感性检验看排序稳不稳。每一步都能复算。")
    add_qa(doc, "为什么不用 AHP？",
           "没有真跑。AHP 要做两两比较矩阵、算特征向量、做一致性检验 CR；我们没做专家问卷，不能声称用了 AHP。表里的“AHP 型”只是把一组相近权重拿来做敏感性情景，不是方法。")
    add_qa(doc, "权重加起来为什么是 0.95，不是 1？",
           "这是沿用 v1 的口径，总预算 0.95，所以综合分上限是 95 不是 100。它不影响排序，但会让绝对分偏低。如果重来，我会归一化到 1，或者在页面上明确写“满分 95”。")
    add_qa(doc, "为什么安全和绿化最高？",
           "跑者最在意安全和绿荫，这是排序的起点；坡度其次；过街和空气再次；设施最低。但权重不是只按重要性，也看数据可靠性：空气只有 1 km 区域值，设施数据质量差，所以不能给太高。")
    add_qa(doc, "设施既然失效，为什么不直接删掉？",
           "它仍然是用户能感知的补给维度，删掉会让结果面板少一块；但数据确实差，所以只保留 0.05，并在报告里明确它是失效维度。以后有更好的 POI，再把它加回来。")
    add_qa(doc, "如果老师问“坡度 10% 是哪门子公开标准”？",
           "直接承认：不是国标，是跑步经验阈值。只有空气的 10 和 40 挂了 WHO 2021 和 GB 3095—2012；其他都是工程锚点。这样答比硬撑更加分。")

    add_note_box(doc, [
        "**保命三句话：**",
        "1. “权重没有唯一正确答案，我们追求的是排序稳健和口径透明。”",
        "2. “只有空气端点挂了公开标准，其他是工程锚点，我不敢说过头。”",
        "3. “真正决定结果的是维度有没有区分度，不是权重多 0.05 少 0.05。”",
    ])

    doc.core_properties.title = "G7 答辩底气卡：P7 GIS 数据处理与 P9 权重调整"
    doc.core_properties.subject = "答辩准备材料"
    doc.core_properties.author = "G7 项目组"
    doc.core_properties.category = "课程汇报"
    doc.core_properties.keywords = "GIS;权重;敏感性;答辩"
    doc.core_properties.comments = "配合 G7汇报讲稿-连贯版.docx 使用。"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build())

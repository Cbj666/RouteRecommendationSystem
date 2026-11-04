# -*- coding: utf-8 -*-
"""生成项目展示 PPT（15 页，16:9）。

运行（用带 python-pptx 的 python）：
    python build/ppt/make_deck.py
输出：
    项目展示-慢跑慢骑适宜性评价与路线推荐.pptx
"""
from __future__ import annotations

import copy
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent / "assets"
OUT = ROOT / "项目展示-慢跑慢骑适宜性评价与路线推荐.pptx"

# ------------------------------------------------------------------ 色板
INK = RGBColor(0x1B, 0x2A, 0x24)
GRAY = RGBColor(0x6D, 0x7C, 0x76)
LIGHT = RGBColor(0xF6, 0xF9, 0xF7)
LINE = RGBColor(0xD8, 0xE0, 0xDB)
GREEN_DEEP = RGBColor(0x14, 0x50, 0x3C)
GREEN = RGBColor(0x2E, 0x8B, 0x6B)
GREEN_PALE = RGBColor(0xE8, 0xF1, 0xEC)
AMBER = RGBColor(0xC9, 0x8B, 0x2E)
AMBER_PALE = RGBColor(0xF7, 0xEE, 0xDC)
RED = RGBColor(0xB5, 0x50, 0x3B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "微软雅黑"
SW, SH = 13.333, 7.5
ML = 0.62                      # 左边距
CW = SW - 2 * ML               # 内容宽度 12.093

prs = Presentation()
prs.slide_width = Inches(SW)
prs.slide_height = Inches(SH)
BLANK = prs.slide_layouts[6]


# ------------------------------------------------------------------ 基础工具
def _ea(run, name: str = FONT) -> None:
    """同时设置 latin / east-asian / cs 字体，避免中文回落成宋体。"""
    from pptx.oxml.ns import qn
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", name)


def text(slide, x, y, w, h, s, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, line=1.32, space_after=0, italic=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    lines = s.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        p.space_after = Pt(space_after)
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.color.rgb = color
        _ea(r)
    return box


def rect(slide, x, y, w, h, fill=None, line_col=None, radius=None,
         line_w=1.0, shape=MSO_SHAPE.RECTANGLE):
    if radius is not None:
        shape = MSO_SHAPE.ROUNDED_RECTANGLE
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius is not None:
        try:
            sp.adjustments[0] = radius
        except Exception:
            pass
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line_col is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line_col
        sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    sp.text_frame.word_wrap = True
    return sp


def shape_text(sp, s, size=12, bold=False, color=INK, align=PP_ALIGN.CENTER,
               anchor=MSO_ANCHOR.MIDDLE, line=1.2, margins=(0.08, 0.02)):
    tf = sp.text_frame
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(margins[0])
    tf.margin_top = tf.margin_bottom = Inches(margins[1])
    for i, ln in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        _ea(r)


def pic(slide, path, x, y, w=None, h=None):
    kw = {}
    if w is not None:
        kw["width"] = Inches(w)
    if h is not None:
        kw["height"] = Inches(h)
    return slide.shapes.add_picture(str(path), Inches(x), Inches(y), **kw)


def crop(src: Path, dst: Path, box) -> Path:
    """box = (left, top, right, bottom) 像素；导出裁剪图。"""
    im = Image.open(src)
    im.crop(box).save(dst)
    return dst


# ------------------------------------------------------------------ 版式
def page(kicker: str, title: str, n: int, total: int = 15, sub: str | None = None) -> object:
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, SW, 0.055, fill=GREEN)
    text(s, ML, 0.40, 8.0, 0.26, kicker, size=10.5, bold=True, color=GREEN)
    text(s, ML, 0.68, CW, 0.62, title, size=25, bold=True, color=INK, line=1.15)
    if sub:
        text(s, ML, 1.20, CW, 0.3, sub, size=12, color=GRAY)
    rect(s, ML, 1.46, 1.30, 0.045, fill=GREEN)
    # 页脚
    rect(s, ML, 6.98, CW, 0.012, fill=LINE)
    text(s, ML, 7.06, 8.6, 0.24,
         "城市慢跑 / 慢骑环境适宜性评价与路线推荐 · 武汉 · 项目展示",
         size=8.5, color=GRAY)
    text(s, SW - ML - 1.2, 7.06, 1.2, 0.24, f"{n:02d} / {total:02d}",
         size=9, color=GRAY, align=PP_ALIGN.RIGHT)
    return s


def table(slide, x, y, widths, rows, row_h=0.5, header_h=0.46, fs=10.5, hfs=10.5,
          aligns=None, zebra=True, first_col_bold=True, header_fill=GREEN_DEEP,
          pad=0.10, valign=MSO_ANCHOR.MIDDLE, col_colors=None):
    """手绘表格：可控边框与配色，避免主题样式干扰。"""
    total_w = sum(widths)
    aligns = aligns or [PP_ALIGN.LEFT] * len(widths)
    rect(slide, x, y, total_w, header_h, fill=header_fill)
    cx = x
    for i, w in enumerate(widths):
        text(slide, cx + pad, y + 0.02, w - 2 * pad, header_h - 0.04, rows[0][i],
             size=hfs, bold=True, color=WHITE, align=aligns[i], anchor=valign)
        cx += w
    cy = y + header_h
    for ri, row in enumerate(rows[1:]):
        if zebra and ri % 2 == 1:
            rect(slide, x, cy, total_w, row_h, fill=LIGHT)
        cx = x
        for ci, w in enumerate(widths):
            col = INK
            if col_colors and ci in col_colors:
                col = col_colors[ci](row[ci]) if callable(col_colors[ci]) else col_colors[ci]
            text(slide, cx + pad, cy + 0.03, w - 2 * pad, row_h - 0.06, row[ci],
                 size=fs, bold=(first_col_bold and ci == 0), color=col,
                 align=aligns[ci], anchor=valign, line=1.18)
            cx += w
        rect(slide, x, cy + row_h - 0.008, total_w, 0.008, fill=LINE)
        cy += row_h
    return cy


def stat(slide, x, y, w, h, big, label, color=GREEN_DEEP, fs_big=20, fs_label=9.5,
         fill=GREEN_PALE):
    rect(slide, x, y, w, h, fill=fill)
    text(slide, x + 0.14, y + 0.10, w - 0.28, 0.42, big, size=fs_big, bold=True,
         color=color, line=1.0)
    text(slide, x + 0.14, y + h - 0.34, w - 0.28, 0.30, label, size=fs_label,
         color=GRAY, line=1.1)


def step(slide, x, y, w, num, head, body, fs=11.5, num_color=GREEN):
    text(slide, x, y, 0.36, 0.28, num, size=11, bold=True, color=num_color)
    text(slide, x + 0.38, y - 0.02, w - 0.38, 0.28, head, size=fs, bold=True, color=INK)
    text(slide, x + 0.38, y + 0.28, w - 0.38, 0.9, body, size=fs - 1.2, color=GRAY, line=1.30)


def bullet(slide, x, y, w, head, body, fs=12, gap=0.06, marker="▪", mcolor=GREEN):
    """加粗小标题 + 正文，同段内以两行呈现。"""
    if body:
        text(slide, x, y, 0.22, 0.26, marker, size=fs - 1, color=mcolor)
        p = text(slide, x + 0.26, y, w - 0.26, 0.26, head, size=fs, bold=True, color=INK)
        text(slide, x + 0.26, y + 0.28, w - 0.26, 0.5, body, size=fs - 1.0, color=GRAY, line=1.30)
        return 0.28 + 0.30 + gap
    text(slide, x, y, 0.22, 0.26, marker, size=fs - 1, color=mcolor)
    text(slide, x + 0.26, y, w - 0.26, 0.3, head, size=fs, color=INK, line=1.3)
    return 0.26 + gap


# ------------------------------------------------------------------ 素材裁剪
ASSETS.mkdir(parents=True, exist_ok=True)
# 封面：裁剪比例必须等于 (13.333-6.55)/7.5 = 0.9045，否则会溢出画布
assets = {}
assets["cover"] = crop(ROOT / "data/output/running/v1/map_layer.png",
                       ASSETS / "cover_map.png", (700, 0, 700 + 1099, 1215))
assets["donghu"] = crop(ROOT / "data/output/running/v1/map_donghu.png",
                        ASSETS / "donghu.png", (252, 80, 2048, 1092))
for k in ("desktop", "loops"):
    pass
DESKTOP = ROOT / "data/output/ui/round-1/desktop.png"
LOOPS = ROOT / "data/output/running/v1/loops.png"

# ================================================================== 1 封面
s = prs.slides.add_slide(BLANK)
pic(s, assets["cover"], 6.55, 0, h=SH)
rect(s, 6.50, 0, 0.075, SH, fill=GREEN)
text(s, 0.90, 1.02, 5.4, 0.28, "空间分析 · 城市计算 · 课程项目展示",
     size=10.5, bold=True, color=GREEN)
text(s, 0.90, 1.45, 5.6, 1.0, "跑哪条线？", size=54, bold=True, color=INK)
text(s, 0.90, 2.62, 5.3, 1.05,
     "城市慢跑 / 慢骑环境的量化评价\n与闭合环线推荐 · 以武汉为例",
     size=18, color=INK, line=1.45)
rect(s, 0.90, 3.92, 2.10, 0.045, fill=GREEN)
text(s, 0.90, 4.16, 5.2, 0.9,
     "9.1 万段路网 · 4.7 万公里 · 五维评分 · 一次点击生成闭环",
     size=12, color=GRAY, line=1.5)
text(s, 0.90, 5.62, 5.2, 1.0,
     "汇报人：＿＿＿＿＿　　指导教师：＿＿＿＿＿\n单位：＿＿＿＿＿＿＿＿＿＿　　2026 年 11 月",
     size=11, color=GRAY, line=1.7)

# ================================================================== 2 研究背景
s = page("01 · 研究背景", "跑步 App 记录“你跑了多少”，却没人回答“你该跑哪儿”", 2)
items = [
    ("需求是真的。", "跑步门槛最低，但“跑哪条线”直接决定体验；\n决策却依赖口碑、朋友圈和一次偶然发现。"),
    ("供给是够的。", "绿道、滨江步道、环湖路大量建成；\n信息却散落在推文、评论和本地人的记忆里。"),
    ("工具是缺的。", "主流 App 的“路线”＝热力图＋手动收藏：\n不可解释、不可定制，不考虑坡度、暴露与红绿灯。"),
]
yy = 1.78
for i, (h, b) in enumerate(items, 1):
    text(s, ML, yy - 0.04, 0.6, 0.5, f"0{i}", size=24, bold=True, color=RGBColor(0xCB, 0xDF, 0xD5))
    text(s, ML + 0.52, yy + 0.02, 6.0, 0.3, h, size=13.5, bold=True, color=INK)
    text(s, ML + 0.52, yy + 0.38, 6.0, 0.8, b, size=11.5, color=GRAY, line=1.42)
    yy += 1.30
rect(s, 7.55, 1.78, 5.15, 3.05, fill=GREEN_PALE)
rect(s, 7.55, 1.78, 0.055, 3.05, fill=GREEN)
text(s, 7.85, 2.02, 4.6, 2.2,
     "同样是 5 km：\n沿江滩跑，还是沿主干道跑，\n噪声、尾气、坡度、人车冲突\n完全不同——\n但在地图上，这两段路看起来一样。",
     size=14, color=GREEN_DEEP, line=1.55)
text(s, 7.85, 4.32, 4.6, 0.4, "—— 这个项目的起点", size=10.5, color=GRAY)
text(s, ML, 5.92, CW, 0.9,
     "政策语境：《健康中国行动（2019—2030）》　·　WHO《GAPPA》2018　·　住建部《城市步行和自行车交通系统规划设计导则》2013　·　《绿道规划设计导则》2016",
     size=10, color=GRAY, line=1.5)

# ================================================================== 3 目标
s = page("02 · 问题界定", "把“这条路适不适合跑”，拆成三个可计算的问题", 3)
cards = [
    ("Q1  量化", "每段路能不能给出 0–100 的适宜性分？",
     "五维指标 + 显式权重；\n每一项都能回溯到一条公式与一个数据源。", "→ P06 指标体系"),
    ("Q2  组织", "高分路段能不能拼成 3 / 5 / 10 km 闭环？",
     "半程折返选折点，回程对去程边双向加价，避免原路折返。", "→ P09 环线算法"),
    ("Q3  解释", "用户凭什么相信这个分数？",
     "逐维拆解、偏好可调、权重敏感性可复算——错了也知道错在哪。", "→ P12 敏感性检验"),
]
x = ML
for tag, q, a, ref in cards:
    rect(s, x, 1.76, 3.83, 1.98, fill=LIGHT, line_col=LINE, line_w=0.75)
    text(s, x + 0.22, 1.92, 3.3, 0.28, tag, size=10.5, bold=True, color=GREEN)
    text(s, x + 0.22, 2.22, 3.36, 0.55, q, size=12.5, bold=True, color=INK, line=1.35)
    text(s, x + 0.22, 2.64, 3.36, 0.62, a, size=10.8, color=GRAY, line=1.40)
    text(s, x + 0.22, 3.36, 3.36, 0.26, ref, size=9, color=GREEN)
    x += 3.83 + 0.30
text(s, ML, 4.00, 3.0, 0.26, "已交付的三件东西", size=10.5, bold=True, color=GREEN)
deliv = [
    ("数据产品", "segments.gpkg\n9.1 万段 × 24 字段"),
    ("算法原型", "环线生成 + 12 条环线量化评测\n3 / 5 / 10 km"),
    ("系统原型", "FastAPI 5 个端点\n+ 高保真前端原型"),
]
x = ML
for h, b in deliv:
    rect(s, x, 4.34, 3.83, 1.02, fill=WHITE, line_col=LINE, line_w=0.75)
    text(s, x + 0.20, 4.46, 3.4, 0.24, h, size=10.5, bold=True, color=INK)
    text(s, x + 0.20, 4.74, 3.4, 0.55, b, size=9.8, color=GRAY, line=1.30)
    x += 3.83 + 0.30
rect(s, ML, 5.76, CW, 0.78, fill=GREEN_DEEP)
text(s, ML + 0.30, 5.90, CW - 0.6, 0.50,
     "所以我们做的不是“又一个跑步 App”，而是一个把“环境适宜性”写进路径规划的空间分析系统。",
     size=13.5, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================== 4 数据
s = page("03 · 数据基础", "五类数据，拼成一张可计算的空间底图", 4)
rows = [
    ["数据源", "尺度 / 规模", "在本项目里干什么"],
    ["OSM 路网（PBF / Shapefile）", "91,203 段 · 4.7 万 km", "图结构、道路等级、单行与桥隧"],
    ["SRTM 数字高程模型", "30 m 网格 · 9 幅瓦片", "路段坡度与累计爬升"],
    ["ESA WorldCover 土地覆盖", "10 m 栅格 · 6 幅瓦片", "树冠覆盖率、绿地邻近度"],
    ["高德运动场馆 POI", "5,137 个点（用 4,081）", "设施可达性：最近的场馆多远"],
    ["OSM POI / 水系 / 绿地", "14,154 点 · 40,631 面", "公园、厕所、便利店、滨水距离"],
]
table(s, ML, 1.72, [3.05, 2.30, 2.55], rows, row_h=0.53, header_h=0.44, fs=10.2, hfs=10.2)
stats = [("12 GB", "原始数据（本地，不入库）"),
         ("45 MB", "派生表，可一键重建"),
         ("91,203", "参与评分的路段"),
         ("0", "人工标注 / 众包打分")]
y = 1.72
for big, lab in stats:
    stat(s, 8.72, y, 3.98, 0.86, big, lab, fs_big=17, fs_label=9.2)
    y += 0.94
rect(s, ML, 5.50, CW, 1.14, fill=LIGHT, line_col=LINE, line_w=0.75)
text(s, ML + 0.24, 5.58, CW - 0.5, 0.98,
     "数据契约：坐标统一 WGS84（EPSG:4326）；长度与坡度先投影到 EPSG:32650 再计算，避免在经纬度上直接用平面公式。\n"
     "原始文件不入库，只保留派生表 + 全部脚本——评审可以在一台干净的机器上用一条命令复现整张表。\n"
     "字段口径、分档规则与已知误差见 docs/数据字典-跑步数据集.md，口径变了要一起改。",
     size=10.8, color=INK, line=1.55, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================== 5 技术路线
s = page("04 · 技术路线", "四层流水线：从 12 GB 原始数据，到一次点击的环线", 5)
cols = [
    ("① 采集", ["OSM PBF / Shapefile", "SRTM 9 幅、WorldCover 6 幅", "高德 Web 服务（带缓存）", "失败响应不入缓存"],
     "data/raw/：12 GB，不入库", "pyosmium · requests"),
    ("② 处理", ["路网清洗与字段统一", "栅格按 bbox 1:1 合成", "σ=150 m 平滑后求梯度", "投影到 32650 算长度"],
     "每段一条记录：\n坡度 / 树冠 / 距离表", "rasterio · geopandas"),
    ("③ 建模", ["五维子分 + 权重合成", "CSR 稀疏图：979,351 节点", "2,075,761 条有向边", "双 Dijkstra 生成环线"],
     "segments.gpkg（45 MB）\n+ 图缓存（37 MB，可重建）", "numpy · scipy.sparse"),
    ("④ 服务", ["FastAPI 5 个端点", "GeoJSON 传输", "Vue 3 + Vite 前端", "Swagger 自文档"],
     "一次 /api/loops 调用：\n环线 + 6 项指标 + 三维子分", "FastAPI · Vue 3"),
]
x = ML
for i, (head, items, produce, tools) in enumerate(cols):
    rect(s, x, 1.76, 2.72, 3.94, fill=LIGHT, line_col=LINE, line_w=0.75)
    rect(s, x, 1.76, 2.72, 0.46, fill=GREEN_DEEP)
    text(s, x + 0.16, 1.83, 2.3, 0.32, head, size=12, bold=True, color=WHITE)
    yy = 2.34
    for it in items:
        text(s, x + 0.16, yy, 2.42, 0.5, "· " + it, size=9.8, color=INK, line=1.32)
        yy += 0.48
    rect(s, x + 0.16, 4.40, 2.40, 0.010, fill=LINE)
    text(s, x + 0.16, 4.50, 2.42, 0.62, produce, size=8.8, color=GREEN_DEEP, line=1.35)
    text(s, x + 0.16, 5.20, 2.42, 0.3, tools, size=8.6, color=GRAY)
    if i < 3:
        ar = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(x + 2.76), Inches(3.44),
                                Inches(0.30), Inches(0.34))
        ar.fill.solid()
        ar.fill.fore_color.rgb = GREEN
        ar.line.fill.background()
        ar.shadow.inherit = False
    x += 2.72 + 0.34
rect(s, ML, 5.96, CW, 0.76, fill=WHITE, line_col=LINE, line_w=0.75)
text(s, ML + 0.24, 6.02, CW - 0.5, 0.62,
     "可复现：全部脚本在 backend/scripts，参数集中在 app/config.py；改评分只需重跑两个脚本，图缓存自动失效重建。",
     size=11, color=GRAY, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================== 6 指标体系
s = page("05 · GIS 设计与建模", "六个维度、六组权重，每一个都能指到一条公式", 6)
rows = [
    ["维度", "权重", "指标与公式", "代理性质"],
    ["安全", "0.25", "道路等级分 + 距主干道 <50 m 扣分", "无路段车流量"],
    ["绿化", "0.25", "0.7×树冠 + 0.3×到绿地距离", "不识别单排行道树"],
    ["坡度", "0.20", "100 ×(1 − |i| / 10)", "SRTM 平滑，±1 个百分点"],
    ["过街", "0.10", "100 − 7 × 200 m 内交叉点数", "数分叉点，不是红绿灯"],
    ["空气", "0.10", "100 ×(40 − NO₂) / 30", "1 km 年均，只做区域校正"],
    ["设施", "0.05", "100 · exp(−d / 500)", "高德 POI，远城偏稀"],
]
table(s, ML, 1.70, [0.85, 0.75, 3.55, 2.05], rows, row_h=0.58, header_h=0.44,
      fs=10.4, hfs=10.4, aligns=[PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.LEFT, PP_ALIGN.LEFT])
text(s, ML, 5.62, 7.2, 0.6,
     "综合分 = Σ 权重 × 子分（权重合计 0.95）；分档：差 <40 · 一般 40–55 · 较好 55–70 · 好 70–85 · 很好 ≥85",
     size=10.5, color=INK, line=1.4)
pic(s, ASSETS / "c_dims.png", 7.95, 1.64, w=4.72)
text(s, 7.95, 4.80, 4.72, 0.48,
     "坡度 88 分、设施 3 分：权重与区分度不匹配，所以设施降到 0.05。",
     size=9.8, color=GRAY, line=1.42)
rect(s, 7.95, 5.36, 4.72, 0.96, fill=GREEN_PALE)
text(s, 8.13, 5.42, 4.36, 0.84,
     "空气与设施负相关 −0.66：中心设施密但空气差。\n所以设施降权、空气入模，是同一件事的两面。",
     size=9.4, color=GREEN_DEEP, line=1.42, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================== 7 理论支撑
s = page("06 · 理论支撑", "四个设计决策，各自站在一篇文献上", 7)
rows = [
    ["设计决策", "文献依据", "我们的做法与差别"],
    ["为什么是这几个维度",
     "Pikora et al. (2003) 把步行环境拆成 functional / safety / aesthetic / destination 四要素",
     "六维与之逐项对应：坡度+过街↔功能，安全↔安全，绿化↔美学，设施↔目的地；空气是额外的环境质量项"],
    ["坡度为什么这样打分",
     "Minetti et al. (2002) 给出坡度—能量代价曲线（跑步/步行）",
     "取 10% 为“极陡”做线性近似；能量多项式作为下一版替换项"],
    ["设施为什么按距离衰减",
     "Luo & Wang (2003) 的 2SFCA：供给应按人口加权，而非最近距离",
     "当前是最近距离近似；2SFCA 是明确的升级路径（需人口栅格）"],
    ["过街为什么是扣分",
     "Frank et al. (2010) 的 walkability 指数里，交叉口密度是正向因子",
     "我们反号：步行服务“到达”，跑步服务“连续”——已作为待验证假设写明"],
]
table(s, ML, 1.70, [2.55, 5.10, 4.42], rows, row_h=0.94, header_h=0.42,
      fs=9.9, hfs=10.2)
text(s, ML, 6.28, CW, 0.55,
     "方法学备选：Saaty (1980) AHP（n=6 时 RI=1.24，要求 CR<0.1）、Shannon (1948) 熵权、Saltelli (2008) 全局敏感性——三者尚未落地，当前用人工权重 + 16 组敏感性检验替代。完整 APA 引文见 docs/参考文献与算法依据.md。",
     size=9.5, color=GRAY, line=1.4)

# ================================================================== 8 空间建模实现
s = page("07 · GIS 设计与建模", "三个工程细节，决定这张图能不能信", 8)
pic(s, assets["donghu"], ML, 1.66, w=7.45)
text(s, ML, 5.96, 7.4, 0.5,
     "东湖片区：9.1 万段中的 14,684 段 · 紫点＝高德运动场馆 · 黑线＝推荐环线 · 色阶 30–85",
     size=9.2, color=GRAY)
rect(s, ML, 6.36, CW, 0.52, fill=GREEN_PALE)
text(s, ML + 0.20, 6.44, CW - 0.4, 0.40,
     "读图：高分带集中在东湖绿道与两江四岸，主干道走廊是成条的浅色低谷——与本地经验一致，这是外部效度的第一层证据。",
     size=9.2, color=GREEN_DEEP)
pit = [
    ("① 栅格镶嵌错位", "rasterio 的 from_bounds 返回整幅 bbox（瓦片外补 0），按偏移贴回会让后一幅覆盖前一幅。→ 改为按 bbox 1:1 合成，只取 >0 像元。"),
    ("② 差分算出假坡度", "直接在 DEM 上相邻像元差分，城区中位坡度 2.66%（实际约 1.2%）。→ 先 σ=150 m 高斯平滑再求梯度。"),
    ("③ 经纬度不能当平面", "全部线段先投影到 EPSG:32650 再算长度与坡度，避免方向性偏短。"),
]
yy = 1.72
for h, b in pit:
    text(s, 8.20, yy, 4.5, 0.28, h, size=11.5, bold=True, color=INK)
    text(s, 8.20, yy + 0.32, 4.5, 1.0, b, size=10.2, color=GRAY, line=1.42)
    yy += 1.46

# ================================================================== 9 环线算法
s = page("08 · 算法设计", "怎么保证“闭环”不像“原路折返”：半程折返 + 双向惩罚", 9)
steps = [
    ("1", "吸附", "起点匹配最近路网节点（示例起点偏差 2 m）"),
    ("2", "取折点", "距离场 0.44–0.56 × 目标 处为候选，按方位角取 8 个方向"),
    ("3", "去程", "偏好代价最短路：代价＝距离 ×(1 + (100−子分)/40)"),
    ("4", "回程", "把去程边双向代价 ×4 后求最短路"),
    ("5", "筛选", "保留总长 85%–115% 的候选，去重后按分排序"),
]
yy = 1.74
for num, head, body in steps:
    text(s, ML, yy, 0.30, 0.30, num, size=12, bold=True, color=GREEN)
    text(s, ML + 0.34, yy - 0.01, 1.0, 0.28, head, size=12, bold=True, color=INK)
    text(s, ML + 1.30, yy, 3.30, 0.62, body, size=9.8, color=GRAY, line=1.35)
    yy += 0.68
text(s, ML, 5.18, 4.66, 1.0,
     "只惩罚单向会退化成“原路往返”；×4 与 ×20 的残余回撤率都约 4%，但 ×20 会减少候选数量，故取 ×4。",
     size=9.6, color=GRAY, line=1.42)
pic(s, LOOPS, 5.42, 1.72, w=7.10)
text(s, 5.42, 4.32, 7.1, 0.4,
     "三个起点 × 各 3 条环线（目标 5 km）：武大 78/74/74 · 东湖 71/66/64 · 江滩 59/56/50",
     size=9.4, color=GRAY)
rect(s, 5.42, 4.80, 7.10, 0.92, fill=GREEN_PALE)
text(s, 5.62, 4.90, 6.8, 0.75,
     "对应文献：penalty-based alternative routes（Abraham et al., 2013）——我们用的是“惩罚已用边”一族里最简单的一档，好处是快，代价是形状偶尔绕街区。",
     size=9.4, color=GREEN_DEEP, line=1.40)
marks = [("12 / 12", "条环线全部闭合"), ("0", "城区回撤边（东湖 10–20）"), ("4.6%", "平均长度偏差")]
xx = ML
for big, lab in marks:
    text(s, xx, 6.02, 0.95, 0.40, big, size=15, bold=True, color=GREEN_DEEP)
    text(s, xx + 0.95, 6.08, 2.55, 0.34, lab, size=9.4, color=GRAY)
    xx += 4.05

# ================================================================== 10 系统架构
s = page("09 · 系统设计", "一次请求穿过四层：浏览器 → API → 图算法 → 数据文件", 10)
layers = [
    ("浏览器", "Vue 3.5 + TypeScript + Vite 5\n偏好开关 · 地图叠加 · 指标面板", GREEN_PALE),
    ("接口层", "FastAPI（uvicorn :8000）\n参数校验 · CORS · Swagger", RGBColor(0xEF, 0xF4, 0xF1)),
    ("算法层", "running.generate_loops()\nCSR 图 + 双 Dijkstra + 候选去重", RGBColor(0xE4, 0xEE, 0xE9)),
    ("数据层", "segments.gpkg / amap_sport_poi.csv\n图缓存 run_graph.npz（37 MB，可重建）", RGBColor(0xD9, 0xE6, 0xDF)),
]
yy = 1.72
for name, desc, fill in layers:
    rect(s, ML, yy, 5.30, 0.98, fill=fill, line_col=LINE, line_w=0.75)
    text(s, ML + 0.22, yy + 0.10, 1.30, 0.28, name, size=12, bold=True, color=GREEN_DEEP)
    text(s, ML + 0.22, yy + 0.42, 4.85, 0.50, desc, size=9.4, color=INK, line=1.30)
    if name != "数据层":
        ar = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(ML + 2.52),
                                Inches(yy + 1.00), Inches(0.22), Inches(0.15))
        ar.fill.solid()
        ar.fill.fore_color.rgb = GREEN
        ar.line.fill.background()
        ar.shadow.inherit = False
    yy += 1.16
rows = [
    ["端点", "作用", "关键参数 / 返回"],
    ["GET /health", "服务与图状态", "979,351 节点 · 2,075,761 边"],
    ["GET /api/segments", "bbox 内评分路段", "limit ≤ 60,000，GeoJSON"],
    ["GET /api/facilities", "bbox 内设施点", "kinds = sport / support / all"],
    ["POST /api/loops", "生成环线", "lng, lat, target_m, prefs"],
    ["GET /api/meta", "数据版本与口径", "权重、分档、步速"],
]
table(s, 6.35, 1.72, [1.72, 1.85, 2.75], rows, row_h=0.50, header_h=0.42, fs=9.4, hfs=9.8)
text(s, 6.35, 4.72, 6.35, 0.80,
     "现状与边界：五个端点全部跑通、有 Swagger 自文档；缓存、限流、分页、部署仍是待办——这一点写在代码注释里，不藏着。",
     size=9.8, color=GRAY, line=1.42)
for k, line in enumerate([
        "换前端不动算法：GeoJSON 是唯一契约",
        "换算法不动前端：/api/loops 的签名不变",
        "换数据不用改代码：重跑管线，重启即生效"]):
    text(s, 6.35, 5.62 + k * 0.40, 6.30, 0.30, "· " + line, size=9.6, color=GREEN_DEEP)

# ================================================================== 11 前端原型
s = page("10 · 系统设计", "三步得到一条能解释的环线：定起点 → 选偏好 → 读分", 11)
pic(s, DESKTOP, ML, 1.58, w=8.02)
text(s, ML, 6.64, 8.4, 0.3, "高保真静态原型 frontend/prototype（1440 × 900）", size=8.5, color=GRAY)
notes = [
    ("输入", "起点（可搜索／点选）、3·5·10 km、四个偏好开关"),
    ("输出", "环线叠加在地图上；右侧 78.5 分 + 6 项实测指标"),
    ("解释", "三维子分条 + 权重构成（避主干道 0.39 / 绿化 0.39 / 平坦 0.23）"),
    ("诚实", "底注写明 SRTM 精度 ±1 个百分点与每类数据的来源"),
]
yy = 1.72
for h, b in notes:
    text(s, 9.16, yy, 3.55, 0.26, h, size=10.2, bold=True, color=GREEN)
    text(s, 9.16, yy + 0.26, 3.55, 0.72, b, size=9.6, color=INK, line=1.38)
    yy += 1.05
text(s, 9.16, 6.02, 3.55, 0.7,
     "地图层：现为 SVG 占位，待接 BMapGL（需 AK）并做 WGS84→BD-09。",
     size=9, color=GRAY, line=1.38)

# ================================================================== 12 敏感性
s = page("11 · 可靠性", "换权重、换方法，结论会不会翻？", 12)
pic(s, ASSETS / "c_sens.png", ML, 1.68, w=6.55)
res = [
    ("单维扰动温和", "任一项 ±20%，Spearman ≥ 0.9940，前 10% 重合 ≥ 0.93"),
    ("整组换权也稳", "AHP 型 0.9870；舒适优先 0.9337；地形优先 0.9104"),
    ("唯一的坑是等权", "全部等权掉到 0.8887——把失效的设施维度抬到 1/6，噪声被放大"),
    ("所以结论是", "分数对“权重怎么定”不敏感，对“维度是否有效”敏感；后者才是真问题"),
]
yy = 1.72
for h, b in res:
    text(s, 7.42, yy, 5.2, 0.28, "· " + h, size=11.5, bold=True, color=INK)
    text(s, 7.62, yy + 0.32, 5.0, 0.62, b, size=10, color=GRAY, line=1.40)
    yy += 1.02
text(s, 7.42, 5.94, 5.2, 0.8,
     "方法：Saltelli et al. (2008) 全局敏感性分析的简化版；脚本 sensitivity_analysis.py，16 组方案可复跑。",
     size=9.2, color=GRAY, line=1.40)

# ================================================================== 13 结果与边界
s = page("12 · 结果与边界", "先说清楚哪里不能信，再谈分数", 13)
rows = [
    ["起点", "#1 环线长度", "综合分"],
    ["武汉大学（八一路珞珈山）", "5.3 km", "78"],
    ["东湖绿道（湖心岛）", "5.6 km", "71"],
    ["汉口江滩", "5.3 km", "59"],
]
table(s, ML, 1.70, [3.10, 1.60, 1.05], rows, row_h=0.50, header_h=0.42, fs=10.2,
      aligns=[PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.CENTER])
text(s, ML, 3.86, 6.10, 0.9,
     "12 条环线平均：转弯 34.9 次 · 长度偏差 4.6% · 城区回撤边 0\n（东湖受水域约束，仍残留 10–20 条）",
     size=9.6, color=GRAY, line=1.45)
text(s, ML, 4.72, 5.9, 0.28, "四条明写的边界", size=10.5, bold=True, color=GREEN)
lime = [
    "没有“人的数据”：无路段车流量、无真实跑步轨迹、无街景与绿视率；",
    "设施维度失效：中位 3 分，评分上限被压到 81（实测最高）；",
    "过街指标与 OSM 实际人行横道的 Spearman 仅 0.373；",
    "坡度对 90% 的路段接近满分，区分度低（中位 88 分）。",
]
yy = 4.96
for t in lime:
    text(s, ML, yy, 5.9, 0.28, "· " + t, size=9.4, color=INK, line=1.3)
    yy += 0.28
pic(s, ASSETS / "c_grade.png", 6.95, 1.66, w=5.65)
text(s, 6.95, 4.34, 5.65, 1.32,
     "替代路径（已写入数据增补清单）：\n"
     "车流量 → 道路等级 + 间距代理；绿视率 → WorldCover 树冠 + 单株树校准样本；\n"
     "设施 → 2SFCA 人口加权；过街 → OSM 人行横道做校准项。",
     size=9.6, color=GRAY, line=1.50)
rect(s, ML, 6.10, CW, 0.62, fill=GREEN_DEEP)
text(s, ML + 0.28, 6.18, CW - 0.56, 0.46,
     "怎么用这个分：看相对排序，不看绝对值——“较好”对“一般”的差异是可解释的，“78 分”本身不是一把尺。",
     size=10.6, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================== 14 创新点
s = page("13 · 创新点", "四点不同：可解释、能闭环、可复现、知道边界", 14)
inno = [
    ("逐段可解释", "分数拆到六个维度，每一维都能指回一条公式和一个数据源；不是一次性黑箱打分。",
     "页面上的三维条来自真实子分，不是事后拼的文案"),
    ("闭环而非最短路", "半程折返 + 双向四倍惩罚，把 A→B 变成 A→B→A；3/5/10 km 三档、偏好可调。",
     "12 条环线全部闭合，城区回撤边为 0"),
    ("可复现", "原始数据不入库，45 MB 派生表 + 全部脚本可本机重建；参数集中在 config.py。",
     "换一台干净机器，两条命令重算 9.1 万段"),
    ("边界写明", "代理性质、误差方向、失效维度都写进数据字典；\n能直说“这一维暂时不可信”。",
     "四条已知问题写进文档，而不是藏起来"),
]
for i, (h, b, ev) in enumerate(inno):
    col = i % 2
    row = i // 2
    bx = ML + col * 6.16
    by = 1.78 + row * 1.84
    rect(s, bx, by, 5.90, 1.62, fill=LIGHT, line_col=LINE, line_w=0.75)
    text(s, bx + 0.24, by + 0.16, 0.5, 0.3, f"0{i+1}", size=13, bold=True,
         color=RGBColor(0xCB, 0xDF, 0xD5))
    text(s, bx + 0.76, by + 0.18, 4.9, 0.3, h, size=13, bold=True, color=INK)
    text(s, bx + 0.76, by + 0.58, 4.90, 0.62, b, size=10.2, color=GRAY, line=1.42)
    text(s, bx + 0.76, by + 1.22, 4.90, 0.30, "证据：" + ev, size=8.8, color=GREEN)
rect(s, ML, 5.54, CW, 0.66, fill=GREEN_PALE)
text(s, ML + 0.28, 5.60, CW - 0.56, 0.54,
     "第五条：偏好可调。同一套分数，换一组权重就从“绿荫优先”切到“平坦优先”，页面上的三维条会跟着变——解释不是事后编的。",
     size=10.5, color=GREEN_DEEP, line=1.40, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================== 15 成果与下一步
s = page("14 · 成果与下一步", "已经跑通的，和接下来要补的", 15)
text(s, ML, 1.70, 5.6, 0.28, "已经跑通", size=11, bold=True, color=GREEN)
done = ["9.1 万段五维评分表 + 三起点环线 + 全市渲染图",
        "16 组权重敏感性 + 12 条环线量化评测",
        "FastAPI 5 个端点 + 高保真前端原型",
        "说明书 v4.0 · 数据字典 · 参考文献手册"]
yy = 2.04
for t in done:
    text(s, ML, yy, 0.22, 0.28, "✓", size=11.5, bold=True, color=GREEN)
    text(s, ML + 0.28, yy, 5.3, 0.55, t, size=10.4, color=INK, line=1.35)
    yy += 0.60
text(s, 6.62, 1.70, 5.9, 0.28, "下一阶段（按性价比排序）", size=11, bold=True, color=AMBER)
nexts = [
    ("数据", "从本地 PBF 重抽 surface / lit / cycleway 标签，补 LTS 骑行分级"),
    ("方法", "设施改 2SFCA；过街用人行横道校准；坡度试能量代价"),
    ("系统", "接 BMapGL 上线，加结果缓存与分页"),
]
yy = 2.04
for tag, b in nexts:
    rect(s, 6.62, yy, 0.62, 0.26, fill=AMBER_PALE)
    text(s, 6.62, yy + 0.02, 0.62, 0.24, tag, size=8.8, bold=True, color=AMBER,
         align=PP_ALIGN.CENTER)
    text(s, 7.34, yy - 0.02, 4.9, 0.62, b, size=10.2, color=INK, line=1.40)
    yy += 0.78
rect(s, ML, 4.86, CW, 1.28, fill=GREEN_DEEP)
text(s, ML + 0.34, 5.02, CW - 0.68, 0.95,
     "我们做的不是“又一个跑步 App”，而是把“环境适宜性”变成可计算、可审计、可迭代的城市空间指标——\n"
     "它既能回答“今天跑哪条线”，也能回答“这条街该不该补绿道”。",
     size=12.5, color=WHITE, line=1.55)
text(s, ML, 6.34, CW, 0.4, "谢谢 · 欢迎提问与指正", size=11, color=GRAY)

prs.save(OUT)
print(f"saved: {OUT}")
print(f"slides: {len(prs.slides._sldIdLst)}")

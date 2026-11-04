"""Generate ppt-master SVG pages for the runroute deck (1280x720)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1] / "projects" / "runroute_ppt169_20261030"
OUT = PROJ / "svg_output"

BG = "#FFFFFF"
SEC_BG = "#F2F6F3"
PRIMARY = "#1A5C46"
ACCENT = "#C0762A"
ACC2 = "#4F9D7D"
INK = "#1F2A26"
SUB = "#5F6F68"
LINE = "#D9E3DD"

W, H = 1280, 720
M = 64
FOOT = "城市慢跑 / 慢骑环境适宜性评价与路线推荐 · 武汉"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cw(ch: str, size: float) -> float:
    o = ord(ch)
    if o < 128:
        if ch == " ":
            return 0.30 * size
        if ch.isdigit():
            return 0.56 * size
        return 0.55 * size
    return 1.06 * size


def tw(s: str, size: float) -> float:
    return sum(cw(c, size) for c in s)


class Page:
    def __init__(self, num: int, role: str = "content"):
        self.num = num
        self.role = role
        self.parts: list[str] = []
        self.seq = 0

    def _id(self, kind: str) -> str:
        self.seq += 1
        return f"p{self.num:02d}-{kind}-{self.seq:02d}"

    # ---------- primitives ----------
    def rect(self, x, y, w, h, fill, rx=0, stroke="none", sw=0, role="decoration"):
        r = f' rx="{rx}"' if rx else ""
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke != "none" else ""
        self.parts.append(
            f'<rect id="{self._id("rect")}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"'
            f'{r}{s} fill="{fill}" data-pptx-role="{role}"/>'
        )

    def line(self, x1, y1, x2, y2, color=LINE, sw=1, role="decoration"):
        self.parts.append(
            f'<line id="{self._id("line")}" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
            f'stroke="{color}" stroke-width="{sw}" data-pptx-role="{role}"/>'
        )

    def circle(self, cx, cy, r, fill, role="decoration"):
        self.parts.append(
            f'<circle id="{self._id("dot")}" cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{fill}" '
            f'data-pptx-role="{role}"/>'
        )

    def image(self, name, x, y, w, h, fit="slice", role="background"):
        self.parts.append(
            f'<image id="{self._id("img")}" href="../images/{name}" x="{x:g}" y="{y:g}" '
            f'width="{w:g}" height="{h:g}" preserveAspectRatio="xMidYMid {fit}" '
            f'data-pptx-role="{role}"/>'
        )

    def group(self, gid, x, y, w, h):
        return _Group(self, gid, x, y, w, h)

    def emit_group(self, gid, bounds, inner: str):
        x, y, bw, bh = bounds
        self.parts.append(
            f'<g id="{gid}" data-pptx-bounds="{x:g} {y:g} {bw:g} {bh:g}">{inner}</g>'
        )

    # ---------- shared chrome ----------
    def head(self, kicker: str, title_lines: list[str], sub: str | None = None):
        with self.group("header", M - 2, 26, W - 2 * M + 4, 150) as g:
            g.text_raw(M, 46, 15, PRIMARY, 600, 1.0, [kicker])
            ty = 96
            g.text_raw(M, ty, 38, INK, 700, 1.24, title_lines)
            rule_y = ty + 1.24 * 38 * (len(title_lines) - 1) + 0.86 * 38 + 26
            g.line(M, rule_y, W - M, rule_y, LINE, 1)
            if sub:
                g.text_raw(M, rule_y + 30, 20, SUB, 400, 1.5, [sub])
        return rule_y

    def foot(self):
        with self.group("footer", M - 2, 654, W - 2 * M + 4, 52) as g:
            g.line(M, 660, W - M, 660, LINE, 1)
            g.text_raw(M, 686, 13, SUB, 400, 1.2, [FOOT])
            g.text_raw(W - M, 686, 13, SUB, 400, 1.2, [f"{self.num:02d} / 13"], anchor="end")

    def note(self, gid, y, lines, size=13):
        with self.group(gid, M - 2, y - size, W - 2 * M + 4, size * 1.6) as g:
            g.text_raw(M, y, size, SUB, 400, 1.4, lines)

    def svg(self) -> str:
        body = "\n  ".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}" font-family="Microsoft YaHei" '
            f'data-pptx-page-role="{self.role}">\n  {body}\n</svg>\n'
        )


class _Group:
    def __init__(self, page: Page, gid: str, x, y, w, h):
        self.page = page
        self.gid = gid
        self.box = [x, y, x + w, y + h]
        self.inner: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.page.emit_group(self.gid, self._bounds(), "".join(self.inner))
        return False

    def _grow(self, b):
        self.box = [min(self.box[0], b[0]), min(self.box[1], b[1]),
                    max(self.box[2], b[2]), max(self.box[3], b[3])]

    def _bounds(self):
        x0, y0, x1, y1 = self.box
        return (round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1))

    def text_raw(self, x, y0, size, fill, weight, leading, lines, anchor="start"):
        self.inner.append(_text_svg(x, y0, size, fill, weight, leading, lines, anchor))
        self._grow(_text_bounds(x, y0, size, leading, lines, anchor))
        return self

    def text(self, *a, **k):
        return self.text_raw(*a, **k)

    def rect(self, x, y, w, h, fill, rx=0, stroke="none", sw=0):
        self.inner.append(
            f'<rect id="{self.page._id("rect")}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"'
            + (f' rx="{rx}"' if rx else "")
            + (f' stroke="{stroke}" stroke-width="{sw}"' if stroke != "none" else "")
            + f' fill="{fill}"/>'
        )
        self._grow((x, y, x + w, y + h))
        return self

    def line(self, x1, y1, x2, y2, color=LINE, sw=1):
        self.inner.append(
            f'<line id="{self.page._id("line")}" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
            f'stroke="{color}" stroke-width="{sw}"/>'
        )
        self._grow((min(x1, x2), y1, max(x1, x2), y1 + sw))
        return self

    def circle(self, cx, cy, r, fill):
        self.inner.append(f'<circle id="{self.page._id("dot")}" cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{fill}"/>')
        self._grow((cx - r, cy - r, cx + r, cy + r))
        return self

    def image_at(self, name, x, y, w, h, fit="meet"):
        self.inner.append(
            f'<image id="{self.page._id("img")}" href="../images/{name}" x="{x:g}" y="{y:g}" '
            f'width="{w:g}" height="{h:g}" preserveAspectRatio="xMidYMid {fit}"/>'
        )
        self._grow((x, y, x + w, y + h))
        return self


def _text_svg(x, y0, size, fill, weight, leading, lines, anchor):
    step = size * leading
    attr = f' text-anchor="{anchor}"' if anchor in ("end", "middle") else ""
    parts = [f'<text x="{x:g}" y="{y0:g}" font-size="{size:g}" fill="{fill}" '
             f'font-weight="{weight}"{attr}>']
    for i, l in enumerate(lines):
        dy = 0 if i == 0 else step
        parts.append(f'<tspan x="{x:g}" dy="{dy:g}">{esc(l)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def _text_bounds(x, y0, size, leading, lines, anchor):
    step = size * leading
    wmax = max(tw(l, size) for l in lines)
    if anchor == "end":
        x0, x1 = x - wmax, x
    elif anchor == "middle":
        x0, x1 = x - wmax / 2, x + wmax / 2
    else:
        x0, x1 = x, x + wmax
    top = y0 - 0.86 * size
    bot = y0 + step * (len(lines) - 1) + 0.32 * size
    return (x0 - 2, top, x1 + 2, bot)


# ---------------------------------------------------------------- pages
def p01(p: Page):
    p.image("city_map.png", 640, 0, 640, 720, "slice")
    p.rect(636, 0, 4, 720, PRIMARY)
    with p.group("cover-text", 80, 100, 536, 520) as g:
        g.text(88, 132, 15, PRIMARY, 600, 1.0, ["城市空间分析 · 课程项目展示"])
        g.text(88, 214, 72, INK, 700, 1.12, ["跑哪条线？"])
        g.text(88, 300, 26, INK, 400, 1.55,
               ["城市慢跑 / 慢骑环境的量化评价", "与闭环路线推荐 · 以武汉为例"])
        g.rect(88, 392, 120, 3, PRIMARY)
        g.text(88, 448, 17, SUB, 400, 1.2,
               ["9.1 万段路网 · 4.7 万公里 · 六维评分 · 一次点击生成闭环"])
        g.text(88, 568, 15, SUB, 400, 1.9,
               ["汇报人 ——   指导教师 ——", "单位 ——   2026 年 11 月"])


def p02(p: Page):
    p.head("01 · 研究背景", ["跑步 App 记录「你跑了多少」，", "没人回答「你该跑哪儿」"])
    facts = [
        ("01", "需求是真的。",
         ["跑步门槛最低，但「跑哪条线」直接决定体验；", "决策却依赖口碑、朋友圈和一次偶然发现。"]),
        ("02", "供给是够的。",
         ["绿道、滨江步道、环湖路大量建成；", "信息却散落在推文、评论和本地人的记忆里。"]),
        ("03", "工具是缺的。",
         ["主流 App 的「路线」＝热力图＋手动收藏：", "不可解释、不可定制，也不管坡度、暴露与红绿灯。"]),
    ]
    y = 238
    for no, head, body in facts:
        with p.group(f"fact-{no}", M, y - 30, 620, 100) as g:
            g.text(M, y + 8, 26, "#C9DDD3", 700, 1.0, [no])
            g.text(M + 46, y, 22, INK, 700, 1.0, [head])
            g.text(M + 46, y + 34, 17, INK, 400, 1.6, body)
        y += 118
    with p.group("quote", 742, 206, 474, 344) as g:
        g.rect(742, 206, 474, 344, SEC_BG)
        g.rect(742, 206, 4, 344, PRIMARY)
        g.text(772, 256, 20, INK, 400, 1.75,
               ["同样是 5 km：", "沿江滩跑，还是沿主干道跑，", "噪声、尾气、坡度、人车冲突", "完全不同——",
                "但在地图上，这两段路看起来一样。"])
        g.text(772, 502, 15, SUB, 400, 1.0, ["—— 这个项目的起点"])
    p.note("policy", 628, ["政策语境：《健康中国行动（2019—2030年）》 · WHO《GAPPA》2018 · 住建部《城市步行和自行车交通系统规划设计导则》2013"])
    p.foot()


def p03(p: Page):
    p.head("02 · 系统介绍", ["把一个说不清的感觉，拆成三个可计算的问题"])
    qs = [
        ("Q1", "量化", "每段路能不能给出 0–100 分？",
         ["六维指标＋显式权重；每一维都", "能回溯到一条公式和一个数据源。"]),
        ("Q2", "组织", "高分路段能不能拼成闭环？",
         ["半程折返选折点；回程对去程边", "双向加价，避免原路折返。"]),
        ("Q3", "解释", "用户凭什么相信这个分数？",
         ["逐维拆解、偏好可调、敏感性可", "复算——错了也知道错在哪。"]),
    ]
    x = M
    for no, tag, q, a in qs:
        with p.group(f"q-{no}", x, 186, 368, 112) as g:
            g.rect(x, 186, 3, 106, LINE)
            g.text(x + 18, 204, 13, PRIMARY, 700, 1.0, [no])
            g.text(x + 56, 204, 13, PRIMARY, 600, 1.0, [tag])
            g.text(x + 18, 238, 20, INK, 700, 1.2, [q])
            g.text(x + 18, 276, 13, SUB, 400, 1.4, a)
        x += 392
    with p.group("modes-figure", M, 308, 1152, 330) as g:
        g.image_at("route_modes.png", M, 308, 1152, 330, "meet")
    p.foot()

def p04(p: Page):
    p.head("03 · 数据与来源", ["五类公开数据，拼成一张可计算的空间底图"])
    cols = [(M, 292), (M + 302, 208), (M + 520, 268)]
    rows = [
        ("OSM 路网（PBF / Shapefile）", "91,203 段 · 4.7 万 km", "图结构、道路等级、单行与桥隧"),
        ("SRTM 数字高程模型", "30 m 网格 · 9 幅瓦片", "路段坡度与累计爬升"),
        ("ESA WorldCover 土地覆盖", "10 m 栅格 · 6 幅瓦片", "树冠覆盖率、绿地邻近度"),
        ("高德运动场馆 POI", "5,137 个点（用 4,081）", "设施可达性：最近的场馆多远"),
        ("CHAP 再分析网格", "0.01° · 2024 年年均", "逐段 PM2.5 / NO2，空气维度"),
    ]
    with p.group("data-table", M, 196, 792, 318) as g:
        g.rect(M, 196, 792, 34, PRIMARY)
        for (cx, _), h in zip(cols, ["数据源", "尺度 · 规模", "在本项目里干什么"]):
            g.text(cx + 12, 219, 15, "#FFFFFF", 600, 1.0, [h])
        y = 230
        for i, (a, b, c) in enumerate(rows):
            if i % 2 == 1:
                g.rect(M, y, 792, 56, SEC_BG)
            g.text(cols[0][0] + 12, y + 35, 17, INK, 600, 1.0, [a])
            g.text(cols[1][0] + 12, y + 35, 17, INK, 400, 1.0, [b])
            g.text(cols[2][0] + 12, y + 35, 17, INK, 400, 1.0, [c])
            y += 56
    stats = [("12 GB", "原始数据（本地，不入库）"), ("45 MB", "派生表，可一键重建"),
             ("91,203", "参与评分的路段"), ("0", "人工标注 / 众包打分")]
    y = 196
    for val, lab in stats:
        with p.group(f"stat-{val}", 888, y, 328, 74) as g:
            g.rect(888, y, 328, 74, SEC_BG)
            g.text(908, y + 40, 32, PRIMARY, 700, 1.0, [val])
            g.text(908, y + 62, 13, SUB, 400, 1.0, [lab])
        y += 86
    p.note("src-note", 566,
           ["数据契约：坐标统一 WGS84（EPSG:4326）；长度与坡度先投影到 EPSG:32650 再计算，",
            "避免在经纬度上直接用平面公式。原始文件不入库，只保留派生表＋全部脚本。"])
    p.foot()


def p05(p: Page):
    p.head("04 · 技术栈", ["计算用 Python，服务用 FastAPI，前端用 Vue"])
    cols = [
        ("① 采集", ["OSM PBF / Shapefile", "SRTM 9 幅、WorldCover 6 幅", "高德 Web 服务（带缓存）",
                    "CHAP 月度 netCDF", "失败响应不入缓存", "原始数据 12 GB 不入库"], "pyosmium · requests"),
        ("② 处理", ["路网清洗与字段统一", "栅格按 bbox 1:1 合成", "σ=150 m 平滑后求梯度",
                    "投影到 32650 算长度", "每段一条记录", "栅格统一到 10 m 档"], "rasterio · geopandas"),
        ("③ 建模", ["六维子分＋权重合成", "CSR 图 979,351 节点", "2,075,761 条有向边",
                    "双 Dijkstra 生成环线", "图缓存 37 MB 可重建", "低分路段代价 ×3.5 上限"], "numpy · scipy.sparse"),
        ("④ 服务", ["FastAPI 5 个端点", "GeoJSON 传输", "Vue 3＋Vite 前端",
                    "Swagger 自动文档", "一次调用返回子分", "CSR 图预载 0.4 s"], "FastAPI · Vue 3"),
    ]
    x = M
    for ci, (head, items, tools) in enumerate(cols, 1):
        with p.group(f"stack-{ci}", x, 196, 268, 344) as g:
            g.rect(x, 196, 268, 40, PRIMARY)
            g.text(x + 14, 223, 17, "#FFFFFF", 600, 1.0, [head])
            y = 266
            for it in items:
                g.text(x + 14, y, 15, INK, 400, 1.0, [it])
                y += 34
            g.line(x + 14, 462, x + 254, 462, LINE, 1)
            g.text(x + 14, 490, 13, SUB, 400, 1.0, [tools])
        x += 284
    p.note("repro", 600, ["可复现：全部脚本在 backend/scripts，参数集中在 app/config.py；改评分只需重跑两个脚本，图缓存自动失效重建。"])
    p.foot()


def p06(p: Page):
    p.head("05 · 系统设计", ["三步交互，一次点击拿到能解释的环线"])
    with p.group("prototype", 528, 186, 690, 434) as g:
        g.rect(528, 186, 686, 434, SEC_BG)
        g.image_at("ui_prototype.png", 540, 198, 662, 410, "meet")
    blocks = [
        ("输入", ["起点可搜索或点选；目标距离 3 / 5 / 10 km；", "四个偏好开关：绿荫滨水、避开主干道、", "尽量平坦、洗手间补给。"]),
        ("输出", ["环线叠加在地图上；右侧 78.5 分＋", "六项实测指标：距离、用时、树冠、", "坡度、最近场馆、起点偏差。"]),
        ("解释", ["三维子分条＋权重构成；底注写明", "SRTM 精度与每类数据的来源。"]),
    ]
    y = 206
    for i, (head, body) in enumerate(blocks):
        with p.group(f"step-{head}", M, y - 26, 424, 118) as g:
            g.text(M, y - 6, 20, PRIMARY, 700, 1.0, [head])
            g.text(M, y + 30, 17, INK, 400, 1.6, body)
        y += 132
    p.note("ui-note", 640, ["现状与边界：前端为高保真静态原型，地图层待接 BMapGL 并做 WGS84→BD-09；五个接口已全部跑通。"])
    p.foot()


def p07(p: Page):
    p.head("06 · GIS 处理", ["从 12 GB 原始数据到 27 字段评分表，四层流水线"])
    stages = [("① 原始", "OSM / SRTM / WorldCover\n高德 POI / CHAP", "12 GB · 不入库"),
              ("② 清洗", "路网去重与字段统一\n91,203 段 · 24 字段", "EPSG:32650"),
              ("③ 指标", "坡度 / 树冠 / 场馆距离\nPM2.5 与 NO2", "每段一条记录"),
              ("④ 评分", "六维子分＋加权合成\n分级与分布", "score_summary.json")]
    x = M
    for i, (head, body, tag) in enumerate(stages):
        with p.group(f"stage-{i+1}", x, 196, 262, 150) as g:
            g.rect(x, 196, 262, 34, PRIMARY)
            g.text(x + 14, 219, 17, "#FFFFFF", 600, 1.0, [head])
            g.rect(x, 230, 262, 116, SEC_BG)
            g.text(x + 14, 262, 15, INK, 400, 1.55, body.split("\n"))
            g.text(x + 14, 322, 13, SUB, 400, 1.0, [tag])
        x += 276
    details = [
        ("栅格镶嵌错位",
         ["rasterio 的 from_bounds 返回整幅 bbox（瓦片外补 0）。按瓦片偏移贴回，",
          "会让后一幅覆盖前一幅——改为按 bbox 1:1 合成，只取大于 0 的像元。"]),
        ("逐点差分算出假坡度",
         ["直接在 DEM 上作相邻像元差分，城区中位坡度 2.66%（实际约 1.2%）。",
          "必须先做 σ=150 m 高斯平滑再求梯度。"]),
        ("经纬度不能当平面",
         ["所有线段先投影到 EPSG:32650 再算长度与坡度，避免方向性系统偏短。"]),
    ]
    y = 386
    for i, (head, body) in enumerate(details):
        with p.group(f"detail-{i+1}", M, y - 30, 1152, 78) as g:
            g.text(M, y, 20, INK, 700, 1.0, [f"{i+1}. " + head])
            g.text(M + 300, y, 15, SUB, 400, 1.55, body)
        y += 82
    p.foot()


def p08(p: Page):
    p.head("07 · 评价算法", ["六维加权：每一维都能指回一条公式"])
    rows = [
        ("安全", "0.25", "道路等级分＋距主干道 <50 m 扣分", "无路段车流量"),
        ("绿化", "0.25", "0.7×树冠＋0.3×到绿地距离", "不识别单排行道树"),
        ("坡度", "0.20", "100×(1−|i|/10)", "SRTM 平滑，±1 个百分点"),
        ("过街", "0.10", "100−7×200 m 内交叉点数", "数的是分叉点，不是红绿灯"),
        ("空气", "0.10", "100×(40−NO2)/30", "1 km 年均，只做区域校正"),
        ("设施", "0.05", "100·exp(−d/500)", "高德 POI，远城偏稀"),
    ]
    with p.group("weight-table", M, 196, 700, 268) as g:
        g.rect(M, 196, 700, 32, PRIMARY)
        for cx, h in [(M + 10, "维度"), (M + 90, "权重"), (M + 170, "公式"), (M + 470, "代理性质")]:
            g.text(cx, 218, 15, "#FFFFFF", 600, 1.0, [h])
        y = 228
        for i, (a, b, c, d) in enumerate(rows):
            if i % 2 == 1:
                g.rect(M, y, 700, 36, SEC_BG)
            g.text(M + 10, y + 24, 17, INK, 700, 1.0, [a])
            g.text(M + 90, y + 24, 17, PRIMARY, 700, 1.0, [b])
            g.text(M + 170, y + 24, 17, INK, 400, 1.0, [c])
            g.text(M + 470, y + 24, 15, SUB, 400, 1.0, [d])
            y += 36
    with p.group("formula-block", 796, 196, 420, 268) as g:
        g.rect(796, 196, 420, 268, SEC_BG)
        g.text(816, 226, 13, PRIMARY, 600, 1.0, ["总分"])
        g.text(816, 258, 17, INK, 400, 1.0, ["score = Σ wᵢ · sᵢ   (i = 六维)"])
        g.text(816, 306, 13, PRIMARY, 600, 1.0, ["空气子分"])
        g.text(816, 338, 17, INK, 400, 1.0, ["s_air = clip(100·(40−NO₂)/30, 0, 100)"])
        g.text(816, 386, 13, PRIMARY, 600, 1.0, ["绿化子分"])
        g.text(816, 418, 17, INK, 400, 1.0, ["s_green = 0.7(1−e^(−2.5S)) + 0.3(1−d/1500)"])
    p.note("w-note", 500,
           ["权重合计 0.95，沿用上一版口径；分档 差<40 / 一般 40–55 / 较好 55–70 / 好 70–85 / 很好≥85。"])
    p.note("theory-note", 546,
           ["理论支撑：六维划分对应步行环境的功能、安全、美观与目的地四类要素（文献待补，本稿先按普适表述占位）。"])
    p.foot()


def p09(p: Page):
    p.head("08 · 评价算法验证", ["换个权重，路段排序几乎不变；等权才会翻车"])
    items = [
        ("单维扰动温和", "任一项 ±20%，Spearman ≥ 0.9940，前 10% 重合 ≥ 0.93"),
        ("整组换权也稳", "AHP 型 0.9870；舒适优先 0.9337；地形优先 0.9104"),
        ("唯一的坑是等权", "全部等权 1/6 掉到 0.8887——把失效的设施维度抬到了与安全同等分量"),
    ]
    y = 216
    for head, body in items:
        with p.group(f"concl-{head[:2]}", M, y - 28, 660, 106) as g:
            g.rect(M, y - 24, 3, 92, PRIMARY if "坑" not in head else ACCENT)
            g.text(M + 20, y, 22, INK, 700, 1.0, [head])
            g.text(M + 20, y + 38, 15, SUB, 400, 1.5, [body])
        y += 118
    with p.group("grade-dist", 760, 196, 456, 300) as g:
        g.text(760, 220, 15, PRIMARY, 600, 1.0, ["91,203 段的分档构成"])
        bars = [("差 <40", 9521, ACCENT), ("一般 40–55", 40483, "#E4CE9A"),
                ("较好 55–70", 39070, ACC2), ("好 70–85", 2129, PRIMARY), ("很好 ≥85", 0, PRIMARY)]
        y2 = 258
        for lab, n, col in bars:
            g.text(760, y2, 13, SUB, 400, 1.0, [lab])
            wbar = n / 40483 * 250
            if n:
                g.rect(880, y2 - 11, max(wbar, 2), 14, col)
            g.text(1140, y2, 13, INK, 600, 1.0, [f"{n:,}"])
            y2 += 46
    p.note("sens-note", 548, ["方法：全局敏感性的简化版，脚本 sensitivity_analysis.py 可复跑 16 组方案；Spearman 衡量两套权重的路段排序一致性。"])
    p.foot()


def p10(p: Page):
    p.head("09 · 路线生成算法", ["半程折返＋双向惩罚：把最短路变成闭环"])
    steps = [
        ("吸附", "起点匹配最近路网节点（示例偏差 2 m）"),
        ("取折点", "距离场 0.44–0.56×目标 处为候选，按方位角取 8 个方向"),
        ("去程", "按偏好代价走最短路，代价见右下公式"),
        ("回程", "把去程边双向代价 ×4 后重算，避免原路折返"),
        ("筛选", "保留总长 85%–115% 的候选，去重后按分排序"),
    ]
    y = 214
    for i, (head, body) in enumerate(steps):
        with p.group(f"step-{i+1}", M, y - 26, 660, 76) as g:
            g.circle(M + 12, y - 8, 12, PRIMARY)
            g.text(M + 12, y - 2, 13, "#FFFFFF", 700, 1.0, [str(i + 1)], anchor="middle")
            g.text(M + 40, y, 20, INK, 700, 1.0, [head])
            g.text(M + 150, y, 15, SUB, 400, 1.4, [body])
        y += 82
    with p.group("cost-formula", 756, 214, 460, 200) as g:
        g.rect(756, 214, 460, 196, SEC_BG)
        g.text(776, 244, 13, PRIMARY, 600, 1.0, ["偏好代价"])
        g.text(776, 278, 17, INK, 400, 1.0, ["c = d · (1 + (100 − p) / 40)"])
        g.text(776, 316, 13, SUB, 400, 1.5, ["d 为段长；p 为该段的偏好子分。", "低分路段代价最高放大到 3.5 倍。"])
        g.line(776, 356, 1196, 356, LINE, 1)
        g.text(776, 386, 13, SUB, 400, 1.0, ["回程再乘 RETRACE_PENALTY = 4.0"])
    p.note("retrace-note", 630, ["实测：只惩罚单向会退化成「原路往返」；×4 与 ×20 的残余回撤率都约 4%，但 ×20 会减少候选数量，故取 4。"])
    p.foot()


def p11(p: Page):
    p.head("10 · 算法验证", ["三种模式都能跑，边界也写在数据里"])
    metrics = [("12 / 12", "条环线全部闭合"), ("0", "城区回撤边"), ("4.6%", "平均长度偏差")]
    x = M
    for val, lab in metrics:
        with p.group(f"metric-{val[:2].strip()}", x, 186, 360, 74) as g:
            g.text(x, 226, 32, PRIMARY, 700, 1.0, [val])
            g.text(x, 256, 13, SUB, 400, 1.0, [lab])
        x += 384
    with p.group("air-gradient", M, 292, 620, 252) as g:
        g.image_at("air_gradient.png", M, 292, 620, 252, "meet")
    p.note("gradient-note", 572,
           ["NO₂ 随中心距离 28.8→18.9（1.52 倍）；PM2.5 几乎无梯度（1.09 倍）"])
    bullets = [
        ("空气是区域变量", "1 km 网格能给出「哪个区」，给不出「哪条路」。"),
        ("代价函数不吃空气", "把 NO₂ 加进代价后，武大→江滩路线一米未变。"),
        ("同圈层内没差别", "道路等级之间只差 0.2–1.8 µg/m³，圈层之间差 9.9。"),
        ("时间杠杆更大", "同一座城，1 月与 7 月的 PM2.5 差 5.24 倍。"),
    ]
    y = 300
    for head, body in bullets:
        with p.group(f"bd-{head[:2]}", 724, y - 30, 492, 66) as g:
            g.rect(724, y - 22, 3, 48, ACC2)
            g.text(744, y, 17, INK, 700, 1.0, [head])
            g.text(744, y + 30, 13, SUB, 400, 1.35, [body])
        y += 74
    p.note("air-note", 620, ["做法上：空气只做区域校正与赛事月份提示，不进入路径代价；这条边界写进了数据字典。"])
    p.foot()

def p12(p: Page):
    p.head("11 · 创新点与预期成果", ["可解释、能闭环、可复现、知道自己不行"])
    cards = [
        ("01 逐段可解释", ["六维子分每一维都能指回一条公式和", "一个数据源，不是一次性黑箱打分。"]),
        ("02 闭环而非最短路", ["半程折返＋双向四倍惩罚，把 A→B 变成 A→B→A；", "3 / 5 / 10 km 三档、偏好可调。"]),
        ("03 可复现", ["原始数据不入库，45 MB 派生表＋全部脚本", "本机重建，参数集中在 config.py。"]),
        ("04 边界写明", ["代理性质、误差方向、失效维度都写进字典，", "能直说「这一维暂时不可信」。"]),
    ]
    pos = [(M, 196), (M + 588, 196), (M, 348), (M + 588, 348)]
    for (head, body), (x, y) in zip(cards, pos):
        with p.group(f"card-{head[:2]}", x, y, 564, 132) as g:
            g.rect(x, y, 564, 128, SEC_BG)
            g.rect(x, y, 4, 128, PRIMARY)
            g.text(x + 22, y + 36, 13, PRIMARY, 700, 1.0, [head])
            g.text(x + 22, y + 64, 17, INK, 400, 1.5, body)
    with p.group("closing-band", M, 512, 1152, 108) as g:
        g.rect(M, 512, 1152, 108, PRIMARY)
        g.text(M + 26, 548, 20, "#FFFFFF", 700, 1.0, ["预期成果：一份可复算的数据产品（9.1 万段 × 27 字段）、一套路线算法、一个可演示的原型"])
        g.text(M + 26, 586, 15, "#D6E6DE", 400, 1.0, ["下一步：补理论文献 · 接实时路况提示层 · 把空气做成赛事月份提示"])
    p.foot()


def p13(p: Page):
    p.rect(0, 0, W, H, PRIMARY, role="background")
    with p.group("thanks", 120, 220, 1040, 300) as g:
        g.text(640, 320, 72, "#FFFFFF", 700, 1.1, ["谢谢"], anchor="middle")
        g.text(640, 396, 22, "#D6E6DE", 400, 1.3, ["欢迎提问与指正"], anchor="middle")
    with p.group("thanks-foot", 120, 560, 1040, 90) as g:
        g.line(520, 560, 760, 560, "#D6E6DE", 1)
        g.text(640, 596, 15, "#D6E6DE", 400, 1.4, ["城市慢跑 / 慢骑环境适宜性评价与路线推荐 · 以武汉为例"], anchor="middle")
        g.text(640, 626, 13, "#9FC0B2", 400, 1.2,
               ["数据：OSM · SRTM · ESA WorldCover · 高德 POI · CHAP 1 km 再分析"], anchor="middle")


PAGES = {1: p01, 2: p02, 3: p03, 4: p04, 5: p05, 6: p06, 7: p07,
         8: p08, 9: p09, 10: p10, 11: p11, 12: p12, 13: p13}


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    want = [int(a) for a in argv[1:]] if len(argv) > 1 else sorted(PAGES)
    for n in want:
        fn = PAGES[n]
        p = Page(n, "cover" if n == 1 else ("ending" if n == 13 else "content"))
        fn(p)
        name = f"{n:02d}_{fn.__name__}.svg"
        (OUT / name).write_text(p.svg(), encoding="utf-8")
        print(f"{name}")


if __name__ == "__main__":
    main(sys.argv)

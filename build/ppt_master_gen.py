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
TOTAL = 13
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

    def head(self, kicker: str, title_lines: list[str]):
        with self.group("header", M - 2, 26, W - 2 * M + 4, 150) as g:
            g.text_raw(M, 46, 15, PRIMARY, 600, 1.0, [kicker])
            ty = 96
            g.text_raw(M, ty, 38, INK, 700, 1.24, title_lines)
            rule_y = ty + 1.24 * 38 * (len(title_lines) - 1) + 0.86 * 38 + 26
            g.line(M, rule_y, W - M, rule_y, LINE, 1)
        return rule_y

    def foot(self):
        with self.group("footer", M - 2, 654, W - 2 * M + 4, 52) as g:
            g.line(M, 660, W - M, 660, LINE, 1)
            g.text_raw(M, 686, 13, SUB, 400, 1.2, [FOOT])
            g.text_raw(W - M, 686, 13, SUB, 400, 1.2, [f"{self.num:02d} / {TOTAL}"], anchor="end")

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
        if not lines:
            return self
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


def _wrap(s: str, n: int) -> list[str]:
    return [s[i:i + n] for i in range(0, len(s), n)]


# ---------------------------------------------------------------- pages
def p01(p: Page):
    p.image("city_map.png", 640, 0, 640, 720, "slice")
    p.rect(636, 0, 4, 720, PRIMARY)
    with p.group("cover-text", 80, 80, 520, 560) as g:
        g.text(88, 120, 15, PRIMARY, 600, 1.0, ["城市空间分析 · 课程项目展示"])
        g.text(88, 186, 38, INK, 700, 1.34, ["城市慢跑 / 慢骑环境的量化评价", "与路线推荐系统"])
        g.text(88, 316, 26, INK, 400, 1.3, ["——以武汉为例"])
        g.rect(88, 372, 120, 3, PRIMARY)
        g.text(88, 424, 17, SUB, 400, 1.2, ["9.1 万段路网 · 4.7 万公里 · 六维评分 · 一次点击生成闭环"])
        g.text(88, 540, 15, SUB, 400, 1.9, ["汇报小组 G7", "2026 年 11 月"])


def p02(p: Page):
    p.head("01 · 研究背景", ["尝试回答慢跑 / 慢骑时「该走哪里」的问题"])
    facts = [
        ("01", "跑步出行的路线选择缺少可量化的依据",
         ["跑步门槛最低，但路线选得好不好直接影响体验；", "目前主要靠口碑、朋友圈和偶然发现。"]),
        ("02", "可用场地的供给已经比较充足",
         ["绿道、滨江步道与环湖路近年大量建成；", "但信息散落在推文、评论和本地人的记忆里。"]),
        ("03", "现有的路线工具不提供环境评价",
         ["主流 App 的「路线」是轨迹热力图加手动收藏；", "不解释、不可定制，也不考虑坡度、暴露与过街。"]),
    ]
    y = 244
    for no, head, body in facts:
        with p.group(f"fact-{no}", M, y - 30, 620, 106) as g:
            g.text(M, y + 8, 26, "#C9DDD3", 700, 1.0, [no])
            g.text(M + 46, y, 20, INK, 700, 1.0, [head])
            g.text(M + 46, y + 34, 17, INK, 400, 1.6, body)
        y += 124
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
    p.head("02 · 系统介绍", ["把环境的量化评价拆成三个可计算的问题"])
    qs = [
        ("Q1", "量化", "为每段路计算 0–100 分",
         ["六维指标加显式权重；每一维都", "能回溯到一条公式和一个数据源。"]),
        ("Q2", "组织", "把高分路段组织成可跑完的闭环",
         ["半程折返选折点；回程对去程边", "双向加价，避免原路折返。"]),
        ("Q3", "解释", "让每个分数都能被拆解和复核",
         ["逐维拆解、偏好可调、敏感性", "可复算，出现偏差时能定位原因。"]),
    ]
    x = M
    for no, tag, q, a in qs:
        with p.group(f"q-{no}", x, 186, 368, 112) as g:
            g.rect(x, 186, 3, 106, LINE)
            g.text(x + 18, 204, 13, PRIMARY, 700, 1.0, [no])
            g.text(x + 56, 204, 13, PRIMARY, 600, 1.0, [tag])
            g.text(x + 18, 236, 20, INK, 700, 1.2, _wrap(q, 17))
            g.text(x + 18, 282, 13, SUB, 400, 1.4, a)
        x += 392
    with p.group("modes-figure", M, 308, 1152, 330) as g:
        g.image_at("route_modes.png", M, 308, 1152, 330, "meet")
    p.foot()


def p04(p: Page):
    p.head("03 · 数据与来源", ["使用五类公开数据，拼成一张可计算的空间底图"])
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
            "避免在经纬度上直接用平面公式。原始文件不入库，只保留派生表与全部脚本。"])
    p.foot()


def p05(p: Page):
    p.head("04 · 系统架构", ["四个层次，依赖只向下"])
    with p.group("uml", M, 186, 1152, 432) as g:
        g.image_at("uml_arch.png", M, 186, 1152, 432, "meet")
    p.note("arch-note", 640, ["分层只为一件事：换前端不动算法（GeoJSON 是唯一契约），换算法不动前端（/api/loops 签名不变），换数据不用改代码（重跑管线、重启即生效）。"])
    p.foot()


def p06(p: Page):
    p.head("05 · 系统设计", ["三次操作得到一条可解释的环线"])
    with p.group("prototype", 520, 186, 696, 436) as g:
        g.rect(520, 186, 696, 436, SEC_BG)
        g.image_at("ui_prototype.png", 528, 194, 680, 420, "meet")
    blocks = [
        ("第一步 · 定起点", ["搜索或在地图上点选；", "可选 3 / 5 / 10 km 目标距离。"]),
        ("第二步 · 说偏好", ["绿荫滨水、避开主干道、", "尽量平坦、洗手间补给四个开关。"]),
        ("第三步 · 读结果", ["总分 78.5 与六项实测指标，", "三条子分条说明分数从哪来。"]),
    ]
    y = 210
    for head, body in blocks:
        with p.group(f"step-{head[:2]}", M, y - 26, 420, 116) as g:
            g.text(M, y - 4, 19, PRIMARY, 700, 1.0, [head])
            g.text(M, y + 32, 16, INK, 400, 1.6, body)
        y += 132
    p.note("ui-note", 640, ["界面为高保真原型：地图全宽铺底，两个侧栏用非圆角玻璃质感浮在上面，不遮挡路线。"])
    p.foot()


def p07(p: Page):
    p.head("06 · GIS 处理", ["一条顺序轴：从 12 GB 原始数据到 27 字段评分表"])
    with p.group("axis", M, 210, 1152, 40) as g:
        g.line(M + 30, 230, 1216 - 34, 230, "#CBD9D1", 2)
        x = M + 56
        for i in range(6):
            g.rect(x - 14, 216, 28, 28, PRIMARY)
            g.text(x, 236, 14, "#FFFFFF", 700, 1.0, [str(i + 1)], anchor="middle")
            x += 210

    stages = [
        ("采集", ["OSM / SRTM / WorldCover", "POI / CHAP 再分析"], "12 GB 原始"),
        ("统一", ["去重、字段对齐", "投影 EPSG:32650"], "91,203 段 × 24 字段"),
        ("取指标", ["坡度 σ=150 m 平滑", "树冠 120 m 窗口"], "每段一条记录"),
        ("归一化", ["每维单调变换", "方向统一为越高越好"], "6 个 0–100 子分"),
        ("加权", ["权重合计 0.95", "按 40/55/70/85 分档"], "score + grade"),
        ("落表", ["写回 GeoPackage", "管线一键复跑"], "27 字段 / 45 MB"),
    ]
    x = M + 56
    for name, body, out in stages:
        with p.group(f"stage-{name}", x - 100, 256, 200, 216) as g:
            g.text(x - 88, 288, 18, INK, 700, 1.0, [name])
            g.text(x - 88, 330, 12, SUB, 400, 1.5, body)
            g.text(x - 88, 438, 14, PRIMARY, 700, 1.0, [out])
        x += 210

    p.note("pit-note", 500, ["三处必须处理的坑：栅格按 bbox 1:1 合成（否则后一幅覆盖前一幅）· 坡度先做 σ=150 m 平滑（否则城区中位坡度虚高到 2.66%）· 全部先投影到 EPSG:32650（否则长度系统性偏短）。"])
    p.foot()


def p08(p: Page):
    p.head("07 · 评价算法", ["六个维度，每一维一条公式"])
    rows = [
        ("安全", "0.25", "与机动车同行的风险"),
        ("绿化", "0.25", "遮阴与绿地接触感"),
        ("坡度", "0.20", "体力负担"),
        ("过街", "0.10", "节奏被打断的频率"),
        ("空气", "0.10", "呼吸环境的区域质量"),
        ("设施", "0.05", "补给与休整的便利"),
    ]
    with p.group("weight-table", M, 190, 664, 274) as g:
        g.rect(M, 190, 664, 34, PRIMARY)
        for cx, h in [(M + 12, "维度"), (M + 92, "权重"), (M + 240, "这个维度在衡量什么")]:
            g.text(cx, 213, 14, "#FFFFFF", 600, 1.0, [h])
        y = 224
        for i, (a, b, c) in enumerate(rows):
            if i % 2 == 1:
                g.rect(M, y, 664, 40, SEC_BG)
            g.text(M + 12, y + 27, 17, INK, 700, 1.0, [a])
            g.text(M + 92, y + 27, 17, PRIMARY, 700, 1.0, [b])
            g.text(M + 240, y + 27, 14.5, INK, 400, 1.0, [c])
            y += 40

    subs = [("绿化子分", "f_green", 330), ("空气子分", "f_air", 350), ("坡度子分", "f_slope", 330)]
    y = 190
    for lab, img, hgt in subs:
        with p.group(f"sub-{lab[:2]}", 752, y, 464, 92) as g:
            g.text(768, y + 18, 12.5, SUB, 400, 1.0, [lab])
            g.image_at(f"{img}.png", 768, y + 26, 428, 58, "meet")
        y += 92

    with p.group("score-row", M, 486, 1152, 112) as g:
        g.rect(M, 486, 1152, 112, SEC_BG)
        g.image_at("f_score.png", M + 24, 504, 320, 76, "meet")
        g.text(M + 380, 512, 12.5, SUB, 400, 1.0, ["总分与分级"])
        g.text(M + 380, 544, 15, INK, 400, 1.55,
               ["先各维归一化到 0–100，再按权重求和；", "按 40 / 55 / 70 / 85 分五档，权重合计 0.95。"])
    p.note("lit-08", 616,
           ["文献：指标分层参照刘信知、孙帅（2025）；绿化用卫星覆盖率而非街景绿视率，两者相关 r = 0.617（高时雨、骆杰轩，2026），是本维度已知局限。"])
    p.foot()


def p09(p: Page):
    p.head("08 · 调参与检验", ["权重的三轮调整，16 组敏感性检验"])
    rounds = [
        ("权重初值", ["按「最影响体感」排序给初值：",
                          "安全 0.30 / 绿化 0.25 / 坡度 0.20", "过街 0.10 / 设施 0.10"]),
        ("阈值依据", ["每一维都挂到一个公开阈值上：",
                          "NO₂ 取 WHO 年均 10 与国标 40 作满分与零分；",
                          "坡度以 10% 记为极陡；设施按 500 m 衰减。"]),
        ("修正后的权重", ["设施中位只有 3 分，且与空气负相关 −0.66；",
                             "设施降到 0.05，省下的 0.05 给空气，", "安全由 0.30 降到 0.25。"]),
    ]
    y = 202
    for head, body in rounds:
        with p.group(f"round-{head[:3]}", M, y - 26, 700, 116) as g:
            g.text(M, y, 19, INK, 700, 1.0, [head])
            g.text(M, y + 32, 14.5, SUB, 400, 1.55, body)
        y += 118

    with p.group("result-table", 800, 190, 416, 250) as g:
        g.rect(800, 190, 416, 30, PRIMARY)
        g.text(816, 210, 12.5, "#FFFFFF", 600, 1.0, ["指标"])
        g.text(1006, 210, 12.5, "#FFFFFF", 600, 1.0, ["调整前"])
        g.text(1106, 210, 12.5, "#FFFFFF", 600, 1.0, ["调整后"])
        data = [("综合分中位", "51.7", "54.0"),
                ("空气子分中位", "—", "54.0"),
                ("设施权重", "0.10", "0.05"),
                ("单维敏感性", "0.9954", "0.9940"),
                ("等权 1/6", "0.8894", "0.8887")]
        y2 = 220
        for i, (a, b, c) in enumerate(data):
            if i % 2 == 1:
                g.rect(800, y2, 416, 44, SEC_BG)
            g.text(816, y2 + 28, 13, SUB, 400, 1.0, [a])
            g.text(1006, y2 + 28, 13, SUB, 400, 1.0, [b])
            g.text(1106, y2 + 28, 13, PRIMARY, 700, 1.0, [c])
            y2 += 44

    with p.group("check-caption", 800, 456, 416, 40) as g:
        g.text(800, 480, 12.5, SUB, 400, 1.0, ["16 组 = 6 维 × ±20% 单维扰动 + 4 组整组替换"])
    p.note("tune-note", 548, ["结论：±20% 的权重扰动下路段排序几乎不变（Spearman ≥ 0.994）；真正决定分数的是每个维度有没有区分度——先修维度，再调权重。"])
    p.note("lit-09", 600,
           ["文献：定权思路参照吉实（2025）的 AHP + 专家咨询；本文未做一致性检验，用 16 组敏感性检验替代。"])
    p.foot()


def p10(p: Page):
    p.head("09 · 路线生成", ["评分变成边的代价，最短路再拼成闭环"])
    steps = [
        ("1", "每段路有分", "评分表里每段自带 score 与三维偏好子分。"),
        ("2", "分变成代价", "低分路段加价，最差放大到 3.5 倍；回程再乘 4。"),
        ("3", "最短路拼环", "半程折返取折点，去程与回程各跑一次 Dijkstra。"),
    ]
    y = 212
    for sym, head, body in steps:
        with p.group(f"flow-{sym}", M, y - 24, 640, 96) as g:
            g.rect(M, y - 14, 26, 26, PRIMARY)
            g.text(M + 13, y + 5, 13, "#FFFFFF", 700, 1.0, [sym], anchor="middle")
            g.text(M + 44, y, 18, INK, 700, 1.0, [head])
            g.text(M + 44, y + 30, 14, SUB, 400, 1.4, [body])
        y += 96
    with p.group("cost-box", M, 502, 640, 96) as g:
        g.rect(M, 502, 640, 96, SEC_BG)
        g.text(M + 20, 524, 12.5, SUB, 400, 1.0, ["边代价"])
        g.image_at("f_cost.png", M + 20, 536, 290, 52, "meet")
        g.text(M + 330, 538, 13, SUB, 400, 1.5, ["d 为段长，p 为偏好子分；", "回程再乘 RETRACE_PENALTY = 4.0"])

    modes = [
        ("环线 5 km", "5.34 km · 78.5 分", "回到起点，适合日常"),
        ("单行线 10 km", "10.35 km · 74.6 分", "A→B 不回头，适合通勤"),
        ("马拉松 42 km", "41.72 km · 63.5 分", "长距离闭环，含暴露剂量"),
    ]
    y = 202
    for name, num, use in modes:
        with p.group(f"mode-{name[:2]}", 744, y, 472, 104) as g:
            g.rect(744, y, 4, 92, PRIMARY)
            g.text(768, y + 24, 17, INK, 700, 1.0, [name])
            g.text(768, y + 56, 15, PRIMARY, 700, 1.0, [num])
            g.text(768, y + 80, 12.5, SUB, 400, 1.0, [use])
        y += 116
    p.note("route-note", 610, ["同一副图、同一套代价函数，只换折点与终点规则就得到三种模式；42.195 km 不需要另写算法。"])
    p.foot()


def p11(p: Page):
    p.head("10 · 空间结论", ["武汉哪里最适合跑步：50 个起点的环线计算结果"])
    with p.group("hotspot-map", M, 178, 780, 444) as g:
        g.image_at("hotspots.png", M, 178, 780, 440, "meet")
    p.note("hotspot-note", 640, ["计算口径：50 个起点 × 目标 5 km，每点取前三条环线的平均分（34–74 分）"])
    finds = [
        ("东湖—沙湖—南湖一带最高", ["前三条环线平均 70–74 分，为全市最高一档。"]),
        ("汉口西部与北部最低", ["同口径只有 34–41 分，缺连续绿道与滨水空间。"]),
        ("汉阳墨水湖、青山居中上", ["69 分上下，可作为次一级候选。"]),
        ("起点位置比路线更决定分数", ["起点移动 2 km，分数差 30 分；", "同一区域换路线只差 5 分。"]),
    ]
    y = 210
    for head, body in finds:
        with p.group(f"find-{head[:2]}", 872, y - 30, 344, 104) as g:
            g.rect(872, y - 22, 3, 70, PRIMARY)
            g.text(892, y, 17, INK, 700, 1.2, _wrap(head, 16))
            g.text(892, y + 50, 13, SUB, 400, 1.35, body)
        y += 108
    p.foot()


def p12(p: Page):
    p.head("11 · 创新点与预期成果", ["三个算法创新与两项可交付的结论"])
    with p.group("innov-title", M, 180, 700, 30) as g:
        g.text(M, 206, 13, PRIMARY, 600, 1.0, ["算法创新"])
    innov = [
        ("01", "六维评价算法",
         "六个维度、六条公式、六个数据源，逐段都能回溯。"),
        ("02", "环线生成算法",
         "半程折返选折点，回程对去程边双向四倍加价，把单程最短路转成闭环。"),
        ("03", "马拉松路线推荐算法",
         "同一套折返框架把目标距离扩到 42.195 km，并给出里程加权暴露剂量。"),
    ]
    y = 240
    for no, head, body in innov:
        with p.group(f"innov-{no}", M, y - 26, 700, 112) as g:
            g.text(M, y, 13, ACC2, 700, 1.0, [no])
            g.text(M + 34, y, 20, INK, 700, 1.0, [head])
            g.text(M + 34, y + 34, 15, SUB, 400, 1.5, _wrap(body, 33))
        y += 112
    with p.group("outcome-block", 796, 186, 420, 348) as g:
        g.rect(796, 186, 420, 348, SEC_BG)
        g.text(816, 212, 13, PRIMARY, 600, 1.0, ["预期成果"])
        g.text(816, 248, 17, INK, 700, 1.2, ["一、路线选择的普适规则"])
        g.text(816, 300, 13, SUB, 400, 1.5,
               ["起点位置的影响（差 30 分）远大于", "路线微调（差 5 分）；先选城区，", "再选路线。"])
        g.text(816, 392, 17, INK, 700, 1.2, ["二、武汉的跑步热点分布"])
        g.text(816, 444, 13, SUB, 400, 1.5,
               ["50 个起点 × 5 km 环线的实算结果：", "东湖—沙湖—南湖优先，汉口西部", "与北部不推荐。"])
    p.note("next-step", 566, ["下一步：把 50 个起点扩到全市网格 · 接实时路况提示层（只做提示，不进评分）· 设施维度升级为 2SFCA"])
    p.note("lit-12", 616,
           ["方法出处：2SFCA 见 Luo & Wang (2003)，作为设施维度的升级路径；回程加价属惩罚式替代路径一族，见 Abraham et al. (2013)。"])
    p.foot()


def p13(p: Page):
    p.rect(0, 0, W, H, "#FFFFFF", role="background")
    with p.group("thanks", 120, 210, 1040, 300) as g:
        g.text(640, 330, 72, PRIMARY, 700, 1.1, ["谢谢"], anchor="middle")
        g.text(640, 406, 22, ACC2, 400, 1.3, ["欢迎提问与指正"], anchor="middle")
    with p.group("thanks-foot", 120, 556, 1040, 96) as g:
        g.line(540, 566, 740, 566, "#CBD9D1", 1)
        g.text(640, 602, 15, SUB, 400, 1.4, ["城市慢跑 / 慢骑环境适宜性评价与路线推荐 · 以武汉为例"], anchor="middle")
        g.text(640, 632, 13, SUB, 400, 1.2,
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

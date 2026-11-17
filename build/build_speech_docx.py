# -*- coding: utf-8 -*-
"""Build the continuous speech DOCX from the presentation script."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "G7汇报讲稿-连贯版.docx"

INK = RGBColor(0x1A, 0x1A, 0x1A)
GREEN = RGBColor(0x1F, 0x4E, 0x3D)
ACCENT = RGBColor(0x2E, 0x6B, 0x52)
GRAY = RGBColor(0x6B, 0x72, 0x80)
LIGHT = RGBColor(0x8A, 0x94, 0x8E)

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
KAI_FONT = "楷体"

BLOCKS: list[tuple[str, str]] = [
    ("h1", "一、开场"),
    ("cue", "【P1 · 封面】"),
    (
        "p",
        "各位老师、同学，大家好。我们是 G7，今天汇报的题目是《城市慢跑 / 慢骑环境的量化评价与路线推荐系统》，落地在武汉。",
    ),
    (
        "p",
        "先用一句话概括：我们给武汉 **9.1 万段道路**各打一个 0 到 100 的适宜性分，再把其中得分高的路段拼成一条能跑回起点的闭环。今天重点讲三件事：这个分是怎么来的，路线是怎么拼出来的，以及我们怎么知道自己没有调错。",
    ),
    ("h1", "二、为什么做"),
    ("cue", "【P2 · 项目背景】"),
    (
        "p",
        "为什么做这件事？同样跑 5 公里，沿江滩跑和沿主干道跑，噪声、尾气、坡度、人车冲突完全是两回事；但在普通地图上，这两段路看起来一模一样。",
    ),
    (
        "p",
        "我们当时看到三个事实。第一，**跑步路线的选择缺少可量化的依据**，主要靠口碑、朋友圈和偶然发现。第二，**场地供给其实不缺**，绿道、滨江步道、环湖路这几年建了很多，缺的是把信息组织起来的人。第三，**现有路线工具不提供环境评价**，主流 App 的路线基本是轨迹热力图加手动收藏，不解释、不可定制，也不考虑坡度、暴露和过街。",
    ),
    (
        "p",
        "所以我们想做的，是把“这条路适不适合跑”从经验问题，变成**可计算、可解释**的问题。这里也先说一句取舍：我们**没有做用户轨迹挖掘**。没有真实轨迹数据，硬做也不可信；我们做的是环境侧的评价，把人的体验拆成可获取的环境指标。",
    ),
    ("h1", "三、三个问题"),
    ("cue", "【P3 · 系统介绍】"),
    (
        "p",
        "具体拆成三个可计算的问题。第一是**量化**：每段路给 0 到 100 分，六个维度加显式权重，每一维都能回溯到一条公式和一个数据源。第二是**组织**：把高分路段组织成能跑完的闭环，半程折返选折点，回程对去程边双向加价，避免原路折返。第三是**解释**：逐维拆解、偏好可调、敏感性可复算，出现偏差时能定位原因。",
    ),
    (
        "p",
        "这三件事最后落在同一副路网的两种输出上：5 公里环线 **78.5 分**，10 公里单行线 **74.6 分**。用的是同一套代价函数，只换选点规则。",
    ),
    ("h1", "四、数据"),
    ("cue", "【P4 · 数据与来源】"),
    (
        "p",
        "先看数据。我们用了五类数据：OSM 路网，**91,203 段、47,051 公里**；SRTM 30 米地形算坡度；ESA WorldCover 10 米地表覆盖算树冠；高德运动场馆 POI，**5,137 个里用了 4,081 个**；CHAP 1 公里再分析网格，给到逐段 NO₂ 和 PM2.5。",
    ),
    (
        "p",
        "右边四个数字是我们的态度：**12.4 GB 原始数据不入库，只留 44.7 MB 派生表**；**91,203 段参与评分**；**人工标注为零**——这张表里没有一个分是手填的。",
    ),
    (
        "p",
        "数据契约一句话：存储和交换统一 WGS84，但长度和坡度**先投影到 EPSG:32650 再算**。在武汉这个纬度，一度经度大约只有 96 公里，直接拿经纬度当平面算，东西向会系统性偏短。",
    ),
    (
        "p",
        "这里还有一个后来才想明白的点：**数据源不是越多越好，是要能落到每一段上。** 武汉的空气质量监测站只有 10 个，3 公里缓冲只覆盖 12.7% 的路段，做不出逐段值，所以空气用 CHAP 1 公里网格；街景 API 拿不到，所以绿化用 10 米地表覆盖。每个选择都是被数据可得性逼出来的，不是随便挑的。",
    ),
    ("h1", "五、系统架构"),
    ("cue", "【P5 · 系统架构｜指架构图】"),
    (
        "p",
        "这一页我不念组件名，讲**为什么这么分层**。项目有四个硬需求：前端要地图交互、参数面板、结果解释，而且地图 SDK 将来可能换；单次请求要在 **1.3 秒左右**算完 **979,351 个节点**；**12.4 GB 原始数据不能进部署包**；评分口径会反复改，不能每改一次就动前端。",
    ),
    (
        "p",
        "对应的就是分层架构，四层，依赖只向下。",
    ),
    (
        "p",
        "**表现层**是独立前端工程，Vue 3.5 加 TypeScript 加 Vite，三个组件：MapView 管路段配色和环线叠加，ControlPanel 管起点、距离和四个偏好开关，ResultPanel 管总分、六项指标和子分条。它**只走 REST/JSON，不直连数据文件**。这样换地图 SDK、换 UI，都不动算法。",
    ),
    (
        "p",
        "**接口层**是 FastAPI，四个 Controller：loops、segments、facilities、meta。Pydantic 做参数校验，CORS 和 Swagger 是框架自带的，服务无状态。**POST /api/loops 这个请求体，是前后端之间最核心的契约。**",
    ),
    (
        "p",
        "**算法层**是整个系统的算法内核。RouteService 负责折点、去程、回程、筛选，ScoringService 负责偏好子分和代价矩阵，这两个是纯函数，输入图和参数、输出节点序列，**不碰 HTTP，不做文件 I/O**；GraphService 负责建图和最近节点吸附，是唯一读一次图缓存的入口。这样核心逻辑能单测，也能把 Dijkstra 换成 A* 而不影响接口层。",
    ),
    (
        "p",
        "**数据层**是只读文件：segments.gpkg 91,203 段乘 27 字段、segment_air.csv、run_graph.npz 37 MB。原始 12 GB 不入库，派生表 45 MB 可部署；重跑管线、重启服务就生效。",
    ),
    (
        "p",
        "这个结构也有代价：**没有数据库，不能并发写；没有微服务，是单进程。** 但我们的负载是只读、离线重算，课程项目这个规模，这个取舍是合适的。",
    ),
    (
        "p",
        "还要如实说明当前状态：**后端五个端点已经跑通，前端完整交互页还是骨架，答辩演示用高保真原型。** 架构图是目标结构，不是全部完工的截图。",
    ),
    ("h1", "六、偏好与权重"),
    ("cue", "【P6 · 系统设计｜指原型】"),
    (
        "p",
        "界面上的操作就三步：定起点、选偏好、读结果。但这一页有一个很容易被问的问题，我直接回答：**用户自己选的偏好，会不会影响六维评价算法里的权重？** 不会。我们把评价和选路分成了两层。",
    ),
    (
        "p",
        "**第一层是离线评价。** 六个权重 W 是固定写死的：安全 0.25、绿化 0.25、坡度 0.15、过街 0.10、空气 0.15、设施 0.05。用这套 W 给 91,203 段各算一个 score，写进 segments.gpkg。**所有人看到的是同一张底图。**",
    ),
    (
        "p",
        "**第二层是在线选路。** 用户的三个偏好——绿荫、避开主干道、平坦——默认归一化成约 0.39、0.39、0.23，只对 s_green、s_safety、s_slope 三个子分做一次加权，得到偏好子分 p；再把 p 变成代价：c 等于 d 乘以括号，1 加 100 减 p 的差除以 40。",
    ),
    (
        "p",
        "所以偏好改变的是“我愿意为哪种路段多绕一点路”，**不是“这段路本身多少分”**。为什么这么设计？三个理由。一是**可比性**：如果每个人改权重，底图就变了，用户之间、两次运行之间都没法比较。二是**性能**：每次请求重算 9 万段不现实。三是**透明**：六维权重是研究参数，应该由我们负责，不能甩给用户。",
    ),
    (
        "p",
        "第四个开关“洗手间 / 补给”目前还没有进代价，只在界面上保留；这是边界，我们如实标了。所以你看到的 **78.5 是这条路线的偏好匹配分，不是路段六维综合分**；右边三条 84、81、65，才是安全、绿化、坡度的子分。",
    ),
    ("h1", "七、GIS 处理流程"),
    ("cue", "【P7 · GIS 数据处理｜指流水线】"),
    (
        "p",
        "这一页是 GIS 流水线，六段。全部用 **Python** 做：GeoPandas 和 pyogrio 读矢量，rasterio 读栅格，NumPy 和 SciPy 做数组、滤波和空间索引，pandas 落表。没有 ArcGIS 手工步骤，每一步都能单独重跑。我按输入、操作、输出讲。",
    ),
    (
        "p",
        "第一段是**采集**。OSM 用 Geofabrik 湖北 extract；SRTM 1 秒高程 9 幅；WorldCover 10 米瓦片；高德 POI 走接口；CHAP 空气从 Zenodo 下。原始合计 **12.4 GB**。",
    ),
    (
        "p",
        "第二段是**统一**。市界外扩 2 公里保连通；筛 25 类可行道路，去掉 motorway；投影到 EPSG:32650 算 length_m；路段中点落在市界内标 in_boundary；顶点按 1e-6 度去重，连续顶点成边。输出 **91,203 段、47,051 公里**，图是 **979,351 个节点、2,075,761 条有向边**。",
    ),
    (
        "p",
        "第三段是**取指标**，这是最花时间的一段，我挑五个说。坡度，9 幅 3601 乘 3601 的 SRTM 先镶嵌，无效值最近邻补；做 σ 等于 150 米的高斯平滑，大约 4.86 个像元；用 np.gradient 求梯度，经向除以 cell_m 乘 cos（30.5 度）；坡度取梯度模长乘 100，封顶 30%；最后沿路段顶点按相邻半段长度加权平均。输出 slope_mean_pct，**中位 1.19%、p90 3.27%**。为什么一定要平滑？直接逐点差分，城区中位坡度会虚高到 **2.66%**，最大能到 533%——那是建筑和树冠噪声，不是地形。",
    ),
    (
        "p",
        "树冠，4 幅 WorldCover 按 bbox 一比一合成，只取大于 0 的像元；10 米降采样到 20 米；对 tree 类做 6 乘 6 的 uniform_filter，约 120 米窗口，得到覆盖率面；在路段顶点取样，按长度加权。输出 tree_share，**均值 21.7%、中位 13.3%**；武大 44%、磨山 87%，这两个点是我们用来验证镶嵌有没有错的。",
    ),
    (
        "p",
        "空气，CHAP 2024 年均，取路段中点所在 0.01 度网格，uint16 乘 0.1，nodata 是 65535；NO₂ **中位 23.8、范围 12.3 到 31.6**；1,056 段缺失用城市中位补。PM2.5 也算出来了，但全市空间梯度只有 **1.09 倍**，只展示、不进分。",
    ),
    (
        "p",
        "设施，高德 5,137 个，剔除台球、棋牌、游戏、歌舞等室内娱乐，剩 **4,081** 个；投影后做最近邻空间连接，得到 d_fac，**中位 1,760 米**。过街与安全，路口用图顶点度大于等于 3 识别，再以路段中点为圆心、数 200 米内的个数，**中位 6、p90 43**；安全用道路等级查表，再加距主干道 50 米、20 米的阶梯扣分。",
    ),
    (
        "p",
        "第四段是**归一化**，六个公式把原始指标压到 0 到 100，下一页展开。第五段是**加权**，固定 W，score 等于 Σ wᵢsᵢ，按 40、55、70、85 分五档。第六段是**落表**，segments.gpkg **27 字段、44.7 MB**，另有坡度、树冠、空气三张中间表，全部可重跑。表里的原始字段，就是下一页六条公式的输入；六个子分和 score 是输出。",
    ),
    (
        "p",
        "这一段踩过三个坑，也是我们真正花时间的地方。第一，**WorldCover 镶嵌错位**。rasterio 的 boundless=True 返回的是整幅 bbox，不是瓦片局部；按瓦片偏移贴回，后一幅会把前一幅覆盖成 0。症状很好认：武大、磨山这种林地 tree_share 等于 0，远山反而 100%。第二，**SRTM 假坡度**。不平滑就差分，城区中位 2.66%，甚至 5% 到 7%，必须先平滑再求梯度。第三，**高德 QPS 限流**。失败响应不能写进缓存，否则重跑会当成有效结果跳过；后来改成 0.45 秒间隔加指数退避。这三个坑不解决，后面所有分数都不可信。",
    ),
    ("h1", "八、六个公式"),
    ("cue", "【P8 · 六维评价公式｜指公式卡片】"),
    (
        "p",
        "六个公式看着吓人，其实只有**三类函数**。",
    ),
    (
        "p",
        "**第一类，查表加阶梯：安全。** s_safe 等于 clip，括号里是 R(fclass) 减 15 乘指示函数 d 小于 50，再减 10 乘指示函数 d 小于 20，最后夹到 0 到 100。R(fclass) 是一张 8 到 95 的道路等级表：footway 95、residential 70、secondary 32、trunk 10。距主干道小于 50 米再扣 15，小于 20 米再扣 10。为什么用阶梯而不是连续函数？因为暴露不是线性的：离主干道 60 米和 500 米差别不大，但 30 米和 10 米差别很大。",
    ),
    (
        "p",
        "**第二类，线性插值：坡度、过街、空气。** 坡度是 100 乘括号 1 减 i 除以 10；过街是 100 减 7n；空气是 100 乘括号 40 减 NO₂ 的差，再除以 30。共同点是**端点决定一切**，函数本身没有魔法。",
    ),
    (
        "p",
        "**第三类，指数饱和或者衰减：绿化、设施。** 绿化是 0.7 乘 100 乘 1 减 e 的负 2.5S 次方，加 0.3 乘 clip，100 乘 1 减 d 除以 1500；这里的 S 不是单看树冠，是 0.8 乘 tree_share 加 0.2 乘 green_share 的合成荫蔽度。设施是 100 乘 e 的负 d 除以 500 次方，指数上是负的 d 除以 500。绿化用指数，是因为树冠收益会饱和：S 取 20% 时大约 39 分，40% 约 63，60% 约 78，80% 约 86，再往上加得很少。设施用指数，是距离衰减的常规形式。",
    ),
    (
        "p",
        "那这些公式是怎么来的？**不是拟合出来的。** 我们没有人工标注，也没有真实轨迹，做不了监督学习。它是**三步设计**。第一步，**定函数族**：必须单调、有界 0 到 100、端点能解释。第二步，**定端点**：空气的 10 和 40 是公开标准，10 是 WHO 2021 年均指导值，40 是 GB 3095—2012 二级年均；设施 500 米、绿地 1500 米，按 80 米每分钟步行折算，大约是 6 分钟和 19 分钟的服务半径；200 米是 10 公里每小时跑 72 秒；50 米、20 米是路侧暴露缓冲；10% 坡度是跑步经验上限。这里要坦白：**只有空气的端点是公开标准，其他是规划、道路分级或跑步经验的锚点，不是国标。** 第三步，**选最简单的函数**：能用线性就不用指数；绿化用指数，是因为饱和这件事必须表达出来。",
    ),
    (
        "p",
        "所以六个公式不是六套黑箱，是**三种函数加六组端点**。真正需要被质疑的不是函数，是端点；端点我们逐条标了依据和实际分布。",
    ),
    (
        "p",
        "这一页还有一条文献依据：指标分层参照刘信知、孙帅 2025 年的研究，并借用 Pikora 等 2003 年的 functional、safety、aesthetic、destination 四类要素，落成六维。同时坦白一个局限：绿化用的是卫星覆盖率，不是街景绿视率；高时雨、骆杰轩 2026 年在 514 个街区实测，两者相关只有 **r 等于 0.617**——覆盖率高，不等于跑起来绿意足。我们没有街景 API，这是清楚的短板。",
    ),
    ("h1", "九、调参与检验"),
    ("cue", "【P9 · 调参与检验｜指三轮】"),
    (
        "p",
        "这一页讲权重怎么从拍脑袋变成有依据。一共三轮。",
    ),
    (
        "p",
        "**第一轮，定顺序和初值。** 按最影响体感排序：安全 0.30、绿化 0.25、坡度 0.20、过街 0.10、设施 0.10，合计 **0.95**。为什么是 0.95 不是 1.0？这是沿用 v1 的口径，总预算 0.95，所以综合分上限是 95 不是 100；后来加空气，是从安全、坡度、设施各让 0.05，不是把总和改成 1.0。归一化只改变绝对分，不改变排序，敏感性分析也证明排序稳健。",
    ),
    (
        "p",
        "**第二轮，定标尺。** PPT 上写的是“每一维的端点挂到公开标准”。这句话其实说得有点满：真正挂公开标准的只有空气；其他五维挂的是规划参数、道路分级或跑步经验。但每一项我都能说清楚用了什么数据、做了什么计算。",
    ),
    (
        "p",
        "**空气**，用 CHAP 年均 NO₂，10 对应 100，40 对应 0，线性；依据是公开标准，WHO 2021 指导值加 GB 3095—2012 二级；实际数据中位 23.8，范围 12.3 到 31.6。",
    ),
    (
        "p",
        "**坡度**，用 slope_mean_pct，0% 对应 100，10% 对应 0，线性；依据是跑步经验阈值；实际中位 1.19%，p90 3.27%。",
    ),
    (
        "p",
        "**绿化**，用树冠和绿地距离，树冠 0 到 1 指数饱和，1500 米线性归零；依据是规划服务半径加工程参数；树冠中位 13.3%，绿地中位 470 米。",
    ),
    (
        "p",
        "**安全**，用道路等级加 d_main_m，查表 8 到 95，50 米、20 米阶梯扣分；依据是道路分级和暴露缓冲；实际中位 56，p10 是 0，p90 是 90。",
    ),
    (
        "p",
        "**过街**，用 200 米内路口数，0 对应 100，每个扣 7，14 个只剩 2 分、15 个才归零；依据是分布反推；实际中位 6，p75 是 18，p90 是 43。",
    ),
    (
        "p",
        "**设施**，用到最近场馆距离，0 对应 100，500 米对应 37，指数衰减；依据是步行服务半径；实际中位 1,760 米，41.6% 为 0 分。",
    ),
    (
        "p",
        "这张表里，**只有空气挂的是公开标准**；坡度 10%、安全查表和 50 米、20 米、设施 500 米、绿地 1500 米、过街 200 米，都是我们挂上去的工程锚点；过街每多一个扣 7 分，也是从分布反推的——全市中位 6 个、p75 是 18 个，取 14 让最密的 30% 只剩 2 分，15 个才归零，剩下 70% 保留区分度。除了空气，其他都不是国标，是我们的设计选择——这些维度没有现成国标可挂，硬编一个标准反而不可信；但每个选择都能说清理由。",
    ),
    (
        "pk",
        "**第三轮，按数据修正，三个动作。**",
    ),
    (
        "p",
        "**坡度 0.20 降到 0.15。** 中位 **88.1 分**，**42.2%** 的段大于等于 90 分，**76%** 的段坡度小于等于 2%。它几乎人人高分，区分度低，还会把总分整体抬高，所以降权。",
    ),
    (
        "p",
        "**设施 0.10 降到 0.05。** 中位 **3.0 分**，**41.6%** 的段是 0 分，d_fac 中位 1,760 米；而且设施和空气的相关系数是**负 0.663**——中心城设施密但空气差，两个都高权会互相抵消。降权，并明确它是失效维度。",
    ),
    (
        "p",
        "**安全 0.30 降到 0.25。** 安全仍是第一梯队，和绿化并列 0.25，但它的核心是道路等级查表，是代理指标；而且和过街在概念上都指向人车冲突。我们只让 0.05，不动过街。",
    ),
    (
        "p",
        "三处各让 0.05，合计 **0.15 给空气**。最终 0.25、0.25、0.15、0.10、0.05、0.15，还是 0.95。",
    ),
    (
        "p",
        "这里和前面的 GIS、公式两页接上：**GIS 决定每个子分的分布，权重决定这些分布怎么相加。** 这些中位数、零分率，都是那张 91,203 行的表实算出来的。按均值粗算，各维对总分的贡献是：安全约 **13.1 分**、绿化 11.2、坡度 12.6、过街 5.0、空气 8.5、设施 1.1。设施权重 5%，实际只贡献 1 分——这就是它失效的直接证据。",
    ),
    (
        "p",
        "最后做了 **16 组检验**。12 组单维乘 0.8 或 1.2：Spearman 在 **0.9941 到 0.9995** 之间，前 10% 重合 0.926 到 0.976。4 组整组替换：AHP 型 0.9834、舒适优先 0.8995、地形优先 0.8628、全等权 0.8849，全等权的前 10% 重合只有 0.626。结论不是权重随便定，而是：**权重加减 20% 基本不改排序；真正敏感的是维度有没有区分度。** 全等权把失效的设施维度抬到六分之一，排序立刻掉。所以我们的原则是：**先修维度，再调权重。**",
    ),
    (
        "p",
        "这一页也有文献依据：定权思路参照吉实 2025 年的文献、专家咨询、AHP 路线。但要说明，**我们没有真跑 AHP，也没做一致性检验，是用敏感性检验替代的。**",
    ),
    ("h1", "十、路线生成"),
    ("cue", "【P10 · 路线生成】"),
    (
        "p",
        "评分是路段的属性，路线是一串路段的组合。中间这一步，是把分变成代价。三步：每段路有分，分变成代价，最短路拼成环。边代价是 c 等于 d 乘以括号，1 加 100 减 p 的差除以 40。低分路段加价，最差放大到 **3.5 倍**；回程再乘 **4**。",
    ),
    (
        "p",
        "环线的做法：从起点跑一次距离场，取 **0.44 到 0.56 倍**目标距离的节点，按方位角取 8 个方向的折点；去程跑 Dijkstra；把去程用过的边**双向**乘 4；再从折点跑回程 Dijkstra；保留总长 **0.85 到 1.15 倍**目标的候选，去重后按偏好分排序。",
    ),
    (
        "p",
        "这里有个过程值得说：**第一版只惩罚去程方向，结果所有环线都是原路往返**，图上看起来像一条开放的线。因为回程走的是反向边，不受影响。改成双向惩罚才解决。系数我们扫过 2、4、8、12、20：4 倍的时候，候选 13 条、残余原路返回 **4.0%**；8 倍以上残余 4.4%，但候选掉到 9 条，所以取 4。",
    ),
    (
        "p",
        "性能：单次 **1.2 秒**，1 次距离场加 1 次去程加 8 次回程。1 到 42 公里的每个整千米都实跑过，**42 个全部有解**，长度误差负 14.9% 到正 13.2%。",
    ),
    ("h1", "十一、空间结论"),
    ("cue", "【P11 · 空间结论｜指热点图】"),
    (
        "p",
        "有了算法，我们想回答一个具体问题：**武汉哪里最适合跑步？** 口径是 **50 个起点、间距约 3 公里**，每个起点跑 3 条 5 公里环线，取前三条的平均分。分数区间 **41 到 75**。",
    ),
    (
        "p",
        "三条结论。**东湖、沙湖、南湖一带最高**，前三条平均 **68 到 75 分**；**汉阳墨水湖、青山居中上**，69 分上下；汉口西部与北部最低。最重要的一条是：**起点位置比路线更决定分数。** 全市最高和最低差 **30 多分**；相邻 3 公里的起点，中位差 **8 分**；而同一起点换一条环线，只差 **2 到 5 分**。",
    ),
    (
        "p",
        "这条直接变成产品建议：**先选城区，再选路线。** 50 个点是演示规模，不是全市普查；扩成更密的网格只是计算量，单次 1.2 秒，不需要改算法。",
    ),
    ("h1", "十二、创新与边界"),
    ("cue", "【P12 · 创新点与成果】"),
    (
        "p",
        "最后总结创新点。三个算法创新。一是**六维评价**：六个维度、六条公式，每一维都对应一套数据、一个代理性质和误差方向。二是**环线生成**：半程折返选折点，回程对去程边双向四倍加价，把单程最短路转成闭环；它属于惩罚式替代路径这一族方法，Abraham 等 2013。三是**两种模式的统一框架**：同一张图、同一套偏好代价，只换折点与终点规则，就得到环线和单行线；1 到 42 公里任意整千米都能出路线。",
    ),
    (
        "p",
        "两项可交付结论：一是**地点远大于路线**，起点差 30 多分，远大于路线微调的 5 分；二是武汉的跑步热点分布。",
    ),
    (
        "p",
        "方法出处要说清楚：设施维度我们**参考了 2SFCA 的思想，也就是 Luo 和 Wang 2003 年的工作，但这一版没有实现人口加权**，仍是最近距离；2SFCA 是下一步。这个不能含糊。",
    ),
    ("h1", "十三、结束"),
    ("cue", "【P13 · 谢谢】"),
    (
        "p",
        "以上就是我们的工作，欢迎老师和同学提问。",
    ),
]


def set_east_asia(style_or_run, name: str) -> None:
    """Set both the Latin and East Asian font on a style or run."""
    style_or_run.font.name = name
    element = style_or_run.element
    rpr = element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)


def style_font(style, name: str, size: float, bold: bool = False, color=None) -> None:
    set_east_asia(style, name)
    style.font.size = Pt(size)
    style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color


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
    run.font.size = Pt(9)
    run.font.color.rgb = LIGHT
    set_east_asia(run, BODY_FONT)


def add_rich_text(paragraph, text: str) -> None:
    """Add text, turning **...** into bold runs."""
    # Remove the authoring space between a bold Chinese sentence and the
    # following Chinese sentence; it otherwise renders as a visible gap.
    text = re.sub(
        r"(\*\*[^*]*[。！？；：，、]\*\*) (?=\S)",
        r"\1",
        text,
    )
    parts = text.split("**")
    for index, part in enumerate(parts):
        if not part:
            continue
        run = paragraph.add_run(part)
        if index % 2 == 1:
            run.bold = True


def add_body(doc: Document, text: str, keep_with_next: bool = False) -> None:
    paragraph = doc.add_paragraph(style="SpeechBody")
    add_rich_text(paragraph, text)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.keep_with_next = keep_with_next


def add_h1(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph(style="SpeechH1")
    paragraph.add_run(text)
    add_bottom_border(paragraph)


def add_cue(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph(style="SpeechCue")
    paragraph.add_run(text)


def build() -> Path:
    doc = Document()

    # Page setup: A4, generous margins, 1.5 line spacing.
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(3.0)

    styles = doc.styles

    normal = styles["Normal"]
    style_font(normal, BODY_FONT, 12)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.space_before = Pt(0)

    body = styles.add_style("SpeechBody", 1)  # WD_STYLE_TYPE.PARAGRAPH
    body.base_style = normal
    style_font(body, BODY_FONT, 12, color=INK)
    body.paragraph_format.first_line_indent = Pt(24)
    body.paragraph_format.line_spacing = 1.5
    body.paragraph_format.space_before = Pt(0)
    body.paragraph_format.space_after = Pt(6)

    cue = styles.add_style("SpeechCue", 1)
    cue.base_style = normal
    style_font(cue, KAI_FONT, 9, color=GRAY)
    cue.paragraph_format.first_line_indent = Pt(0)
    cue.paragraph_format.space_before = Pt(2)
    cue.paragraph_format.space_after = Pt(6)
    cue.paragraph_format.line_spacing = 1.0
    cue.paragraph_format.keep_with_next = True

    h1 = styles.add_style("SpeechH1", 1)
    h1.base_style = normal
    style_font(h1, HEAD_FONT, 15, bold=True, color=GREEN)
    h1.paragraph_format.first_line_indent = Pt(0)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(8)
    h1.paragraph_format.line_spacing = 1.0
    h1.paragraph_format.keep_with_next = True

    # Cover.
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_before = Pt(90)
    kicker.paragraph_format.space_after = Pt(26)
    run = kicker.add_run("G7 项目组 · 课程汇报")
    run.font.size = Pt(10)
    run.font.color.rgb = ACCENT
    run.bold = True
    set_east_asia(run, HEAD_FONT)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(10)
    run = title.add_run("从「打分」到「跑起来」")
    run.font.size = Pt(28)
    run.bold = True
    run.font.color.rgb = GREEN
    set_east_asia(run, HEAD_FONT)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_before = Pt(0)
    subtitle.paragraph_format.space_after = Pt(26)
    run = subtitle.add_run("城市慢跑 / 慢骑环境适宜性评价与路线推荐")
    run.font.size = Pt(14)
    run.font.color.rgb = GRAY
    set_east_asia(run, KAI_FONT)

    rule = doc.add_paragraph()
    rule.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rule.paragraph_format.space_before = Pt(0)
    rule.paragraph_format.space_after = Pt(22)
    add_bottom_border(rule, color="1F4E3D", size=10)

    cn_chars = sum(
        len(re.findall(r"[\u4e00-\u9fff]", text)) for kind, text in BLOCKS if kind == "p"
    )
    approx_chars = int(round(cn_chars / 100.0) * 100)
    approx_minutes = max(1, int(round(cn_chars / 300.0)))

    meta_lines = [
        "对应 PPT：presentation/G7项目设计-2026113.pptx（13 页）",
        f"正文约 {approx_chars:,} 字 · 正常语速约 {approx_minutes} 分钟",
        "方括号内为翻页与指图提示，不必念出",
    ]
    for line in meta_lines:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(5)
        run = paragraph.add_run(line)
        run.font.size = Pt(10.5)
        run.font.color.rgb = GRAY
        set_east_asia(run, BODY_FONT)

    date = doc.add_paragraph()
    date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date.paragraph_format.space_before = Pt(150)
    run = date.add_run("2026 年 11 月")
    run.font.size = Pt(10.5)
    run.font.color.rgb = LIGHT
    set_east_asia(run, BODY_FONT)

    # New section for the body, with page numbers starting at 1.
    body_section = doc.add_section(WD_SECTION.NEW_PAGE)
    body_section.page_width = Cm(21.0)
    body_section.page_height = Cm(29.7)
    body_section.top_margin = Cm(2.54)
    body_section.bottom_margin = Cm(2.54)
    body_section.left_margin = Cm(3.0)
    body_section.right_margin = Cm(3.0)

    pg_num_type = OxmlElement("w:pgNumType")
    pg_num_type.set(qn("w:start"), "1")
    body_section._sectPr.append(pg_num_type)

    footer = body_section.footer
    footer.is_linked_to_previous = False
    footer_paragraph = footer.paragraphs[0]
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_paragraph.paragraph_format.space_before = Pt(0)
    footer_paragraph.paragraph_format.space_after = Pt(0)
    run = footer_paragraph.add_run("— ")
    run.font.size = Pt(9)
    run.font.color.rgb = LIGHT
    set_east_asia(run, BODY_FONT)
    add_page_field(footer_paragraph)
    run = footer_paragraph.add_run(" —")
    run.font.size = Pt(9)
    run.font.color.rgb = LIGHT
    set_east_asia(run, BODY_FONT)

    # Body.
    for kind, text in BLOCKS:
        if kind == "h1":
            add_h1(doc, text)
        elif kind == "cue":
            add_cue(doc, text)
        elif kind == "pk":
            add_body(doc, text, keep_with_next=True)
        else:
            add_body(doc, text)

    # Document properties.
    doc.core_properties.title = "从「打分」到「跑起来」——城市慢跑 / 慢骑环境适宜性评价与路线推荐"
    doc.core_properties.subject = "G7 项目汇报讲稿（连贯版）"
    doc.core_properties.author = "G7 项目组"
    doc.core_properties.last_modified_by = "G7 项目组"
    doc.core_properties.category = "课程汇报"
    doc.core_properties.keywords = "城市慢跑;六维评价;环线生成;GIS;武汉"
    doc.core_properties.comments = "对应 13 页答辩 PPT 的连贯演讲稿。"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)

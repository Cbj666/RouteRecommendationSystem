# AGENTS.md — AI 协作者上下文

给接手本仓库的 AI Agent（以及人）看的说明。**改代码前先读完**。
最后更新：2026-11-25

---

## 1. 项目是什么

**城市慢跑 / 慢骑环境适宜性评价与路线推荐**（课程项目）。

给定起点和 3/5/10 km 目标距离，在武汉 9.1 万段路网上：
1. 给每段路打 **0–100 适宜性分**（安全 / 绿化 / 坡度 / 过街 / 设施 / 空气六维，权重显式）；
2. 生成两种路线：**闭合环线**（半程折返 + 去程边 4× 双向惩罚）、
   **单行线 A→B**（距离环带选终点、不回头）；
3. 在原型页上展示地图、路线与可解释指标；
4. 用同一套流程扫描 50 个起点，给出「武汉哪里跑起来分数最高」的空间结论。

> **历史**：项目原为「个性化等时圈」（v3.0），选题被占后转向。
> 路网图、最短路、POI 统计等内核仍保留在 `app/graph.py`、`app/isochrone.py`，
> 旧文档归档在 `docs/archive/等时圈版本/`。**不要把新功能写回等时圈文档。**

---

## 2. 环境与命令

```powershell
.\.venv\Scripts\python.exe -V       # Python 3.13.3
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUNBUFFERED='1'
```

脚本可在任意工作目录运行（路径基于 `__file__`）。

**密钥**：高德/百度/天地图/AQICN 的 Key 只从**环境变量**或项目根 `.env` 读取
（环境变量优先），统一入口 `backend/app/secrets.py`。开工前先自检：

```powershell
.\.venv\Scripts\python.exe -m app.secrets check   # 只输出掩码，缺任何一个退出码为 1
```

细则（含 Agent 禁令、泄露处置、错误码对照）见 `docs/过程/密钥与安全.md`。

```powershell
# 数据（一次性；raw 不入库）
.\.venv\Scripts\python.exe backend\scripts\fetch_dem.py            # SRTM 9 幅瓦片
.\.venv\Scripts\python.exe backend\scripts\fetch_amap_sport_poi.py # 高德场馆（有缓存）

# 计算
.\.venv\Scripts\python.exe backend\scripts\build_air_quality_chap.py --year 2024  # 逐段空气（首次下载 ~6 MB×2）
.\.venv\Scripts\python.exe backend\scripts\build_slope.py          # 坡度
.\.venv\Scripts\python.exe backend\scripts\build_canopy.py         # 树冠
.\.venv\Scripts\python.exe backend\scripts\build_running_dataset.py# 六维评分
.\.venv\Scripts\python.exe backend\scripts\plot_running_map.py     # 地图

# 环线
.\.venv\Scripts\python.exe backend\scripts\run_loop_demo.py

# 热点网格（改写评分或路网后重跑，产物给 /api/hotspot 用）
.\.venv\Scripts\python.exe backend\scripts\build_hotspot_grid.py

# HTTP 接口（线上联调走它；底图另有 public/geo 静态兜底）
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

---

## 3. 仓库地图

| 路径 | 作用 | 入库 |
|---|---|---|
| `backend/app/running.py` | **跑步图 + 两种路线生成（当前核心）** | ✅ |
| `backend/app/api.py` | FastAPI 13 路由（图层 + 目录 + 元信息 + 厕所 + 地点搜索 + 环线/单行线 + 热点网格） | ✅ |
| `backend/app/datasets.py` | 四个图层（路段/水绿/场馆/厕所）的内存缓存、bbox 过滤、GeoJSON 序列化 | ✅ |
| `backend/app/segment_tiles.py` | `/api/segments?detail=basic` 的预切网格索引（0.01°）+ 每段预序列化 + LRU（含 gzip 字节）+ ETag | ✅ |
| `backend/app/config.py` | 参数（步速、车速、权重）：唯一"魔法数字"来源 | ✅ |
| `backend/app/paths.py` | 全项目路径定义 | ✅ |
| `backend/app/graph.py` | 多模式交通图（前版，接驳用） | ✅ |
| `backend/app/isochrone.py` | 等时圈内核（前版，保留） | ✅ |
| `backend/scripts/build_slope.py` | SRTM → 路段坡度 | ✅ |
| `backend/scripts/build_canopy.py` | WorldCover → 路段树冠 | ✅ |
| `backend/scripts/build_running_dataset.py` | 六维评分 → `segments.gpkg` | ✅ |
| `backend/scripts/run_loop_demo.py` | 3 起点环线 → GeoJSON + PNG | ✅ |
| `backend/scripts/fetch_amap_sport_poi.py` | 高德场馆抓取（**勿重跑**，有缓存） | ✅ |
| `backend/scripts/fetch_amap_toilet_poi.py` | 高德公厕抓取（2026-11，6,122 个；缓存 `data/cache/amap_toilet/`） | ✅ |
| `backend/scripts/merge_amap_toilet_poi.py` | 公厕合并进 `poi.gpkg`（5,839 个，幂等） | ✅ |
| `backend/scripts/build_air_quality_chap.py` | CHAP 1 km 年均 PM2.5 / NO2 → 逐段空气 | ✅ |
| `backend/scripts/build_air_monthly.py` | CHAP 月网格 → 12 个月曲线 | ✅ |
| `backend/scripts/build_hotspot_grid.py` | 路段 → 全城热点网格（默认 2 km，`data/output/running/v1/hotspot/`，`/api/hotspot` 的数据源） | ✅ |
| `data/processed/v1/` | 基础数据集（路网 / 公交 / 地铁 / POI） | ✅ |
| `data/processed/running/v1/` | 坡度、树冠、场馆、评分（约 45 MB） | ✅ |
| `data/processed/running/graph/` | 跑步图缓存（37 MB） | ❌ 可重建 |
| `data/raw/` | SRTM、WorldCover、OSM、高德缓存（约 12 GB） | ❌ |
| `data/output/running/v1/` | 地图、环线图、GeoJSON | ✅ |
| `frontend/prototype/` | 静态原型 + 截图（旧视觉，已被 reference 取代） | ✅ |
| `frontend/app/` | **Vue 交互页（当前前端交付物）**：两页签（环线推荐 / 热点地图）+ 13 个静态图层 + SVG 底图 + 全城 2 km 热点网格 + 环线/单行线 + 在线地点搜索 + 厕所筛选 + 路段详情 + 移动端；`npm run build` / `scripts/ui-smoke.mjs`。适宜性地图页源码保留但不在页签里露出 | ✅ |
| `frontend/reference/` | 零依赖 SVG 参考实现（视觉真源） | ✅ |
| `docs/` | 三个入口文档（说明书 / 分工卡片 / 交接说明）+ 数据、汇报、过程、literature、archive 五个子目录 | ✅ |
| `presentation/` | 答辩 PPT、原型图、热点图、讲稿、素材（`素材/*.png` 不入库，可重出） | ✅ |
| `build/` | 生成脚本（配图、PPT、文档同步），**只入库 `*.py` 与 `proto/*.html`**，渲染产物不入库 | ✅ |
| `tools/` | 一次性历史脚本，**不要当参考实现** | ✅ |

---

## 4. 数据契约

字段细节见 `docs/数据/数据字典-跑步数据集.md` 与 `docs/数据/数据字典-v1.md`。必记：

| 事实 | 说明 |
|---|---|
| CRS | 全部 **WGS84 (EPSG:4326)**；长度/坡度用 **EPSG:32650** 计算 |
| 评分主表 | `data/processed/running/v1/segments.gpkg` 图层 `segments`，9.1 万行 |
| 评分字段 | `s_safety / s_green / s_slope / s_cross / s_fac / s_air`（0–100）+ `score` + `grade` |
| 原始指标 | `slope_mean_pct`、`tree_share`、`d_main_m`、`cross_200m`、`d_fac_m`、`no2_ugm3`、`pm25_ugm3` |
| 环线输出 | `data/output/running/v1/loops.geojson`，属性含 `rank`、`score`、`sub`(JSON) |
| 场馆 | `data/processed/running/v1/amap_sport_poi.csv`，5,137 个（含 `in_boundary`） |
| 公厕 | `data/processed/running/v1/amap_toilet_poi.csv`，6,122 个；`poi.gpkg` 内 5,839 个（`source_layer="amap_toilet"`） |
| 基础路网 | `data/processed/v1/osm_walk_roads.gpkg` 图层 `walk_roads`，9.1 万段 |
| 热点网格 | `data/output/running/v1/hotspot/grid.json`，1,853 格 / 133 热点（默认 2 km，`build_hotspot_grid.py --cell-lng/--cell-lat` 可调，`/api/hotspot` 原样返回） |

**不要**在新代码里读 `data/interim/`（上游中间表，字段更乱）。

---

## 5. 代码入口

```python
import sys; sys.path.insert(0, "backend")
from app import running

g = running.load_or_build()                    # 979,351 节点 / 2,075,761 边
loops = running.generate_loops(g, 114.3547, 30.5342, target_m=5000,
                               prefs={"green": 1.0, "safe": 1.0, "flat": 0.6})
# 每条：length_m / minutes / score / tree_share / slope_mean_pct / facility_m / sub
fc = running.to_geojson(g, loops)              # FeatureCollection（LineString）
```

图结构：

```text
顶点 = segments.gpkg 里每条路段的首尾顶点（1e-6 度去重）
边   = 相邻顶点，双向，携带该段的 score / tree_share / slope / cross / d_fac
代价 = 距离 × (1 + (100 − 偏好子分) / 40)      # 低分路段最多贵 3.5 倍
```

环线算法（改之前先读 `app/running.py` 的注释）：

1. 距离场取 0.44–0.56×目标 处为候选折点，按方位角取 8 个方向；
2. 去程用偏好代价最短路；
3. 回程把去程边**双向**代价 ×4 后最短路（只惩罚单向会导致原路往返）；
   实测 ×4 与 ×20 的残余原路返回率都是 ~4%，但 ×20 会减少候选数量，故取 ×4；
4. 保留总长 85%–115% 目标的候选，去重后按分排序。

**性能（2026-11-24 改）**：单次环线 0.1–0.5 秒（1–42 km），此前 1.1–2.5 秒。
两处裁剪，正确性靠距离上界保证，不是近似：

- 距离场加 `limit=0.62×目标`（折点带上界），带外节点距离为 `inf`；
- 去程/回程不再跑全图，改在起点欧氏球内的**局部子图**（`_build_local()`）上算，
  半径 `LOOP_RADIUS_RATIO = 0.5 × LENGTH_HIGH × 1.15 ≈ 0.66×目标`。
  依据：合法环线总长 ≤1.15×目标，环上任一点到起点的直线距离不超过总长一半。
  **`LENGTH_HIGH` 与 `LOOP_RADIUS_RATIO` 是绑定关系**，改长度容差必须同步改半径；
- 已知副作用：网络边缘的稀疏区（如 1 km + 城北），某个折点的全图最优回程会绕出
  球外（该环本来就超长、会被丢掉），子图内则会走出一条合法回程，因此**极少数
  情况下路线集合会替换一条**（同区间、分数略低）。2026-11-24 全档位对比：31/31
  组 3/5/10 km 输出逐字节一致。

**视口路段（2026-11-25 改）**：`GET /api/segments?detail=basic` 不再每次走 geopandas
（`clip` + `to_json`），改由 `app/segment_tiles.py` 的 0.01° 网格索引直接拼 JSON 片段，
响应体连同 gzip 字节缓存进 LRU（96 条），并带 `ETag` / 304。实测同一 bbox 第二次请求
12–27 ms（此前 56–642 ms），传输体积约为原来的 1/7。
`detail=basic` 因此只剩 `osm_id/score/grade` 三个字段——需要 `fclass`/`name`/六维/空气时
必须用 `detail=full` 或 `/api/segments/{osm_id}`（`full` 仍走旧路径，行为不变）。
索引按**外包框相交**筛选，比几何相交多极少数贴边段（≤0.2%，画在视野外）。

---

## 6. 评分口径

| 维度 | 权重 | 来源 | 代理性质 |
|---|---:|---|---|
| 安全 | 0.36 | 道路等级 + 距主干道距离 | 无路段车流量 |
| 绿化 | 0.26 | 0.7×WorldCover 树冠 + 0.3×到绿地距离 | 不识别单排行道树 |
| 坡度 | 0.06 | SRTM 30 m 平滑后梯度 | ±1 个百分点 |
| 过街 | 0.15 | 200 m 内路口数 | 只数顶点度 ≥3 |
| 设施 | 0.06 | 到最近设施点的指数衰减；设施 = 高德场馆 4,081 + OSM 配套 5,344 + 高德公厕 5,117 = 14,542 | 只算"到最近点"，不反映沿途密度 |
| 空气 | 0.11 | CHAP 1 km 年均 NO₂，(40−x)/30 | 只做区域校正，圈层内差 0.2–1.8 µg/m³ |

**权重合计 1.00**（v2 口径，2026-11-17 定版，v5 = 上表），所以 `score` 是六维加权平均、满分 100。
分档线：差 <35、一般 35–50、较好 50–65、好 65–80、很好 ≥80（旧 v1 口径合计 0.95、分档 40/55/70/85，
旧 85 线高于全网最高分故"很好"恒为 0；v2 把 std 从 9.9 抬到 12.4，与 v1 秩相关 0.98、前 10% 重合 0.87）。

调权重看效果：`backend/scripts/plot_score_heatmap.py` 用已存 `s_*` 列直接重算综合分并出热力图，
不用重跑 pipeline（数学等价）；候选权重表在 `data/output/running/v1/weights/candidates.json`，
每次运行的指标记在 `data/output/running/v1/weights/iterations.csv`。用法：
`--preset v5 --bins 35,50,65,80`、`--w safety=0.36,...`、`--config candidates.json --preset v1,v5`。

改权重：改 `build_running_dataset.py` 的 `W` 或调用 `generate_loops(prefs=...)`。
**改评分必须重跑** `build_running_dataset.py`，再重跑 `run_loop_demo.py`（图缓存会过期）。

---

## 7. 常见任务

- **换起点 / 距离**：改 `run_loop_demo.py` 的 `ORIGINS` 与 `TARGET_M`。
- **加一个评分维度**：在 `build_running_dataset.py` 算指标 → 加子分 → 调权重 → 更新
  `docs/数据/数据字典-跑步数据集.md`。
- **改环线形状**：调 `generate_loops(max_candidates=)`、折点带宽（0.44–0.56）、
  回程惩罚（4.0）。
- **换城市**：改 `build_canopy.py` / `build_slope.py` 的瓦片清单与 bbox，
  `prepare_dataset.py` 的 `WALKABLE`，其余逻辑通用。
- **重出热点网格**：改评分或路网后跑 `build_hotspot_grid.py`，再 `node frontend/app/scripts/sync-geo.mjs`
  （复制到 `public/geo/hotspot/` 做静态兜底）；前端只经 `/api/hotspot`，不读 `data/`。

---

## 8. 已踩过的坑（不要重复）

1. **WorldCover 拼接错位**：`rasterio` 的 `read(window=from_bounds(bbox), boundless=True)`
   返回的是**整幅 bbox**（瓦片外补 0），不是瓦片局部；按瓦片偏移贴回会让后一幅覆盖前一幅。
   正确做法是按 bbox 1:1 合成，只用 `>0` 的像元。
   症状：林地 `tree_share = 0`、远山 100%。
2. **SRTM 逐点差分会得到假坡度**（城区中位 2.66%）；必须先平滑（σ=150 m）再求梯度。
3. **环线原路往返**：只惩罚去程方向的有向边不够，回程是反向边，必须**双向**惩罚。
4. **高德 QPS 限流**（`CUQPS_HAS_EXCEEDED_THE_LIMIT`）：间隔 0.45 s + 指数退避；
   **失败响应不要写进缓存**，否则重跑会当成有效结果跳过。
5. **pyosmium 打不开中文路径的 PBF**（Windows）：先复制到 ASCII 路径再解析。
6. **CSR 属性对齐**：同一 (u,v) 可能来自多条 OSM way，`csr_matrix` 会合并重复项，
   导致属性数组长度与 `nnz` 不一致。先 `unique` + 按 (row, col) 排序再显式构造 `indptr`。
7. **`distance_m` vs `dist_route_m`**（前版遗留）：前者是直线距离，只能用于展示。
8. **不要重新抓高德**：`data/cache/amap_sport/` 有 500+ 条响应，重跑会耗配额。
9. **中文路径 + PowerShell**：读写文本用 Python + `encoding="utf-8"`；
   `Set-Content` 会按 GBK 重写导致乱码。
10. **GeoDataFrame 拼设施点会丢几何/错位**（2026-11 修）：`poi[["poi_id","name"]]`
    会连 geometry 列一起丢掉（下游 `geometry.notna()` 直接过滤掉整批 OSM 点）；
    `GeoSeries(shapely.points(...))` 用默认 RangeIndex，而 `am` 是过滤后的原索引，
    构造 GeoDataFrame 时索引对不齐 → 828/4,081 个场馆几何变空。
    正确写法：`am.reset_index(drop=True)` + `np.asarray(geom)` + 选择列时带 `"geometry"`。
11. **密钥四处抄**（2026-11 统一）：原先 `amap.py` 解析 `.env`、两个 fetch 脚本各写一份
    正则、`baidu_place.py` 还认 `AK.txt`，同一个 Key 三套优先级。现在一律用
    `backend/app/secrets.py` 的 `require()`（环境变量 > `.env` > `.env.txt`）。
    **不要**再在脚本里 `re.search(r"GAODE_KEY\s*=\s*(\S+)")`，也不要把 Key 拼进日志或异常消息。

---

## 9. 改完怎么自检

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'backend'); from app import running; g=running.load_or_build(); lp=running.generate_loops(g,114.3547,30.5342,5000); print(len(lp), lp[0]['length_m'], round(lp[0]['score'],1))"
```

判据：`length_m` 在 4250–5750 之间，`score` 在 60–90 之间，路线闭合（首尾节点相同）。

改了评分后重跑 `build_running_dataset.py` 与 `run_loop_demo.py`，
并删除 `data/processed/running/graph/` 让图缓存重建。

---

## 10. 文档索引

| 文档 | 读它的场景 |
|---|---|
| `docs/项目交接说明.md` | 全项目到哪一步了 |
| `docs/接口契约.md` | 前后端唯一依据（当前 v1.5：13 路由，含地点搜索、热点网格与视口路段快速通道） |
| `docs/项目说明书.md` | 答辩口径、指标体系、边界 |
| `docs/过程/开发进展-慢跑适宜性与环线.md` | 实现细节、踩过的坑、结果 |
| `docs/数据/数据字典-跑步数据集.md` | 评分/环线字段 |
| `docs/数据/数据补充清单.md` | 数据从哪来、什么补不来 |
| `docs/数据/数据现状与增补建议.md` | 现用数据审计、失效维度、可增补数据与改造公式 |
| `docs/literature/参考文献与算法依据.md` | 五维/环线的文献锚点，写报告与答辩 PPT 前读 |
| `docs/过程/design-guidelines.md` | 做前端页面前 |
| `docs/过程/密钥与安全.md` | 要用高德/百度 Key、或怀疑 Key 泄露时 |
| `docs/分工卡片.md` | 组内分工、交付物与剩余工作 |
| `docs/汇报/答辩稿.md`、`docs/汇报/讲稿.md` | 排练与答辩 |
| `docs/literature/参考文献.md` | 已核对过的引用清单与「不能说什么」 |
| `docs/archive/等时圈版本/` | 旧选题，仅供追溯，**不要引用** |

**改结构或改评分口径时，同步更新本文件与 `docs/项目交接说明.md`。**

## 前端交付补充（2026-11-25）

界面是**两页签**：环线推荐（默认）/ 热点地图。适宜性地图页的源码保留在 `MapStage.vue` / `App.vue` 的 `map` 分支里，但 `TopBar.vue` 不再给入口，需要时可把 `{ key: 'map', label: '适宜性地图' }` 加回 `tabs`。

路线统一用 `/api/routes`，厕所用 `/api/toilets`，在线地点搜索用 `/api/places/search`（高德 Key 只在后端，返回 WGS84），热点网格用 `/api/hotspot`（离线脚本产物，前端不读 `data/`），路段详情由小 bbox 的 `/api/segments?detail=full` 查询。保留静态地图兜底（`public/geo/hotspot/grid.json` 等，由 `sync-geo.mjs` 复制，不入库）。

真实联调用 `VITE_USE_MOCK=0` 与 `UI_REAL=1 node scripts/ui-smoke.mjs`（当前 33/33）；mock 用 `$env:VITE_USE_MOCK='1'` 重启 vite 后 `UI_REAL=0`（当前 36/36）。BMapGL 底图仍未接入，在线搜索在 mock 模式下退化为 4 条内置地点。

拖动与缩放（2026-11-25 改）：单指拖动走 `svgAdapter.beginPan()/panBy()/endPan()`——把 SVG 放大到 160% 并同步放宽 viewBox，拖动期只改 CSS `transform`（合成器搬运、不重光栅化），松手再落成真实 viewBox；`MapStage.clampPan()` 把位移夹在地图范围内。矢量缩放仍改 viewBox。实测 DPR=1 拖动主线程耗时 0.252 → 0.052 s、LayoutCount 60 → 2。

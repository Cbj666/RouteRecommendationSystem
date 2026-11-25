# 前端应用（Vue 3 + TypeScript + Vite）

「跑步友好度 · 武汉」交互页：选起点 → 选目标距离/偏好 → 生成候选环线 → 地图高亮 + 右栏可解释指标；
第二个页签是“热点地图”，用全城 1 km 网格分级展示高分聚集区（离线脚本算好、后端 `/api/hotspot` 提供）。
底图由 **13 个空间图层**组成（水体 / 绿地 / 行政边界 / 三级路网 / 地铁线站 / 公交线站 / 运动场馆 / 公共厕所 / 空气质量站），
统一全城视野（热点页按全市域 bbox 取景），图层可逐个开关；数据检测口径、字段与来源见 [`docs/数据图层清单.md`](docs/数据图层清单.md)。

视觉真源是 [`../reference/index.html`](../reference/index.html) 与 [`../../docs/前端原型规格.md`](../../docs/前端原型规格.md)；
接口字段唯一依据是 [`../../docs/接口契约.md`](../../docs/接口契约.md)（v1.4）。

## 快速开始

```powershell
cd frontend\app
npm install
Copy-Item .env.example .env.local      # 首次；默认 VITE_USE_MOCK=1，无后端也能跑
npm run dev                            # http://127.0.0.1:5173
```

`.env.local`：

```bash
VITE_USE_MOCK=1        # 1=本地 mock（默认）；0=走后端
```

**前端不配置、不读取任何地图厂商的开发者 Key**（高德 / 百度 / 天地图等）。
底图来自构建期 `public/geo` 静态图层；地点搜索只走 `src/api/client.ts` 的
`searchPlaces` → `GET /api/places/search`，Key 由后端持有。

有后端时（仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

再把 `VITE_USE_MOCK` 改成 `0`；`vite.config.ts` 已把 `/api`、`/health` 代理到 8000。
本机若没有系统 Python，可用仓库根目录的 embeddable 环境（已 gitignore）：`.\.python-embed\python.exe -m uvicorn app.api:app --app-dir backend --port 8000`。

## 常用命令

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器（会先 `sync:geo`） |
| `npm run build` | `vue-tsc --noEmit && vite build`（构建前自动 `sync:geo`） |
| `npm run preview -- --host 127.0.0.1 --port 5173 --strictPort` | 预览构建产物；**截图/演示推荐**（无文件监听） |
| `npm run sync:geo` | 从 `data/` 生成 `public/geo/` 下 13 层 geojson + `manifest.json`（幂等，按源文件 mtime 跳过） |
| `node scripts\ui-smoke.mjs` | 无头冒烟：mock 模式 **53 项**断言 + 截图（需先以 `VITE_USE_MOCK=1` build + preview） |
| `$env:UI_REAL='1'; node scripts\ui-smoke.mjs` | 真后端冒烟：额外比对接口分数/耗时（需 `VITE_USE_MOCK=0` 构建 + 后端 8000） |

只运行断言时可设置 `$env:UI_SCREENSHOTS='0'` 跳过截图。

> 不要在 `npm run dev` 运行时用会做「原子写临时目录」的编辑器/工具改 `src`：Vite 的 FSWatcher
> 会对 `*.tmpdir` 报 `EBUSY` 退出。已加 `server.watch.ignored`，但迭代截图仍建议 `build + preview`。

## 目录

```text
src/
  App.vue                画布缩放（桌面 1600×1000；≤900px 单列）+ 全局 ←/→
  components/            TopBar 搜索、LeftPanel 参数、MapStage、RightPanel 结果、
                         LayerPanel 数据图层、LegendBox、FooterBar、StatusOverlay（四态）
  stores/planner.ts      单例 reactive store：起点/距离/偏好/候选/请求竞态 +
                         范围 extent / manifest / 图层开关与懒加载缓存
  map/                   MapAdapter 抽象、SvgAdapter（manifest 驱动 13 图层）、
                         layerConfig（叠放顺序与配色注册表）；不接第三方地图 Key
  lib/                   projection（片区固定 VIEW / 全城 fitView 动态适配）、
                         color（色阶）、format、geo
  api/client.ts          6 个请求封装 + ApiError + mock 路由
  mocks/                 真实响应快照（含 4 组 loops）
  styles/                tokens.css（设计变量）、base.css（画布与移动端文档流）
scripts/
  sync-geo.mjs           空间数据管线：13 层 geojson + manifest（纯 Node 内置）
  ui-smoke.mjs           Edge headless + CDP 冒烟
public/geo/              构建时生成，已 gitignore（源数据在 data/ 与 data/output/...）
docs/数据图层清单.md      数据检测记录：16 个空间文件 / 13 个渲染图层
```

## 已实现

- **数据图层**：`public/geo/manifest.json` 驱动 13 层 SVG（水体 2,034 面 / 绿地 1,552 面 / 行政边界 /
  核心路网 8,005 段 / 干道路网 19,298 段 / 全量路网 90,193 段 / 地铁 18 线 231 站 / 公交 1,124 线 7,823 站 /
  运动场馆 5,137 / 热点 50 / 空气站 19）。默认开启 6 层；面板可逐个开关，数据懒加载并缓存。
- **视口细粒度路网**：滚轮、双指或按钮缩放（1×–128×），放大后拖动平移；视口宽度 ≤30 km 时按量化 bbox 请求
  `/api/segments`（上限 4 万段，LRU 缓存），移出视野即释放；超出时提示"当前范围路段过多，已简化显示"。
- **适宜性地图**：路网按 score 着色（#D94F4F→#15503C），环线白描边 + 黑线，起点与单行线终点标记。点击地图设置起点，点「复位」恢复默认视野。
- **环线推荐**：起点（2 预设 + 在线搜索 + 地图点击）、3/5/10 km、三个路线偏好开关、生成、`‹ 1/3 ›` 与 ←/→ 切换候选。
- **热点地图**：全城 1,853 格（默认 2 km）分级设色，按分数映射到连续色带（五档分界落在色带 0/0.25/0.5/0.75/1，与图例对得上）并做一次高斯模糊，颜色在格间平滑过渡；格子的方框边线单独画一层，保留网格感。左侧 Top20 榜单、右侧六维详情、图例和“以此处为起点”联动。支持**区域筛选**：在图上拖出矩形或圆形，只统计覆盖到的网格并按长度加权重算均分与排名（区域外压暗，`Esc`/清除恢复全城）。热点页不显示设施点位。数据来自 `/api/hotspot`（离线脚本 `backend/scripts/build_hotspot_grid.py` 产物），失败回退 `/geo/hotspot/grid.json`。
- **四态**：加载（顶部 pill + CTA 文案）、无结果（中性提示，不报错）、失败（红框 + HTTP 码）、底图/manifest 失败。
- **可解释面板**：距离/用时/树冠/坡度/场馆/吸附距离 + 安全/绿化/坡度三条子分 + 权重脚注。
- **响应式**：1440×900（整页 0.9 缩放）；宽度不超过 1100 px 或高度不超过 680 px 时改用单列纵向滚动，地图保持 16:10，路线设置与结果在图层面板之前。
- **mock 自测**：`/?mock=empty`、`/?mock=error`、`/?mock=slow`（仅 mock 模式）。

## 当前交付范围（2026-11-25）

- 顶部两页签切换：环线推荐（默认）、热点地图。适宜性地图页源码保留（`App.vue` 的 `map` 分支），但不在页签里露出；起点对比页与片区/全城切换已移除。
- 真后端路线统一调用 `POST /api/routes`，支持环线、自动终点单行线和 1–42 km；单行线显示终点。
- 双起点使用同一组距离与偏好独立请求，支持单侧无结果、失败重试和过期响应丢弃。
- 适宜性地图点击道路，以小 bbox 请求 `/api/segments?detail=full` 后选择最近 40 m 内路段，展示六维子分、原始指标和权重。
- 洗手间通过 `/api/toilets` 加载，可筛选无障碍。该开关只影响点图层。
- 五档图例与返回的 `grade` 一致，当前元信息分界 35 / 50 / 65 / 80。六维评分权重通过 `/api/meta` 展示。
- 地图保留构建期 `public/geo` 静态资产，运行时不直接读仓库 `data/`。更新数据后重新运行 `npm run sync:geo`。
- mock 覆盖两个预设起点的 5 km 环线快照、单行线 A/B 选点与 4 条内置地点搜索；真实服务覆盖厕所筛选、路段详情与高德在线搜索。
- 在线搜索通过 `/api/places/search` 调高德（Key 只在后端，坐标转 WGS84），结果以编号标记同步到地图；空关键词仍显示两个预设地点。地图为 SVG 静态底图，前端不加载任何第三方地图 JS、不持有地图开发者 Key。
- 热点页签读 `/api/hotspot`（全城 1,853 格 / 133 热点，2 km 网格、评分按路段长度加权，v2 分档 35/50/65/80）；mock 模式用 `src/mocks/hotspot.ts` 的 500 格都市区示例。字段与重建步骤见 `docs/过程/热点地图前端实现与交接.md`。

2026-11-25 热点页区域筛选与去设施点后复验：`vue-tsc` 与 `npm run build` 成功，真后端 37/37、mock 40/40（新增热点页无设施点位、矩形区域筛选生效、区域内榜单按分排序、清除恢复全城四条用例，截图 `hotspot-region.png`）。2026-11-25 拖动/缩放与视口路网优化后复验：`vue-tsc` 与 `npm run build` 成功，真后端 33/33、mock 36/36（新增拖动用例：合成器平移松手后 viewBox 已落地、过扫描尺寸清空）。2026-11-25 两页签 + 全城热点改造验收通过：真后端 32/32、mock 35/35（页签顺序、全城 2 km 网格 1,853 格、榜单/详情联动、环线自动生成、地点搜索、390/320 px）。同日更早的合并验收（fixSearch 地点搜索 × main 视口性能 × PR #6 热点地图）：`npm run build` 成功，真后端 38/38、mock 43/43（含环线/单行线两种模式的地点搜索选点、编号标记与选中生成路线，热点页签与 390 px 热点页；起点对比页已在 main 移除，故不再有对比用例）。2026-11-25 早先记录：真后端 32/32、mock 37/37；2026-11-24 记录：真后端 36/36；2026-11-23 记录：真后端 32/32、mock 37/37。检查记录在 `data/output/ui/frontend-delivery/checks.json`（本次）与 `data/output/ui/delivery-real/checks.json`、`delivery-mock/checks.json`。

## 联调验收

```powershell
# 仓库根目录启动后端；没有 .venv 的机器可用本机已有 Python 环境
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
# frontend/app 下启动真后端前端
$env:VITE_USE_MOCK='0'
npm run dev
# 另一终端，frontend/app 下运行
$env:UI_REAL='1'
node scripts/ui-smoke.mjs
```

无后端验收时使用 `VITE_USE_MOCK=1` 启动前端并将 `UI_REAL` 设为 0（同时把 `UI_URL` 指到 mock 实例的端口，否则会打到 5173 的真后端）。脚本覆盖图层开关、两页签、全城热点网格、区域筛选、路线自动生成、单行线 A/B 选点、地点搜索和窄屏。真实服务额外覆盖 42 km、厕所筛选、路段详情与高德在线搜索，mock 额外覆盖加载、空结果和异常（`/?mock=empty|error|slow`）。

可选截图用 `UI_SCREENSHOTS=1`；默认只输出检查记录。mock 路段详情数据按需加载，构建时会提示大于 500 kB 的示例分包。

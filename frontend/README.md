# frontend 前端交付入口

2026-11-24 已交付 Vue 四页签（新增“热点地图”示例页）、真实路线、双起点对比、路段六维详情与厕所筛选。启动和验收步骤以 [app/README.md](app/README.md) 为准。

前端做两件事：**把路线画在地图上**、**把分数讲清楚**。数据全部来自后端的 **11 个接口**
（契约见 [`docs/接口契约.md`](../docs/接口契约.md)）。**Vue 代码不读 `data/` 下的任何文件**。

```text
frontend/
├── app/                ← 真正要开发的 Vue 3 工程（Vite + TS）
├── prototype/          ← 高保真静态原型，只作视觉参考，不参与构建
└── README.md           ← 你正在读的这一份
```

## 1. 十分钟跑起来（不需要 Python 后端）

```powershell
cd frontend\app
npm install
Copy-Item .env.example .env.local
# 把 .env.local 里的 VITE_USE_MOCK 改成 1
npm run dev
```

打开 <http://127.0.0.1:5173> 就能看到页面，数据来自 `src/mocks/*.json`
（旧版真实响应快照）。注意：mock 只覆盖 `health / meta / segments / facilities / loops`
五个旧接口；**water-green、pois、toilets、layers、routes 没有 mock**，要联调请开后端。

## 2. 接真后端

```powershell
# 仓库根目录
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

`.env.local` 里 `VITE_USE_MOCK=0`，`npm run dev` 即可 —— vite 已把 `/api` 和 `/health`
代理到 8000。后端启动时会预热四个数据集，`/health` 的 `datasets` 字段能自检。

## 3. 页面是空的，等你写

`src/` 里**只留了数据层**：`types.ts`、`api/client.ts`、`mocks/`。
`App.vue`、`components/*.vue`、`store.ts`、`style.css` 都已删除——页面结构由你们自己定。
`main.ts` 目前挂的是一个占位页，写好后把它换成 `createApp(App).mount('#app')` 即可。

地图这一层要从零做，但有**一份能跑的参考实现**可以先看：

> [`reference/index.html`](reference/index.html) —— 用原生 JS + SVG 把
> `data/output/running/v1/web/segments_city.geojson` 和
> `mocks/loops_5km_wuda.json` 画成和 PPT 里那张图一样（1600×1000，无任何依赖）。
> 跑法见 [`reference/README.md`](reference/README.md)。**它只是“怎么画”的参考，
> 数据走的是静态文件；搬到 Vue 时请把数据源换成下面的后端接口。**

1. 申请百度地图**浏览器端** AK（<https://lbsyun.baidu.com>，Referer 白名单填
   `http://127.0.0.1:5173/*`），填进 `.env.local` 的 `VITE_BAIDU_AK`；
2. 引入 BMapGL，**WGS84 → BD-09 的偏移必须做**（后端给的是 WGS84，百度要 BD-09，
   直接用会整体偏移几百米）；
3. 底图：**走后端，不要 fetch `data/`**：
   - `GET /api/segments`：不传 bbox 时返回默认视口（约 8,425 段），适合首屏；
     退到城市级视野时传更大的 bbox，`limit` 最大 60000，响应带 `truncated`；
   - `GET /api/water-green`：水体 / 绿地底图，画在路网下面，`kind=water|green|all`；
   - `GET /api/pois?kinds=sport&exclude_leisure=true`：运动场馆点；
   - 字段名、`score` 配色、`null` 距离语义见 [`docs/接口契约.md`](../docs/接口契约.md)；
4. 结果：`POST /api/routes` 的第 1 条画成粗线（白描边 + 黑实线两层），其余淡一点；
   `mode=loop` 为闭合环线，`mode=oneway` 为 A→B 单行线（可传 `end_lng/end_lat` 指定终点）；
   右栏显示 `score`、`target_ok` 与 `JSON.parse(props.sub)` 的三个子分。
   旧 `POST /api/loops` 仍可用，新代码请用 `/api/routes`。

**复刻标准**（配色、字号、间距、每一条文案）写在 [`docs/前端原型规格.md`](../docs/前端原型规格.md)。

## 4. 三条纪律

- **Vue 不读 `data/`**：segments / water-green / POI / 环线 / 元信息全部走 `/api/...`；
  只有 `reference/` 和 `prototype/` 这两个静态参考物可以读文件；
- **不要改后端字段名**，`sub` 就是 JSON 字符串，`score` 在 loops 与 segments 里是两种口径；
- 拿不准的字段先看 `docs/接口契约.md`，那里有真实响应样例；字段中文名和数量可以
  直接读 `GET /api/layers`，不要在代码里重复维护一份。

## 5. 目录

```text
frontend/app/src/
├── api/client.ts        ← 旧版 5 个接口的封装（含 mock 开关）；新图层按契约加函数
├── mocks/               ← 旧版响应快照（只在 VITE_USE_MOCK=1 时用）
├── types.ts             ← 接口类型，和契约一一对应
└── main.ts              ← 占位页，页面由你写
```

## 6. 新接口速查

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/layers` | 先读它：图层是否就绪、数量、bbox、字段中文名 |
| GET | `/api/segments` | 评分路段（bbox + limit + `detail=basic|full`） |
| GET | `/api/segments/{osm_id}` | 单条路段全部属性 |
| GET | `/api/water-green` | 水体 / 绿地（bbox + kind + simplify） |
| GET | `/api/pois` | 运动场馆（bbox + kinds + exclude_leisure） |
| GET | `/api/toilets` | 公共厕所（bbox + accessible + limit） |
| GET | `/api/facilities` | 旧版别名，新代码不要用 |
| POST | `/api/routes` | 路线生成：`mode=loop|oneway`，1–42 km，带起点校验 |
| POST | `/api/loops` | 旧版环线别名，新代码不要用 |
| GET | `/health` | 图与数据集自检 |
| GET | `/api/meta` | 权重 / 分档 / 数据版本 / 六维说明 |

问题找组长，或直接看 `docs/项目交接说明.md` §2.1 的组内分工。

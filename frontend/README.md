# frontend —— 前端组从这里开始

前端做两件事：**把环线画在地图上**、**把分数讲清楚**。数据全部来自后端的 5 个接口（契约见
[`docs/接口契约.md`](../docs/接口契约.md)）。

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
（从真后端抓的响应快照，字段完全一致）。

## 2. 接真后端

```powershell
# 仓库根目录
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

`.env.local` 里 `VITE_USE_MOCK=0`，`npm run dev` 即可 —— vite 已把 `/api` 和 `/health` 代理到 8000。

## 3. 页面是空的，等你写

`src/` 里**只留了数据层**：`types.ts`、`api/client.ts`、`mocks/`。
`App.vue`、`components/*.vue`、`store.ts`、`style.css` 都已删除——页面结构由你们自己定。
`main.ts` 目前挂的是一个占位页，写好后把它换成 `createApp(App).mount('#app')` 即可。

地图这一层要从零做，但有**一份能跑的参考实现**可以先看：

> [`reference/index.html`](reference/index.html) —— 用原生 JS + SVG 把
> `data/output/running/v1/web/segments_city.geojson` 和
> `mocks/loops_5km_wuda.json` 画成和 PPT 里那张图一样（1600×1000，无任何依赖）。
> 跑法见 [`reference/README.md`](reference/README.md)。看懂它再搬到 Vue + 地图库，比对着截图猜快得多。

1. 申请百度地图**浏览器端** AK（<https://lbsyun.baidu.com>，Referer 白名单填 `http://127.0.0.1:5173/*`），
   填进 `.env.local` 的 `VITE_BAIDU_AK`；
2. 引入 BMapGL，**WGS84 → BD-09 的偏移必须做**（后端给的是 WGS84，百度要 BD-09，直接用会整体偏移几百米）；
3. 底图：**先不要走后端**，直接 `fetch` `data/output/running/v1/web/segments_city.geojson`
   （中心城 8,005 段，1.8 MB，属性 `score` 直接上色）；退到城市级视野时换 `segments_arterial.geojson`；
   要全城又不共享后端时才用 `segments_all.geojson`（29 MB）。三份文件的说明在
   [`data/output/running/v1/web/README.md`](../data/output/running/v1/web/README.md)；
4. 结果：`POST /api/loops` 的第 1 条画成粗线（白描边 + 黑实线两层），其余淡一点；
   右栏显示 `score` 与 `JSON.parse(props.sub)` 的三个子分。

**复刻标准**（配色、字号、间距、每一条文案）写在 [`docs/前端原型规格.md`](../docs/前端原型规格.md)。

## 4. 三条纪律

- **底图可以读 `data/output/running/v1/web/`**（那三份 GeoJSON 就是给你们准备的）；
  其余数据（环线、设施、元信息）走 API，本地没后端就用 mock；
- **不要改后端字段名**，`sub` 就是 JSON 字符串，`score` 在 loops 与 segments 里是两种口径；
- 拿不准的字段先看 `docs/接口契约.md`，那里有真实响应样例。

## 5. 目录

```text
frontend/app/src/
├── api/client.ts        ← 5 个接口的封装（含 mock 开关）
├── mocks/               ← 真实响应快照（只在 VITE_USE_MOCK=1 时用）
├── types.ts             ← 接口类型，和契约一一对应
└── main.ts              ← 占位页，页面由你写
```

问题找组长，或直接看 `docs/项目交接说明.md` §2.1 的组内分工。

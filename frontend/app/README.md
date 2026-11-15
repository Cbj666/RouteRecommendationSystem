# 前端应用（Vue 3 + TypeScript + Vite）

「跑步友好度 · 武汉」交互页：选起点 → 选目标距离/偏好 → 生成候选环线 → 地图高亮 + 右栏可解释指标。
视觉真源是 [`../reference/index.html`](../reference/index.html) 与 [`../../docs/前端原型规格.md`](../../docs/前端原型规格.md)；
接口字段唯一依据是 [`../../docs/接口契约.md`](../../docs/接口契约.md)（v1.1）。

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
VITE_BAIDU_AK=         # 百度浏览器端 AK；留空则用 SVG 底图
```

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
| `npm run sync:geo` | 从 `data/output/running/v1/web/` 复制底图到 `public/geo/` |
| `node scripts\ui-smoke.mjs` | 无头冒烟：mock 模式 **21 项**断言 + 8 张截图（需先 build + preview） |
| `$env:UI_REAL='1'; node scripts\ui-smoke.mjs` | 真后端冒烟：20 项，额外比对接口分数/耗时（需 `VITE_USE_MOCK=0` 构建 + 后端 8000） |

> 不要在 `npm run dev` 运行时用会做「原子写临时目录」的编辑器/工具改 `src`：Vite 的 FSWatcher
> 会对 `*.tmpdir` 报 `EBUSY` 退出。已加 `server.watch.ignored`，但迭代截图仍建议 `build + preview`。

## 目录

```text
src/
  App.vue                画布缩放（桌面 1600×1000；≤900px 单列）+ 全局 ←/→
  components/            TopBar 搜索、LeftPanel 参数、MapStage、RightPanel 结果、
                         LegendBox、FooterBar、StatusOverlay（四态）
  stores/planner.ts      单例 reactive store：起点/距离/偏好/候选/请求竞态
  map/                   MapAdapter 抽象 + SvgAdapter（BMapGL 适配器预留）
  lib/                   projection（经纬度→1600×1000）、color（色阶）、format、geo
  api/client.ts          6 个请求封装 + ApiError + mock 路由
  mocks/                 真实响应快照（含 4 组 loops）
  styles/                tokens.css（设计变量）、base.css（画布与移动端文档流）
scripts/
  sync-geo.mjs           底图同步
  ui-smoke.mjs           Edge headless + CDP 冒烟
public/geo/              构建时生成，已 gitignore（源数据在 data/output/.../web/）
```

## 已实现

- **适宜性地图**：8,005 段按 score 着色（#D94F4F→#15503C），环线白描边 + 黑线，起点标记（仅自定义点）。
- **环线推荐**：起点（2 预设 + 搜索 + 地图点击）、3/5/10 km、四个偏好开关、生成、`‹ 1/3 ›` 与 ←/→ 切换候选。
- **四态**：加载（顶部 pill + CTA 文案）、无结果（中性提示，不报错）、失败（红框 + HTTP 码）、底图失败。
- **可解释面板**：距离/用时/树冠/坡度/场馆/吸附距离 + 安全/绿化/坡度三条子分 + 权重脚注。
- **响应式**：1440×900（整页 0.9 缩放）、390×844（单列、地图 16:10、可纵向滚动、无横向滚动）。
- **mock 自测**：`/?mock=empty`、`/?mock=error`、`/?mock=slow`（仅 mock 模式）。

## 已知限制（详见 `docs/接口契约.md` §6）

| # | 限制 | 前端现状 |
|---|---|---|
| G1 | 后端无单行线 `mode` | 「单行线 A→B」置灰，title 说明 |
| G2 | `/api/segments` 无 `s_air`/原始指标 | 底图与环线可解释；单段明细未做 |
| G3 | loops 无 `grade`，score 口径不同 | 徽标按 `score>=75/65/55` 本地判定 |
| G4 | `/api/facilities` 忽略 `kinds` | 第 4 开关仅图层，title 说明 |
| G6 | 无地理编码 | 搜索仅 2 个预设 + 地图点选；接 AK 后可用 BMapGL `LocalSearch` |
| G7 | 错误码不统一 | 按 4xx/5xx 分类展示后端原文 |

## 验收

- `npm run build` 零错误；
- `node scripts\ui-smoke.mjs` 18/18；
- `data/output/ui/m1/shot-1600.png` 与 `presentation/前端原型图.png` 面板区逐像素对齐（地图细线 1 px 抗锯齿差，已知）；
- `data/output/ui/m2/mobile-390-full.png` 无横向滚动，整页可滚动。

## 组内约定

- 类型只加不删；删字段必须同步 `docs/接口契约.md` 变更记录；
- 页面不直接 `fetch`，统一走 `src/api/client.ts`；
- WGS84→BD-09 只允许在 `map/baiduAdapter` 边界发生一次。

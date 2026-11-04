# 前端骨架（Vue 3 + 百度地图）

前端组的起点。**现在能跑起来，但地图是占位、接口走 mock。**

上层说明见 [`../README.md`](../README.md)，接口字段见 [`docs/接口契约.md`](../../docs/接口契约.md)。

## 启动

```powershell
cd frontend\app
npm install
Copy-Item .env.example .env.local      # 首次
npm run dev                            # http://127.0.0.1:5173
```

`.env.local` 里两个开关：

- `VITE_USE_MOCK=1` —— 走 `src/mocks/*.json`，**不需要后端**；
- `VITE_BAIDU_AK=` —— 百度浏览器端 AK，不填则地图显示占位。

接真后端时先起：

```powershell
# 仓库根目录
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

再把 `VITE_USE_MOCK` 改回 `0`。

## 已经搭好的（只有数据层）

```text
src/
  types.ts                接口类型（与 docs/接口契约.md 一一对应）
  api/client.ts           5 个接口封装 + ApiError + mock 开关
  mocks/                  真实响应快照（health/meta/segments/facilities/loops）
  main.ts                 占位冒烟页（会显示一行说明，不是真界面）
```

**页面文件已全部删除**：`App.vue`、`components/{MapPanel,ControlPanel,ResultPanel}.vue`、
`store.ts`、`style.css` 都不在了 —— 布局、状态管理、样式体系由你们自己定。
写好后把 `main.ts` 最后一行换成 `createApp(App).mount('#app')`。

## 你要做的

1. **接百度地图**：`index.html` 里取消注释脚本，自己写地图组件实现 `new BMapGL.Map(...)`，
   把 `loops` 画成 Polyline。**坐标系**：后端出 WGS84，百度要 BD-09，转换只在这里做一次。
2. **接接口**：`api/client.ts` 里已经写好五个函数，把 `.env.local` 的 `VITE_USE_MOCK` 改成 `0` 即可。
   注意 `loops.features[0].properties.sub` 是 **JSON 字符串**，要 `JSON.parse`。
3. **评分底图**：`fetchSegments(bbox, limit)` 返回 GeoJSON（带 `truncated` 标记，超了要缩 bbox 或分块），
   按 `score` 着色（RdYlGn，25–70，见 `docs/过程/design-guidelines.md`）。
4. **交互**：点地图设起点 → 调 `fetchLoops` → 更新右侧面板。

## 验收

- 改起点后 3 秒内出结果；
- 环线与评分底图对齐，无几十米偏移（坐标转换错了会差几百米）；
- 1440×900 与 390×844 都无横向滚动。

## 组内约定（摘自 `docs/分工卡片.md` §二）

| 角色 | 你负责 |
|---|---|
| 前端组 · A | 定契约、`ControlPanel` / `ResultPanel`、结果可解释 |
| 前端组 · B | 地图层（BMapGL + 坐标转换）、`/api/segments` 着色与分块 |

两边都改 `src/api/client.ts` 时先打招呼；类型改动只加不删，删字段要同步 `docs/接口契约.md`。

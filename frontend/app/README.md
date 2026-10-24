# 前端骨架（Vue 3 + 百度地图）

卡片 1 的起点。现在能跑起来，但地图是占位、接口是 mock。

## 启动

```powershell
cd frontend\app
npm install
npm run dev          # http://127.0.0.1:5173
```

后端先起：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

## 已经搭好的

```text
src/
  main.ts                 挂载
  App.vue                 三栏布局（复用 prototype 的视觉）
  style.css               设计变量（颜色、间距、字体）
  types.ts                接口类型
  api/client.ts           fetch 封装 + mock 回退
  components/
    MapPanel.vue          百度地图占位（TODO：接 JS API、画线）
    ControlPanel.vue      起点 / 距离档 / 偏好开关
    ResultPanel.vue       综合分、六项指标、子分条
  store.ts                极简响应式状态（不引 pinia）
```

## 你要做的

1. **接百度地图**：`index.html` 里取消注释脚本，`MapPanel.vue` 里实现
   `new BMapGL.Map(...)`，把 `loops` 画成 Polyline。
   **注意坐标系**：后端出 WGS84，百度要 BD-09，转换只在这里做一次。
2. **接接口**：`api/client.ts` 里已经有 `fetchLoops`，把 mock 删掉即可。
3. **评分底图**：`GET /api/segments?bbox=...` 返回 GeoJSON，按 `score` 着色
   （色带见 `docs/design-guidelines.md`：RdYlGn，25–70）。
4. **交互**：点地图设起点 → 调 `/api/loops` → 更新右侧面板。

## 验收（摘自任务卡）

- 改起点后 3 秒内出结果；
- 环线与评分底图对齐，无几十米偏移；
- 1440×900 与 390×844 都无横向滚动。

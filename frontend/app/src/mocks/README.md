# mocks —— 真实响应快照

这五个 JSON 是从本机后端**真实抓下来的**，不是手写假数据，字段与线上完全一致。

| 文件 | 对应接口 | 规模 | 抓取参数 |
|---|---|---|---|
| `health.json` | `GET /health` | 1 条 | — |
| `meta.json` | `GET /api/meta` | 1 条 | — |
| `segments.json` | `GET /api/segments` | 1200 段 | bbox `114.352,30.530,114.366,30.540`，`limit=1200`（`truncated: true`） |
| `facilities.json` | `GET /api/facilities` | 216 点 | bbox `114.330,30.515,114.400,30.570`，`kinds=all` |
| `loops.json` | `POST /api/loops` | 6 条候选 | 起点 `114.3547,30.5342`，`target_m=5000` |

## 另外四组环线（换起点 / 换距离时用）

`loops.json` 只有一个场景。想试别的起点或距离，用这四份，**形状与 `/api/loops` 完全一致**
（同样是 `generate_loops` 真算出来的，不是手写）：

| 文件 | 起点 | `target_m` | 第 1 条 |
|---|---|---:|---|
| `loops_3km_wuda.json` | 武大 114.3547, 30.5342 | 3,000 | 2.70 km / 80.2 分 |
| `loops_5km_wuda.json` | 同上 | 5,000 | 5.34 km / 78.5 分 |
| `loops_10km_wuda.json` | 同上 | 10,000 | 8.51 km / 69.0 分 |
| `loops_5km_donghu.json` | 东湖 114.4120, 30.5560 | 5,000 | 4.78 km / 68.6 分 |

每份 3 条候选、30 KB 上下。用的时候按 `(起始点, 距离档)` 挑一份即可，例如：

```ts
const MOCK_BY_CASE = {
  'wuda-3000': () => import('../mocks/loops_3km_wuda.json'),
  'wuda-5000': () => import('../mocks/loops_5km_wuda.json'),
  'wuda-10000': () => import('../mocks/loops_10km_wuda.json'),
  'donghu-5000': () => import('../mocks/loops_5km_donghu.json'),
}
```

重出命令：`python build/export_web_network.py`（会同时重写 `segments_city/arterial`）。


## 怎么用

在 `frontend/app/.env.local` 里写：

```text
VITE_USE_MOCK=1
```

`src/api/client.ts` 会改成读这些 JSON，页面不依赖 Python 后端也能跑起来。

## 什么时候重新抓

后端字段变了（例如 `/api/segments` 补上 `s_air`）之后，重新跑一遍：

```powershell
# 1) 起后端
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8123

# 2) 在项目根目录抓取（脚本会覆盖本目录）
.\.venv\Scripts\python.exe build\_capture_mocks.py --port 8123
```

脚本里改了端口的话记得同步；抓之前确认脚本里的 bbox 与上表一致。

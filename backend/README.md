# backend —— HTTP 接口层与分析内核

后端现在同时负责两件事：

1. **HTTP 接口层**：把 `segments.gpkg`、`water_green.geojson`、`amap_sport_poi.csv`
   读进内存，统一以 GeoJSON 提供给 Vue。前端不再直接 `fetch` `data/` 下的文件。
2. **分析内核**：跑步图、环线 / 单行线生成、坡度 / 树冠 / 评分流水线。

```text
app/
  api.py                 FastAPI 应用（9 个路由；启动时预热图 + 三个数据集）
  datasets.py            三个图层的懒加载缓存、bbox 过滤、GeoJSON 序列化
  running.py             跑步图 + 两种路线生成（当前核心）
  config.py              Params：全部建模参数（唯一的"魔法数字"来源）
  paths.py               全项目路径定义（不要在别处硬编码路径）
  graph.py               多模式图：路网 + 公交 + 地铁（前版，接驳用）
  isochrone.py           等时圈内核（前版，保留，不要引用旧结论）
scripts/                 命令行脚本（可在任意工作目录运行）
  build_slope.py         SRTM → 路段坡度
  build_canopy.py        WorldCover → 路段树冠
  build_air_quality_chap.py  CHAP → 逐段空气
  build_running_dataset.py   六维评分 → segments.gpkg
  run_loop_demo.py       环线演示 → GeoJSON + PNG
  fetch_amap_sport_poi.py    高德场馆抓取（有缓存，勿重跑）
requirements.txt
```

## 组员第一次运行

`.venv/` 是本地虚拟环境，已在 `.gitignore` 中，不会随 Git 仓库分发；
每个组员在自己电脑上建一份（Python 3.13，64 位）：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

不需要激活环境；后面直接调用 `.\.venv\Scripts\python.exe` 即可。
如果 `py` 命令不存在，改用 `python -m venv .venv`。

## 起服务

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 前端开发地址：<http://127.0.0.1:5173>（vite 已代理 `/api` 与 `/health`）
- 启动日志会打印图规模与三个数据集行数；约 0.4 s + 0.9 s。

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 图规模 + 数据集行数 + 加载时间 |
| GET | `/api/layers` | 图层目录：数量 / bbox / 字段中文名 / 源文件时间 |
| GET | `/api/meta` | 权重、分档、数据版本 |
| GET | `/api/segments` | bbox 内评分路段；`detail=basic` 14 字段 / `full` 26 字段 |
| GET | `/api/segments/{osm_id}` | 单条路段全部属性 |
| GET | `/api/water-green` | 水体 / 绿地；`kind=water|green|all` |
| GET | `/api/pois` | 运动场馆点；默认剔除休闲娱乐 |
| GET | `/api/facilities` | 旧版兼容别名（新代码用 `/api/pois`） |
| POST | `/api/loops` | 环线 / 单行线候选 |

字段、参数、错误码与示例见 [`docs/接口契约.md`](../docs/接口契约.md)。

## 数据层约定

- `app/datasets.py` 用模块级缓存 + 双检锁懒加载；`lifespan` 里 `preload()` 预热。
- 三个源文件：

  | 图层 | 文件 | 行数 |
  |---|---:|---:|
  | segments | `data/processed/running/v1/segments.gpkg` | 91,203 |
  | water_green | `data/output/running/v1/web/water_green.geojson` | 3,586 |
  | pois | `data/processed/running/v1/amap_sport_poi.csv` | 5,137 |

- **`inf` → `null`**：`d_green_m` / `d_water_m` / `d_main_m` 用 `inf` 表示“搜索半径内没有”。
  `GeoDataFrame.to_json()` 会写成 `Infinity`，浏览器 `JSON.parse` 不接受，所以
  `datasets._json_safe()` 在加载时统一转成 `None`。
- **bbox 过滤**用 `gdf.cx[...]`（GeoPandas 空间索引），不是逐行判断。
- **gzip**：`GZipMiddleware(minimum_size=1024)`，`application/geo+json` 会被压缩；
  默认视口的路段响应约 4.85 MB → 709 KB。
- 源文件缺失时 `DatasetUnavailable` → 503，不阻塞服务启动，也不返回 500。

## 常用命令

```powershell
# 数据（一次性；raw 不入库）
.\.venv\Scripts\python.exe backend\scripts\fetch_dem.py
.\.venv\Scripts\python.exe backend\scripts\fetch_amap_sport_poi.py

# 计算（改了评分必须按顺序重跑）
.\.venv\Scripts\python.exe backend\scripts\build_slope.py
.\.venv\Scripts\python.exe backend\scripts\build_canopy.py
.\.venv\Scripts\python.exe backend\scripts\build_air_quality_chap.py --year 2024
.\.venv\Scripts\python.exe backend\scripts\build_running_dataset.py
.\.venv\Scripts\python.exe backend\scripts\run_loop_demo.py

# 起服务
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

改评分后要删除 `data/processed/running/graph/` 让图缓存重建（缓存会过期）。

## 自检

```powershell
# 图与路线
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'backend'); from app import running; g=running.load_or_build(); lp=running.generate_loops(g,114.3547,30.5342,5000); print(len(lp), lp[0]['length_m'], round(lp[0]['score'],1))"

# 接口（服务已起）
curl.exe "http://127.0.0.1:8000/health"
curl.exe "http://127.0.0.1:8000/api/layers"
curl.exe "http://127.0.0.1:8000/api/segments?limit=2&detail=full"
```

判据：`length_m` 在 4250–5750 之间，`score` 在 60–90 之间，路线闭合；
`/health.datasets` 三项都非 `null`。

## 前版说明

`graph.py` / `isochrone.py` 是「个性化等时圈」时期的内核，保留用于接驳与追溯。
**新功能不要写回等时圈文档**；旧文档在 `docs/archive/等时圈版本/`。

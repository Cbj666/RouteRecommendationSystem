# 城市慢跑 / 慢骑环境适宜性评价与路线推荐系统

用公开数据评价武汉每条街道"跑起来舒不舒服"，并推荐闭合环线或单行线。

> 给定起点与目标距离（3/5/10 km），在 9.1 万段路网上打分（安全 / 绿化 / 坡度 /
> 过街 / 设施 / 空气六维），再生成若干条**尽量避免重走原路**的环线，或一条明确的 A→B
> 单行线，并解释每条为什么好。

课程项目（选题调整后）。原「个性化等时圈」选题已被其他组占用，
旧版文档归档在 `docs/archive/等时圈版本/`，路网与图计算的成果仍然复用。

## 现状

| 模块 | 状态 |
|---|---|
| 数据：路网 47,051 km、SRTM 30 m、WorldCover 10 m 树冠、高德 5,137 场馆 | 完成 |
| 六维评分（9.1 万段 / 4.7 万公里，全程可解释） | 完成 |
| 路线生成：环线（4× 双向惩罚）+ 单行线 A→B（0.2 s 量级） | 完成 |
| 前端静态原型（1440×900） | 完成 |
| Vue + 百度地图 可交互版 | 未开始 |
| FastAPI 接口（11 路由：图层 / 路线 / 厕所 / 元信息） | 完成，见 `docs/接口契约.md` |
| 答辩 PPT | 未开始 |

## 结果一览

| 起点 | 5 km 环线 | 用时 | 综合分 | 树冠 | 平均坡度 |
|---|---|---:|---:|---:|---:|
| 武汉大学 | 5.34 km | 32 min | 78.5 | 58% | 3.5% |
| 东湖绿道 | 5.58 km | 34 min | 70.9 | 64% | 3.0% |
| 汉口江滩 | 5.30 km | 32 min | 58.6 | 38% | 0.7% |

- 环线图：`data/output/running/v1/loops.png`
- 评分地图：`data/output/running/v1/map_donghu.png`
- 前端原型：`data/output/ui/round-1/desktop.png`

## 目录结构

```text
backend/
  app/
    api.py         FastAPI 11 路由（图层 / 目录 / 路线 / 厕所 / 元信息）
    datasets.py    四个图层（路段 / 水绿 / 场馆 / 厕所）的缓存与序列化
    config.py      建模参数（速度、候车、权重）
    paths.py       全项目路径
    running.py     ★ 跑步图 + 环线 / 单行线生成
    graph.py       多模式交通图（前版，接驳用）
    isochrone.py   等时圈内核（前版，保留）
  scripts/
    fetch_dem.py              SRTM 高程（9 幅瓦片）
    fetch_amap_sport_poi.py   高德运动场馆（网格 + 翻页）
    fetch_amap_toilet_poi.py  高德公共厕所（2026-11，6,122 个）
    merge_amap_toilet_poi.py  公厕合并进 poi.gpkg（5,839 个）
    build_slope.py            坡度（150 m 平滑后求梯度）
    build_canopy.py           树冠（WorldCover 10 m）
    build_running_dataset.py  六维评分 → segments.gpkg
    plot_running_map.py       评分地图 + 原型底图
    run_loop_demo.py          3 个起点的环线
    prepare_dataset.py / verify_dataset.py   基础数据集（前版）
frontend/prototype/index.html  静态原型
data/
  raw/           原始下载（SRTM、WorldCover、OSM、高德缓存），不入库
  processed/v1/  基础数据集（路网 / 公交 / 地铁 / POI）
  processed/running/v1/  坡度、树冠、场馆、公厕、评分
  output/running/v1/     地图、环线、GeoJSON
docs/            说明书、数据字典、进展报告
tools/           一次性历史脚本
```

## 快速开始

### 0. 本机环境（每个组员做一次）

`.venv/` 是**本机虚拟环境**，已经在 `.gitignore` 里，不会提交到 Git。
它名字以点开头，Windows 资源管理器默认可能看不到，不是“仓库里丢了文件”。
每个组员在自己电脑上建一份，**不要拷贝别人的 `.venv`**。

需要 **Python 3.13（64 位）**，在仓库根目录执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -V
```

最后一条应输出 `Python 3.13.x`。如果 `py` 不可用，把 `py -3.13` 换成 `python`；
如果 `python` 是 Microsoft Store 的占位程序，先从 python.org 安装 Python 3.13，
安装时勾选 “Add python.exe to PATH”。

> PowerShell 如果拦截 `Activate.ps1`，不用激活：下面所有命令都直接调用
> `.\.venv\Scripts\python.exe`，不依赖激活。

### 1. 起后端（前端联调只认它）

在**仓库根目录**执行，保持终端不关：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>（根路径 `/` 会跳到这里）
- 看到 `Application startup complete` 才算就绪；启动会加载图和四个图层，约 1–2 s。
  如果 `data/processed/running/graph/` 缓存不存在，会先重建，第一次会慢一些。
- 前端不需要 `data/`，所有图层都走 `/api/...`。

### 2. 起前端（另开一个终端）

```powershell
cd frontend\app
npm install          # 第一次才需要
npm run dev
```

打开 <http://127.0.0.1:5173>。Vite 已把 `/api`、`/health` 代理到 8000。

### 3. 数据/算法脚本（需要重算时才跑）

```powershell
# raw 数据不入库，见 docs/数据/数据补充清单.md
.\.venv\Scripts\python.exe backend\scripts\fetch_dem.py

# 计算
.\.venv\Scripts\python.exe backend\scripts\build_slope.py
.\.venv\Scripts\python.exe backend\scripts\build_canopy.py
.\.venv\Scripts\python.exe backend\scripts\fetch_amap_sport_poi.py
.\.venv\Scripts\python.exe backend\scripts\build_running_dataset.py
.\.venv\Scripts\python.exe backend\scripts\plot_running_map.py

# 环线
.\.venv\Scripts\python.exe backend\scripts\run_loop_demo.py
```

## 关键文档

- [docs/项目交接说明.md](docs/项目交接说明.md) —— 进度真相来源
- [docs/项目说明书.md](docs/项目说明书.md) —— 答辩主文档（Word 版同名 .docx）
- [docs/过程/开发进展-慢跑适宜性与环线.md](docs/过程/开发进展-慢跑适宜性与环线.md)
- [docs/数据/数据字典-跑步数据集.md](docs/数据/数据字典-跑步数据集.md)
- [AGENTS.md](AGENTS.md) —— 用 AI 协作者时先喂这份

## 已知限制（写进报告，不要说反）

- 没有街景：百度/高德不提供、腾讯需企业认证、Mapillary 中国区影像老旧；
  绿化用 **ESA WorldCover 10 m 树冠** 代理，反映成片林荫，**不识别单排行道树**；
- 没有路段车流量：安全用道路等级 + 距主干道距离 + 路口密度代理；
- 没有官方健身设施清单：设施用高德 POI（场馆 4,081 + 公厕 5,117，另加 OSM 配套点，共 14,542），远城区仍偏稀；
- 评分是**代理指标**，不等于真实跑步体验，也没有用轨迹做过验证。

## 数据来源

OSM（路网 / 绿地 / 水体 / POI）、NASA SRTM（高程）、ESA WorldCover（地表覆盖）、
高德开放平台（运动场馆 POI）。OSM 遵循 ODbL，高德数据遵循其开放平台协议。

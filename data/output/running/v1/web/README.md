# web/ — 前端可直接 fetch 的 GeoJSON

这些文件不依赖后端、不依赖 `data/raw`，`fetch()` 之后直接丢给地图库即可。
坐标系统一 **WGS84（EPSG:4326）**，全部为纯经纬度，不需要再做投影。

| 文件 | 体积 | 要素 | 什么时候用 |
|---|---:|---:|---|
| `segments_city.geojson` | 1.81 MB | 8,005 段 | **默认用它**。范围正好是 PPT 原型图那一屏（114.305–114.405 / 30.508–30.562） |
| `segments_arterial.geojson` | 7.16 MB | 19,298 段 | 退到城市级视野时用它，否则中心城外一片空白 |
| `segments_all.geojson` | 29.1 MB | 90,193 段 | 整市全量。只想「一眼看到全部路网、不想开后端」时用，首屏加载会慢 |
| `water_green.geojson` | 2.43 MB | 3,586 面 | 水体 / 绿地底图（画在路网下面） |

> 三份路网属性完全一样：`score`（0–100 整数，直接上色）、`grade`（差/一般/较好/好/很好）、`fclass`（OSM 道路等级）。
> 坐标保留 4 位小数（约 11 m），已剔除退化几何，`geometry` 不会是 null。

## 上色（与 PPT 原型图一致）

`t = clamp((score - 30) / 42, 0, 1)`，在 5 个停靠点之间线性插值：

| t | 分数 | 颜色 |
|---:|---:|---|
| 0.00 | 30 | `#D94F4F` |
| 0.25 | 40.5 | `#E8A33D` |
| 0.50 | 51 | `#8FBF6A` |
| 0.75 | 61.5 | `#2E7A5D` |
| 1.00 | ≥72 | `#15503C` |

线宽：matplotlib 端用的是 `linewidths=0.9`（dpi 100，约 1.25 px），SVG / Canvas 里给 1.25 左右最接近。

## 水体与绿地

`kind` 只有两个值：`water` / `green`。

- 水体 2,034 个面：`hubei.gpkg` 的 `gis_osm_water_a_free`，面积 ≥ 0.03 km²
- 绿地 1,552 个面：`gis_osm_landuse_a_free` 里的 `forest / scrub / park / grass / meadow / recreation_ground / orchard / vineyard / village_green / heath`，面积 ≥ 0.02 km²
- 已 `simplify(0.0002)`（约 22 m），体积从 8.56 MB 压到 2.43 MB

建议配色：水体 `#B3D4E6`、林地 `#9FC49B`、草地公园 `#CFE3BE`、底色 `#F5F8F2`。
**注意**：PPT 里那张原型图其实没有画水绿（`make_map.py --plain`），加上它们只会更好看，
想 1:1 复刻就把这一层关掉。

## 重出

```powershell
.\.venv\Scripts\python.exe build\export_web_assets.py    # 水绿底图
.\.venv\Scripts\python.exe build\export_web_network.py   # 三份路网 + 4 份路线 mock
.\.venv\Scripts\python.exe build\round_route_mocks.py    # 收敛 mock 浮点（体积减半）
.\.venv\Scripts\python.exe build\check_web_geojson.py    # 自查：要素数 / 空几何 / 体积
```

只想重出小份、不要 29 MB 那份：`build\export_web_network.py --no-all`。

## 路线几何

环线不在这里，在 `frontend/app/src/mocks/loops_*.json`（4 个场景，每个 3 条候选，
形状与后端 `POST /api/loops` 完全一致）。用法见 `frontend/app/src/mocks/README.md`。

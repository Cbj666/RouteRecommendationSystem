# 一键复现：从已有原始数据到环线图
#
# 用法：
#   .\run_all.ps1                 # 全流程
#   .\run_all.ps1 -SkipTests      # 跳过测试
#
# 前置：.venv 已建好，data/raw 下有 DEM / WorldCover / OSM（见 docs/环境与复现.md）

param(
    [switch]$SkipTests,
    [switch]$SkipPlot
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$py = '.\.venv\Scripts\python.exe'

function Step($name, $block) {
    $t0 = Get-Date
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { throw "$name 失败（exit $LASTEXITCODE）" }
    Write-Host ("    用时 {0:N1}s" -f ((Get-Date) - $t0).TotalSeconds) -ForegroundColor DarkGray
}

function Require($path, $hint) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "缺少 $path —— $hint"
    }
}

# ---- 0. 环境检查 -------------------------------------------------------
Require $py '先在项目根目录创建 venv：python -m venv .venv'
Require 'data/raw/hubei/hubei-261013-free-OpenMap/hubei.gpkg' '把 OSM 湖北提取放到 data/raw/hubei/（见 data/README.md）'
Require 'data/raw/boundary/武汉市_市.geojson' '市界文件缺失'
Require 'data/raw/dem/skadi' '跑 backend/scripts/fetch_dem.py 下载 SRTM'
Require 'data/raw/worldcover' '下载 4 幅 WorldCover .tif 到 data/raw/worldcover/'

# ---- 1. 基础数据集（已存在则跳过） -------------------------------------
if (-not (Test-Path 'data/processed/v1/manifest.json')) {
    Step '准备基础数据集 v1' { & $py backend/scripts/prepare_dataset.py }
} else {
    Write-Host '基础数据集 v1 已存在，跳过' -ForegroundColor DarkGray
}

# ---- 2. 跑步数据集 -----------------------------------------------------
Step '计算坡度' { & $py backend/scripts/build_slope.py }
Step '计算树冠' { & $py backend/scripts/build_canopy.py }
Step '抓取场馆（有缓存则不消耗配额）' { & $py backend/scripts/fetch_amap_sport_poi.py }
Step '五维评分' { & $py backend/scripts/build_running_dataset.py }

# ---- 3. 图与环线 -------------------------------------------------------
Step '生成环线' { & $py backend/scripts/run_loop_demo.py }
if (-not $SkipPlot) {
    Step '评分地图' { & $py backend/scripts/plot_running_map.py }
}

# ---- 4. 测试 -----------------------------------------------------------
if (-not $SkipTests) {
    Step '冒烟测试' { & $py -m pytest tests -q }
}

Write-Host "`n全部完成。" -ForegroundColor Green
Write-Host '产物：data/output/running/v1/{loops.png, loops.geojson, map_donghu.png}'

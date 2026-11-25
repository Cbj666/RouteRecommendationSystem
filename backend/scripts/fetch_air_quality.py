"""抓取武汉空气质量监测站（AQICN / World Air Quality Index）。

数据源：https://aqicn.org/api/  ——「All the APIs are provided for free」，
个人 token 在 https://aqicn.org/data-platform/token/ 申请，写在仓库根目录 .env：

    AQICN_TOKEN=xxxxxxxxxxxxxxxxxxxx

用到的三个端点（全部 GET，token 走 query）：

    /search/?keyword=wuhan            按名称找站（含已停更的老站，要按时间剔除）
    /map/bounds/?latlng=miny,minx,maxy,maxx   矩形内的站（武汉一次返回 10 个）
    /feed/@UID/                       单站详情：iaqi + 主导污染物 + 预报

重要口径（写论文/PPT 时别写错）

* `data.iaqi` 里的数字是**分指数**（0–500 的 AQI 刻度），不是浓度 µg/m³；
  浓度只在 `data.forecast.daily.pm25[*].avg` 这类预报字段里出现。
* `data.aqi` 是 AQICN 计算的综合 AQI，中国站点默认按 US EPA 口径；
  与生态环境部 HJ 633—2012 的 AQI 不是一套（后者对 PM2.5 更宽松），
  要跟国控站对比时必须换算，不能直接混用。
* 这是**实时快照**，没有历史接口。要时间序列只能定时采样存本地。

产物

    data/cache/aqicn/{uid}_{YYYYmmddHH}.json        原始响应（失败响应不写缓存）
    data/processed/running/v1/air_quality_stations.csv   每站一行

用法

    .\\.venv\\Scripts\\python.exe backend\\scripts\\fetch_air_quality.py
    .\\.venv\\Scripts\\python.exe backend\\scripts\\fetch_air_quality.py --force
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT / "data" / "raw" / "boundary" / "武汉市_市.geojson"
CACHE = ROOT / "data" / "cache" / "aqicn"
OUT = ROOT / "data" / "processed" / "running" / "v1"
CSV_NAME = "air_quality_stations.csv"

BASE = "https://api.waqi.info"
USER_AGENT = "Mozilla/5.0 (isochrone-course-project; air-quality fetcher)"
SLEEP_S = 1.1          # 免费 token 有速率限制，慢慢来
STALE_H = 6.0          # 超过 6 小时没更新视为停更站


def load_token() -> str:
    """AQICN token：环境变量优先，其次项目根 .env（见 app/secrets.py）。"""
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/ for `app`
    from app.secrets import require as require_secret

    return require_secret(
        "AQICN_TOKEN",
        hint="https://aqicn.org/data-platform/token/ 免费申请",
    )


def api(path: str, token: str) -> dict:
    """调一个端点，返回 data 段；status != ok 直接抛错（调用方决定要不要吞）。"""
    url = f"{BASE}{path}{'&' if '?' in path else '?'}token={token}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if str(payload.get("status")) != "ok":
        raise RuntimeError(f"AQICN status={payload.get('status')} ({payload.get('data')})")
    return payload["data"]


def list_stations(token: str, bbox: tuple[float, float, float, float]) -> dict[int, dict]:
    """两张网取并集：bbox 矩形 + 关键词搜索。返回 {uid: {lat, lon, name}}。"""
    miny, minx, maxy, maxx = bbox
    found: dict[int, dict] = {}

    bounds = api(f"/map/bounds/?latlng={miny:.4f},{minx:.4f},{maxy:.4f},{maxx:.4f}", token)
    for it in bounds:
        uid = int(it["uid"])
        found[uid] = {
            "uid": uid,
            "lat": float(it["lat"]),
            "lon": float(it["lon"]),
            "name": it.get("station", {}).get("name", ""),
        }
    print(f"[aqicn] map/bounds -> {len(bounds)} 站", flush=True)

    time.sleep(SLEEP_S)
    search = api("/search/?keyword=wuhan", token)
    added = 0
    for it in search:
        st = it.get("station", {})
        geo = st.get("geo") or []
        if len(geo) != 2:
            continue
        uid = int(st.get("uid") or 0)
        if not uid or uid in found:
            continue
        found[uid] = {
            "uid": uid,
            "lat": float(geo[0]),
            "lon": float(geo[1]),
            "name": st.get("name", ""),
        }
        added += 1
    print(f"[aqicn] search/wuhan -> 新增 {added} 站（合计 {len(found)}）", flush=True)
    return found


def parse_station(data: dict) -> dict:
    """把 /feed/@UID/ 的 data 摊平成一行。iaqi 是分指数，不是浓度。"""
    iaqi = data.get("iaqi", {}) or {}
    fc = (data.get("forecast", {}) or {}).get("daily", {}) or {}
    fpm = fc.get("pm25") or []
    city = data.get("city", {}) or {}
    t = data.get("time", {}) or {}
    row = {
        "uid": data.get("idx"),
        "name": city.get("name", ""),
        "lat": (city.get("geo") or [None, None])[0],
        "lon": (city.get("geo") or [None, None])[1],
        "aqi": data.get("aqi"),
        "dominant": data.get("dominentpol") or data.get("dominantpol"),
        "time_iso": t.get("iso"),
        "time_epoch": t.get("v"),
        "url": city.get("url"),
    }
    for k in ("pm25", "pm10", "o3", "no2", "so2", "co"):
        row[f"iaqi_{k}"] = (iaqi.get(k) or {}).get("v")
    for k in ("t", "h", "p", "w"):
        row[f"met_{k}"] = (iaqi.get(k) or {}).get("v")
    # 唯一能拿到的“真浓度”：预报里的 PM2.5（µg/m³）
    row["fc_pm25_avg"] = fpm[0].get("avg") if fpm else None
    row["fc_pm25_day"] = fpm[0].get("day") if fpm else None
    return row


def mark_duplicates(df: pd.DataFrame, radius_m: float = 1500.0) -> pd.DataFrame:
    """标记「同一个实测站被报了两次」。

    AQICN 会同时给出一个城市级条目（如 uid 1529 "Wuhan (武汉)"）和它对应的
    某个实测站（uid 910 汉口江滩），两者坐标只差几百米、各污染物分指数完全一致。
    按「分指数签名相同 + 相距 < 1.5 km + uid 更大者」判定为重复，置 dup_of=小 uid。
    """
    df = df.reset_index(drop=True)
    df["dup_of"] = pd.NA
    keys = ["iaqi_pm25", "iaqi_pm10", "iaqi_o3", "iaqi_no2", "iaqi_so2", "iaqi_co", "aqi"]

    def sig(r):  # noqa: ANN001
        return tuple(None if pd.isna(r[k]) else r[k] for k in keys)

    pts = gpd.GeoSeries(gpd.points_from_xy(df["lon"], df["lat"]), crs=4326).to_crs(32650)
    for i in range(len(df)):
        if not pd.isna(df.at[i, "dup_of"]):
            continue
        for j in range(i + 1, len(df)):
            if sig(df.iloc[i]) != sig(df.iloc[j]):
                continue
            if pts.iloc[i].distance(pts.iloc[j]) <= radius_m:
                df.at[j, "dup_of"] = df.at[i, "uid"]
    n = int(df["dup_of"].notna().sum())
    if n:
        print(f"[aqicn] 去重：{n} 个条目与已有站重复（dup_of 非空），实际站数 {len(df) - n}")
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取武汉空气质量监测站（AQICN）")
    ap.add_argument("--force", action="store_true", help="忽略本小时缓存，强制重抓")
    args = ap.parse_args()

    token = load_token()
    print(f"[aqicn] token 已加载（长度 {len(token)}）", flush=True)

    boundary = gpd.read_file(BOUNDARY).to_crs(4326)
    geom = boundary.geometry.union_all()
    minx, miny, maxx, maxy = boundary.total_bounds
    bbox = (miny, minx, maxy, maxx)

    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    stations = list_stations(token, bbox)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d%H")

    rows: list[dict] = []
    hit = miss = fail = 0
    for uid, meta in sorted(stations.items()):
        cf = CACHE / f"{uid}_{stamp}.json"
        data = None
        if cf.exists() and not args.force:
            data = json.loads(cf.read_text(encoding="utf-8"))
            hit += 1
        else:
            try:
                time.sleep(SLEEP_S)
                data = api(f"/feed/@{uid}/", token)
                cf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                miss += 1
            except Exception as exc:                      # noqa: BLE001
                print(f"[aqicn] uid {uid} 失败：{exc}", flush=True)
                fail += 1
                continue

        row = parse_station(data)
        row["uid"] = row["uid"] or uid
        row["lat"] = meta["lat"]
        row["lon"] = meta["lon"]
        row["name"] = row["name"] or meta["name"]
        row["in_boundary"] = bool(shapely.contains_xy(geom, meta["lon"], meta["lat"]))
        if row.get("time_epoch"):
            # AQICN 的 time.v 是「把本地时间当 UTC 塞进 epoch」，不是真正的 UTC 时刻，
            # 直接和 UTC now 相减会差一个时区（武汉 8 小时），所以拿本地 naive 时间去比。
            stamp_naive = datetime.fromtimestamp(row["time_epoch"], tz=timezone.utc).replace(tzinfo=None)
            age = (datetime.now() - stamp_naive).total_seconds() / 3600
        else:
            age = None
        row["age_h"] = round(age, 2) if age is not None else None
        row["stale"] = (age is None) or (age > STALE_H)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(["stale", "aqi"], na_position="last")
    df = mark_duplicates(df)
    out_path = OUT / CSV_NAME
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[aqicn] 写入 {out_path.relative_to(ROOT)}  行={len(df)}（缓存命中 {hit} / 新抓 {miss} / 失败 {fail}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

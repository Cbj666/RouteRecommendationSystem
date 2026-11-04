import urllib.request, json, pathlib, rasterio, numpy as np, time
from rasterio.windows import Window
H = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'}
rec = '21770406'
out = pathlib.Path('data/raw/chap'); out.mkdir(parents=True, exist_ok=True)
bbox = (113.70, 30.00, 115.10, 31.40)   # 武汉大致范围

def get_month(m):
    name = 'CHAP_PM2.5_M1K_%s_V4.nc' % m
    p = out / name
    if not p.exists():
        url = 'https://zenodo.org/api/records/%s/files/%s/content' % (rec, name)
        for i in range(3):
            try:
                t = time.time()
                with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=180) as r, open(p,'wb') as f:
                    f.write(r.read())
                print('  dl %s %.1f MB %.1fs' % (name, p.stat().st_size/1e6, time.time()-t)); break
            except Exception as e:
                print('  retry', i, type(e).__name__); time.sleep(3)
    with rasterio.open(p) as src:
        scale = float(src.tags().get('PM2.5#scale_factor', 1.0))
        win = src.window(*bbox)
        a = src.read(1, window=win, boundless=True, fill_value=65535).astype('float32')
    v = a[a != 65535] * scale
    return v

print('武汉 PM2.5 月均（1 km 网格，市域外接矩形）')
for m in ['202401', '202407', '202411']:
    v = get_month(m)
    print('  %s  n=%7d  中位 %.1f  均值 %.1f  p10 %.1f  p90 %.1f  µg/m³' % (m, len(v), np.median(v), v.mean(), np.percentile(v,10), np.percentile(v,90)))

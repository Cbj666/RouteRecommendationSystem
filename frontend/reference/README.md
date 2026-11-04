# reference —— PPT 那张原型图的「可运行参考实现」

这个目录只有一个 `index.html`，作用是把「同样的数据画成同样的画面」这件事**证明给你看**，
不是让谁直接用。它用原生 JS + SVG，零依赖、零构建，1600×1000 画布。

```powershell
# 在仓库根目录起一个静态服务（file:// 下 fetch 会被浏览器拦，必须走 http）
.\.venv\Scripts\python.exe -m http.server 8080
```

打开 <http://127.0.0.1:8080/frontend/reference/index.html>，应当看到和 PPT 第 6 页同一张图：
米白底、按分数上色的路网、一条白描边黑实线的环线、左右两块毛玻璃面板。

## 它读哪三个文件

| 文件 | 用来画什么 |
|---|---|
| `data/output/running/v1/web/segments_city.geojson` | 路网，按 `score` 上色（8,005 段 / 1.8 MB） |
| `data/output/running/v1/web/water_green.geojson` | 水体与绿地（可选，PPT 那张其实没画） |
| `frontend/app/src/mocks/loops_5km_wuda.json` | 黑色环线（真实后端响应，形状同 `POST /api/loops`） |

## 要从它这里抄走的四件事

1. **投影**：`x = (lon - lon0) / (lon1 - lon0) * W`，`y = (lat1 - lat) / (lat1 - lat0) * H`。
   这套等比投影之所以不变形，是因为 `VIEW` 那个 bbox 在纬度 30.5° 处正好是 1.6:1；换 bbox 要自己算。
   真做产品用地图库（BMapGL / MapLibre），别自己投。
2. **色阶**：`t = clamp((score - 30) / 42, 0, 1)`，在 `#D94F4F → #E8A33D → #8FBF6A → #2E7A5D → #15503C`
   五档间线性插值。**这是和 PPT 完全一致的那个算法**，别自己另定一套（很容易偏成一片通红）。
3. **线宽**：路网 1.25 px（等价 matplotlib 的 `linewidths=0.9 @ dpi100`）；环线两层——
   白 `9.2 px` 打底、黑 `5.3 px` 压上，端点/拐角都是 `round`。
4. **绘制顺序**：水绿 → 低分路段 → 高分路段 → 环线 → 起点圆点。
   先把低分画掉，高分才不会被子盖住。

## 它故意没做的事

- 没有交互（点击、拖拽、缩放）：那是地图库的活，抄个渲染逻辑就行；
- 面板里所有数字是写死的（78.5 / 5.34 km …），只为对齐视觉，不代表要这么写死；
- 百度底图、BD-09 偏移都没接——`.env.local` 里配 `VITE_BAIDU_AK` 之后由 BMapGL 负责。

想核对「有没有画歪」，把它和 `presentation/前端原型图.png` 并排看：
路网的疏密、那条环线的形状、图例的位置，都应当能对上。

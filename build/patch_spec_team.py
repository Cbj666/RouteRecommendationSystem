from pathlib import Path

p = Path('docs/项目说明书.md')
s = p.read_text(encoding='utf-8')

old = """## 十一、小组分工

见 `docs/分工卡片.md`（按角色列出负责模块、交付物与证据路径）。"""
new = """## 十一、小组分工

七人分三组 + 组长：

| 组 | 人 | 负责层 | 主要交付 |
|---|---|---|---|
| 前端组 | 2 | 表现层 + 接口契约 | 可点交互页、地图层（BMapGL）、`docs/接口契约.md` |
| 后端组 | 3 | 接口层 + 算法层 | 5 个端点（Python / FastAPI，含缓存、校验、错误码） |
| 热点分析 | 1 | 算法层·空间分析 | 50 起点热点图与结论 |
| 组长 | 1 | 数据层 + 文档答辩 | 四份底表、说明书、PPT、讲稿 |

技术路线：后端 **Python（FastAPI）**，单进程单端口，`/docs` 即接口文档；不引入 Java 网关或 gRPC。
按角色列出的模块、交付物与证据路径见 `docs/分工卡片.md`。"""
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('说明书 §十一 已更新，字数', len(s))

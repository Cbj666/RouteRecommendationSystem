/**
 * 地图绘制开关。
 *
 * 水/绿面：reference/index.html 会画，但 PPT 那张原型图**没有画**（见
 * frontend/reference/README.md：「水体与绿地（可选，PPT 那张其实没画）」）。
 * 验收基准是 PPT，所以默认关闭；打开后是淡蓝/淡绿半透明面。
 */
export const DRAW_WATER_GREEN = false

/**
 * 起点标记：PPT 那张原型的路网图层里没有起点圆点（make_map.py 只画环线），
 * 默认关闭以逐像素对齐。M2 交互时可打开，用圆点反馈「起点已改变」。
 */
export const DRAW_ORIGIN_MARKER = false


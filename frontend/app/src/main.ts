import { createApp, h } from 'vue'

/**
 * 冒烟页（占位）。真正的页面由前端组来写：
 *   1. 在 src/ 下新建 App.vue（或任意页面组件）
 *   2. 把下面这段换掉：createApp(App).mount('#app')
 *
 * 数据与接口层已经就绪，不需要动：
 *   - src/types.ts      ← 与后端真实响应一致的类型
 *   - src/api/client.ts ← 5 个接口函数 + ApiError + mock 开关
 *   - src/mocks/        ← 真实响应快照，VITE_USE_MOCK=1 时用它跑
 *
 * 契约见仓库根目录 docs/接口契约.md。
 */
const Placeholder = {
  render() {
    return h(
      'div',
      {
        style:
          'font-family:system-ui,"Microsoft YaHei",sans-serif;color:#1F2A26;' +
          'max-width:760px;margin:12vh auto;padding:0 24px;line-height:1.7',
      },
      [
        h('div', { style: 'font-size:13px;letter-spacing:.18em;color:#4F9D7D' }, 'RUNNING SUITABILITY · WUHAN'),
        h('h1', { style: 'font-size:34px;margin:10px 0 18px' }, '前端骨架已就绪，页面留给你来写'),
        h('p', { style: 'color:#5F6F68;margin:0 0 22px' },
          '这里现在是占位页。删掉它，写你自己的 App.vue —— 数据、类型、接口函数都已经备好。'),
        h('ul', { style: 'margin:0 0 24px;padding-left:20px;color:#1F2A26' }, [
          h('li', {}, '看接口：docs/接口契约.md（11 个端点 + 真实样例）'),
          h('li', {}, '看类型：src/types.ts（字段以后端真实响应为准）'),
          h('li', {}, '无后端联调：.env.local 里写 VITE_USE_MOCK=1'),
        ]),
        h('p', { style: 'color:#8A9A93;font-size:13px;margin:0' },
          'npm run dev → http://127.0.0.1:5173'),
      ]
    )
  },
}

createApp(Placeholder).mount('#app')

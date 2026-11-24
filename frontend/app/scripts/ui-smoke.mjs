/**
 * 前端交付冒烟，使用 Edge headless 与 CDP。
 * UI_REAL=1 覆盖真实路线、42 km、厕所、详情、双点对比与单侧失败。
 * 默认 mock 覆盖候选、四页签、热点网格、对比、加载/空/异常与窄屏。
 * UI_URL 指向开发服务器。UI_SCREENSHOTS=1 可选截图。
 * 记录写入 data/output/ui/<UI_OUT>，默认 frontend-delivery。
 */
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = resolve(HERE, '../../../data/output/ui', process.env.UI_OUT || 'frontend-delivery')
const REAL = process.env.UI_REAL === '1'
const SCREENSHOTS = process.env.UI_SCREENSHOTS === '1'
const URL_APP = process.env.UI_URL || 'http://127.0.0.1:5173/'
const PORT = Number(process.env.CDP_PORT || 9333)
const EDGE =
  process.env.EDGE ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitForJson(url, tries = 60) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url)
      if (r.ok) return await r.json()
    } catch {
      /* 浏览器还没起来 */
    }
    await sleep(250)
  }
  throw new Error(`CDP 没有就绪：${url}`)
}

const proc = spawn(
  EDGE,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    '--window-size=1600,1000',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${resolve(process.env.TEMP || '/tmp', `dsh-ui-smoke-${PORT}`)}`,
    'about:blank',
  ],
  { stdio: 'ignore' },
)

let ws
const pageErrors = []
const consoleErrors = []
const failedRequests = []
try {
  const list = await waitForJson(`http://127.0.0.1:${PORT}/json/list`)
  const page = list.find((t) => t.type === 'page' && t.url === 'about:blank')
  if (!page) throw new Error('没有找到页面 target')

  ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.onopen = res
    ws.onerror = () => rej(new Error('WebSocket 连接失败'))
  })

  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? rej(new Error(msg.error.message)) : res(msg.result)
      return
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      pageErrors.push(d.exception?.description || d.text)
    } else if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
      consoleErrors.push(msg.params.entry.text)
    } else if (msg.method === 'Network.loadingFailed') {
      failedRequests.push(msg.params.errorText)
    }
  }
  const send = (method, params = {}) =>
    new Promise((res, rej) => {
      const id = ++seq
      const timeout = setTimeout(() => {
        pending.delete(id)
        rej(new Error(`CDP 命令超时：${method}`))
      }, 20000)
      pending.set(id, {
        res: (result) => { clearTimeout(timeout); res(result) },
        rej: (error) => { clearTimeout(timeout); rej(error) },
      })
      ws.send(JSON.stringify({ id, method, params }))
    })

  const evalJs = async (expression) => {
    const r = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (r.exceptionDetails) {
      throw new Error(r.exceptionDetails.exception?.description || 'evaluate 失败')
    }
    return r.result.value
  }

  await send('Runtime.enable')
  await send('Page.enable')
  await send('Log.enable')
  await send('Network.enable')
  // headless 窗口含边框，实际视口会小几像素；固定成 1600×1000 再截图
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1600,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await send('Page.navigate', { url: URL_APP })
  await send('Page.bringToFront')

  const waitUntil = async (expr, timeout = 30000) => {
    const t0 = Date.now()
    while (Date.now() - t0 < timeout) {
      if (await evalJs(expr)) return true
      await sleep(150)
    }
    return false
  }


  const checks = []
  async function check(name, expression) {
    const ok = await waitUntil("Boolean(" + expression + ")", 30000)
    checks.push({ name, ok })
    console.log((ok ? 'PASS  ' : 'FAIL  ') + name)
    if (!ok) throw new Error(name + '\n' + await evalJs("JSON.stringify({text:document.body.innerText,width:document.documentElement.scrollWidth,wide:Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right > innerWidth+1).slice(0,12).map(e=>({tag:e.tagName,cl:String(e.className),w:e.getBoundingClientRect().width}))})"))
  }
  const click = (selector) => evalJs("document.querySelector(" + JSON.stringify(selector) + ").click()")
  const tab = async (index) => {
    await evalJs("document.querySelectorAll('.tabs .tab')[" + index + "].click()")
    await check('页签 ' + index + ' 高亮', "document.querySelectorAll('.tabs .tab')[" + index + "].classList.contains('on')")
  }
  const capture = async (name) => {
    if (!SCREENSHOTS) return
    await mkdir(OUT, { recursive: true })
    const result = await send('Page.captureScreenshot', { format: 'png' })
    await writeFile(resolve(OUT, name + '.png'), Buffer.from(result.data, 'base64'))
  }
  await check('地图与数据图层就绪', "document.querySelector('g[data-layer=roads] path') && document.querySelector('.layers') && document.querySelector('.map-details')")
  await check('地图视图隐藏路线条件', "!document.querySelector('.left')")
  await tab(3)
  await check('热点页签与网格', "document.querySelector('.hotspot-rank h3')?.textContent.includes('武汉跑步热点地图') && document.querySelectorAll('.hotspot-overlay path').length > 50 && document.querySelector('.hotspot-detail')")
  await capture('hotspot-desktop')
  await tab(0)
  await click('[data-layer="water"] .layer-check')
  await check('关闭水体', "!document.querySelector('g[data-layer=water]')")
  await click('[data-layer="water"] .layer-check')
  await check('恢复水体', "document.querySelector('g[data-layer=water] path')")
  if (REAL) {
    await click('.toilet-options label:first-child input')
    await check('公共厕所加载', "document.querySelectorAll('g[data-layer=toilets] circle').length > 1000")
    await click('.toilet-options label:last-child input')
    await check('无障碍筛选', "document.querySelectorAll('g[data-layer=toilets] circle').length > 0 && document.querySelectorAll('g[data-layer=toilets] circle').length < 1000")
    await evalJs("document.querySelector('.map-host').dispatchEvent(new MouseEvent('click', {clientX: 800, clientY: 500, bubbles: true}))")
    await evalJs("(()=>{const host=document.querySelector('.map-host');const rect=host.getBoundingClientRect();host.dispatchEvent(new MouseEvent('click',{clientX:rect.x+(114.354694-114.305)/0.1*rect.width,clientY:rect.y+(30.562-30.534203)/0.054*rect.height,bubbles:true}))})()")
    await check('路段六维和高亮', "document.querySelectorAll('.road-detail tbody tr').length === 6 && document.querySelector('g[data-layer=selection] path')")
    await capture('road-detail')
  }
  await tab(1)
  await check('环线生成与地图路线', "document.querySelector('.score b') && document.querySelector('g[data-layer=route] path') && !document.querySelector('.pill')")
  await click('.cand .cbtn:last-child')
  await check('切换候选', "document.querySelector('.cidx').textContent.startsWith('2/')")
  await evalJs("document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowLeft',bubbles:true}))")
  await check('键盘候选切换', "document.querySelector('.cidx').textContent.startsWith('1/')")
  if (REAL) {
    await evalJs("document.querySelectorAll('.segs')[0].querySelectorAll('button')[1].click()")
    await check('单行线与终点', "document.querySelector('.rt').textContent.includes('单行线') && document.querySelector('g[data-layer=marker]').textContent.includes('终') && !document.querySelector('.pill')")
    await capture('oneway')
    await evalJs("document.querySelectorAll('.segs')[0].querySelector('button').click()")
    await check('恢复环线', "document.querySelector('.rt').textContent.includes('环线') && !document.querySelector('.pill')")
    await evalJs("const input=document.querySelector('.custom-distance input'); input.value='42'; input.dispatchEvent(new Event('change',{bubbles:true}))")
    await check('42 km 路线', "document.querySelector('.cell b')?.textContent.includes('km') && !document.querySelector('.pill') && !document.querySelector('.box.err')")
    await evalJs("document.querySelectorAll('.segs')[1].querySelectorAll('button')[1].click()")
    await check('恢复 5 km', "document.querySelector('.cell b') && !document.querySelector('.pill')")
  }
  await tab(2)
  await check('顶部导航保持可见', "document.querySelectorAll('.topbar').length === 1 && document.querySelector('.compare-page')")
  await evalJs("var b=document.querySelector('select[aria-label=\"起点 B\"]');b.value='1';b.dispatchEvent(new Event('change',{bubbles:true}))")
  await check('对比可提交', "!document.querySelector('.submit').disabled")
  await click('.submit')
  await check('双起点真实路线与差值', "document.querySelectorAll('.compare-map path[data-side]').length === 2 && document.querySelector('.difference') && !document.querySelector('.submit').textContent.includes('正在')")
  await capture('compare-desktop')
  await tab(0)
  await tab(2)
  await check('返回后对比结果保留', "document.querySelectorAll('.compare-map path[data-side]').length === 2 && document.querySelector('.difference')")
  if (REAL) {
    await evalJs("document.querySelector('.controls input[type=checkbox]').click()")
    await check('修改条件清除旧结果', "!document.querySelector('.difference') && document.querySelectorAll('.compare-map path[data-side]').length === 0")
    await click('.submit')
    await check('修改偏好后可重新比较', "document.querySelector('.difference') && document.querySelectorAll('.compare-map path[data-side]').length === 2")
  }

  if (REAL) {
    await evalJs("document.querySelectorAll('.pick')[1].click()")
    await evalJs("(async()=>{const manifest=await (await fetch('/geo/manifest.json')).json();const {project,fitViewBBox}=await import('/src/lib/projection.ts');const c=manifest.view.city;const [x,y]=project(fitViewBBox([c.lon0,c.lat0,c.lon1,c.lat1],24),114.3805,30.549);const host=document.querySelector('.map-host');const svg=host.querySelector('svg');const view=svg.viewBox.baseVal;const rect=host.getBoundingClientRect();host.dispatchEvent(new MouseEvent('click',{clientX:rect.x+(x-view.x)/view.width*rect.width,clientY:rect.y+(y-view.y)/view.height*rect.height,bubbles:true}))})()")
    await check('地图设置 B 起点', "document.querySelector('select[aria-label=\"起点 B\"]').value === '' && !document.querySelector('.submit').disabled")
    await click('.submit')
    await check('单侧失败保留另一侧', "document.querySelectorAll('.compare-map path[data-side]').length === 1 && document.querySelectorAll('.side-status button').length === 1 && !document.querySelector('.difference')")
    await evalJs("var b=document.querySelector('select[aria-label=\"起点 B\"]');b.value='1';b.dispatchEvent(new Event('change',{bubbles:true}))")
    await check('修正起点可提交', "!document.querySelector('.submit').disabled")
    await click('.submit')
    await check('修正后恢复双侧', "document.querySelectorAll('.compare-map path[data-side]').length === 2 && document.querySelector('.difference')")
  }
  await send('Emulation.setDeviceMetricsOverride', { width:390,height:844,deviceScaleFactor:1,mobile:false })
  await check('390 px 对比无横向溢出', "document.documentElement.scrollWidth <= 390 && document.querySelectorAll('.tabs .tab').length === 4")
  await capture('compare-mobile')
  await tab(1)
  await check('窄屏推荐结果可见', "document.querySelector('.right') && document.documentElement.scrollWidth <= 390")
  await tab(3)
  await check('窄屏热点页可读', "document.querySelector('.hotspot-rank') && document.querySelector('.hotspot-detail') && document.documentElement.scrollWidth <= 390")
  await capture('hotspot-mobile')
  await send('Emulation.setDeviceMetricsOverride', { width:320,height:568,deviceScaleFactor:1,mobile:false })
  await check('320 px 无横向溢出', "document.documentElement.scrollWidth <= 320")
  if (!REAL) {
    for (const scenario of ['empty', 'error', 'slow']) {
      await send('Page.navigate', { url: URL_APP + '?mock=' + scenario })
      await check('场景导航 ' + scenario, "document.querySelectorAll('.tabs .tab').length === 4")
      await tab(1)
      await check('路线状态 ' + scenario, scenario === 'empty' ? "document.querySelector('.box.notice')" :
        scenario === 'error' ? "document.querySelector('.box.err')" : "document.querySelector('.pill')")
      await tab(2)
      await evalJs("var b=document.querySelector('select[aria-label=\"起点 B\"]');b.value='1';b.dispatchEvent(new Event('change',{bubbles:true}))")
      await check('场景对比可提交', "!document.querySelector('.submit').disabled")
      await click('.submit')
      await check('双侧状态 ' + scenario, scenario === 'empty' ?
        "Array.from(document.querySelectorAll('.side-status')).every(e=>e.textContent.includes('无合适路线'))" :
        scenario === 'error' ? "document.querySelectorAll('.side-status button').length === 2" :
        "document.querySelector('.submit').textContent.includes('正在')")
    }
  }
  if (pageErrors.length) throw new Error(pageErrors.join('\n'))
  await mkdir(OUT, { recursive: true })
  await writeFile(resolve(OUT, 'checks.json'), JSON.stringify({ real:REAL, checks, pageErrors, consoleErrors, failedRequests }, null, 2))
  console.log(checks.length + '/' + checks.length + ' passed')
} finally {
  ws?.close()
  proc.kill()
}

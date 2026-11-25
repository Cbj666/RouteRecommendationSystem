<script setup lang="ts">
import { computed } from 'vue'
import { GRADE_COLORS, GRADE_LABELS } from '../lib/color'
import { selectedHotspot, useHotspotAsOrigin } from '../stores/hotspot'

const dimensions = [
  { key: 's_safety', label: '安全', weight: 0.36 },
  { key: 's_green', label: '绿化', weight: 0.26 },
  { key: 's_slope', label: '坡度', weight: 0.06 },
  { key: 's_cross', label: '过街', weight: 0.15 },
  { key: 's_fac', label: '设施', weight: 0.06 },
  { key: 's_air', label: '空气', weight: 0.11 },
] as const

const topDimensions = computed(() => {
  const cell = selectedHotspot.value
  if (!cell) return []
  return [...dimensions]
    .sort((a, b) => cell.subs[b.key] - cell.subs[a.key])
    .slice(0, 2)
})

function gradeColor(grade: string): string {
  const index = GRADE_LABELS.indexOf(grade)
  return GRADE_COLORS[index < 0 ? GRADE_COLORS.length - 1 : index]
}
</script>

<template>
  <aside class="hotspot-detail glass" aria-label="热点格详情">
    <template v-if="selectedHotspot">
      <div class="head">
        <div>
          <p class="eyebrow">{{ selectedHotspot.isHotspot ? '高值聚集格' : '网格单元' }}<template v-if="selectedHotspot.rank > 0"> · 第 {{ selectedHotspot.rank }} 名</template><template v-else> · 样本不足 1 km</template></p>
          <h3>{{ selectedHotspot.name }}</h3>
          <p class="cluster">{{ selectedHotspot.cluster }}</p>
        </div>
        <span class="badge" :style="{ background: gradeColor(selectedHotspot.grade) }">
          {{ selectedHotspot.grade }}
        </span>
      </div>

      <div class="score-box">
        <strong class="num">{{ selectedHotspot.score.toFixed(1) }}</strong>
        <span>/ 100</span>
        <small>格内按路段长度加权</small>
      </div>

      <dl class="meta">
        <div><dt>样本路段</dt><dd>{{ selectedHotspot.nSeg }} 段</dd></div>
        <div><dt>覆盖长度</dt><dd>{{ Math.round(selectedHotspot.lenM) }} m</dd></div>
        <div><dt>热点判定</dt><dd>{{ selectedHotspot.isHotspot ? '是 · 高值簇' : '否' }}</dd></div>
      </dl>

      <section class="dims" aria-label="六维子分">
        <h4>六维子分</h4>
        <div v-for="dim in dimensions" :key="dim.key" class="dim-row">
          <span class="dim-label">{{ dim.label }}</span>
          <span class="bar"><i :style="{ width: selectedHotspot.subs[dim.key] + '%' }"></i></span>
          <span class="dim-score num">{{ selectedHotspot.subs[dim.key].toFixed(0) }}</span>
          <span class="dim-weight num">{{ Math.round(dim.weight * 100) }}%</span>
        </div>
      </section>

      <p class="explain">
        高分主要来自
        <b>{{ topDimensions[0]?.label }}</b>
        与
        <b>{{ topDimensions[1]?.label }}</b>
        两个维度。
      </p>

      <button type="button" class="cta" @click="useHotspotAsOrigin">
        以此处为起点
      </button>
      <p class="note">
        只回填起点，不自动生成路线。网格由离线脚本按 1 km 聚合，评分为样本路段的长度加权平均。
      </p>
    </template>
    <p v-else class="empty">点击地图上的网格或左侧榜单查看详情。</p>
  </aside>
</template>

<style scoped>
.hotspot-detail {
  position: absolute;
  top: 88px;
  right: 24px;
  width: 326px;
  max-height: 740px;
  overflow: auto;
  padding: 18px;
  z-index: 4;
  font-size: 12.5px;
  line-height: 1.55;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.eyebrow {
  color: var(--muted);
  font-size: 10.5px;
  letter-spacing: 0.02em;
}

h3 {
  margin-top: 3px;
  font-size: 18px;
  line-height: 1.3;
}

.cluster {
  margin-top: 2px;
  color: var(--sub);
  font-size: 11px;
}

.badge {
  flex: none;
  padding: 3px 9px;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.score-box {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 14px 0 10px;
  padding: 10px 12px;
  background: rgba(231, 241, 234, 0.72);
  border-left: 3px solid var(--accent);
}

.score-box strong {
  color: var(--accent);
  font-size: 30px;
  line-height: 1;
}

.score-box span {
  color: var(--muted);
  font-size: 11px;
}

.score-box small {
  margin-left: auto;
  color: var(--muted);
  font-size: 10px;
}

.meta {
  display: grid;
  gap: 5px;
  margin-bottom: 14px;
}

.meta div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--line);
}

.meta dt {
  color: var(--muted);
}

.meta dd {
  color: var(--ink);
  font-weight: 600;
}

.dims h4 {
  margin-bottom: 7px;
  font-size: 12px;
}

.dim-row {
  display: grid;
  grid-template-columns: 32px 1fr 28px 30px;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}

.dim-label {
  color: var(--sub);
  font-size: 11px;
}

.bar {
  height: 5px;
  overflow: hidden;
  background: rgba(21, 80, 60, 0.1);
}

.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
}

.dim-score {
  text-align: right;
  font-size: 11px;
  font-weight: 600;
}

.dim-weight {
  color: var(--muted);
  text-align: right;
  font-size: 10px;
}

.explain {
  margin-top: 12px;
  padding: 9px 10px;
  color: var(--sub);
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid var(--line);
  font-size: 11px;
}

.explain b {
  color: var(--accent);
}

.cta {
  width: 100%;
  margin-top: 14px;
  padding: 10px 12px;
  color: #fff;
  background: var(--accent);
  font-size: 12.5px;
  font-weight: 600;
}

.cta:hover {
  background: #1c644b;
}

.note {
  margin-top: 8px;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.5;
}

.empty {
  color: var(--muted);
}
</style>

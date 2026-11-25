<script setup lang="ts">
import { computed } from 'vue'
import { activeLoop, state } from '../stores/planner'
import { GRADE_BINS, GRADE_COLORS, GRADE_LABELS } from '../lib/color'
import { fmtKm } from '../lib/format'

const length = computed(() => {
  const m = activeLoop.value?.properties.length_m
  return m ? fmtKm(m) : '—'
})
</script>

<template>
  <div class="legend glass">
    <h5>慢跑适宜性</h5>
    <div v-for="(label, index) in GRADE_LABELS" :key="label" class="grade-row">
      <i :style="{ background: GRADE_COLORS[index] }"></i>{{ label }}
      {{
        index === 0
          ? '≤ ' + GRADE_BINS[0]
          : index === 4
            ? '> ' + GRADE_BINS[3]
            : '(' + GRADE_BINS[index - 1] + ', ' + GRADE_BINS[index] + ']'
      }}
    </div>

    <div class="poi-legend">
      <div class="poi-row">
        <span class="sym sym-facility" aria-hidden="true"></span>运动场馆
      </div>
      <div class="poi-row">
        <span class="sym sym-toilet" aria-hidden="true"></span>公共厕所
      </div>
      <div class="poi-row">
        <span class="sym sym-toilet sym-accessible" aria-hidden="true"></span>无障碍公厕
      </div>
      <div class="poi-row">
        <span class="sym sym-cluster" aria-hidden="true"></span>整城设施聚合（越大越多）
      </div>
    </div>

    <div v-if="state.tab === 'loops'" class="lk">
      <span class="line" aria-hidden="true"></span>推荐路线 {{ length }}
    </div>
  </div>
</template>

<style scoped>
.grade-row {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  line-height: 1.6;
}
.grade-row i {
  display: inline-block;
  width: 14px;
  height: 4px;
}
.legend {
  position: absolute;
  right: 380px;
  bottom: 24px;
  padding: 12px 16px;
  font-size: 12px;
  color: var(--sub);
  z-index: 4;
}

h5 {
  font-size: 12px;
  color: var(--ink);
  font-weight: 600;
  margin-bottom: 6px;
}

.poi-legend {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.poi-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  line-height: 1.35;
}

.sym {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.sym-facility {
  width: 10px;
  height: 10px;
  margin-inline: 2px;
  background: #c2410c;
  border-radius: 2px;
  box-shadow: 0 0 0 1px #fff;
}

.sym-toilet {
  width: 10px;
  height: 10px;
  margin-inline: 2px;
  background: #1d4ed8;
  border-radius: 50%;
  box-shadow: 0 0 0 1.5px #fff, 0 0 0 2px rgba(29, 78, 216, 0.28);
  position: relative;
}

.sym-accessible::after {
  content: '';
  width: 3.5px;
  height: 3.5px;
  border-radius: 50%;
  background: #fff;
}

.sym-cluster {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #374151;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  box-shadow: 0 0 0 1px #fff;
}

.lk {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
  white-space: nowrap;
}

.line {
  width: 14px;
  height: 3px;
  background: #1b1b1b;
  display: inline-block;
  flex: none;
}
</style>

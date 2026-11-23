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
      {{ index === 0 ? '≤ ' + GRADE_BINS[0] : index === 4 ? '> ' + GRADE_BINS[3] : '(' + GRADE_BINS[index - 1] + ', ' + GRADE_BINS[index] + ']' }}
    </div>
    <div v-if="state.tab === 'loops'" class="lk">
      <span class="line" aria-hidden="true"></span>推荐路线 {{ length }}
    </div>
  </div>
</template>

<style scoped>
.grade-row { display: flex; gap: 8px; align-items: center; font-size: 12px; line-height: 1.6; }
.grade-row i { display: inline-block; width: 14px; height: 4px; }
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
  margin-bottom: 8px;
}

.ramp {
  width: 118px;
  height: 8px;
  background: linear-gradient(90deg, #d94f4f, #e8a33d, #8fbf6a, #2e7a5d, #15503c);
}

.lscale {
  display: flex;
  justify-content: space-between;
  width: 118px;
  font-size: 10.5px;
  line-height: 1;
  color: var(--muted);
  margin-top: 4px;
}

.lk {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
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

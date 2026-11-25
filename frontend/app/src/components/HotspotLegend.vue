<script setup lang="ts">
import { GRADE_BINS, GRADE_COLORS, GRADE_LABELS } from '../lib/color'
</script>

<template>
  <div class="legend hotspot-legend glass">
    <h5>网格评分</h5>
    <div v-for="(label, index) in GRADE_LABELS" :key="label" class="grade-row">
      <i :style="{ background: GRADE_COLORS[index] }"></i>{{ label }}
      {{ index === 0 ? '≤ ' + GRADE_BINS[0] : index === 4 ? '> ' + GRADE_BINS[3] : '(' + GRADE_BINS[index - 1] + ', ' + GRADE_BINS[index] + ']' }}
    </div>
    <div class="keys">
      <span><i class="hotspot-swatch"></i>热点格</span>
      <span><i class="selected-swatch"></i>当前格</span>
    </div>
  </div>
</template>

<style scoped>
.hotspot-legend {
  position: absolute;
  right: 380px;
  bottom: 24px;
  padding: 12px 16px;
  z-index: 4;
  color: var(--sub);
  font-size: 12px;
}

h5 {
  margin-bottom: 8px;
  color: var(--ink);
  font-size: 12px;
  font-weight: 600;
}

.grade-row {
  display: flex;
  gap: 8px;
  align-items: center;
  line-height: 1.6;
}

.grade-row i {
  display: inline-block;
  width: 14px;
  height: 4px;
}

.keys {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 7px;
  white-space: nowrap;
}

.keys span {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}

.hotspot-swatch,
.selected-swatch {
  display: inline-block;
  width: 14px;
  height: 8px;
}

.hotspot-swatch {
  border: 1px solid var(--accent);
  background: rgba(21, 80, 60, 0.18);
}

.selected-swatch {
  border: 2px solid #1f2a26;
  background: rgba(21, 80, 60, 0.34);
}
</style>

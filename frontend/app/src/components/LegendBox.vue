<script setup lang="ts">
import { computed } from 'vue'
import { activeLoop } from '../stores/planner'
import { fmtKm } from '../lib/format'

const length = computed(() => {
  const m = activeLoop.value?.properties.length_m
  return m ? fmtKm(m) : '—'
})
</script>

<template>
  <div class="legend glass">
    <h5>慢跑适宜性</h5>
    <div class="ramp" aria-hidden="true"></div>
    <div class="lscale"><span>30</span><span>50</span><span>70</span><span>85</span></div>
    <div class="lk">
      <span class="line" aria-hidden="true"></span>推荐环线 {{ length }}
    </div>
  </div>
</template>

<style scoped>
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

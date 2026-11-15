<script setup lang="ts">
import {
  generate,
  setMode,
  setTarget,
  state,
  targetOptions,
  togglePref,
  type PlannerState,
} from '../stores/planner'

const prefRows: { key: keyof PlannerState['prefs']; label: string }[] = [
  { key: 'green', label: '尽量绿荫 / 滨水' },
  { key: 'safe', label: '避开机动车主干道' },
  { key: 'flat', label: '尽量平坦' },
  { key: 'facility', label: '洗手间 / 补给点' },
]
</script>

<template>
  <section class="left glass" aria-label="路线条件">
    <div class="label">起点</div>
    <div class="origin">
      <div class="pin" aria-hidden="true">起</div>
      <div class="origin-text">
        <b>{{ state.origin.name }}</b>
        <span class="num">
          {{ state.origin.lng.toFixed(4) }}, {{ state.origin.lat.toFixed(4) }}
        </span>
      </div>
    </div>

    <div class="row">
      <div class="label">路线模式</div>
      <div class="segs" role="group" aria-label="路线模式">
        <button class="seg" :class="{ on: state.mode === 'loop' }" @click="setMode('loop')">
          环线
        </button>
        <button
          class="seg"
          disabled
          title="单行线 A→B 需要后端新增 mode 参数（契约缺口 G1），当前版本只支持环线"
        >
          单行线 A→B
        </button>
      </div>
    </div>

    <div class="row">
      <div class="label">目标距离</div>
      <div class="segs" role="group" aria-label="目标距离">
        <button
          v-for="m in targetOptions"
          :key="m"
          class="seg"
          :class="{ on: state.targetM === m }"
          @click="setTarget(m)"
        >
          {{ m / 1000 }} km
        </button>
      </div>
    </div>

    <div class="row">
      <div class="label">偏好</div>
      <div class="prefs">
        <button
          v-for="p in prefRows"
          :key="p.key"
          class="pref"
          role="switch"
          :aria-checked="state.prefs[p.key]"
          :aria-label="p.label"
          :title="p.key === 'facility' ? '设施图层：后端暂未提供 kind 字段（契约缺口 G4），当前只保留开关' : undefined"
          @click="togglePref(p.key)"
        >
          <span>{{ p.label }}</span>
          <span class="sw" :class="{ on: state.prefs[p.key] }" aria-hidden="true"><i></i></span>
        </button>
      </div>
    </div>

    <button class="cta" :disabled="state.loading" @click="generate">
      {{ state.loading ? '正在生成…' : '生成路线' }}
      <small>环线：半程折返 + 回程双向惩罚</small>
    </button>
  </section>
</template>

<style scoped>
.left {
  position: absolute;
  left: 24px;
  top: 88px;
  width: 306px;
  padding: 22px 22px 0;
  z-index: 4;
}

.label {
  font-size: 13px;
  color: var(--muted);
  letter-spacing: 1px;
  margin-bottom: 10px;
}

.origin {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}

.pin {
  width: 26px;
  height: 26px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex: none;
}

.origin-text b {
  display: block;
  font-size: 16px;
  line-height: 1.35;
  margin-bottom: 4px;
  word-break: break-word;
}

.origin-text span {
  font-size: 12.5px;
  color: var(--faint);
}

.row {
  margin-top: 20px;
}

.segs {
  display: flex;
  gap: 8px;
}

.seg {
  flex: 1;
  text-align: center;
  padding: 9px 0;
  font-size: 14px;
  border: 1px solid #dfe8e3;
  color: var(--sub);
  background: transparent;
}

.seg.on {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 600;
}

.seg:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.prefs {
  display: flex;
  flex-direction: column;
}

.pref {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 11px 0;
  font-size: 14.5px;
  border-bottom: 1px dashed var(--dash);
  text-align: left;
  background: transparent;
}

.sw {
  width: 42px;
  height: 22px;
  background: #d7e0da;
  position: relative;
  display: inline-block;
  flex: none;
  transition: background 0.15s ease;
}

.sw i {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: left 0.15s ease;
}

.sw.on {
  background: var(--accent);
}

.sw.on i {
  left: 23px;
}

.cta {
  display: block;
  width: calc(100% + 44px);
  margin: 26px 0 0 -22px;
  background: var(--accent);
  color: #fff;
  text-align: center;
  padding: 17px 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}

.cta:disabled {
  opacity: 0.75;
}

.cta small {
  display: block;
  font-weight: 400;
  font-size: 11.5px;
  color: #bfd8cc;
  margin-top: 5px;
  letter-spacing: 0;
}

@media (prefers-reduced-motion: reduce) {
  .sw,
  .sw i {
    transition: none;
  }
}
</style>

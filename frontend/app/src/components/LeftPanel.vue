<script setup lang="ts">
import { computed } from 'vue'
import {
  generate,
  setMode,
  setPickingPoint,
  setTarget,
  state,
  targetOptions,
  togglePref,
  type PlannerState,
} from '../stores/planner'
import { USE_MOCK } from '../api/client'

const prefRows: { key: keyof PlannerState['prefs']; label: string }[] = [
  { key: 'green', label: '尽量绿荫 / 滨水' },
  { key: 'safe', label: '避开机动车主干道' },
  { key: 'flat', label: '尽量平坦' },
]

const onewayHint = computed(() => {
  if (!state.onewayA) return '先点地图选起点，再点终点'
  if (!state.onewayB) return '已选起点 A，请点地图选终点 B'
  return state.pickingPoint === 'A'
    ? '点击地图重选起点 A'
    : '点地图可直接重选终点 B；点 A 卡重选起点'
})

const ctaDisabled = computed(() => {
  if (state.loading) return true
  if (state.mode === 'oneway') return !state.onewayA || !state.onewayB
  return false
})

const ctaSubtitle = computed(() => {
  if (state.mode === 'loop') return '返回起点的闭合路线'
  if (!state.onewayA || !state.onewayB) return '请在地图上依次点选起点 A 与终点 B'
  return '按已选起点 A 与终点 B 生成路线'
})
</script>

<template>
  <section class="left glass" aria-label="路线条件">
    <div class="label">路线模式</div>
    <div class="segs mode-segs" role="group" aria-label="路线模式">
      <button class="seg" :class="{ on: state.mode === 'loop' }" @click="setMode('loop')">
        环线
      </button>
      <button class="seg" :class="{ on: state.mode === 'oneway' }" @click="setMode('oneway')">
        单行线 A→B
      </button>
    </div>

    <!-- 环线模式：单起点 + 目标距离 -->
    <template v-if="state.mode === 'loop'">
      <div class="row">
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
        <label v-if="!USE_MOCK" class="custom-distance">
          自定义距离（km）
          <input
            type="number"
            min="1"
            max="42"
            step="0.1"
            :value="state.targetM / 1000"
            @change="
              (event) => {
                const km = Number((event.target as HTMLInputElement).value)
                if (km >= 1 && km <= 42) setTarget(km * 1000)
              }
            "
          />
        </label>
      </div>
    </template>

    <!-- F2 单行线模式：A / B 两张选点卡，隐藏目标距离 -->
    <template v-else>
      <div class="row oneway-box">
        <div class="oneway-hint" role="status">{{ onewayHint }}</div>
        <button
          type="button"
          class="point-card"
          :class="{ active: state.pickingPoint === 'A' }"
          data-point="A"
          @click="setPickingPoint('A')"
        >
          <span class="pin pin-a" aria-hidden="true">A</span>
          <span class="origin-text">
            <b>{{ state.onewayA ? state.onewayA.name : '点击地图选择起点 A' }}</b>
            <span class="num">
              {{
                state.onewayA
                  ? `${state.onewayA.lng.toFixed(4)}, ${state.onewayA.lat.toFixed(4)}`
                  : '未选择'
              }}
            </span>
          </span>
          <span class="pick-tag">{{ state.pickingPoint === 'A' ? '选点中' : '重选' }}</span>
        </button>

        <button
          type="button"
          class="point-card"
          :class="{ active: state.pickingPoint === 'B' }"
          data-point="B"
          @click="setPickingPoint('B')"
        >
          <span class="pin pin-b" aria-hidden="true">B</span>
          <span class="origin-text">
            <b>{{ state.onewayB ? state.onewayB.name : '点击地图选择终点 B' }}</b>
            <span class="num">
              {{
                state.onewayB
                  ? `${state.onewayB.lng.toFixed(4)}, ${state.onewayB.lat.toFixed(4)}`
                  : '未选择'
              }}
            </span>
          </span>
          <span class="pick-tag">{{ state.pickingPoint === 'B' ? '选点中' : '重选' }}</span>
        </button>

        <p v-if="state.onewayError" class="oneway-err" role="alert">
          {{ state.onewayError }}
        </p>
      </div>
    </template>

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
          @click="togglePref(p.key)"
        >
          <span>{{ p.label }}</span>
          <span class="sw" :class="{ on: state.prefs[p.key] }" aria-hidden="true"><i></i></span>
        </button>
      </div>
    </div>

    <button class="cta" :disabled="ctaDisabled" @click="generate">
      {{ state.loading ? '正在生成…' : '生成路线' }}
      <small>{{ ctaSubtitle }}</small>
    </button>
  </section>
</template>

<style scoped>
.custom-distance {
  display: block;
  margin-top: 10px;
  font-size: 12px;
  color: var(--sub);
}
.custom-distance input {
  width: 64px;
  margin-left: 8px;
  padding: 4px;
  font: inherit;
  border: 1px solid #dfe8e3;
  background: rgba(255, 255, 255, 0.8);
}
.left {
  position: absolute;
  left: 24px;
  top: 88px;
  width: 306px;
  padding: 20px 22px 0;
  z-index: 4;
}

.label {
  font-size: 13px;
  color: var(--muted);
  letter-spacing: 1px;
  margin-bottom: 8px;
}

.mode-segs {
  margin-bottom: 4px;
}

.origin {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.oneway-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.oneway-hint {
  font-size: 12px;
  color: var(--accent);
  background: var(--accent-weak);
  padding: 7px 10px;
  line-height: 1.45;
}

.point-card {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 1px solid #dfe8e3;
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.point-card.active {
  border-color: var(--accent);
  background: rgba(231, 241, 234, 0.55);
}

.point-card .origin-text {
  flex: 1;
  min-width: 0;
}

.point-card .origin-text b {
  font-size: 13.5px;
  margin-bottom: 2px;
}

.pick-tag {
  flex: none;
  font-size: 11px;
  color: var(--muted);
}

.point-card.active .pick-tag {
  color: var(--accent);
  font-weight: 600;
}

.oneway-err {
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #a33333;
  background: #fff3f3;
  border: 1px solid #e8b4b4;
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

.pin-a {
  background: #15503c;
}

.pin-b {
  background: #c2410c;
}

.origin-text b {
  display: block;
  font-size: 15px;
  line-height: 1.35;
  margin-bottom: 4px;
  word-break: break-word;
}

.origin-text span {
  font-size: 12px;
  color: var(--faint);
}

.row {
  margin-top: 16px;
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
  padding: 10px 0;
  font-size: 14px;
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
  margin: 22px 0 0 -22px;
  background: var(--accent);
  color: #fff;
  text-align: center;
  padding: 16px 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}

.cta:disabled {
  opacity: 0.55;
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

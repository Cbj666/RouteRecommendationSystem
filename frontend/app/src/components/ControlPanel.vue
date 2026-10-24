<script setup lang="ts">
import { state } from '../store'

defineEmits<{ generate: [] }>()

const targets = [3000, 5000, 10000]
</script>

<template>
  <section class="panel">
    <h3>起点</h3>
    <div class="origin">
      <div class="pin">起</div>
      <div>
        <b>{{ state.origin.label }}</b>
        <span class="num">{{ state.origin.lng.toFixed(4) }}, {{ state.origin.lat.toFixed(4) }}</span>
      </div>
    </div>

    <h3>目标距离</h3>
    <div class="chips">
      <button
        v-for="t in targets"
        :key="t"
        class="chip"
        :class="{ on: state.targetM === t }"
        @click="state.targetM = t"
      >{{ t / 1000 }} km</button>
    </div>

    <h3>偏好</h3>
    <label class="row">
      <span>尽量绿荫 / 滨水</span>
      <input type="range" min="0" max="2" step="0.1" v-model.number="state.prefs.green" />
    </label>
    <label class="row">
      <span>避开机动车主干道</span>
      <input type="range" min="0" max="2" step="0.1" v-model.number="state.prefs.safe" />
    </label>
    <label class="row">
      <span>尽量平坦</span>
      <input type="range" min="0" max="2" step="0.1" v-model.number="state.prefs.flat" />
    </label>

    <button class="cta" :disabled="state.loading" @click="$emit('generate')">
      {{ state.loading ? '计算中…' : '生成推荐环线' }}
    </button>

    <p class="meta">
      环线权重：避开主干道 {{ state.prefs.safe.toFixed(2) }} ·
      绿化 {{ state.prefs.green.toFixed(2) }} ·
      平坦 {{ state.prefs.flat.toFixed(2) }}<br />
      路网 OSM · 坡度 SRTM 30 m · 树冠 ESA 10 m · 场馆 高德
    </p>
  </section>
</template>

<style scoped>
.panel { padding: 16px; display: flex; flex-direction: column; gap: 12px; min-height: 0; overflow: auto; }
.origin {
  display: flex; align-items: center; gap: 10px; padding: 11px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--bg);
}
.pin {
  width: 26px; height: 26px; border-radius: 50%; background: #fff;
  border: 2px solid var(--accent); display: grid; place-items: center;
  color: var(--accent); font-size: 12px;
}
.origin b { display: block; font-size: 14px; }
.origin span { font-size: 12px; color: var(--muted); }

.chips { display: flex; gap: 8px; }
.chip {
  flex: 1; padding: 9px 0; border: 1px solid var(--line); border-radius: 10px;
  background: transparent; font-size: 14px; color: var(--muted);
}
.chip.on { border-color: var(--accent); color: var(--accent); background: var(--accent-weak); font-weight: 600; }

.row { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--ink); }
.row input { width: 100%; accent-color: var(--accent); }

.cta {
  margin-top: auto; padding: 12px; border-radius: 11px; border: 0;
  background: var(--accent); color: #fff; font-size: 15px; font-weight: 600;
}
.cta:disabled { opacity: .6; cursor: wait; }
.meta { font-size: 11.5px; color: var(--muted); line-height: 1.6; margin: 0; }
</style>

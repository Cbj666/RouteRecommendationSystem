<script setup lang="ts">
import { clearError, generate, state } from '../stores/planner'
</script>

<template>
  <div class="overlay" aria-live="polite">
    <div v-if="state.mapError" class="box err glass-solid">
      <b>底图加载失败</b>
      <p>{{ state.mapError }}</p>
      <p class="hint">
        请先运行 npm run sync:geo（npm run dev / build 的 pre 脚本会自动执行），确认
        public/geo/manifest.json 与各图层 geojson 已生成。
      </p>
    </div>

    <div v-else-if="state.tab === 'loops' && state.emptyMsg" class="box notice glass-solid">
      <b>{{ state.mode === 'oneway' ? '没有可用的单行线' : '没有可用的环线' }}</b>
      <p>{{ state.emptyMsg }}</p>
      <div class="acts">
        <button class="act" @click="generate">再试一次</button>
        <button class="act ghost" @click="clearError">关闭</button>
      </div>
    </div>

    <div v-else-if="state.tab === 'loops' && state.mode === 'loop' && state.error" class="box err glass-solid">
      <p>{{ state.error }}</p>
      <div class="acts">
        <button class="act" @click="generate">重试</button>
        <button class="act ghost" @click="clearError">关闭</button>
      </div>
    </div>

    <div v-else-if="state.tab === 'loops' && state.loading" class="pill">
      <span class="spin" aria-hidden="true"></span>正在生成路线…
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  top: 88px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 560px;
  pointer-events: none;
}

.box {
  pointer-events: auto;
  width: 100%;
  background: #fff3f3;
  border: 1px solid #e8b4b4;
  color: #a33333;
  padding: 14px 18px;
  font-size: 13px;
  line-height: 1.7;
}

.box b {
  display: block;
  margin-bottom: 4px;
}

.hint {
  margin-top: 6px;
  color: #8a5a5a;
  font-size: 12px;
}

.notice {
  background: var(--accent-weak);
  border-color: #c9dfd3;
  color: var(--accent);
}

.notice .act {
  background: var(--accent);
}

.notice .act.ghost {
  color: var(--accent);
  border-color: #b7d1c2;
}

.acts {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.act {
  padding: 5px 14px;
  background: #a33333;
  color: #fff;
  font-size: 12.5px;
}

.act.ghost {
  background: transparent;
  color: #a33333;
  border: 1px solid #d9a3a3;
}

.pill {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--line);
  box-shadow: 0 8px 28px rgba(18, 58, 44, 0.12);
  font-size: 13px;
  color: var(--sub);
}

.spin {
  width: 13px;
  height: 13px;
  border: 2px solid #cfded6;
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: turn 0.8s linear infinite;
}

@keyframes turn {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
  }
}
</style>

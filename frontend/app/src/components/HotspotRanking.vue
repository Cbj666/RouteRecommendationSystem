<script setup lang="ts">
import {
  filteredHotspots,
  hotspotCellCount,
  hotspotNote,
  hotspotState,
  hotspotSummary,
  regionSummary,
  selectHotspot,
  setDrawMode,
  setHotspotFilter,
  setRegion,
  visibleHotspotCount,
} from '../stores/hotspot'
import type { RegionDrawMode } from '../stores/hotspot'

function startDraw(mode: RegionDrawMode): void {
  setDrawMode(hotspotState.drawMode === mode ? 'none' : mode)
}

function clearRegion(): void {
  setDrawMode('none')
  setRegion(null)
}
</script>

<template>
  <aside class="hotspot-rank glass" aria-label="热点排行榜">
    <header>
      <h3>武汉跑步热点地图</h3>
      <p>{{ hotspotNote }}</p>
      <p v-if="hotspotSummary" class="meta">
        {{ hotspotCellCount.toLocaleString() }} 格 · {{ hotspotSummary.hotspots.toLocaleString() }} 个热点 · 均分
        {{ hotspotSummary.meanScore }} · 覆盖 {{ hotspotSummary.totalLengthKm.toLocaleString() }} km
      </p>
    </header>

    <p v-if="hotspotState.loading" class="state">网格载入中…</p>
    <p v-else-if="hotspotState.error" class="state error">{{ hotspotState.error }}</p>

    <div class="region" role="group" aria-label="区域筛选">
      <span class="region-label">区域筛选</span>
      <button
        type="button"
        :class="{ on: hotspotState.drawMode === 'rect' }"
        @click="startDraw('rect')"
      >
        矩形
      </button>
      <button
        type="button"
        :class="{ on: hotspotState.drawMode === 'circle' }"
        @click="startDraw('circle')"
      >
        圆形
      </button>
      <button v-if="hotspotState.region" type="button" class="clear" @click="clearRegion">
        清除
      </button>
    </div>
    <p v-if="hotspotState.drawMode !== 'none'" class="hint">
      {{
        hotspotState.drawMode === 'rect'
          ? '在地图上按下并拖出矩形'
          : '在地图上按下作为圆心，向外拖出半径'
      }}
    </p>
    <p v-if="regionSummary" class="region-meta">
      区域内 {{ regionSummary.cells.toLocaleString() }} 格 ·
      {{ regionSummary.hotspots.toLocaleString() }} 个热点 · 均分
      {{ regionSummary.meanScore.toFixed(1) }} · 覆盖
      {{ (regionSummary.lenM / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 }) }} km
    </p>

    <div class="filters" role="group" aria-label="热点筛选">
      <button
        type="button"
        :class="{ on: hotspotState.filter === 'all' }"
        @click="setHotspotFilter('all')"
      >
        全部
      </button>
      <button
        type="button"
        :class="{ on: hotspotState.filter === 'hotspot' }"
        @click="setHotspotFilter('hotspot')"
      >
        仅热点 <span>{{ visibleHotspotCount }}</span>
      </button>
    </div>

    <ol class="rank-list">
      <li
        v-for="(cell, index) in filteredHotspots.slice(0, 20)"
        :key="cell.id"
        :class="{ on: cell.id === hotspotState.selectedId, hot: cell.isHotspot }"
        @click="selectHotspot(cell.id)"
      >
        <span class="rank num">{{
          hotspotState.region ? index + 1 : cell.rank > 0 ? cell.rank : '—'
        }}</span>
        <span class="name">
          <b>{{ cell.name }}</b>
          <small>{{ cell.cluster }} · {{ Math.round(cell.lenM) }} m</small>
        </span>
        <span class="score num">{{ cell.score.toFixed(1) }}</span>
      </li>
    </ol>

    <p class="foot">
      点击榜单或地图格子查看六维详情。区域筛选只统计覆盖到的网格（按路段长度加权）。
    </p>
  </aside>
</template>

<style scoped>
.hotspot-rank {
  position: absolute;
  top: 88px;
  left: 24px;
  bottom: 24px;
  width: 306px;
  padding: 18px;
  z-index: 4;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

header {
  flex: none;
}

h3 {
  font-size: 17px;
  line-height: 1.3;
}

header p {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
}

header p.meta {
  color: var(--sub);
  font-variant-numeric: tabular-nums;
  font-size: 10.5px;
}

.state {
  flex: none;
  margin-top: 10px;
  color: var(--muted);
  font-size: 11px;
}

.state.error {
  color: #b43737;
}

.filters {
  display: flex;
  gap: 6px;
  margin: 14px 0 10px;
  flex: none;
}

.filters button {
  padding: 5px 10px;
  border: 1px solid var(--line);
  color: var(--sub);
  font-size: 11.5px;
  line-height: 1.4;
  background: rgba(255, 255, 255, 0.55);
}

.filters button.on {
  color: var(--accent);
  border-color: rgba(21, 80, 60, 0.35);
  background: var(--accent-weak);
  font-weight: 600;
}

.filters span {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.region {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  flex: none;
}

.region-label {
  color: var(--muted);
  font-size: 11px;
  margin-right: 2px;
}

.region button {
  padding: 4px 9px;
  border: 1px solid var(--line);
  color: var(--sub);
  font-size: 11.5px;
  line-height: 1.4;
  background: rgba(255, 255, 255, 0.55);
}

.region button.on {
  color: var(--accent);
  border-color: rgba(21, 80, 60, 0.35);
  background: var(--accent-weak);
  font-weight: 600;
}

.region button.clear {
  color: #b43737;
  border-color: rgba(180, 55, 55, 0.3);
}

.hint {
  margin-top: 6px;
  color: var(--accent);
  font-size: 10.5px;
  line-height: 1.45;
}

.region-meta {
  margin-top: 6px;
  color: var(--sub);
  font-size: 10.5px;
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
}

.rank-list {
  list-style: none;
  overflow: auto;
  min-height: 0;
  margin: 0 -6px;
  padding: 0 6px;
  scrollbar-width: thin;
}

.rank-list li {
  display: grid;
  grid-template-columns: 26px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 6px;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
}

.rank-list li:hover {
  background: rgba(231, 241, 234, 0.55);
}

.rank-list li.on {
  background: var(--accent-weak);
  box-shadow: inset 3px 0 0 var(--accent);
}

.rank {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--muted);
  background: rgba(21, 80, 60, 0.06);
  font-size: 10.5px;
}

.rank-list li:nth-child(-n + 3) .rank {
  color: #fff;
  background: var(--accent);
}

.name {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.name b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  font-weight: 600;
}

.name small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: 10.5px;
}

.score {
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
}

.rank-list li.hot .score::before {
  content: '';
  display: inline-block;
  width: 5px;
  height: 5px;
  margin-right: 4px;
  border-radius: 50%;
  background: #d94f4f;
  vertical-align: 2px;
}

.foot {
  flex: none;
  padding-top: 10px;
  color: var(--muted);
  font-size: 10.5px;
  line-height: 1.5;
}
</style>

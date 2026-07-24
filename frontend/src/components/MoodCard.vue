<script setup lang="ts">
import type { MoodOut } from '../api/client'
import { computed } from 'vue'
import TooltipIcon from './TooltipIcon.vue'

const props = defineProps<{ mood: MoodOut | null; loading: boolean }>()
const emit = defineEmits<{ refresh: [] }>()

const scorePercent = computed(() => {
  if (!props.mood) return 50
  return ((props.mood.score - 1) / 9) * 100
})

const fillColor = computed(() => {
  if (!props.mood) return '#d6d3d1'
  const s = props.mood.score
  if (s <= 3.0) return '#8b5cf6'
  if (s <= 6.0) return '#f59e0b'
  return '#10b981'
})

const labelClass = computed(() => {
  if (!props.mood) return 'text-stone-400'
  switch (props.mood.label) {
    case '低落': return 'text-violet-600 bg-violet-50'
    case '平稳': return 'text-amber-600 bg-amber-50'
    case '良好': return 'text-emerald-600 bg-emerald-50'
    default: return 'text-stone-500 bg-stone-50'
  }
})
</script>

<template>
  <div class="bg-white rounded-2xl shadow-sm shadow-stone-200/50 p-5">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <i class="fa-solid fa-heart text-rose-400"></i>
        <h3 class="text-sm font-semibold text-stone-700">情绪指数</h3>
        <TooltipIcon text="基于你最近的记录，由 AI 分析得出的情绪状态参考。1-3 低落、4-6 平稳、7-10 良好。这不是医学诊断，仅为自我觉察辅助。" />
      </div>
      <button @click="emit('refresh')" :disabled="loading"
        class="text-xs text-violet-500 active:text-violet-700 disabled:text-stone-300 font-medium transition-colors py-1 px-2 rounded-lg active:bg-violet-50">
        <i :class="['fa-solid', loading ? 'fa-spinner animate-spin' : 'fa-rotate']"></i>
        <span class="ml-1">{{ loading ? '分析中...' : '刷新' }}</span>
      </button>
    </div>

    <div v-if="loading && !mood" class="animate-pulse space-y-3">
      <div class="h-4 bg-stone-100 rounded-full w-full"></div>
      <div class="h-3 bg-stone-100 rounded w-2/3"></div>
    </div>

    <div v-else-if="!mood" class="text-center py-6 text-stone-400">
      <i class="fa-solid fa-heart-circle-plus text-2xl mb-2 block"></i>
      <p class="text-xs">点击「刷新」生成情绪指数</p>
    </div>

    <div v-else class="space-y-3">
      <div class="flex items-center gap-3">
        <span class="text-3xl font-bold text-stone-800 w-12 text-right tabular-nums">{{ mood.score.toFixed(1) }}</span>
        <div class="flex-1 h-4 bg-stone-100 rounded-full overflow-hidden">
          <div class="h-full rounded-full transition-all duration-700 ease-out" :style="{ width: scorePercent + '%', backgroundColor: fillColor }"></div>
        </div>
        <span :class="['text-xs font-semibold px-2 py-1 rounded-full', labelClass]">{{ mood.label }}</span>
      </div>
      <div class="flex justify-between text-[10px] text-stone-300 -mt-1 px-1">
        <span>1 低落</span><span>5 平稳</span><span>10 良好</span>
      </div>
      <p class="text-sm text-stone-600 leading-relaxed">{{ mood.summary }}</p>
      <div v-if="mood.key_factors.length" class="flex flex-wrap gap-1.5">
        <span v-for="(f, i) in mood.key_factors" :key="i"
          class="text-[11px] bg-stone-50 text-stone-500 rounded-full px-2.5 py-1">{{ f }}</span>
      </div>
    </div>
  </div>
</template>
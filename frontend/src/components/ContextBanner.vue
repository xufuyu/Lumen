<script setup lang="ts">
import type { ContextOut } from '../api/client'
import TooltipIcon from './TooltipIcon.vue'

defineProps<{ context: ContextOut | null; loading: boolean }>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <div class="bg-white rounded-2xl shadow-sm shadow-stone-200/50 p-5">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <i class="fa-solid fa-location-dot text-violet-400"></i>
        <h2 class="text-sm font-semibold text-stone-700">当前状态</h2>
        <TooltipIcon text="根据你最近的事件和待办任务自动生成的摘要，帮你快速了解当前在做的事情和最重要的下一步。" />
      </div>
      <button @click="$emit('refresh')" :disabled="loading"
        class="text-xs text-violet-500 active:text-violet-700 disabled:text-stone-300 font-medium transition-colors py-1 px-2 rounded-lg active:bg-violet-50">
        <i :class="['fa-solid', loading ? 'fa-spinner animate-spin' : 'fa-arrows-rotate']"></i>
        <span class="ml-1">{{ loading ? '刷新中...' : '刷新' }}</span>
      </button>
    </div>

    <div v-if="loading" class="animate-pulse space-y-2">
      <div class="h-3 bg-stone-100 rounded w-full"></div>
      <div class="h-3 bg-stone-100 rounded w-3/4"></div>
      <div class="h-3 bg-stone-100 rounded w-1/2"></div>
    </div>

    <p v-else-if="context && context.id !== 0" class="text-base text-stone-600 leading-relaxed">{{ context.summary }}</p>

    <div v-else class="text-center py-5">
      <i class="fa-solid fa-seedling text-2xl text-stone-200 mb-2 block"></i>
      <p class="text-sm text-stone-400">尚无足够的记录来生成摘要</p>
      <p class="text-xs text-stone-300 mt-1">开始记录后，系统会自动整理你的状态</p>
    </div>
  </div>
</template>
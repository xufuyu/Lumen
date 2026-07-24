<script setup lang="ts">
import TooltipIcon from './TooltipIcon.vue'

defineProps<{
  icon: string
  value: number | string
  label: string
  color?: string
  tooltip?: string
}>()
</script>

<template>
  <div class="bg-white rounded-2xl shadow-sm shadow-stone-200/50 p-4 flex flex-col items-center gap-2 text-center">
    <i :class="['fa-solid', icon, 'text-xl', color === 'amber' ? 'text-amber-400' : color === 'blue' ? 'text-sky-400' : color === 'green' ? 'text-emerald-400' : 'text-stone-300']"></i>
    <p class="text-2xl font-bold text-stone-800 leading-none">{{ value }}</p>
    <div class="flex items-center gap-1">
      <p class="text-[11px] text-stone-400 font-medium">{{ label }}</p>
      <TooltipIcon v-if="tooltip" :text="tooltip" />
    </div>
  </div>
</template>
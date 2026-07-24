<script setup lang="ts">
import type { TaskOut } from '../api/client'
import { computed } from 'vue'
import TooltipIcon from './TooltipIcon.vue'

const props = defineProps<{ task: TaskOut }>()
const emit = defineEmits<{ statusChange: [id: number, status: string]; delete: [id: number] }>()

const priorityBadge = computed(() => {
  switch (props.task.priority) {
    case 'high': return { text: '高', color: 'bg-rose-50 text-rose-600' }
    case 'medium': return { text: '中', color: 'bg-amber-50 text-amber-600' }
    case 'low': return { text: '低', color: 'bg-stone-100 text-stone-500' }
    default: return { text: props.task.priority, color: 'bg-stone-100 text-stone-500' }
  }
})

const statusIcon = computed(() => {
  switch (props.task.status) {
    case 'pending': return 'fa-regular fa-circle'
    case 'in_progress': return 'fa-solid fa-circle-half-stroke'
    case 'done': return 'fa-solid fa-circle-check'
    default: return 'fa-regular fa-circle'
  }
})

const statusIconColor = computed(() => {
  switch (props.task.status) {
    case 'pending': return 'text-stone-300'
    case 'in_progress': return 'text-amber-400'
    case 'done': return 'text-emerald-400'
    default: return 'text-stone-300'
  }
})

function cycleStatus() {
  const order = ['pending', 'in_progress', 'done']
  const idx = order.indexOf(props.task.status)
  const next = order[(idx + 1) % order.length]
  emit('statusChange', props.task.id, next)
}

function formatDate(dt: string | null) {
  if (!dt) return null
  return new Date(dt).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const isOverdue = computed(() => {
  if (!props.task.due_date || props.task.status === 'done') return false
  return new Date(props.task.due_date) < new Date()
})
</script>

<template>
  <div :class="[
    'bg-white rounded-2xl shadow-sm shadow-stone-200/50 p-4 hover:shadow-md transition-shadow',
    task.status === 'done' ? 'opacity-50' : '',
  ]">
    <div class="flex items-start gap-3">
      <button @click="cycleStatus" class="mt-0.5 shrink-0 text-xl transition-colors hover:scale-110 active:scale-95">
        <i :class="[statusIcon, statusIconColor]"></i>
      </button>
      <div class="flex-1 min-w-0">
        <h3 :class="['text-sm font-semibold', task.status === 'done' ? 'text-stone-400 line-through' : 'text-stone-800']">{{ task.title }}</h3>
        <p v-if="task.description" class="text-xs text-stone-500 mt-1 line-clamp-2">{{ task.description }}</p>
        <div class="flex items-center gap-2 mt-2 flex-wrap">
          <span :class="['text-[11px] px-1.5 py-0.5 rounded-full font-medium', priorityBadge.color]">{{ priorityBadge.text }}</span>
          <span v-if="task.due_date && task.status !== 'done'" class="text-[11px] text-stone-400">{{ formatDate(task.due_date) }}</span>
          <span v-if="isOverdue" class="text-[11px] text-rose-500 font-semibold">已过期</span>
          <span v-if="task.confidence < 1" class="text-[11px] text-stone-400">系统推测 · {{ Math.round(task.confidence * 100) }}%</span>
          <TooltipIcon v-if="task.confidence < 1" text="此任务由 AI 从你的记录中推测得出，不一定是你的实际意图。" />
        </div>
      </div>
    </div>
    <div class="flex gap-2 mt-3">
      <button v-if="task.status !== 'done'" @click="emit('statusChange', task.id, 'in_progress')"
        class="text-xs text-violet-600 active:text-violet-800 font-medium transition-colors py-1 px-2 -ml-2 rounded-lg active:bg-violet-50">
        <i class="fa-solid fa-play mr-1 text-[10px]"></i>{{ task.status === 'pending' ? '开始' : '完成' }}
      </button>
      <button v-if="task.status === 'done'" @click="emit('statusChange', task.id, 'pending')"
        class="text-xs text-stone-500 active:text-stone-700 font-medium transition-colors py-1 px-2 -ml-2 rounded-lg active:bg-stone-100">
        <i class="fa-solid fa-rotate-left mr-1"></i>重新打开
      </button>
      <button @click="emit('delete', task.id)" class="text-xs text-stone-400 active:text-rose-500 transition-colors py-1 px-2 rounded-lg active:bg-rose-50 ml-auto">删除</button>
    </div>
  </div>
</template>
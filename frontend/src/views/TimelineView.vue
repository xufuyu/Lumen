<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  listEvents, listTasks, updateEvent, deleteEvent, updateTask,
  type EventOut, type TaskOut,
} from '../api/client'
import { groupByDay, formatSmartDate, dayOffset } from '../utils/date'
import TimelineCard from '../components/TimelineCard.vue'
import TaskCard from '../components/TaskCard.vue'

const { t, locale } = useI18n()

const events = ref<EventOut[]>([])
const doneTasks = ref<TaskOut[]>([])
const loading = ref(false)
const filter = ref<'' | 'events' | 'tasks'>('')  // '' = 全部混排

async function load() {
  loading.value = true
  try {
    const [ev, done] = await Promise.all([
      listEvents({ limit: 100 }),
      listTasks({ status: 'done', sort: 'created_at' }),
    ])
    events.value = ev.items
    doneTasks.value = done.items
  } catch (e) { console.error(e) } finally { loading.value = false }
}

async function handleConfirm(id: number) { try { await updateEvent(id, { status: 'confirmed' }); await load() } catch (e) { console.error(e) } }
async function handleDeleteEvent(id: number) { try { await deleteEvent(id); await load() } catch (e) { console.error(e) } }
async function handleTaskStatus(id: number, status: string) {
  try { await updateTask(id, { status }); await load() } catch (e) { console.error(e) }
}

// Unified items with a common `time` for sorting/grouping.
interface UnifiedItem {
  type: 'event' | 'done_task'
  time: string   // ISO
  event?: EventOut
  task?: TaskOut
}

const merged = computed<UnifiedItem[]>(() => {
  const items: UnifiedItem[] = []
  if (filter.value !== 'tasks') {
    for (const e of events.value) {
      items.push({ type: 'event', time: e.start_time || e.created_at, event: e })
    }
  }
  if (filter.value !== 'events') {
    for (const t of doneTasks.value) {
      items.push({ type: 'done_task', time: t.completed_at || t.created_at, task: t })
    }
  }
  // Newest first
  items.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
  return items
})

const grouped = computed(() => groupByDay(merged.value, m => m.time))
const sortedDays = computed(() => {
  const keys = Array.from(grouped.value.keys())
  return keys.sort((a, b) => {
    if (a === null) return 1
    if (b === null) return -1
    // Past first (recent first) → chronological reverse
    const oa = dayOffset(a) ?? 0
    const ob = dayOffset(b) ?? 0
    return ob - oa
  })
})

function dayLabel(key: string | null): string {
  if (!key) return t('tasks.groups.someday')
  return formatSmartDate(key, locale.value)
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <h2 class="text-base font-bold text-stone-700"><i class="fa-solid fa-calendar-days mr-2 text-violet-400"></i>{{ t('timeline.title') }}</h2>
      <div class="flex gap-1 flex-wrap">
        <button v-for="opt in [
          {v: '', k: 'all'},
          {v: 'events', k: 'events'},
          {v: 'tasks', k: 'doneTasks'},
        ]" :key="opt.v"
          @click="filter = opt.v as any"
          :class="['text-xs px-3 py-2 rounded-full font-medium transition-colors',
            filter === opt.v ? 'bg-violet-100 text-violet-600' : 'text-stone-400 active:text-stone-600 active:bg-stone-100']">
          {{ t(`timeline.filter.${opt.k}`) }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="n in 3" :key="n" class="bg-stone-100 rounded-2xl h-24 animate-pulse"></div>
    </div>

    <div v-else-if="merged.length === 0" class="text-center py-16 text-stone-400">
      <i class="fa-solid fa-calendar-days text-3xl mb-4 block text-stone-200"></i>
      <p class="text-base text-stone-500 font-medium">{{ t('timeline.empty') }}</p>
      <p class="text-sm text-stone-300 mt-1">{{ t('timeline.emptySub') }}</p>
    </div>

    <div v-else class="space-y-5">
      <section v-for="dayK in sortedDays" :key="dayK ?? 'someday'" class="space-y-2">
        <div class="flex items-center gap-2 sticky top-0 bg-white/90 backdrop-blur-sm py-1 z-[1]">
          <span class="text-xs font-bold text-stone-700">{{ dayLabel(dayK) }}</span>
          <span class="text-[10px] text-stone-400">{{ grouped.get(dayK)?.length ?? 0 }}</span>
          <div class="flex-1 h-px bg-stone-100"></div>
        </div>
        <div class="space-y-3">
          <template v-for="item in grouped.get(dayK)" :key="item.type + '-' + (item.event?.id ?? item.task?.id)">
            <TimelineCard v-if="item.type === 'event' && item.event"
              :event="item.event" @confirm="handleConfirm" @delete="handleDeleteEvent" />
            <TaskCard v-else-if="item.type === 'done_task' && item.task"
              :task="item.task"
              @status-change="handleTaskStatus"
              @delete="(id) => handleTaskStatus(id, 'pending')" />
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

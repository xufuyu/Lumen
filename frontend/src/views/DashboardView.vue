<script setup lang="ts">
/**
 * DashboardView — desktop-first, "自适应尺寸" overview.
 *
 * Layout responds at three breakpoints:
 *  - < md:  single column, sections stack in a scannable order
 *  - md-lg: 2-column grid
 *  - ≥ lg:  12-column grid with tiled cards
 *
 * Data is pulled fresh on mount and on `lumen:refresh` (fired by sync.ts).
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  listTasks, listEvents, listRecords,
  getCurrentContext, getLatestMood, generateMood,
  type TaskOut, type EventOut, type RecordOut, type ContextOut, type MoodOut,
} from '../api/client'
import { dayKey, dayOffset, formatSmartDate, formatSmartDateTime } from '../utils/date'

const { t, locale } = useI18n()
const router = useRouter()

const tasks = ref<TaskOut[]>([])
const events = ref<EventOut[]>([])
const records = ref<RecordOut[]>([])
const context = ref<ContextOut | null>(null)
const mood = ref<MoodOut | null>(null)
const loading = ref(false)
const moodLoading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const [tk, ev, rc, ctx, m] = await Promise.all([
      listTasks({ status: 'pending,in_progress,done', sort: 'due_date' }),
      listEvents({ limit: 20 }),
      listRecords({ page_size: 10 }),
      getCurrentContext().catch(() => null),
      getLatestMood().catch(() => null),
    ])
    tasks.value = tk.items
    events.value = ev.items
    records.value = rc.items
    context.value = ctx
    if (m?.mood) mood.value = m.mood
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function handleRefreshMood() {
  moodLoading.value = true
  try {
    const res = await generateMood()
    if (res.mood) mood.value = res.mood
  } finally {
    moodLoading.value = false
  }
}

// ── Derived slices ────────────────────────────────────────────────────────
const todayTasks = computed(() => tasks.value.filter(t => {
  if (t.status === 'in_progress') return true
  if (t.due_date && dayOffset(t.due_date) === 0) return true
  if (!t.due_date && dayOffset(t.created_at) === 0 && t.status !== 'done') return true
  return false
}))

const upcomingTasks = computed(() => tasks.value
  .filter(t => t.status !== 'done' && t.due_date && (dayOffset(t.due_date) ?? -1) >= 1 && (dayOffset(t.due_date) ?? -1) <= 6)
  .sort((a, b) => new Date(a.due_date!).getTime() - new Date(b.due_date!).getTime()))

const doneToday = computed(() => tasks.value.filter(t =>
  t.status === 'done' && t.completed_at && dayOffset(t.completed_at) === 0,
))

const pendingCount = computed(() => tasks.value.filter(t => t.status === 'pending').length)
const inProgressCount = computed(() => tasks.value.filter(t => t.status === 'in_progress').length)
const doneCount = computed(() => tasks.value.filter(t => t.status === 'done').length)

// 7-day heatmap: intensity = # of items (records/tasks/events) touched that day.
interface HeatDay { key: string; label: string; offset: number; count: number; hasEvent: boolean; hasTask: boolean }
const weekHeatmap = computed<HeatDay[]>(() => {
  const days: HeatDay[] = []
  for (let offset = -6; offset <= 0; offset++) {
    const d = new Date()
    d.setDate(d.getDate() + offset)
    d.setHours(0, 0, 0, 0)
    const k = dayKey(d)!
    let count = 0
    let hasEvent = false
    let hasTask = false
    for (const r of records.value) if (dayKey(r.created_at) === k) count++
    for (const e of events.value) if (dayKey(e.start_time || e.created_at) === k) { count++; hasEvent = true }
    for (const t of tasks.value) if (dayKey(t.completed_at) === k) { count++; hasTask = true }
    days.push({
      key: k,
      label: formatSmartDate(d, locale.value),
      offset,
      count,
      hasEvent,
      hasTask,
    })
  }
  return days
})
const heatMax = computed(() => Math.max(1, ...weekHeatmap.value.map(d => d.count)))

function heatOpacity(count: number): string {
  const ratio = count / heatMax.value
  if (count === 0) return 'bg-stone-100'
  if (ratio < 0.25) return 'bg-violet-200'
  if (ratio < 0.5) return 'bg-violet-300'
  if (ratio < 0.75) return 'bg-violet-400'
  return 'bg-violet-500'
}

// Voice emotion breakdown from recent records
interface EmoBar { emo: string; count: number; color: string; label: string }
const emotionBreakdown = computed<EmoBar[]>(() => {
  const counts: Record<string, number> = {}
  for (const r of records.value) {
    // meta_json isn't in RecordOut; skip. But we can still tally by type as
    // a lightweight signal: how much of recent capture was voice vs text.
    counts[r.type] = (counts[r.type] || 0) + 1
  }
  return Object.entries(counts).map(([emo, count]) => ({
    emo,
    count,
    color: emo === 'voice' ? 'bg-violet-400' : 'bg-stone-300',
    label: emo === 'voice' ? t('dashboard.voiceLabel') : t('dashboard.textLabel'),
  }))
})

// ── Refresh on external sync ───────────────────────────────────────────────
const syncHandler = () => { loadAll() }
onMounted(() => {
  loadAll()
  window.addEventListener('lumen:refresh', syncHandler)
})
onUnmounted(() => {
  window.removeEventListener('lumen:refresh', syncHandler)
})

const moodEmoji = computed(() => {
  if (!mood.value) return '😶'
  const s = mood.value.score
  if (s >= 7) return '😊'
  if (s >= 4) return '😐'
  return '😔'
})
const moodColor = computed(() => {
  if (!mood.value) return 'text-stone-300'
  const s = mood.value.score
  if (s <= 3) return 'text-violet-500'
  if (s <= 6) return 'text-amber-500'
  return 'text-emerald-500'
})

function priorityDot(p: string): string {
  return p === 'high' ? 'bg-rose-400' : p === 'medium' ? 'bg-amber-400' : 'bg-stone-300'
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-base font-bold text-stone-700">
        <i class="fa-solid fa-chart-simple mr-2 text-violet-400"></i>{{ t('dashboard.title') }}
      </h2>
      <button @click="loadAll" :disabled="loading" class="text-xs text-violet-500 font-medium">
        <i :class="['fa-solid mr-1', loading ? 'fa-spinner animate-spin' : 'fa-arrows-rotate']"></i>{{ t('home.refresh') }}
      </button>
    </div>

    <!-- Responsive grid: mobile=1col, tablet=2col, desktop=12col -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-3 lg:gap-4 auto-rows-min">

      <!-- Context banner: full width -->
      <section v-if="context && context.id !== 0"
        class="md:col-span-2 lg:col-span-8 bg-gradient-to-br from-violet-50 to-white rounded-2xl border border-violet-100 px-4 py-3">
        <div class="flex items-center gap-2 mb-1">
          <i class="fa-solid fa-location-dot text-violet-400 text-xs"></i>
          <h3 class="text-xs font-bold text-stone-700">{{ t('home.contextTitle') }}</h3>
        </div>
        <p class="text-sm text-stone-600 leading-relaxed line-clamp-3">{{ context.summary }}</p>
      </section>

      <!-- Mood: right side on desktop, spans 2 rows -->
      <section class="lg:col-span-4 lg:row-span-2 bg-gradient-to-br from-violet-50/60 to-rose-50/40 rounded-2xl border border-stone-100 px-4 py-3.5 flex flex-col">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs font-bold text-stone-700"><i class="fa-solid fa-heart-pulse mr-1.5 text-violet-400"></i>{{ t('dashboard.mood') }}</h3>
          <button @click="handleRefreshMood" class="text-stone-300 hover:text-violet-400">
            <i :class="['fa-solid text-[10px]', moodLoading ? 'fa-spinner animate-spin' : 'fa-arrows-rotate']"></i>
          </button>
        </div>
        <div v-if="mood" class="flex-1 flex flex-col justify-center">
          <div class="flex items-center gap-3 mb-2">
            <span class="text-3xl">{{ moodEmoji }}</span>
            <div>
              <div :class="['text-2xl font-bold', moodColor]">{{ mood.score.toFixed(1) }}</div>
              <div class="text-xs text-stone-500">{{ mood.label }}</div>
            </div>
          </div>
          <p class="text-xs text-stone-500 leading-snug line-clamp-3">{{ mood.summary }}</p>
          <div v-if="mood.key_factors.length" class="mt-2 flex flex-wrap gap-1">
            <span v-for="(f, i) in mood.key_factors.slice(0, 4)" :key="i"
              class="text-[10px] bg-white/70 rounded-full px-2 py-0.5 text-stone-500">{{ f }}</span>
          </div>
        </div>
        <div v-else class="flex-1 flex items-center justify-center text-xs text-stone-400 text-center">
          {{ t('dashboard.moodEmpty') }}
        </div>
      </section>

      <!-- Stat tiles: 3 across on mobile -->
      <section class="md:col-span-2 lg:col-span-8 grid grid-cols-3 gap-2">
        <div class="bg-white rounded-2xl border border-stone-100 px-3 py-3 text-center">
          <div class="text-2xl font-bold text-violet-500">{{ pendingCount }}</div>
          <div class="text-[10px] text-stone-400 mt-0.5">{{ t('tasks.status.pending') }}</div>
        </div>
        <div class="bg-white rounded-2xl border border-stone-100 px-3 py-3 text-center">
          <div class="text-2xl font-bold text-amber-500">{{ inProgressCount }}</div>
          <div class="text-[10px] text-stone-400 mt-0.5">{{ t('tasks.status.in_progress') }}</div>
        </div>
        <div class="bg-white rounded-2xl border border-stone-100 px-3 py-3 text-center">
          <div class="text-2xl font-bold text-emerald-500">{{ doneCount }}</div>
          <div class="text-[10px] text-stone-400 mt-0.5">{{ t('tasks.status.done') }}</div>
        </div>
      </section>

      <!-- Today tasks: takes 7 cols on desktop -->
      <section class="md:col-span-2 lg:col-span-7 bg-white rounded-2xl border border-stone-100 p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-xs font-bold text-stone-700"><i class="fa-solid fa-sun mr-1.5 text-violet-400"></i>{{ t('dashboard.today') }}</h3>
          <button @click="router.push('/tasks')" class="text-[11px] text-violet-500">{{ t('home.viewAll') }}</button>
        </div>
        <div v-if="todayTasks.length === 0" class="text-center py-6 text-xs text-stone-300">
          <i class="fa-regular fa-face-smile block text-lg mb-1"></i>{{ t('dashboard.todayEmpty') }}
        </div>
        <div v-else class="space-y-1.5">
          <div v-for="task in todayTasks.slice(0, 6)" :key="task.id"
            @click="router.push('/tasks')"
            class="flex items-center gap-2.5 rounded-xl bg-stone-50 hover:bg-stone-100 px-3 py-2 cursor-pointer transition-colors">
            <span :class="['w-2 h-2 rounded-full shrink-0', priorityDot(task.priority)]"></span>
            <span :class="['text-xs flex-1 truncate', task.status === 'in_progress' ? 'text-amber-700 font-medium' : 'text-stone-700']">{{ task.title }}</span>
            <span v-if="task.status === 'in_progress'" class="text-[9px] text-amber-500">{{ t('tasks.status.in_progress') }}</span>
            <span v-else-if="task.due_date" class="text-[10px] text-stone-400">{{ formatSmartDateTime(task.due_date, locale) }}</span>
          </div>
          <p v-if="todayTasks.length > 6" class="text-[10px] text-stone-400 text-center pt-1">+{{ todayTasks.length - 6 }} {{ t('home.tasksUnit') }}</p>
        </div>
      </section>

      <!-- Week heatmap: 5 cols on desktop -->
      <section class="md:col-span-1 lg:col-span-5 bg-white rounded-2xl border border-stone-100 p-4">
        <h3 class="text-xs font-bold text-stone-700 mb-3"><i class="fa-solid fa-fire mr-1.5 text-violet-400"></i>{{ t('dashboard.week') }}</h3>
        <div class="flex items-end gap-1.5 h-20">
          <div v-for="day in weekHeatmap" :key="day.key" class="flex-1 flex flex-col items-center justify-end gap-1">
            <div :class="['w-full rounded-md transition-all', heatOpacity(day.count)]"
              :style="{ height: (30 + (day.count / heatMax) * 40) + 'px' }"
              :title="`${day.label}: ${day.count} 项`"></div>
            <span class="text-[9px] text-stone-400">{{ day.label }}</span>
          </div>
        </div>
        <div class="flex items-center justify-between mt-3 text-[10px] text-stone-400">
          <span><i class="fa-solid fa-square mr-1 text-stone-200"></i>{{ t('dashboard.heatEmpty') }}</span>
          <span>→</span>
          <span><i class="fa-solid fa-square mr-1 text-violet-500"></i>{{ t('dashboard.heatActive') }}</span>
        </div>
      </section>

      <!-- Upcoming: 7 cols on desktop -->
      <section class="md:col-span-2 lg:col-span-7 bg-white rounded-2xl border border-stone-100 p-4">
        <h3 class="text-xs font-bold text-stone-700 mb-3"><i class="fa-solid fa-forward mr-1.5 text-violet-400"></i>{{ t('dashboard.upcoming') }}</h3>
        <div v-if="upcomingTasks.length === 0" class="text-center py-4 text-xs text-stone-300">{{ t('dashboard.upcomingEmpty') }}</div>
        <div v-else class="space-y-1.5">
          <div v-for="task in upcomingTasks.slice(0, 5)" :key="task.id"
            @click="router.push('/tasks')"
            class="flex items-center gap-2.5 rounded-xl bg-stone-50 hover:bg-stone-100 px-3 py-2 cursor-pointer transition-colors">
            <span :class="['w-2 h-2 rounded-full shrink-0', priorityDot(task.priority)]"></span>
            <span class="text-xs flex-1 truncate text-stone-700">{{ task.title }}</span>
            <span class="text-[10px] text-stone-500 font-medium">{{ formatSmartDate(task.due_date, locale) }}</span>
          </div>
        </div>
      </section>

      <!-- Recent capture / emotion mix: 5 cols on desktop -->
      <section class="md:col-span-1 lg:col-span-5 bg-white rounded-2xl border border-stone-100 p-4">
        <h3 class="text-xs font-bold text-stone-700 mb-3"><i class="fa-solid fa-microphone mr-1.5 text-violet-400"></i>{{ t('dashboard.captureMix') }}</h3>
        <div v-if="emotionBreakdown.length === 0" class="text-center py-4 text-xs text-stone-300">{{ t('dashboard.captureEmpty') }}</div>
        <div v-else class="space-y-2">
          <div v-for="bar in emotionBreakdown" :key="bar.emo" class="flex items-center gap-2">
            <span class="text-[10px] text-stone-500 w-14 shrink-0">{{ bar.label }}</span>
            <div class="flex-1 h-2 bg-stone-100 rounded-full overflow-hidden">
              <div :class="['h-full rounded-full', bar.color]"
                :style="{ width: ((bar.count / records.length) * 100) + '%' }"></div>
            </div>
            <span class="text-[10px] text-stone-400 w-6 text-right">{{ bar.count }}</span>
          </div>
        </div>
      </section>

      <!-- Done today: full width strip -->
      <section v-if="doneToday.length" class="md:col-span-2 lg:col-span-12 bg-emerald-50/50 rounded-2xl border border-emerald-100 p-4">
        <h3 class="text-xs font-bold text-emerald-700 mb-2">
          <i class="fa-solid fa-check mr-1.5"></i>{{ t('dashboard.doneToday') }} · {{ doneToday.length }}
        </h3>
        <div class="flex flex-wrap gap-2">
          <span v-for="t in doneToday" :key="t.id"
            class="text-[11px] bg-white rounded-full px-3 py-1 text-stone-600 border border-emerald-100">
            <i class="fa-solid fa-check text-emerald-400 text-[9px] mr-1"></i>{{ t.title }}
          </span>
        </div>
      </section>

    </div>
  </div>
</template>

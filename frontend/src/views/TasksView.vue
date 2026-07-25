<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { listTasks, createTask, updateTask, deleteTask, type TaskOut } from '../api/client'
import { groupByDay, formatSmartDate, dayOffset } from '../utils/date'
import TaskCard from '../components/TaskCard.vue'

const { t, locale } = useI18n()

const tasks = ref<TaskOut[]>([])
const loading = ref(false)
// Note: 'done' filter is intentionally removed — completed tasks live in the
// Timeline view. Filters here are focused on active/soon-to-be-active work.
const statusFilter = ref<'' | 'today' | 'pending' | 'in_progress'>('')
const showCreate = ref(false)
const newTitle = ref('')
const newPriority = ref('medium')

async function load() {
  loading.value = true
  try {
    // Always fetch pending + in_progress; we filter/group on the client.
    const res = await listTasks({ status: 'pending,in_progress', sort: 'due_date' })
    tasks.value = res.items
  } catch (e) { console.error(e) } finally { loading.value = false }
}

async function handleStatusChange(id: number, status: string) { try { await updateTask(id, { status }); await load() } catch (e) { console.error(e) } }
async function handleDelete(id: number) { try { await deleteTask(id); await load() } catch (e) { console.error(e) } }

async function handleCreate() {
  const title = newTitle.value.trim()
  if (!title) return
  try { await createTask({ title, priority: newPriority.value }); newTitle.value = ''; newPriority.value = 'medium'; showCreate.value = false; await load() } catch (e) { console.error(e) }
}

// Filter the list based on the active tab.
const filteredTasks = computed(() => {
  if (statusFilter.value === 'in_progress') return tasks.value.filter(t => t.status === 'in_progress')
  if (statusFilter.value === 'pending') return tasks.value.filter(t => t.status === 'pending')
  if (statusFilter.value === 'today') {
    return tasks.value.filter(t => {
      // "Today" = in-progress OR due today OR created today (with no due date)
      if (t.status === 'in_progress') return true
      if (t.due_date && dayOffset(t.due_date) === 0) return true
      if (!t.due_date && dayOffset(t.created_at) === 0) return true
      return false
    })
  }
  return tasks.value  // '' = 全部活跃
})

// Group by the sort key (due date if present, otherwise created).
// The pass-through is done so items land in chronological buckets: today,
// tomorrow, day after, etc. In-progress tasks with no due date fall under
// their created day so they don't vanish.
const grouped = computed(() => {
  return groupByDay(filteredTasks.value, t => t.due_date || t.created_at)
})

// Sort day keys: today first, then future days ascending, then past days
// descending, then the null bucket (no date).
const sortedDays = computed(() => {
  const keys = Array.from(grouped.value.keys())
  return keys.sort((a, b) => {
    if (a === null) return 1
    if (b === null) return -1
    const oa = dayOffset(a) ?? 0
    const ob = dayOffset(b) ?? 0
    // Today first, then future ascending, then past descending
    if (oa >= 0 && ob >= 0) return oa - ob
    if (oa < 0 && ob < 0) return ob - oa
    return oa >= 0 ? -1 : 1
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
      <h2 class="text-base font-bold text-stone-700"><i class="fa-solid fa-circle-check mr-2 text-violet-400"></i>{{ t('tasks.title') }}</h2>
      <div class="flex gap-2 flex-wrap">
        <div class="flex gap-1">
          <button v-for="opt in [
            {v: '', k: 'active'},
            {v: 'today', k: 'today'},
            {v: 'pending', k: 'pending'},
            {v: 'in_progress', k: 'inProgress'},
          ]" :key="opt.v"
            @click="statusFilter = opt.v as any"
            :class="['text-xs px-3 py-2 rounded-full font-medium transition-colors',
              statusFilter === opt.v ? 'bg-violet-100 text-violet-600' : 'text-stone-400 active:text-stone-600 active:bg-stone-100']">
            {{ t(`tasks.filter.${opt.k}`) }}
          </button>
        </div>
        <button @click="showCreate = !showCreate" class="text-xs bg-violet-500 hover:bg-violet-600 text-white rounded-full px-4 py-1.5 font-semibold transition-colors">
          <i class="fa-solid fa-plus mr-1"></i>{{ t('tasks.newTask') }}
        </button>
      </div>
    </div>

    <p class="text-[11px] text-stone-400 -mt-2">
      <i class="fa-regular fa-lightbulb mr-1"></i>{{ t('tasks.doneMovedHint') }}
    </p>

    <div v-if="showCreate" class="bg-white rounded-2xl shadow-sm p-4 space-y-3">
      <input v-model="newTitle" @keydown.enter="handleCreate" type="text" :placeholder="t('tasks.placeholder')"
        class="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-2.5 text-sm placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-transparent" />
      <div class="flex gap-2">
        <select v-model="newPriority" class="text-xs border border-stone-200 rounded-xl px-3 py-2 bg-white text-stone-600">
          <option value="high">{{ t('priority.high') }}</option>
          <option value="medium">{{ t('priority.medium') }}</option>
          <option value="low">{{ t('priority.low') }}</option>
        </select>
        <button @click="handleCreate" :disabled="!newTitle.trim()" class="text-xs bg-violet-500 hover:bg-violet-600 disabled:bg-stone-200 text-white rounded-xl px-4 py-2 font-medium transition-colors ml-auto">{{ t('tasks.add') }}</button>
        <button @click="showCreate = false" class="text-xs bg-stone-100 hover:bg-stone-200 text-stone-600 rounded-xl px-4 py-2 font-medium transition-colors">{{ t('tasks.cancel') }}</button>
      </div>
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="n in 3" :key="n" class="bg-stone-100 rounded-2xl h-20 animate-pulse"></div>
    </div>

    <div v-else-if="filteredTasks.length === 0" class="text-center py-16 text-stone-400">
      <i class="fa-solid fa-circle-check text-3xl mb-4 block text-stone-200"></i>
      <p class="text-base text-stone-500 font-medium">{{ t('tasks.empty') }}</p>
      <p class="text-sm text-stone-300 mt-1">{{ t('tasks.emptySub') }}</p>
    </div>

    <!-- Day-grouped task list -->
    <div v-else class="space-y-5">
      <section v-for="dayK in sortedDays" :key="dayK ?? 'someday'" class="space-y-2">
        <div class="flex items-center gap-2 sticky top-0 bg-white/90 backdrop-blur-sm py-1 z-[1]">
          <span class="text-xs font-bold text-stone-700">{{ dayLabel(dayK) }}</span>
          <span class="text-[10px] text-stone-400">{{ grouped.get(dayK)?.length ?? 0 }} {{ t('home.tasksUnit') }}</span>
          <div class="flex-1 h-px bg-stone-100"></div>
        </div>
        <div class="space-y-3">
          <TaskCard v-for="task in grouped.get(dayK)" :key="task.id" :task="task"
            @status-change="handleStatusChange" @delete="handleDelete" />
        </div>
      </section>
    </div>
  </div>
</template>

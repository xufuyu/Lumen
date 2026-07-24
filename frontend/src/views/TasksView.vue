<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listTasks, createTask, updateTask, deleteTask, type TaskOut } from '../api/client'
import TaskCard from '../components/TaskCard.vue'

const tasks = ref<TaskOut[]>([])
const loading = ref(false)
const statusFilter = ref('')
const showCreate = ref(false)
const newTitle = ref('')
const newPriority = ref('medium')

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { sort: 'priority' }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await listTasks(params as Parameters<typeof listTasks>[0])
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

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-base font-bold text-stone-700"><i class="fa-solid fa-circle-check mr-2 text-violet-400"></i>我要做什么？</h2>
      <div class="flex gap-2">
        <div class="flex gap-1">
          <button v-for="opt in [{v:'',t:'活跃'},{v:'pending',t:'待办'},{v:'in_progress',t:'进行中'},{v:'done',t:'已完成'}]" :key="opt.v"
            @click="statusFilter = opt.v; load()"
            :class="['text-xs px-3 py-2 rounded-full font-medium transition-colors',
              statusFilter === opt.v ? 'bg-violet-100 text-violet-600' : 'text-stone-400 active:text-stone-600 active:bg-stone-100']">
            {{ opt.t }}
          </button>
        </div>
        <button @click="showCreate = !showCreate" class="text-xs bg-violet-500 hover:bg-violet-600 text-white rounded-full px-4 py-1.5 font-semibold transition-colors">+ 新增</button>
      </div>
    </div>

    <div v-if="showCreate" class="bg-white rounded-2xl shadow-sm p-4 space-y-3">
      <input v-model="newTitle" @keydown.enter="handleCreate" type="text" placeholder="输入任务标题…"
        class="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-2.5 text-sm placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-transparent" />
      <div class="flex gap-2">
        <select v-model="newPriority" class="text-xs border border-stone-200 rounded-xl px-3 py-2 bg-white text-stone-600">
          <option value="high">高优先</option><option value="medium">中等</option><option value="low">低优先</option>
        </select>
        <button @click="handleCreate" :disabled="!newTitle.trim()" class="text-xs bg-violet-500 hover:bg-violet-600 disabled:bg-stone-200 text-white rounded-xl px-4 py-2 font-medium transition-colors ml-auto">添加</button>
        <button @click="showCreate = false" class="text-xs bg-stone-100 hover:bg-stone-200 text-stone-600 rounded-xl px-4 py-2 font-medium transition-colors">取消</button>
      </div>
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="n in 3" :key="n" class="bg-stone-100 rounded-2xl h-20 animate-pulse"></div>
    </div>

    <div v-else-if="tasks.length === 0" class="text-center py-16 text-stone-400">
      <i class="fa-solid fa-circle-check text-3xl mb-4 block text-stone-200"></i>
      <p class="text-base text-stone-500 font-medium">还没有想做的事</p>
      <p class="text-sm text-stone-300 mt-1">记录内容中提到的行动项会自动出现在这里</p>
    </div>

    <div v-else class="space-y-3">
      <TaskCard v-for="task in tasks" :key="task.id" :task="task" @status-change="handleStatusChange" @delete="handleDelete" />
    </div>
  </div>
</template>
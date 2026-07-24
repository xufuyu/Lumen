<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listEvents, updateEvent, deleteEvent, type EventOut } from '../api/client'
import TimelineCard from '../components/TimelineCard.vue'

const events = ref<EventOut[]>([])
const loading = ref(false)
const statusFilter = ref('')

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { limit: 50 }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await listEvents(params as Parameters<typeof listEvents>[0])
    events.value = res.items
  } catch (e) { console.error(e) } finally { loading.value = false }
}

async function handleConfirm(id: number) { try { await updateEvent(id, { status: 'confirmed' }); await load() } catch (e) { console.error(e) } }
async function handleDelete(id: number) { try { await deleteEvent(id); await load() } catch (e) { console.error(e) } }

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-base font-bold text-stone-700"><i class="fa-solid fa-calendar-days mr-2 text-violet-400"></i>我做了什么？</h2>
      <div class="flex gap-1">
        <button v-for="opt in [{v:'',t:'全部'},{v:'inferred',t:'系统推测'},{v:'confirmed',t:'已确认'},{v:'modified',t:'已修改'}]" :key="opt.v"
          @click="statusFilter = opt.v; load()"
          :class="['text-xs px-3 py-2 rounded-full font-medium transition-colors',
            statusFilter === opt.v ? 'bg-violet-100 text-violet-600' : 'text-stone-400 active:text-stone-600 active:bg-stone-100']">
          {{ opt.t }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="n in 3" :key="n" class="bg-stone-100 rounded-2xl h-24 animate-pulse"></div>
    </div>

    <div v-else-if="events.length === 0" class="text-center py-16 text-stone-400">
      <i class="fa-solid fa-calendar-days text-3xl mb-4 block text-stone-200"></i>
      <p class="text-base text-stone-500 font-medium">还没有做过的事</p>
      <p class="text-sm text-stone-300 mt-1">{{ statusFilter ? '没有匹配的事件' : '在首页记录一些活动后，系统会自动整理出你做过的事' }}</p>
    </div>

    <div v-else class="space-y-3">
      <TimelineCard v-for="event in events" :key="event.id" :event="event" @confirm="handleConfirm" @delete="handleDelete" />
    </div>
  </div>
</template>
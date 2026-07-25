<script setup lang="ts">
import type { EventOut } from '../api/client'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TooltipIcon from './TooltipIcon.vue'

const props = defineProps<{ event: EventOut }>()
const emit = defineEmits<{ confirm: [id: number]; delete: [id: number] }>()
const { t, locale } = useI18n()

const statusBadge = computed(() => {
  switch (props.event.status) {
    case 'inferred': return { text: t('timeline.status.inferred'), color: 'bg-amber-50 text-amber-600' }
    case 'confirmed': return { text: t('timeline.status.confirmed'), color: 'bg-emerald-50 text-emerald-600' }
    case 'modified': return { text: t('timeline.status.modified'), color: 'bg-sky-50 text-sky-600' }
    default: return { text: props.event.status, color: 'bg-stone-50 text-stone-500' }
  }
})

function formatTime(dt: string | null) {
  if (!dt) return null
  const d = new Date(dt)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) return d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString(locale.value, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="bg-white rounded-2xl shadow-sm shadow-stone-200/50 p-4 hover:shadow-md transition-shadow">
    <div class="flex gap-3">
      <!-- Timeline dot -->
      <div class="flex flex-col items-center pt-1">
        <div class="w-2.5 h-2.5 rounded-full bg-violet-200 ring-2 ring-violet-50 shrink-0"></div>
        <div class="w-px flex-1 bg-stone-100 mt-1"></div>
      </div>

      <div class="flex-1 min-w-0 pb-2">
        <div class="flex items-center gap-2 flex-wrap mb-1">
          <h3 class="font-semibold text-stone-800 text-sm">{{ event.title }}</h3>
          <span :class="['text-[11px] px-1.5 py-0.5 rounded-full font-medium', statusBadge.color]">{{ statusBadge.text }}</span>
          <TooltipIcon :text="t('timeline.inferredTip')" />
        </div>
        <p v-if="event.description" class="text-sm text-stone-500 line-clamp-2">{{ event.description }}</p>
        <div class="flex items-center gap-3 mt-2 text-xs text-stone-400">
          <span v-if="event.start_time">{{ formatTime(event.start_time) }}</span>
          <span v-if="event.source_record_ids.length">{{ t('timeline.fromRecords', { n: event.source_record_ids.length }) }}</span>
        </div>

        <div class="flex gap-2 mt-3">
          <button v-if="event.status === 'inferred'" @click="emit('confirm', event.id)"
            class="text-xs text-emerald-600 active:text-emerald-800 font-medium transition-colors py-1 px-2 -ml-2 rounded-lg active:bg-emerald-50">
            <i class="fa-solid fa-check mr-1"></i>{{ t('timeline.confirm') }}
          </button>
          <button @click="emit('delete', event.id)"
            class="text-xs text-stone-400 active:text-rose-500 transition-colors py-1 px-2 rounded-lg active:bg-rose-50">{{ t('records.delete') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
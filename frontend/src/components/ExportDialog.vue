<script setup lang="ts">
/**
 * ExportDialog — pick a scope (all / today / pending) and download markdown.
 *
 * The dialog opens over the app, previews the count for each scope so the
 * user sees what they're about to grab, and triggers a browser download.
 */
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { exportMarkdown, getExportCounts, type ExportScope, type ExportCounts } from '../api/client'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

const counts = ref<ExportCounts | null>(null)
const busy = ref<ExportScope | null>(null)
const err = ref('')

async function loadCounts() {
  try {
    counts.value = await getExportCounts()
  } catch (e) {
    console.error(e)
  }
}

async function downloadScope(scope: ExportScope) {
  busy.value = scope
  err.value = ''
  try {
    const blob = await exportMarkdown(scope)
    const url = URL.createObjectURL(blob)
    // Extract filename from a temporary anchor with `download` attribute.
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const filename = `lumen-${scope}-${stamp}.md`
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: unknown) {
    err.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = null
  }
}

onMounted(loadCounts)
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="props.open" class="fixed inset-0 z-50 flex items-center justify-center" @click.self="emit('close')">
        <div class="absolute inset-0 bg-black/30" />
        <div class="relative bg-white rounded-2xl shadow-xl w-[420px] max-w-[92vw] mx-4 p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-bold text-stone-700">
              <i class="fa-solid fa-file-arrow-down mr-2 text-violet-400"></i>{{ t('export.title') }}
            </h2>
            <button @click="emit('close')" class="text-stone-300 hover:text-stone-500">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>

          <p class="text-[11px] text-stone-400 mb-4">{{ t('export.hint') }}</p>

          <div class="space-y-2.5">
            <!-- All -->
            <button @click="downloadScope('all')" :disabled="busy !== null"
              class="w-full flex items-center gap-3 rounded-xl border border-stone-200 hover:border-violet-300 hover:bg-violet-50/30 px-4 py-3 text-left transition-colors disabled:opacity-50">
              <div class="w-9 h-9 rounded-lg bg-violet-50 text-violet-500 flex items-center justify-center shrink-0">
                <i class="fa-solid fa-database text-sm"></i>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold text-stone-700">{{ t('export.all') }}</p>
                <p class="text-[10px] text-stone-400">
                  <template v-if="counts">
                    {{ t('export.taskCount', { n: counts.all.tasks }) }} ·
                    {{ t('export.eventCount', { n: counts.all.events }) }} ·
                    {{ t('export.recordCount', { n: counts.all.records }) }}
                  </template>
                  <template v-else>{{ t('export.loading') }}</template>
                </p>
              </div>
              <i v-if="busy === 'all'" class="fa-solid fa-spinner animate-spin text-violet-400"></i>
              <i v-else class="fa-solid fa-download text-stone-300"></i>
            </button>

            <!-- Today -->
            <button @click="downloadScope('today')" :disabled="busy !== null"
              class="w-full flex items-center gap-3 rounded-xl border border-stone-200 hover:border-violet-300 hover:bg-violet-50/30 px-4 py-3 text-left transition-colors disabled:opacity-50">
              <div class="w-9 h-9 rounded-lg bg-amber-50 text-amber-500 flex items-center justify-center shrink-0">
                <i class="fa-solid fa-sun text-sm"></i>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold text-stone-700">{{ t('export.today') }}</p>
                <p class="text-[10px] text-stone-400">
                  <template v-if="counts">{{ t('export.itemCount', { n: counts.today.total }) }}</template>
                  <template v-else>{{ t('export.loading') }}</template>
                </p>
              </div>
              <i v-if="busy === 'today'" class="fa-solid fa-spinner animate-spin text-violet-400"></i>
              <i v-else class="fa-solid fa-download text-stone-300"></i>
            </button>

            <!-- Pending -->
            <button @click="downloadScope('pending')" :disabled="busy !== null"
              class="w-full flex items-center gap-3 rounded-xl border border-stone-200 hover:border-violet-300 hover:bg-violet-50/30 px-4 py-3 text-left transition-colors disabled:opacity-50">
              <div class="w-9 h-9 rounded-lg bg-rose-50 text-rose-400 flex items-center justify-center shrink-0">
                <i class="fa-regular fa-circle text-sm"></i>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold text-stone-700">{{ t('export.pending') }}</p>
                <p class="text-[10px] text-stone-400">
                  <template v-if="counts">{{ t('export.taskCount', { n: counts.pending.tasks }) }}</template>
                  <template v-else>{{ t('export.loading') }}</template>
                </p>
              </div>
              <i v-if="busy === 'pending'" class="fa-solid fa-spinner animate-spin text-violet-400"></i>
              <i v-else class="fa-solid fa-download text-stone-300"></i>
            </button>
          </div>

          <p v-if="err" class="mt-4 text-[11px] text-rose-500 bg-rose-50 rounded-lg px-3 py-2">
            <i class="fa-solid fa-triangle-exclamation mr-1"></i>{{ err }}
          </p>
          <p class="mt-4 text-[10px] text-stone-400 text-center">{{ t('export.formatHint') }}</p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s ease;
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
</style>

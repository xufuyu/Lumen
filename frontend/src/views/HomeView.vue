<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  createRecord, triggerProcess, getCurrentContext, listRecords, listTasks, listEvents,
  generateMood, getLatestMood, deleteRecord, updateRecord, updateTask, resolveMerge, askQuestionStream,
  type ContextOut, type RecordOut, type TaskOut, type EventOut, type MoodOut, type MergeCandidate,
  type QueryResponse,
} from '../api/client'
import RecordInput from '../components/RecordInput.vue'

const { t } = useI18n()
const router = useRouter()

const context = ref<ContextOut | null>(null)
const contextLoading = ref(false)
const mood = ref<MoodOut | null>(null)
const moodLoading = ref(false)
const recentRecords = ref<RecordOut[]>([])
const activeTasks = ref<TaskOut[]>([])
const recentEvents = ref<EventOut[]>([])
const submitting = ref(false)
const recordCount = ref(0)
const taskCount = ref(0)
const eventCount = ref(0)

const toast = ref<{ type: 'success' | 'error' | 'info'; message: string; icon?: string; action?: { label: string; onClick: () => void } } | null>(null)
const mergeCandidates = ref<MergeCandidate[]>([])
const showStatusDetail = ref(false)

// 后台处理状态：显示一个不阻塞的"整理中"角标
const processing = ref(false)

// 问答：内联展示，与记录共用输入框
interface QAExchange { id: number; question: string; answer?: string; sources?: QueryResponse['sources']; disclaimer?: string | null; loading: boolean }
const qaLog = ref<QAExchange[]>([])
let qaIdCounter = 0

// ── Toast 自动关闭 ─────────────────────────────────────────────────
let toastTimer: ReturnType<typeof setTimeout> | null = null
const TOAST_DURATION: Record<'success' | 'error' | 'info', number> = {
  success: 2500,
  error: 4000,
  info: 4000,
}

function clearToastTimer() {
  if (toastTimer) { clearTimeout(toastTimer); toastTimer = null }
}
function dismissToast() {
  clearToastTimer()
  toast.value = null
}
function showToast(type: 'success' | 'error' | 'info', message: string, icon?: string, action?: { label: string; onClick: () => void }) {
  clearToastTimer()
  toast.value = { type, message, icon, action }
  toastTimer = setTimeout(() => { toast.value = null; toastTimer = null }, action ? 8000 : TOAST_DURATION[type])
}
onUnmounted(clearToastTimer)

async function handleDeleteRecord(id: number) {
  try { await deleteRecord(id); showToast('success', t('records.delete') + ' OK'); await loadAll() } catch (e: unknown) { showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`) }
}
async function handleReprocessRecord(id: number) {
  try { await updateRecord(id, { status: 'unprocessed' }); await triggerProcess(); showToast('success', t('records.reprocess') + ' OK'); await loadAll() } catch (e: unknown) { showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`) }
}

async function loadAll() {
  contextLoading.value = true
  try {
    const [ctx, recs, tasks, events, m] = await Promise.all([
      getCurrentContext().catch(() => null), listRecords({ page_size: 5 }),
      listTasks({ status: 'pending,in_progress' }), listEvents({ limit: 5 }), getLatestMood().catch(() => null),
    ])
    context.value = ctx; recentRecords.value = recs.items; recordCount.value = recs.total
    activeTasks.value = tasks.items; taskCount.value = tasks.total; recentEvents.value = events.items; eventCount.value = events.total
    if (m?.mood) mood.value = m.mood
  } catch { showToast('error', t('input.procError')) } finally { contextLoading.value = false }
}

async function handleRefreshContext() {
  contextLoading.value = true
  try { await triggerProcess(); context.value = await getCurrentContext(); showToast('success', t('home.contextTitle') + ' OK') } catch (e: unknown) { showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`) } finally { contextLoading.value = false }
}
async function handleRefreshMood() {
  moodLoading.value = true
  try { const res = await generateMood(); if (res.mood) { mood.value = res.mood; showToast('success', t('mood.refresh')) } else { showToast('error', res.message || t('input.procError')) } } catch (e: unknown) { showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`) } finally { moodLoading.value = false }
}

// ── 发送：记录落库后，整理和问答并发执行 ────────────
async function handleSend(content: string, type: string = 'text', voiceEmotion: string = '') {
  submitting.value = true

  // 1. 创建记录（快）
  try {
    await createRecord(content, type, voiceEmotion || undefined)
    loadAll()
  } catch (e: unknown) {
    showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`)
    submitting.value = false
    return
  }
  submitting.value = false

  // 2. 后台整理 + 问答 并发（不互等）
  processing.value = true
  const id = ++qaIdCounter
  const entry: QAExchange = { id, question: content, loading: true }
  qaLog.value.push(entry)
  if (qaLog.value.length > 5) qaLog.value.splice(0, qaLog.value.length - 5)

  // 整理（后台）
  const procPromise = (async () => {
    try {
      const procResult = await triggerProcess()
      if (procResult.merge_candidates?.length) {
        mergeCandidates.value = [...mergeCandidates.value, ...procResult.merge_candidates]
      }
      await loadAll()
      if (procResult.tasks_created || procResult.events_created || procResult.tasks_updated) {
        const bits: string[] = []
        if (procResult.tasks_created) bits.push(`${procResult.tasks_created} ${t('input.procTodo')}`)
        if (procResult.tasks_updated) bits.push(`${procResult.tasks_updated} ${t('input.procUpdate')}`)
        if (procResult.events_created) bits.push(`${procResult.events_created} ${t('input.procEvent')}`)
        if (bits.length > 0) showToast('success', `${t('input.procDone')} ${bits.join(' · ')}`)
      }
      // 自动完成的任务 — 显示可撤销 toast
      if (procResult.auto_completed_tasks?.length) {
        for (const act of procResult.auto_completed_tasks) {
          showToast('success', `「${act.title}」${t('tasks.status.done')}`, 'fa-check', {
            label: t('input.undo'),
            onClick: () => updateTask(act.task_id, { status: 'pending' }).then(() => {
              showToast('info', `「${act.title}」${t('input.undoOk')}`)
              loadAll()
            }),
          })
        }
      }
    } catch (e: unknown) {
      showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`)
    }
  })()

  // 问答（并发，流式输出）
  try {
    await askQuestionStream(
      content,
      // onChunk: 流式追加到回答
      (chunk) => {
        const existing = qaLog.value.find(q => q.id === id)
        if (existing) {
          existing.answer = (existing.answer || '') + chunk
        }
      },
      // onDone: 解析最终结果
      (data) => {
        const existing = qaLog.value.find(q => q.id === id)
        if (!existing) return
        if (data.is_question === false) {
          // 不是问题，移除 QA 条目
          qaLog.value = qaLog.value.filter(q => q.id !== id)
        } else {
          existing.answer = data.answer || existing.answer || ''
          existing.sources = data.sources
          existing.disclaimer = data.disclaimer
          existing.loading = false
        }
      },
      // onError
      (err) => {
        const existing = qaLog.value.find(q => q.id === id)
        if (existing) {
          existing.answer = `Error: ${err}`
          existing.loading = false
        }
      },
    )
  } catch (e: unknown) {
    const existing = qaLog.value.find(q => q.id === id)
    if (existing) {
      existing.answer = `Error: ${e instanceof Error ? e.message : ''}`
      existing.loading = false
    }
  }

  await procPromise
  processing.value = false
}
function dismissQA(id: number) {
  qaLog.value = qaLog.value.filter(q => q.id !== id)
}

async function handleResolveMerge(candidate: MergeCandidate, action: 'merge' | 'keep_separate') {
  try {
    await resolveMerge(candidate.new_task_id, action)
    mergeCandidates.value = mergeCandidates.value.filter(c => c.new_task_id !== candidate.new_task_id)
    showToast('success', action === 'merge' ? t('merge.merge') : t('merge.keep'))
    await loadAll()
  } catch (e: unknown) { showToast('error', `${t('input.procError')}: ${e instanceof Error ? e.message : ''}`) }
}

function formatRelative(dt: string) {
  const diff = Date.now() - new Date(dt).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(hours / 24)}天前`
}

const priorityBadge = (p: string) => p === 'high' ? 'bg-rose-50 text-rose-600' : p === 'medium' ? 'bg-amber-50 text-amber-600' : 'bg-stone-100 text-stone-500'
const priorityLabel = (p: string) => p === 'high' ? t('priority.high') : p === 'medium' ? t('priority.medium') : t('priority.low')
const hasContent = computed(() => recordCount.value > 0 || taskCount.value > 0 || eventCount.value > 0)

// Mood display helpers
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

const syncHandler = () => { loadAll() }

onMounted(async () => {
  await loadAll()
  window.addEventListener('lumen:refresh', syncHandler)
  if (!sessionStorage.getItem('advx-welcomed')) {
    sessionStorage.setItem('advx-welcomed', '1')
    showToast('info', hasContent.value
      ? t('home.welcomeBack')
      : t('home.welcome'))
  }
})
onUnmounted(() => {
  window.removeEventListener('lumen:refresh', syncHandler)
})
</script>

<template>
  <div class="flex flex-col min-h-[calc(100vh-7rem)] h-[calc(100dvh-7rem)] lg:h-auto lg:min-h-0 gap-4 lg:grid lg:grid-cols-5 lg:gap-5 lg:grid-flow-dense">

    <!-- Toast -->
    <Transition name="toast-slide">
      <div v-if="toast" @click="dismissToast"
        :class="['fixed top-16 inset-x-4 mx-auto max-w-sm z-50 rounded-2xl px-4 py-3 text-sm font-medium cursor-pointer shadow-lg text-white',
          toast.type === 'success' ? 'bg-emerald-500' :
          toast.type === 'error' ? 'bg-rose-500' :
          'bg-gradient-to-r from-violet-500 to-rose-500']">
        <div class="flex items-center justify-between gap-2">
          <span class="flex-1 min-w-0">
            <i :class="['fa-solid mr-1.5',
              toast.icon ? toast.icon :
              toast.type === 'success' ? 'fa-check-circle' :
              toast.type === 'error' ? 'fa-circle-exclamation' :
              'fa-hand-wave']"></i>{{ toast.message }}
          </span>
          <button v-if="toast.action" @click.stop="toast.action.onClick(); dismissToast()"
            class="shrink-0 text-xs font-semibold underline underline-offset-2 opacity-90 hover:opacity-100">
            {{ toast.action.label }}
          </button>
        </div>
      </div>
    </Transition>

    <!-- Merge Suggestions (desktop: full width) -->
    <TransitionGroup name="merge-fade" tag="div" class="space-y-2 lg:col-span-5">
      <div v-for="c in mergeCandidates" :key="c.new_task_id"
        class="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3">
        <p class="text-xs text-stone-600 leading-snug">
          <span class="font-semibold">「{{ c.new_title }}」</span>
          与 <span class="font-semibold">「{{ c.existing_title }}」</span> 是同一件事吗？
          <span class="text-stone-400">({{ (c.score * 100).toFixed(0) }}%)</span>
        </p>
        <div class="flex gap-2 mt-2">
          <button @click="handleResolveMerge(c, 'merge')"
            class="text-[11px] bg-amber-500 text-white rounded-full px-3 py-1 font-semibold">{{ t('merge.merge') }}</button>
          <button @click="handleResolveMerge(c, 'keep_separate')"
            class="text-[11px] bg-white border border-stone-200 text-stone-500 rounded-full px-3 py-1">{{ t('merge.keep') }}</button>
        </div>
      </div>
    </TransitionGroup>

    <!-- ===== Sections: mobile scrollable, desktop grid items via contents ===== -->
    <div class="flex-1 overflow-y-auto overscroll-contain lg:overflow-visible lg:flex-none lg:contents space-y-4 lg:space-y-0">

      <!-- Tasks: left column top on desktop -->
      <section v-if="hasContent" class="lg:col-span-3 lg:row-start-1">
        <div class="flex items-center justify-between mb-2.5">
          <h2 class="text-sm font-bold text-stone-700">
            <i class="fa-solid fa-circle-check mr-1.5 text-violet-400"></i>我要做什么？
            <span class="text-xs text-stone-400 font-normal ml-1">{{ taskCount }} {{ t('home.tasksUnit') }}</span>
          </h2>
          <button @click="router.push('/tasks')" class="text-xs text-violet-500 font-medium">{{ t('home.viewAll') }}</button>
        </div>
        <div v-if="activeTasks.length === 0" class="text-center py-6 text-stone-300 text-xs">{{ t('home.tasksEmpty') }}</div>
        <div v-else class="space-y-1.5">
          <div v-for="task in activeTasks.slice(0, 4)" :key="task.id"
            @click="router.push('/tasks')"
            class="flex items-center gap-3 rounded-xl bg-stone-50 px-4 py-3 hover:bg-stone-100 transition-colors cursor-pointer active:scale-[0.98]">
            <span :class="['w-2 h-2 rounded-full shrink-0', task.priority === 'high' ? 'bg-rose-400' : task.priority === 'medium' ? 'bg-amber-400' : 'bg-stone-300']"></span>
            <span :class="['text-sm flex-1 truncate', task.status === 'done' ? 'text-stone-400 line-through' : 'text-stone-700']">{{ task.title }}</span>
            <span :class="['text-[10px] px-1.5 py-0.5 rounded-full font-medium', priorityBadge(task.priority)]">{{ priorityLabel(task.priority) }}</span>
          </div>
        </div>
      </section>

      <!-- Events: left column bottom on desktop -->
      <section v-if="hasContent" class="lg:col-span-3 lg:row-start-2">
        <div class="flex items-center justify-between mb-2.5">
          <h2 class="text-sm font-bold text-stone-700">
            <i class="fa-solid fa-calendar-days mr-1.5 text-violet-400"></i>我做了什么？
            <span class="text-xs text-stone-400 font-normal ml-1">{{ eventCount }} {{ t('home.eventsUnit') }}</span>
          </h2>
          <button @click="router.push('/timeline')" class="text-xs text-violet-500 font-medium">{{ t('home.viewAll') }}</button>
        </div>
        <div v-if="recentEvents.length === 0" class="text-center py-6 text-stone-300 text-xs">{{ t('home.eventsEmpty') }}</div>
        <div v-else class="space-y-1.5">
          <div v-for="evt in recentEvents.slice(0, 3)" :key="evt.id"
            @click="router.push('/timeline')"
            class="flex items-center gap-3 rounded-xl bg-stone-50 px-4 py-2.5 hover:bg-stone-100 transition-colors cursor-pointer">
            <div class="w-1.5 h-1.5 rounded-full bg-violet-200 shrink-0"></div>
            <span class="text-sm text-stone-600 truncate flex-1">{{ evt.title }}</span>
            <span v-if="evt.status === 'inferred'" class="text-[10px] text-amber-500 bg-amber-50 px-1.5 py-0.5 rounded-full">{{ t('records.inferred') }}</span>
          </div>
        </div>
      </section>

      <!-- Context: right column bottom on desktop -->
      <section v-if="context && context.id !== 0" class="lg:col-span-2 lg:col-start-4 lg:row-start-2">
        <div class="flex items-center justify-between mb-2.5">
          <h2 class="text-sm font-bold text-stone-700">
            <i class="fa-solid fa-location-dot mr-1.5 text-violet-400"></i>我正在做什么？
          </h2>
          <button @click="handleRefreshContext()" class="text-xs text-violet-500 font-medium">
            <i :class="['fa-solid mr-1', contextLoading ? 'fa-spinner animate-spin' : 'fa-arrows-rotate']"></i>刷新
          </button>
        </div>
        <div class="rounded-xl bg-stone-50 px-4 py-3">
          <p class="text-sm text-stone-600 leading-relaxed line-clamp-3">{{ context.summary }}</p>
        </div>
      </section>

    <!-- Empty state: new user, inside wrapper so input stays at bottom -->
    <div v-if="!hasContent && !contextLoading" class="flex-1 lg:col-span-5 flex flex-col items-center justify-center py-16 text-center">
      <i class="fa-solid fa-hand-wave text-3xl mb-3 block text-stone-200"></i>
      <p class="text-sm text-stone-400 font-medium">{{ t('home.emptyTitle') }}</p>
      <p class="text-xs text-stone-300 mt-1">{{ t('home.emptySub') }}</p>
    </div>

    </div>

    <!-- Input + Mood group (mobile: bottom bar; desktop: below grid) -->
    <div class="shrink-0 lg:col-span-5 space-y-3 lg:space-y-4 bg-white pt-2 lg:pt-0">
      <!-- QA log (inline chat above input) -->
      <TransitionGroup name="qa-fade" tag="div" class="space-y-2">
        <div v-for="qa in qaLog" :key="qa.id"
          class="bg-white rounded-2xl border border-stone-100 shadow-sm shadow-stone-100/50 p-3.5">
          <!-- Question row -->
          <div class="flex items-start gap-2 mb-2">
            <i class="fa-solid fa-user text-[10px] text-stone-300 mt-1"></i>
            <p class="text-xs text-stone-500 flex-1 leading-snug">{{ qa.question }}</p>
            <button @click="dismissQA(qa.id)" class="shrink-0 text-stone-300 hover:text-stone-500 text-xs px-1">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
          <!-- Answer row -->
          <div class="flex items-start gap-2 pl-4 border-l-2 border-sky-100">
            <i class="fa-solid fa-comment-dots text-sky-400 text-xs mt-1 shrink-0"></i>
            <div class="flex-1 min-w-0">
              <p v-if="qa.loading" class="text-sm text-stone-400 italic">
                <span class="inline-block w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse mr-1"></span>
                思考中…
              </p>
              <p v-else class="text-sm text-stone-700 leading-relaxed whitespace-pre-wrap">{{ qa.answer }}</p>
              <div v-if="qa.disclaimer" class="mt-1.5 text-[10px] text-amber-500 italic">
                <i class="fa-solid fa-triangle-exclamation mr-1"></i>{{ qa.disclaimer }}
              </div>
              <div v-if="qa.sources && qa.sources.length" class="mt-2 flex flex-wrap gap-1">
                <span v-for="(s, i) in qa.sources.slice(0, 3)" :key="i"
                  class="text-[10px] bg-stone-50 text-stone-400 rounded-full px-2 py-0.5 truncate max-w-[220px]"
                  :title="s.excerpt">
                  {{ s.excerpt.slice(0, 30) }}{{ s.excerpt.length > 30 ? '…' : '' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- Input -->
      <div class="relative">
        <RecordInput @send="handleSend" @toast="(type, msg) => showToast(type, msg)" :disabled="submitting" />
        <!-- 后台整理指示器 -->
        <Transition name="qa-fade">
          <div v-if="processing" class="absolute -top-2 right-0 flex items-center gap-1 text-[10px] text-violet-500 bg-violet-50 rounded-full px-2 py-0.5 font-medium shadow-sm">
            <i class="fa-solid fa-spinner animate-spin text-[9px]"></i>
            AI 整理中…
          </div>
        </Transition>
      </div>

      <!-- Mood -->
      <div v-if="mood" @click="showStatusDetail = !showStatusDetail"
        class="bg-gradient-to-r from-violet-50/50 to-rose-50/30 rounded-2xl border border-stone-100 px-4 py-3 cursor-pointer active:scale-[0.98] transition-transform hover:shadow-sm">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2.5">
            <span class="text-xl">{{ moodEmoji }}</span>
            <div>
              <div class="flex items-baseline gap-1">
                <span :class="['text-lg font-bold', moodColor]">{{ mood.score.toFixed(1) }}</span>
                <span class="text-xs text-stone-400">{{ mood.label }}</span>
              </div>
              <p class="text-[11px] text-stone-500 line-clamp-1 mt-0.5">{{ mood.summary }}</p>
            </div>
          </div>
          <button @click.stop="handleRefreshMood()"
            class="shrink-0 w-7 h-7 rounded-full bg-white/80 flex items-center justify-center text-stone-300 hover:text-violet-400 transition-colors">
            <i :class="['fa-solid text-[10px]', moodLoading ? 'fa-spinner animate-spin' : 'fa-arrows-rotate']"></i>
          </button>
        </div>

        <Transition name="expand">
          <div v-if="showStatusDetail" class="mt-3 pt-3 border-t border-stone-200/50 space-y-2">
            <div class="flex items-center justify-between text-[10px] text-stone-300 px-0.5">
              <span>1 低落</span><span>5 平稳</span><span>10 良好</span>
            </div>
            <div class="h-2 bg-stone-100 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all duration-700"
                :style="{ width: ((mood.score - 1) / 9 * 100) + '%', backgroundColor: mood.score <= 3 ? '#8b5cf6' : mood.score <= 6 ? '#f59e0b' : '#10b981' }"></div>
            </div>
            <div v-if="mood.key_factors.length" class="flex flex-wrap gap-1.5">
              <span v-for="(f, i) in mood.key_factors" :key="i" class="text-[10px] bg-white/70 rounded-full px-2.5 py-1 text-stone-500">{{ f }}</span>
            </div>
          </div>
        </Transition>
      </div>

      <div v-else @click="handleRefreshMood()"
        class="bg-stone-50 rounded-2xl border border-stone-100 px-4 py-3 flex items-center justify-center gap-2 cursor-pointer hover:shadow-sm">
        <i class="fa-solid fa-heart-circle-plus text-stone-300 text-sm"></i>
        <span class="text-xs text-stone-400">记录一些日常后，点击生成情绪指数</span>
      </div>
    </div>

    <!-- Records: desktop right-column top (hidden on mobile) -->
    <section v-if="hasContent" class="hidden lg:block lg:col-start-4 lg:col-span-2 lg:row-start-1">
      <div class="flex items-center justify-between mb-2.5">
        <h2 class="text-sm font-bold text-stone-700">
          <i class="fa-solid fa-note-sticky mr-1.5 text-violet-400"></i>最近记录
          <span class="text-xs text-stone-400 font-normal ml-1">{{ recordCount }} {{ t('home.recordsUnit') }}</span>
        </h2>
        <button @click="router.push('/timeline')" class="text-xs text-violet-500 font-medium">{{ t('home.viewAll') }}</button>
      </div>
      <div v-if="recentRecords.length === 0" class="text-center py-6 text-stone-300 text-xs">{{ t('home.recordsEmpty') }}</div>
      <div v-else class="space-y-1.5">
        <div v-for="rec in recentRecords.slice(0, 5)" :key="rec.id"
          class="rounded-xl bg-stone-50 px-4 py-3">
          <p class="text-sm text-stone-700 leading-snug">{{ rec.content }}</p>
          <div class="flex items-center justify-between mt-2">
            <p class="text-xs text-stone-400">{{ formatRelative(rec.created_at) }}</p>
            <div class="flex gap-1">
              <button @click="handleReprocessRecord(rec.id)" class="text-xs text-violet-400 hover:text-violet-600 px-2 py-1"><i class="fa-solid fa-rotate-right mr-1"></i>{{ t('records.reprocess') }}</button>
              <button @click="handleDeleteRecord(rec.id)" class="text-xs text-rose-400 hover:text-rose-600 px-2 py-1"><i class="fa-solid fa-trash-can mr-1"></i>{{ t('records.delete') }}</button>
            </div>
          </div>
        </div>
      </div>
    </section>


  </div>

  <!-- Records: mobile below viewport (scroll down to see) -->
  <section v-if="hasContent" class="lg:hidden px-4 sm:px-6 pt-4 pb-6 space-y-1.5">
    <div class="flex items-center justify-between mb-2.5">
      <h2 class="text-sm font-bold text-stone-700">
        <i class="fa-solid fa-note-sticky mr-1.5 text-violet-400"></i>最近记录
        <span class="text-xs text-stone-400 font-normal ml-1">{{ recordCount }} {{ t('home.recordsUnit') }}</span>
      </h2>
      <button @click="router.push('/timeline')" class="text-xs text-violet-500 font-medium">{{ t('home.viewAll') }}</button>
    </div>
    <div v-if="recentRecords.length === 0" class="text-center py-6 text-stone-300 text-xs">{{ t('home.recordsEmpty') }}</div>
    <div v-else class="space-y-1.5">
      <div v-for="rec in recentRecords.slice(0, 5)" :key="rec.id"
        class="rounded-xl bg-stone-50 px-4 py-3">
        <p class="text-sm text-stone-700 leading-snug">{{ rec.content }}</p>
        <div class="flex items-center justify-between mt-2">
          <p class="text-xs text-stone-400">{{ formatRelative(rec.created_at) }}</p>
          <div class="flex gap-1">
            <button @click="handleReprocessRecord(rec.id)" class="text-xs text-violet-400 hover:text-violet-600 px-2 py-1"><i class="fa-solid fa-rotate-right mr-1"></i>{{ t('records.reprocess') }}</button>
            <button @click="handleDeleteRecord(rec.id)" class="text-xs text-rose-400 hover:text-rose-600 px-2 py-1"><i class="fa-solid fa-trash-can mr-1"></i>{{ t('records.delete') }}</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.toast-slide-enter-active { transition: all 0.2s ease; }
.toast-slide-leave-active { transition: all 0.15s ease; }
.toast-slide-enter-from { opacity: 0; transform: translateY(-8px); }
.toast-slide-leave-to { opacity: 0; transform: translateY(-8px); }

.merge-fade-enter-active { transition: all 0.25s ease; }
.merge-fade-leave-active { transition: all 0.15s ease; }
.merge-fade-enter-from { opacity: 0; transform: translateY(-6px); }
.merge-fade-leave-to { opacity: 0; transform: translateX(16px); }

.expand-enter-active { transition: all 0.2s ease; }
.expand-leave-active { transition: all 0.15s ease; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; overflow: hidden; }

.qa-fade-enter-active { transition: all 0.22s ease; }
.qa-fade-leave-active { transition: all 0.15s ease; position: absolute; width: 100%; }
.qa-fade-enter-from { opacity: 0; transform: translateY(6px); }
.qa-fade-leave-to { opacity: 0; transform: translateY(-4px); }
.qa-fade-move { transition: transform 0.2s ease; }
</style>

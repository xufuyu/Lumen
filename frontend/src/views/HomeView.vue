<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  createRecord, triggerProcess, getCurrentContext, listRecords, listTasks, listEvents,
  generateMood, getLatestMood, deleteRecord, updateRecord, resolveMerge, askQuestion,
  type ContextOut, type RecordOut, type TaskOut, type EventOut, type MoodOut, type MergeCandidate,
  type QueryResponse,
} from '../api/client'
import RecordInput from '../components/RecordInput.vue'

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

const toast = ref<{ type: 'success' | 'error' | 'info'; message: string; icon?: string } | null>(null)
const mergeCandidates = ref<MergeCandidate[]>([])
const showRecords = ref(false)
const showStatusDetail = ref(false)

// 后台处理状态：显示一个不阻塞的"整理中"角标
const processing = ref(false)

// 声学情绪 → 中文短标签（用于 toast）
const EMO_LABEL: Record<string, string> = {
  neutral: '平和', happy: '愉悦', sad: '低落', angry: '烦躁',
  fearful: '焦虑', disgusted: '厌烦', surprised: '惊讶',
}

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
function showToast(type: 'success' | 'error' | 'info', message: string, icon?: string) {
  clearToastTimer()
  toast.value = { type, message, icon }
  toastTimer = setTimeout(() => { toast.value = null; toastTimer = null }, TOAST_DURATION[type])
}
onUnmounted(clearToastTimer)

async function handleDeleteRecord(id: number) {
  if (!confirm('确定要删除这条记录吗？')) return
  try { await deleteRecord(id); showToast('success', '记录已删除。'); await loadAll() } catch (e: unknown) { showToast('error', `删除失败：${e instanceof Error ? e.message : '未知错误'}`) }
}
async function handleReprocessRecord(id: number) {
  try { await updateRecord(id, { status: 'unprocessed' }); await triggerProcess(); showToast('success', '已重新整理。'); await loadAll() } catch (e: unknown) { showToast('error', `整理失败：${e instanceof Error ? e.message : '未知错误'}`) }
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
  } catch { showToast('error', '加载数据失败，请检查网络连接。') } finally { contextLoading.value = false }
}

async function handleRefreshContext() {
  contextLoading.value = true
  try { await triggerProcess(); context.value = await getCurrentContext(); showToast('success', '"我正在做什么？"已刷新。') } catch (e: unknown) { showToast('error', `刷新失败：${e instanceof Error ? e.message : '未知错误'}`) } finally { contextLoading.value = false }
}
async function handleRefreshMood() {
  moodLoading.value = true
  try { const res = await generateMood(); if (res.mood) { mood.value = res.mood; showToast('success', '情绪指数已生成。') } else { showToast('error', res.message || '生成失败。') } } catch (e: unknown) { showToast('error', `生成失败：${e instanceof Error ? e.message : '未知错误'}`) } finally { moodLoading.value = false }
}

// ── 提交记录：只等 createRecord（快），整理放后台 ────────────────
async function handleSubmit(content: string, type: string = 'text', voiceEmotion: string = '') {
  submitting.value = true
  try {
    await createRecord(content, type, voiceEmotion || undefined)
    if (voiceEmotion) {
      const emoLabel = EMO_LABEL[voiceEmotion] || voiceEmotion
      showToast('success', `已记录（语气：${emoLabel}），后台整理中…`)
    } else {
      showToast('success', '已记录，正在后台整理…')
    }
    // 快速刷新列表让新记录立刻显示（此时状态是 unprocessed）
    loadAll()
  } catch (e: unknown) {
    showToast('error', `记录失败：${e instanceof Error ? e.message : '未知错误'}`)
    submitting.value = false
    return
  }
  submitting.value = false

  // 后台执行 LLM 整理，不阻塞 UI
  processing.value = true
  try {
    const procResult = await triggerProcess()
    if (procResult.merge_candidates && procResult.merge_candidates.length > 0) {
      mergeCandidates.value = [...mergeCandidates.value, ...procResult.merge_candidates]
    }
    await loadAll()
    // 只在有实质产出时才提示，避免噪音
    if (procResult.tasks_created || procResult.events_created) {
      const bits: string[] = []
      if (procResult.tasks_created) bits.push(`${procResult.tasks_created} 项待办`)
      if (procResult.events_created) bits.push(`${procResult.events_created} 个事件`)
      showToast('success', `整理完成 · 新增 ${bits.join(' · ')}`)
    }
  } catch (e: unknown) {
    showToast('error', `后台整理失败：${e instanceof Error ? e.message : '未知错误'}`)
  } finally {
    processing.value = false
  }
}

// ── 问答：同一输入框，走另一个 API，结果内联展示 ────────────────
async function handleAsk(question: string, _voiceEmotion: string = '') {
  // 问答暂不使用声学情绪（可在未来接入 answer_query prompt）
  const id = ++qaIdCounter
  const entry: QAExchange = { id, question, loading: true }
  qaLog.value.push(entry)
  // 保持最近 5 条问答，避免堆积
  if (qaLog.value.length > 5) qaLog.value.splice(0, qaLog.value.length - 5)
  try {
    const res = await askQuestion(question)
    entry.answer = res.answer
    entry.sources = res.sources
    entry.disclaimer = res.disclaimer
  } catch (e: unknown) {
    entry.answer = `抱歉，出错了：${e instanceof Error ? e.message : '未知错误'}`
  } finally {
    entry.loading = false
  }
}
function dismissQA(id: number) {
  qaLog.value = qaLog.value.filter(q => q.id !== id)
}

async function handleResolveMerge(candidate: MergeCandidate, action: 'merge' | 'keep_separate') {
  try {
    await resolveMerge(candidate.new_task_id, action)
    mergeCandidates.value = mergeCandidates.value.filter(c => c.new_task_id !== candidate.new_task_id)
    showToast('success', action === 'merge' ? '任务已合并。' : '任务分别保留。')
    await loadAll()
  } catch (e: unknown) { showToast('error', `操作失败：${e instanceof Error ? e.message : '未知错误'}`) }
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
const priorityLabel = (p: string) => p === 'high' ? '高' : p === 'medium' ? '中' : '低'
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

onMounted(async () => {
  await loadAll()
  if (!sessionStorage.getItem('advx-welcomed')) {
    sessionStorage.setItem('advx-welcomed', '1')
    showToast('info', hasContent.value
      ? '欢迎回来 — 记录任何想到的事，我来帮你整理。'
      : '欢迎来到 AdventureX — 想到什么就写下来，或者直接问我。')
  }
})
</script>

<template>
  <div class="flex flex-col gap-4 lg:gap-5 min-h-[calc(100dvh-7rem)] lg:min-h-0">

    <!-- Toast -->
    <Transition name="toast-slide">
      <div v-if="toast" @click="dismissToast"
        :class="['fixed top-16 inset-x-4 mx-auto max-w-sm z-50 rounded-2xl px-4 py-3 text-sm font-medium cursor-pointer shadow-lg text-white',
          toast.type === 'success' ? 'bg-emerald-500' :
          toast.type === 'error' ? 'bg-rose-500' :
          'bg-gradient-to-r from-violet-500 to-rose-500']">
        <span>
          <i :class="['fa-solid mr-1.5',
            toast.icon ? toast.icon :
            toast.type === 'success' ? 'fa-check-circle' :
            toast.type === 'error' ? 'fa-circle-exclamation' :
            'fa-hand-wave']"></i>{{ toast.message }}
        </span>
      </div>
    </Transition>

    <!-- Records Overlay (slide-in on mobile, centered modal on desktop) -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="showRecords" class="fixed inset-0 z-40 flex lg:items-center lg:justify-center" @click.self="showRecords = false">
          <div class="absolute inset-0 bg-black/20 backdrop-blur-sm" />
          <!-- Mobile: slide from left | Desktop: centered card -->
          <div class="relative bg-white shadow-2xl overflow-y-auto
            absolute inset-y-0 left-0 w-80 max-w-[85vw]
            lg:static lg:inset-auto lg:w-[480px] lg:max-h-[70vh] lg:rounded-2xl lg:mx-4">
            <div class="sticky top-0 bg-white/95 backdrop-blur border-b border-stone-100 px-5 py-4 flex items-center justify-between lg:rounded-t-2xl">
              <h2 class="text-sm font-bold text-stone-700"><i class="fa-solid fa-note-sticky mr-2 text-violet-400"></i>最近记录</h2>
              <button @click="showRecords = false" class="text-stone-300 hover:text-stone-500"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div class="p-4 space-y-2">
              <div v-if="recentRecords.length === 0" class="text-center py-12 text-stone-400">
                <i class="fa-solid fa-note-sticky text-2xl mb-2 block text-stone-200"></i>
                <p class="text-xs">暂无记录</p>
              </div>
              <div v-for="rec in recentRecords" :key="rec.id"
                class="rounded-xl bg-stone-50 px-4 py-3">
                <p class="text-sm text-stone-700 leading-snug">{{ rec.content }}</p>
                <div class="flex items-center justify-between mt-2">
                  <p class="text-xs text-stone-400">{{ formatRelative(rec.created_at) }}</p>
                  <div class="flex gap-1">
                    <button @click="handleReprocessRecord(rec.id)" class="text-xs text-violet-400 hover:text-violet-600 px-2 py-1"><i class="fa-solid fa-rotate-right mr-1"></i>重整理</button>
                    <button @click="handleDeleteRecord(rec.id)" class="text-xs text-rose-400 hover:text-rose-600 px-2 py-1"><i class="fa-solid fa-trash-can mr-1"></i>删除</button>
                  </div>
                </div>
              </div>
              <button v-if="recordCount > 5" @click="router.push('/timeline'); showRecords = false"
                class="w-full text-xs text-violet-500 font-medium py-2 text-center">查看全部 {{ recordCount }} 条记录 →</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Merge Suggestions -->
    <TransitionGroup name="merge-fade" tag="div" class="space-y-2 mb-4">
      <div v-for="c in mergeCandidates" :key="c.new_task_id"
        class="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3">
        <p class="text-xs text-stone-600 leading-snug">
          <span class="font-semibold">「{{ c.new_title }}」</span>
          与 <span class="font-semibold">「{{ c.existing_title }}」</span> 是同一件事吗？
          <span class="text-stone-400">({{ (c.score * 100).toFixed(0) }}%)</span>
        </p>
        <div class="flex gap-2 mt-2">
          <button @click="handleResolveMerge(c, 'merge')"
            class="text-[11px] bg-amber-500 text-white rounded-full px-3 py-1 font-semibold">合并</button>
          <button @click="handleResolveMerge(c, 'keep_separate')"
            class="text-[11px] bg-white border border-stone-200 text-stone-500 rounded-full px-3 py-1">分开保留</button>
        </div>
      </div>
    </TransitionGroup>

    <!-- ===== SECTION 1: Tasks (top, prominent) ===== -->
    <section v-if="hasContent">
      <div class="flex items-center justify-between mb-2.5">
        <h2 class="text-sm font-bold text-stone-700">
          <i class="fa-solid fa-circle-check mr-1.5 text-violet-400"></i>我要做什么？
          <span class="text-xs text-stone-400 font-normal ml-1">{{ taskCount }} 项</span>
        </h2>
        <button @click="router.push('/tasks')" class="text-xs text-violet-500 font-medium">查看全部 →</button>
      </div>
      <div v-if="activeTasks.length === 0" class="text-center py-6 text-stone-300 text-xs">还没有想做的事</div>
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

    <!-- ===== SECTION 2: Timeline (mid) ===== -->
    <section v-if="hasContent">
      <div class="flex items-center justify-between mb-2.5">
        <h2 class="text-sm font-bold text-stone-700">
          <i class="fa-solid fa-calendar-days mr-1.5 text-violet-400"></i>我做了什么？
          <span class="text-xs text-stone-400 font-normal ml-1">{{ eventCount }} 个事件</span>
        </h2>
        <button @click="router.push('/timeline')" class="text-xs text-violet-500 font-medium">查看全部 →</button>
      </div>
      <div v-if="recentEvents.length === 0" class="text-center py-6 text-stone-300 text-xs">暂无事件</div>
      <div v-else class="space-y-1.5">
        <div v-for="evt in recentEvents.slice(0, 3)" :key="evt.id"
          @click="router.push('/timeline')"
          class="flex items-center gap-3 rounded-xl bg-stone-50 px-4 py-2.5 hover:bg-stone-100 transition-colors cursor-pointer">
          <div class="w-1.5 h-1.5 rounded-full bg-violet-200 shrink-0"></div>
          <span class="text-sm text-stone-600 truncate flex-1">{{ evt.title }}</span>
          <span v-if="evt.status === 'inferred'" class="text-[10px] text-amber-500 bg-amber-50 px-1.5 py-0.5 rounded-full">推测</span>
        </div>
      </div>
    </section>

    <!-- ===== Context (above input) ===== -->
    <section v-if="context && context.id !== 0">
      <div class="bg-gradient-to-r from-sky-50/80 to-violet-50/30 rounded-2xl border border-sky-100/50 px-4 py-3">
        <div class="flex items-center gap-2 mb-1">
          <i class="fa-solid fa-location-dot text-sky-400 text-sm"></i>
          <span class="text-xs font-semibold text-stone-500">我正在做什么？</span>
          <button @click="handleRefreshContext()" class="ml-auto text-[10px] text-violet-400 hover:text-violet-600">
            <i :class="['fa-solid mr-0.5', contextLoading ? 'fa-spinner animate-spin' : 'fa-arrows-rotate']"></i>刷新
          </button>
        </div>
        <p class="text-sm text-stone-600 leading-relaxed line-clamp-3">{{ context.summary }}</p>
      </div>
    </section>

    <!-- Input + Mood group (pushed to bottom) -->
    <div class="mt-auto space-y-3 lg:space-y-4">
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
        <RecordInput @submit="handleSubmit" @ask="handleAsk" :disabled="submitting" />
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

    <!-- Empty state -->
    <div v-if="!hasContent && !contextLoading" class="flex-1 flex flex-col items-center justify-center py-16 text-center">
      <i class="fa-solid fa-hand-wave text-3xl mb-3 block text-stone-200"></i>
      <p class="text-sm text-stone-400 font-medium">在下方输入框中记录你的日常</p>
      <p class="text-xs text-stone-300 mt-1">想到什么写什么，不用想太多</p>
    </div>

    <!-- Quick action: records button (floating) -->
    <button v-if="hasContent" @click="showRecords = true"
      class="fixed bottom-24 right-4 lg:bottom-8 lg:right-8 z-30 w-11 h-11 lg:w-12 lg:h-12 rounded-full bg-white shadow-lg border border-stone-200 flex items-center justify-center text-stone-400 hover:text-violet-500 active:scale-95 transition-all"
      aria-label="最近记录">
      <i class="fa-solid fa-clock-rotate-left text-lg"></i>
      <span v-if="recordCount > 0" class="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-violet-500 text-white text-[9px] font-bold flex items-center justify-center">{{ recordCount > 9 ? '9+' : recordCount }}</span>
    </button>

    <!-- Desktop: Records modal -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="showRecords" class="fixed inset-0 z-40 hidden lg:flex items-center justify-center" @click.self="showRecords = false">
          <div class="absolute inset-0 bg-black/20" />
          <div class="relative bg-white rounded-2xl shadow-2xl w-[480px] max-h-[70vh] overflow-y-auto mx-4">
            <div class="sticky top-0 bg-white border-b border-stone-100 px-6 py-4 flex items-center justify-between rounded-t-2xl">
              <h2 class="text-sm font-bold text-stone-700">最近记录</h2>
              <button @click="showRecords = false" class="text-stone-300 hover:text-stone-500"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div class="p-4 space-y-2">
              <div v-for="rec in recentRecords" :key="rec.id"
                class="rounded-xl bg-stone-50 px-4 py-3">
                <p class="text-sm text-stone-700 leading-snug">{{ rec.content }}</p>
                <div class="flex items-center justify-between mt-2">
                  <p class="text-xs text-stone-400">{{ formatRelative(rec.created_at) }}</p>
                  <div class="flex gap-1">
                    <button @click="handleReprocessRecord(rec.id)" class="text-xs text-violet-400 hover:text-violet-600 px-2 py-1"><i class="fa-solid fa-rotate-right mr-1"></i>重整理</button>
                    <button @click="handleDeleteRecord(rec.id)" class="text-xs text-rose-400 hover:text-rose-600 px-2 py-1"><i class="fa-solid fa-trash-can mr-1"></i>删除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
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

.drawer-enter-active { transition: all 0.2s ease; }
.drawer-leave-active { transition: all 0.15s ease; }
.drawer-enter-from { opacity: 0; }
.drawer-leave-to { opacity: 0; }

.expand-enter-active { transition: all 0.2s ease; }
.expand-leave-active { transition: all 0.15s ease; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; overflow: hidden; }

.qa-fade-enter-active { transition: all 0.22s ease; }
.qa-fade-leave-active { transition: all 0.15s ease; position: absolute; width: 100%; }
.qa-fade-enter-from { opacity: 0; transform: translateY(6px); }
.qa-fade-leave-to { opacity: 0; transform: translateY(-4px); }
.qa-fade-move { transition: transform 0.2s ease; }
</style>

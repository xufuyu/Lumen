<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import VoiceRecordButton from './VoiceRecordButton.vue'
import { polishAsrText } from '../api/client'

const { t } = useI18n()
const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{
  send: [content: string, type: string, voiceEmotion: string]
  toast: [type: 'error' | 'info', message: string]
}>()

const content = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const menuRoot = ref<HTMLElement | null>(null)
const voiceRef = ref<InstanceType<typeof VoiceRecordButton> | null>(null)
const showPrefixMenu = ref(false)

// Streaming ASR state — emotion 静默采集（不显示 UI，仅提交时带上）
const streamPrefix = ref('')
const detectedEmotion = ref('')
const isStreaming = ref(false)
const submitType = ref<'text' | 'voice'>('text')
const pendingSubmit = ref(false)  // 录音中用户点击发送 → 停录后自动提交

// 隐式润色：ASR 完成后异步请 LLM 修同音字，跟用户手动编辑抢时间
// 用递增 token 标识"最新一次录音"，防止旧请求覆盖新录音的内容
let polishToken = 0
let polishAbort: AbortController | null = null
const POLISH_TIMEOUT_MS = 3500  // 超时放弃

const prompts = [
  { label: t('input.prefixes.justDid'), prefix: t('input.prefixesFull.justDid'), icon: 'fa-check', color: 'text-emerald-500' },
  { label: t('input.prefixes.needToDo'), prefix: t('input.prefixesFull.needToDo'), icon: 'fa-flag', color: 'text-amber-500' },
  { label: t('input.prefixes.thinking'), prefix: t('input.prefixesFull.thinking'), icon: 'fa-lightbulb', color: 'text-violet-500' },
  { label: t('input.prefixes.feeling'), prefix: t('input.prefixesFull.feeling'), icon: 'fa-heart', color: 'text-rose-500' },
  { label: t('input.prefixes.ask'), prefix: t('input.prefixesFull.ask'), icon: 'fa-comment-dots', color: 'text-sky-500' },
]

function focusWithPrefix(prefix: string) {
  content.value = prefix
  submitType.value = 'text'
  showPrefixMenu.value = false
  nextTick(() => {
    textarea.value?.focus()
    textarea.value?.setSelectionRange(prefix.length, prefix.length)
  })
}

function onStarted() {
  streamPrefix.value = content.value
  isStreaming.value = true
  submitType.value = 'voice'

  // 取消上一次未完成的润色请求
  if (polishAbort) {
    try { polishAbort.abort() } catch { /* */ }
  }
  polishAbort = null
  polishToken++
}

function onDelta(text: string, stash: string, emotion: string) {
  // onStarted 已经把 isStreaming 置 true 并抓取了 streamPrefix，这里直接更新即可
  submitType.value = 'voice'
  if (emotion) detectedEmotion.value = emotion

  // text = 已确认累计（含前文纠错，整体替换）
  // stash = 可纠错尾部（会被下次 delta 改写）
  // 用户要求直接拼进 textarea，让实时输入所见即所得
  const combined = text + stash
  content.value = streamPrefix.value
    ? (combined ? streamPrefix.value + ' ' + combined : streamPrefix.value)
    : combined
}

function onCompleted(text: string, emotion: string) {
  // done 到达 —— 单次 utterance 结束（VAD 自动 or 用户 stop）
  if (text) {
    submitType.value = 'voice'
    content.value = streamPrefix.value ? streamPrefix.value + ' ' + text : text
  }
  if (emotion) detectedEmotion.value = emotion
  isStreaming.value = false
  streamPrefix.value = ''

  // 用户录音中点击了发送按钮 → 停录后自动提交
  if (pendingSubmit.value) {
    pendingSubmit.value = false
    nextTick(() => handleEnter())
    return
  }

  nextTick(() => textarea.value?.focus())

  // 隐式润色 pass：短文本无必要（噪音大、修正也不明显）
  if (text && text.trim().length >= 4) {
    polishAsrOnce(text, content.value)
  }
}

async function polishAsrOnce(originalText: string, baseline: string) {
  // 取消上一个还在飞的润色
  if (polishAbort) {
    try { polishAbort.abort() } catch { /* */ }
    polishAbort = null
  }
  const myToken = ++polishToken
  const controller = new AbortController()
  polishAbort = controller
  const timeoutId = setTimeout(() => {
    try { controller.abort() } catch { /* */ }
  }, POLISH_TIMEOUT_MS)

  try {
    const res = await polishAsrText(originalText, controller.signal)

    // 三道闸：过期 / 无变化 / 用户已改
    if (myToken !== polishToken) return
    if (!res.changed) return
    if (content.value !== baseline) return

    // 尾部替换
    const tailStart = baseline.length - originalText.length
    if (tailStart >= 0 && baseline.slice(tailStart) === originalText) {
      content.value = baseline.slice(0, tailStart) + res.polished
    }
  } catch (e: unknown) {
    // AbortError（超时/新录音）和网络错误都静默降级
    if (e instanceof Error && e.name === 'AbortError') return
    // 其他错误也不影响用户，继续使用 ASR 原文
  } finally {
    clearTimeout(timeoutId)
    if (polishAbort === controller) polishAbort = null
  }
}

function onManualInput() {
  if (!isStreaming.value) {
    submitType.value = 'text'
    // 手动编辑后清掉声学情绪，避免把上一次语音的情绪错误关联到新文字
    if (detectedEmotion.value) detectedEmotion.value = ''
  }
}

async function handleSend() {
  const text = content.value.trim()
  if (!text || props.disabled) return
  emit('send', text, submitType.value, detectedEmotion.value)
  content.value = ''
  detectedEmotion.value = ''
  submitType.value = 'text'
  await nextTick()
  textarea.value?.focus()
}

async function handleEnter() {
  // 录音中：自动停止录音，onCompleted 会重新调用本函数
  if (isStreaming.value) {
    pendingSubmit.value = true
    voiceRef.value?.stopRecording()
    return
  }
  await handleSend()
}

function onDocClick(e: MouseEvent) {
  if (menuRoot.value && !menuRoot.value.contains(e.target as Node)) {
    showPrefixMenu.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocClick, true))
onUnmounted(() => document.removeEventListener('click', onDocClick, true))
</script>

<template>
  <div class="flex flex-col">
    <div class="px-1 pb-1">
      <textarea
        ref="textarea"
        v-model="content"
        @input="onManualInput"
        @keydown.enter.exact.prevent="handleEnter"
        :placeholder="isStreaming ? t('input.recording') : t('input.placeholderDefault')"
        rows="3"
        :disabled="disabled"
        class="w-full resize-none text-base sm:text-lg text-stone-800 placeholder:text-stone-300 bg-transparent border-none focus:outline-none leading-relaxed disabled:opacity-50"
      ></textarea>
    </div>

    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-1.5 min-w-0">
        <VoiceRecordButton ref="voiceRef" @started="onStarted" @delta="onDelta" @completed="onCompleted" @error="msg => emit('toast', 'error', msg)" />

        <!-- Prefix menu (collapsed) -->
        <div ref="menuRoot" class="relative">
          <button type="button" @click.stop="showPrefixMenu = !showPrefixMenu" :disabled="disabled"
            :class="['shrink-0 flex items-center gap-1 text-[11px] sm:text-xs rounded-full px-2.5 sm:px-3 py-1.5 transition-colors whitespace-nowrap disabled:opacity-50 font-medium',
              showPrefixMenu ? 'bg-violet-100 text-violet-600' : 'text-violet-500 bg-violet-50 active:bg-violet-100']">
            <i :class="['fa-solid', showPrefixMenu ? 'fa-xmark' : 'fa-plus', 'text-[10px]']"></i>
            <span>{{ t('input.quick') }}</span>
          </button>

          <Transition name="prefix-pop">
            <div v-if="showPrefixMenu"
              class="absolute bottom-full left-0 mb-2 z-20 bg-white rounded-2xl shadow-lg border border-stone-100 py-1.5 min-w-[132px]">
              <button v-for="p in prompts" :key="p.label"
                @click="focusWithPrefix(p.prefix)"
                class="w-full flex items-center gap-2.5 px-3.5 py-2 hover:bg-stone-50 active:bg-stone-100 transition-colors text-left">
                <i :class="['fa-solid text-xs w-3.5 text-center', p.icon, p.color]"></i>
                <span class="text-xs text-stone-600 font-medium">{{ p.label }}</span>
              </button>
            </div>
          </Transition>
        </div>
      </div>

      <button
        @click="handleEnter"
        :disabled="(!content.trim() && !isStreaming) || disabled"
        :class="['shrink-0 rounded-2xl px-5 sm:px-6 py-2.5 text-sm font-semibold transition-all active:scale-95 shadow-sm disabled:bg-stone-200 disabled:text-stone-400 disabled:shadow-none text-white',
          isStreaming ? 'bg-rose-500 active:bg-rose-600 shadow-rose-200' : 'bg-violet-500 active:bg-violet-600 shadow-violet-200']"
        :title="t('input.send')"
      >
        <i :class="['fa-solid mr-1 text-xs', isStreaming ? 'fa-stop' : 'fa-paper-plane']"></i>
        {{ disabled ? '…' : isStreaming ? t('input.stopAndSend') : t('input.send') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.scrollbar-hide::-webkit-scrollbar { display: none; }
.scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }

.prefix-pop-enter-active { transition: all 0.15s ease; transform-origin: bottom left; }
.prefix-pop-leave-active { transition: all 0.1s ease; transform-origin: bottom left; }
.prefix-pop-enter-from, .prefix-pop-leave-to { opacity: 0; transform: scale(0.92) translateY(4px); }
</style>

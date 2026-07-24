<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import VoiceRecordButton from './VoiceRecordButton.vue'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{
  submit: [content: string, type: string, voiceEmotion: string]
  ask: [question: string, voiceEmotion: string]
}>()

const content = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const menuRoot = ref<HTMLElement | null>(null)
const showPrefixMenu = ref(false)

// Streaming ASR state
const streamPrefix = ref('')
const stashPreview = ref('')     // 可纠错尾部预览（灰色）
const detectedEmotion = ref('')  // 声学情绪（7 类之一或空）
const isStreaming = ref(false)
const submitType = ref<'text' | 'voice'>('text')

const prompts = [
  { label: '刚做完', prefix: '我刚做完：', icon: 'fa-check', color: 'text-emerald-500' },
  { label: '要做的', prefix: '我需要做：', icon: 'fa-flag', color: 'text-amber-500' },
  { label: '在想', prefix: '我在想：', icon: 'fa-lightbulb', color: 'text-violet-500' },
  { label: '感受', prefix: '我的感受：', icon: 'fa-heart', color: 'text-rose-500' },
  { label: '问一下', prefix: '问一下：', icon: 'fa-comment-dots', color: 'text-sky-500' },
]

// 情绪 → 中文标签 + 颜色（浅色 chip）
const EMOTION_META: Record<string, { label: string; cls: string; icon: string }> = {
  neutral:   { label: '平和',   cls: 'bg-stone-100 text-stone-500',   icon: 'fa-face-meh' },
  happy:     { label: '愉悦',   cls: 'bg-amber-50 text-amber-600',    icon: 'fa-face-smile' },
  sad:       { label: '低落',   cls: 'bg-sky-50 text-sky-600',        icon: 'fa-face-frown' },
  angry:     { label: '烦躁',   cls: 'bg-rose-50 text-rose-600',      icon: 'fa-face-angry' },
  fearful:   { label: '焦虑',   cls: 'bg-indigo-50 text-indigo-600',  icon: 'fa-face-flushed' },
  disgusted: { label: '厌烦',   cls: 'bg-lime-50 text-lime-700',      icon: 'fa-face-tired' },
  surprised: { label: '惊讶',   cls: 'bg-fuchsia-50 text-fuchsia-600', icon: 'fa-face-surprise' },
}
const emotionMeta = computed(() => detectedEmotion.value ? EMOTION_META[detectedEmotion.value] : null)

// 问答意图检测：不依赖标点。
const askKeywordAtStart = /^(问一下|查一下|问下|查下|我想知道|想知道|请问|帮我查|帮我看看|看看|告诉我|是不是|能不能|可不可以|要不要|有没有|该不该|要怎么|怎么|如何|为什么|为啥|哪里|哪个|哪些|什么时候|什么|谁|是否|多少|几个|几天|多久)/
const looksLikeQuestion = computed(() => {
  const t = content.value.trim()
  if (!t) return false
  if (/[?？]$/.test(t)) return true
  return askKeywordAtStart.test(t)
})

function focusWithPrefix(prefix: string) {
  content.value = prefix
  submitType.value = 'text'
  showPrefixMenu.value = false
  nextTick(() => {
    textarea.value?.focus()
    textarea.value?.setSelectionRange(prefix.length, prefix.length)
  })
}

function onDelta(text: string, stash: string, emotion: string) {
  if (!isStreaming.value) {
    streamPrefix.value = content.value
    isStreaming.value = true
  }
  submitType.value = 'voice'
  if (emotion) detectedEmotion.value = emotion

  // text = 已确认累计（整体替换），stash = 可纠错尾部（不落 textarea，另处预览）
  const confirmed = streamPrefix.value
    ? (text ? streamPrefix.value + ' ' + text : streamPrefix.value)
    : text
  content.value = confirmed
  stashPreview.value = stash
}

function onCompleted(text: string, emotion: string) {
  if (text) {
    submitType.value = 'voice'
    content.value = streamPrefix.value ? streamPrefix.value + ' ' + text : text
  }
  if (emotion) detectedEmotion.value = emotion
  stashPreview.value = ''
  isStreaming.value = false
  streamPrefix.value = ''
  nextTick(() => textarea.value?.focus())
}

function onManualInput() {
  if (!isStreaming.value) {
    submitType.value = 'text'
    // 手动输入时清掉情绪徽标（不是语音的了）
    if (detectedEmotion.value) detectedEmotion.value = ''
  }
}

function clearEmotion() {
  detectedEmotion.value = ''
}

async function handleSubmit() {
  const text = content.value.trim()
  if (!text || props.disabled) return
  emit('submit', text, submitType.value, detectedEmotion.value)
  content.value = ''
  detectedEmotion.value = ''
  stashPreview.value = ''
  submitType.value = 'text'
  await nextTick()
  textarea.value?.focus()
}

async function handleAsk() {
  const text = content.value.trim()
  if (!text || props.disabled) return
  emit('ask', text, detectedEmotion.value)
  content.value = ''
  detectedEmotion.value = ''
  stashPreview.value = ''
  submitType.value = 'text'
  await nextTick()
  textarea.value?.focus()
}

async function handleEnter() {
  if (looksLikeQuestion.value) await handleAsk()
  else await handleSubmit()
}

// 点击菜单外部关闭
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
        :placeholder="looksLikeQuestion ? '看起来是个问题… 按回车我来回答' : '随便记点什么… 想到什么写什么'"
        rows="3"
        :disabled="disabled"
        class="w-full resize-none text-base sm:text-lg text-stone-800 placeholder:text-stone-300 bg-transparent border-none focus:outline-none leading-relaxed disabled:opacity-50"
      ></textarea>

      <!-- stash 可纠错尾部预览 - 灰色斜体，实时更新 -->
      <Transition name="stash-fade">
        <div v-if="stashPreview" class="text-sm text-stone-400 italic leading-snug -mt-1">
          <i class="fa-solid fa-wave-square text-[10px] text-violet-400 mr-1"></i>{{ stashPreview }}
        </div>
      </Transition>
    </div>

    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-1.5 min-w-0 flex-wrap">
        <VoiceRecordButton @delta="onDelta" @completed="onCompleted" />

        <!-- 声学情绪徽标 - 点击可清除 -->
        <Transition name="emotion-pop">
          <button v-if="emotionMeta" type="button" @click="clearEmotion"
            :class="['shrink-0 flex items-center gap-1 text-[11px] rounded-full px-2 py-0.5 transition-all active:scale-95', emotionMeta.cls]"
            :title="`声学情绪：${emotionMeta.label}（会随记录一起发送，点击清除）`">
            <i :class="['fa-solid text-[10px]', emotionMeta.icon]"></i>
            <span class="font-medium">{{ emotionMeta.label }}</span>
            <i class="fa-solid fa-xmark text-[9px] opacity-40 ml-0.5"></i>
          </button>
        </Transition>

        <!-- Prefix menu (collapsed) -->
        <div ref="menuRoot" class="relative">
          <button type="button" @click.stop="showPrefixMenu = !showPrefixMenu" :disabled="disabled"
            :class="['shrink-0 flex items-center gap-1 text-[11px] sm:text-xs rounded-full px-2.5 sm:px-3 py-1.5 transition-colors whitespace-nowrap disabled:opacity-50 font-medium',
              showPrefixMenu ? 'bg-violet-100 text-violet-600' : 'text-violet-500 bg-violet-50 active:bg-violet-100']">
            <i :class="['fa-solid', showPrefixMenu ? 'fa-xmark' : 'fa-plus', 'text-[10px]']"></i>
            <span>快捷</span>
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
        :disabled="!content.trim() || disabled"
        :class="['shrink-0 rounded-2xl px-5 sm:px-6 py-2.5 text-sm font-semibold transition-all active:scale-95 shadow-sm disabled:bg-stone-200 disabled:text-stone-400 disabled:shadow-none text-white',
          looksLikeQuestion
            ? 'bg-sky-500 active:bg-sky-600 shadow-sky-200'
            : 'bg-violet-500 active:bg-violet-600 shadow-violet-200']"
        :title="looksLikeQuestion ? '按下发送问题（回车键）' : '按下保存记录（回车键）'"
      >
        <i :class="['fa-solid mr-1 text-xs', looksLikeQuestion ? 'fa-comment-dots' : 'fa-check']"></i>
        {{ disabled ? '…' : looksLikeQuestion ? '问一下' : '记录' }}
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

.stash-fade-enter-active, .stash-fade-leave-active { transition: opacity 0.15s ease; }
.stash-fade-enter-from, .stash-fade-leave-to { opacity: 0; }

.emotion-pop-enter-active { transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1); }
.emotion-pop-leave-active { transition: all 0.15s ease; }
.emotion-pop-enter-from, .emotion-pop-leave-to { opacity: 0; transform: scale(0.7); }
</style>

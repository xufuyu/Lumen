<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { askQuestion, type QueryResponse } from '../api/client'

interface Message { role: 'user' | 'assistant'; content: string; response?: QueryResponse }

const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const chatContainer = ref<HTMLElement | null>(null)

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  await scrollToBottom()
  try {
    const res = await askQuestion(text)
    messages.value.push({ role: 'assistant', content: res.answer, response: res })
  } catch {
    messages.value.push({ role: 'assistant', content: '抱歉，处理你的问题时出现了错误。请稍后再试。' })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
}
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-12rem)] lg:h-[calc(100vh-10rem)]">
    <div ref="chatContainer" class="flex-1 overflow-y-auto space-y-4 mb-4 flex flex-col">
      <div v-if="messages.length === 0" class="text-center text-stone-400 py-16">
        <i class="fa-solid fa-comment-dots text-3xl mb-4 block"></i>
        <p class="text-base text-stone-500 font-medium">问我任何关于你近期活动的问题</p>
        <p class="text-sm text-stone-300 mt-1">例如："我这周做了什么？""有什么待办事项？"</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i"
        :class="['max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
          msg.role === 'user' ? 'bg-violet-500 text-white self-end ml-auto' : 'bg-stone-100 text-stone-700']">
        <p>{{ msg.content }}</p>
        <div v-if="msg.response?.sources.length" class="mt-2 pt-2 border-t border-white/20">
          <p class="text-xs opacity-70 mb-1">来源：</p>
          <div v-for="src in msg.response.sources" :key="src.record_id" class="text-xs opacity-60 truncate">{{ src.excerpt }}</div>
        </div>
        <div v-if="msg.response?.disclaimer" class="mt-2 pt-2 border-t border-white/20">
          <p class="text-xs opacity-70 italic"><i class="fa-solid fa-triangle-exclamation mr-1"></i>{{ msg.response.disclaimer }}</p>
        </div>
      </div>

      <div v-if="loading" class="flex items-center gap-2 text-stone-400 text-sm px-1">
        <span class="w-2 h-2 rounded-full bg-violet-400 animate-pulse"></span>正在思考...
      </div>
    </div>

    <div class="flex gap-2">
      <input v-model="input" @keydown.enter="send" type="text" placeholder="问一个问题…" :disabled="loading"
        class="flex-1 rounded-2xl border border-stone-200 bg-stone-50 px-5 py-3 text-sm placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-transparent disabled:opacity-50" />
      <button @click="send" :disabled="!input.trim() || loading"
        class="bg-violet-500 hover:bg-violet-600 disabled:bg-stone-200 disabled:text-stone-400 text-white rounded-2xl px-5 py-3 text-sm font-semibold transition-all active:scale-95">发送</button>
    </div>
  </div>
</template>
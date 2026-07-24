<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const emit = defineEmits<{
  // 新一轮录音真正开始（麦克风+WS 均就绪）—— RecordInput 用它复位 streaming 状态
  started: []
  // text: 已确认累计文本（整体替换）；stash: 尾部可纠错预览；emotion: 声学情绪（可空）
  delta: [text: string, stash: string, emotion: string]
  // 最终文本 + 最终情绪 —— 收到即视为本次录音结束（VAD 自动 or 用户 stop 均触发）
  completed: [text: string, emotion: string]
}>()

const state = ref<'idle' | 'connecting' | 'recording'>('idle')
const error = ref('')

let audioCtx: AudioContext | null = null
let stream: MediaStream | null = null
let processor: ScriptProcessorNode | null = null
let sourceNode: MediaStreamAudioSourceNode | null = null
let gainNode: GainNode | null = null
let ws: WebSocket | null = null

// ── Float32 采样 → Int16 小端字节 ──

function float32ToInt16Bytes(samples: Float32Array): ArrayBuffer {
  const int16 = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i++) {
    int16[i] = Math.max(-32768, Math.min(32767, (samples[i] * 32767) | 0))
  }
  return int16.buffer
}

// ── 简易线性插值重采样（任意采样率 → 16000 Hz） ──

function resampleTo16k(samples: Float32Array, fromRate: number): Float32Array {
  if (fromRate === 16000) return samples
  const ratio = fromRate / 16000
  const outLen = Math.round(samples.length / ratio)
  const out = new Float32Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const srcIdx = i * ratio
    const srcFloor = Math.floor(srcIdx)
    const srcCeil = Math.min(srcFloor + 1, samples.length - 1)
    const frac = srcIdx - srcFloor
    out[i] = samples[srcFloor] * (1 - frac) + samples[srcCeil] * frac
  }
  return out
}

// ── WebSocket 消息处理 ──

function handleWsMessage(e: MessageEvent) {
  try {
    const msg = JSON.parse(e.data)
    switch (msg.type) {
      case 'interim':
        // Qwen3-ASR 流式：text=已确认累计（整体替换），stash=可纠错尾部预览
        emit('delta', msg.text || '', msg.stash || '', msg.emotion || '')
        break

      case 'done':
        // 单次 utterance 结束：VAD 自动或用户 stop 都会触发
        // 无论是哪种，都要停麦、关 ws、置 idle，避免"以为还在录"
        emit('completed', msg.text || '', msg.emotion || '')
        cleanupAudio()
        closeWs()
        state.value = 'idle'
        break

      case 'error':
        error.value = (msg.message && !msg.message.includes('commit') && !msg.message.includes('buffer'))
          ? msg.message
          : t('input.micError')
        // 出错也算一次结束 —— 通知父组件复位状态，别把下一次录音的文本覆盖当前输入
        emit('completed', '', '')
        cleanupAudio()
        closeWs()
        state.value = 'idle'
        break
    }
  } catch { /* 非 JSON 消息忽略 */ }
}

function handleWsClose() {
  // 未预期的关闭（比如后端断线）— 通知父组件复位，别让下次录音顶掉当前文字
  if (state.value === 'recording' || state.value === 'connecting') {
    emit('completed', '', '')
    cleanupAudio()
    state.value = 'idle'
  }
}

function handleWsError() {
  error.value = t('input.micError')
  emit('completed', '', '')
  cleanupAudio()
  closeWs()
  state.value = 'idle'
}

function closeWs() {
  if (ws) {
    ws.onmessage = null
    ws.onclose = null
    ws.onerror = null
    try { ws.close() } catch { /* */ }
    ws = null
  }
}

// ── 开始录音 ──

async function start() {
  error.value = ''
  state.value = 'connecting'

  // 清理上一次可能残留的连接（stop 后 WebSocket 可能在等 done 响应）
  closeWs()

  try {
    // 1. 获取麦克风
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: { ideal: 16000 },
        channelCount: { ideal: 1 },
        echoCancellation: true,
        noiseSuppression: true,
      },
    })
    // 使用默认采样率创建 AudioContext（避免某些系统不支持 16kHz 而抛出 NotSupportedError）
    audioCtx = new AudioContext()
    const actualRate = audioCtx.sampleRate

    // 2. 建立 WebSocket 连接
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${location.host}/api/asr/ws`
    ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'

    let wsTimeout: ReturnType<typeof setTimeout> | null = null
    await new Promise<void>((resolve, reject) => {
      if (!ws) return reject(new Error('ws null'))
      ws.onopen = () => {
        if (wsTimeout) { clearTimeout(wsTimeout); wsTimeout = null }
        resolve()
      }
      ws.onerror = () => {
        if (wsTimeout) { clearTimeout(wsTimeout); wsTimeout = null }
        reject(new Error('WebSocket 连接失败'))
      }
      // 超时 5s
      wsTimeout = setTimeout(() => {
        wsTimeout = null
        reject(new Error('WebSocket 连接超时'))
      }, 5000)
    })

    ws.onmessage = handleWsMessage
    ws.onclose = handleWsClose
    ws.onerror = handleWsError

    // 3. 启动音频采集 → 二进制帧发送
    // buffer=1024 samples ≈ 21ms@48kHz — 更小的 buffer 降低采集延迟，实时输入更跟手
    sourceNode = audioCtx.createMediaStreamSource(stream)
    processor = audioCtx.createScriptProcessor(1024, 1, 1)

    processor.onaudioprocess = (e) => {
      const samples = new Float32Array(e.inputBuffer.getChannelData(0))
      const resampled = resampleTo16k(samples, actualRate)
      const bytes = float32ToInt16Bytes(resampled)
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(bytes)
      }
    }

    // 通过零增益节点连接到 destination，确保 onaudioprocess 触发但不播放声音
    gainNode = audioCtx.createGain()
    gainNode.gain.value = 0
    sourceNode.connect(processor)
    processor.connect(gainNode)
    gainNode.connect(audioCtx.destination)
    state.value = 'recording'
    // 通知父组件"新一轮录音就绪"—— 让它复位 streaming 状态、重新捕获 streamPrefix
    emit('started')

  } catch (e: unknown) {
    cleanup()
    if (e instanceof DOMException && e.name === 'NotAllowedError') {
      error.value = t('input.micError')
    } else {
      error.value = e instanceof Error ? e.message : t('input.micError')
    }
    state.value = 'idle'
  }
}

// ── 停止录音 → 发送 stop → 等待二遍完成 ──

function stop() {
  // 立即停麦
  cleanupAudio()
  const wasRecording = state.value === 'recording'
  state.value = 'idle'

  if (!ws || ws.readyState !== WebSocket.OPEN) return

  // 只有确实在录音中才发 stop（避免空 buffer commit 报错）
  if (wasRecording) {
    ws.send(JSON.stringify({ type: 'stop' }))
  } else {
    closeWs()
  }
}

function toggle() {
  if (state.value === 'recording') stop()
  else if (state.value === 'idle') start()
}

function cleanupAudio() {
  if (processor) { try { processor.disconnect() } catch { /* */ } processor = null }
  if (gainNode) { try { gainNode.disconnect() } catch { /* */ } gainNode = null }
  if (sourceNode) { try { sourceNode.disconnect() } catch { /* */ } sourceNode = null }
  if (audioCtx) { try { audioCtx.close() } catch { /* */ } audioCtx = null }
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null }
}

function cleanup() {
  cleanupAudio()
  closeWs()
}

function stopRecording() {
  if (state.value === 'recording') stop()
}

defineExpose({ stopRecording, isRecording: computed(() => state.value === 'recording') })

onUnmounted(cleanup)
</script>

<template>
  <div class="inline-flex items-center gap-1.5">
    <button type="button" @click="toggle" :disabled="state === 'connecting'"
      :class="['shrink-0 w-9 h-9 flex items-center justify-center rounded-full transition-all',
        state === 'recording' ? 'bg-rose-500 text-white animate-pulse' :
        state === 'connecting' ? 'bg-amber-100 text-amber-500' :
        'bg-stone-100 text-stone-400 active:bg-violet-100 active:text-violet-500']"
      :title="state === 'recording' ? t('input.stop') : state === 'connecting' ? t('input.connecting') : t('input.record')">
      <i :class="['fa-solid', state === 'recording' ? 'fa-stop' : state === 'connecting' ? 'fa-spinner animate-spin' : 'fa-microphone']"></i>
    </button>
    <span v-if="state === 'recording'" class="text-xs text-rose-400 font-medium shrink-0">{{ t('input.recording') }}</span>
    <span v-else-if="state === 'connecting'" class="text-xs text-amber-500 shrink-0">{{ t('input.connecting') }}</span>
    <span v-if="error" class="text-xs text-rose-500 shrink-0 truncate max-w-[120px]">{{ error }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'

const emit = defineEmits<{
  // text: 已确认累计文本（整体替换）；stash: 尾部可纠错预览；emotion: 声学情绪（可空）
  delta: [text: string, stash: string, emotion: string]
  // 最终文本 + 最终情绪
  completed: [text: string, emotion: string]
  // VAD 反馈（前端可选做视觉指示）
  vad: [phase: 'started' | 'stopped']
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
        // 最终结果 + 情绪
        emit('completed', msg.text || '', msg.emotion || '')
        closeWs()
        state.value = 'idle'
        break

      case 'vad_speech_started':
        emit('vad', 'started')
        break

      case 'vad_speech_stopped':
        emit('vad', 'stopped')
        break

      case 'error':
        error.value = msg.message || '语音识别错误'
        break
    }
  } catch { /* 非 JSON 消息忽略 */ }
}

function handleWsClose() {
  // 只在录音中意外断开时才切 idle，正常 stop 已由 stop() 切了
  if (state.value === 'recording') {
    state.value = 'idle'
  }
}

function handleWsError() {
  error.value = '语音服务连接失败'
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
    // buffer=2048 samples ≈ 46ms@44.1kHz / 43ms@48kHz — 平衡实时性与消息频率
    sourceNode = audioCtx.createMediaStreamSource(stream)
    processor = audioCtx.createScriptProcessor(2048, 1, 1)

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

  } catch (e: unknown) {
    cleanup()
    if (e instanceof DOMException && e.name === 'NotAllowedError') {
      error.value = '麦克风权限被拒绝'
    } else {
      error.value = e instanceof Error ? e.message : '无法启动录音'
    }
    state.value = 'idle'
  }
}

// ── 停止录音 → 发送 stop → 等待二遍完成 ──

function stop() {
  cleanupAudio()

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    state.value = 'idle'
    return
  }

  // 先更新 UI，让用户知道点击已生效
  state.value = 'idle'
  // 发送 stop 信号，触发服务端二遍识别
  ws.send(JSON.stringify({ type: 'stop' }))
  // 不立即关闭 ws — 等待 done 消息后由 handleWsMessage 关闭
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

onUnmounted(cleanup)
</script>

<template>
  <div class="inline-flex items-center gap-1.5">
    <button type="button" @click="toggle" :disabled="state === 'connecting'"
      :class="['shrink-0 w-9 h-9 flex items-center justify-center rounded-full transition-all',
        state === 'recording' ? 'bg-rose-500 text-white animate-pulse' :
        state === 'connecting' ? 'bg-amber-100 text-amber-500' :
        'bg-stone-100 text-stone-400 active:bg-violet-100 active:text-violet-500']"
      :title="state === 'recording' ? '点击停止' : state === 'connecting' ? '连接中...' : '语音输入'">
      <i :class="['fa-solid', state === 'recording' ? 'fa-stop' : state === 'connecting' ? 'fa-spinner animate-spin' : 'fa-microphone']"></i>
    </button>
    <span v-if="state === 'recording'" class="text-xs text-rose-400 font-medium shrink-0">说话中...</span>
    <span v-else-if="state === 'connecting'" class="text-xs text-amber-500 shrink-0">连接中...</span>
    <span v-if="error" class="text-xs text-rose-500 shrink-0 truncate max-w-[120px]">{{ error }}</span>
  </div>
</template>

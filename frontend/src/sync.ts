/** Real-time sync: WebSocket + polling fallback for same-ID multi-device sync. */

import { ref } from 'vue'
import { getUserId } from './user'

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

export const syncConnected = ref(false)

// Polling fallback: check /api/health every 10s; any mutation on same ID
// will be picked up next time the page reloads
let lastRefreshVersion = 0

function triggerRefresh() {
  window.dispatchEvent(new CustomEvent('lumen:refresh'))
}

export function connectSync() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  const uid = getUserId()
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/api/ws/sync?user_id=${encodeURIComponent(uid)}`

  try {
    ws = new WebSocket(url)
  } catch {
    startPolling()
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    syncConnected.value = true
    stopPolling()
    const ping = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
    }, 60000)
    ws!.addEventListener('close', () => clearInterval(ping), { once: true })
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'refresh') {
        lastRefreshVersion = Date.now()
        triggerRefresh()
      }
    } catch { /* */ }
  }

  ws.onclose = () => {
    syncConnected.value = false
    ws = null
    startPolling()
    scheduleReconnect()
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectSync()
  }, 5000)
}

// Polling fallback: every 10s, trigger a refresh (lightweight)
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(triggerRefresh, 10_000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

export function disconnectSync() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  stopPolling()
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  syncConnected.value = false
}

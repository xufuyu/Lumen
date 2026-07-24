/** Real-time sync: listen for data changes from same user_id on other devices. */

import { ref } from 'vue'
import { getUserId } from './user'

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

export const syncConnected = ref(false)

export function connectSync() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  const uid = getUserId()
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/api/ws/sync?user_id=${encodeURIComponent(uid)}`

  try {
    ws = new WebSocket(url)
  } catch {
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    syncConnected.value = true
    // Send ping every 60s to keep connection alive
    const ping = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
    }, 60000)
    ws!.addEventListener('close', () => clearInterval(ping), { once: true })
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'refresh') {
        // Another device changed data → reload
        window.dispatchEvent(new CustomEvent('lumen:refresh'))
      }
    } catch { /* ignore malformed messages */ }
  }

  ws.onclose = () => {
    syncConnected.value = false
    ws = null
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

export function disconnectSync() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  if (ws) {
    ws.onclose = null // prevent reconnect
    ws.close()
    ws = null
  }
  syncConnected.value = false
}

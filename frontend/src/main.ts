import { createApp } from 'vue'
import './assets/fa-all.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { i18n } from './i18n'
import './install' // register beforeinstallprompt listener early

createApp(App).use(router).use(i18n).mount('#app')

// ── Service Worker: PWA 离线缓存 + 自动更新 ───────────────────────────────────
// 网站更新后 SW 检测到新 sw.js → skipWaiting 激活 → controllerchange → 自动刷新
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {})

  // 新 SW 接管时刷新一次（refreshing 防止循环）
  let refreshing = false
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return
    refreshing = true
    window.location.reload()
  })
}

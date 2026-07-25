/**
 * PWA install prompt + in-app-browser detection.
 *
 * Runs as a side-effect module: import once in main.ts to register the
 * beforeinstallprompt listener early (the event fires once on page load).
 *
 * Design philosophy: gentle, one-shot, respectful — no shouting, no red
 * badges, no urgency. Dismissal is remembered for a cooling-off period so we
 * never nag. See InstallHint.vue for the UI.
 */

import { ref, computed } from 'vue'

// Result of environment detection — decides which (if any) hint to show.
export type HintMode =
  | 'none'            // installed / dismissed / unsupported / unknown
  | 'inapp'           // WeChat / QQ / Douyin / etc. — suggest opening in browser
  | 'ios-safari'      // iOS Safari — manual "Share → Add to Home Screen"
  | 'android-install' // Chromium with a captured beforeinstallprompt event

const DISMISS_KEY = 'lumen:install-hint-dismissed'
const COOLDOWN_DAYS = 7

// Captured beforeinstallprompt event; null on iOS/in-app/desktop-Safari.
const deferredPrompt = ref<any>(null)

// True once the app is running as an installed PWA — hint stays hidden.
const isStandalone = ref(false)

// Reactive mirror of the localStorage dismiss timestamp — needed so the
// computed hintMode recomputes when the user closes the hint. Initialized
// from storage below.
const dismissedAt = ref<number>(0)

if (typeof window !== 'undefined') {
  // Read prior dismissal so the hint stays hidden across reloads within the
  // cool-off window.
  try {
    const raw = localStorage.getItem(DISMISS_KEY)
    if (raw) {
      const ts = Number(raw)
      if (Number.isFinite(ts)) dismissedAt.value = ts
    }
  } catch {}

  // 不拦截 beforeinstallprompt —— 让浏览器显示原生安装提示。
  // iOS Safari 和内嵌浏览器没有此事件，仍由 InstallHint.vue 提供文字引导。
  window.addEventListener('beforeinstallprompt', () => {
    deferredPrompt.value = null
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt.value = null
    // Once installed, the user clearly doesn't need the nudge again.
    const now = Date.now()
    try { localStorage.setItem(DISMISS_KEY, String(now)) } catch {}
    dismissedAt.value = now
  })

  const mm = window.matchMedia?.('(display-mode: standalone)')
  isStandalone.value = !!mm?.matches || (window.navigator as any).standalone === true
  mm?.addEventListener?.('change', (e) => { isStandalone.value = e.matches })
}

function isDismissedRecently(): boolean {
  if (!dismissedAt.value) return false
  return Date.now() - dismissedAt.value < COOLDOWN_DAYS * 24 * 60 * 60 * 1000
}

// UA sniffing is unreliable in general, but for these in-app WebViews it is
// the only signal available — the vendors explicitly stamp their name.
function isInAppBrowser(): boolean {
  const ua = navigator.userAgent
  return /MicroMessenger|QQ\/|QQBrowser|Weibo|WeiBo|aweme|douyin|XiaoHongShu|xhsdiscover|AlipayClient|DingTalk|Lark|LarkLocale|baiduboxapp|Kwai|FBAN|FBAV|Instagram|LinkedInApp/i.test(ua)
}

function isIOS(): boolean {
  const ua = navigator.userAgent
  return /iPhone|iPad|iPod/i.test(ua) ||
    // iPadOS 13+ reports as Mac; distinguish by touch support.
    (ua.includes('Macintosh') && 'ontouchend' in document)
}

function isIOSSafari(): boolean {
  if (!isIOS()) return false
  const ua = navigator.userAgent
  // Chrome/Firefox/Edge/Opera on iOS have their own UA tokens and can't A2HS.
  return !/CriOS|FxiOS|EdgiOS|OPiOS|OPT\//i.test(ua)
}

export const hintMode = computed<HintMode>(() => {
  if (typeof window === 'undefined') return 'none'
  if (isStandalone.value) return 'none'
  if (isDismissedRecently()) return 'none'
  if (isInAppBrowser()) return 'inapp'
  if (deferredPrompt.value) return 'android-install'
  if (isIOSSafari()) return 'ios-safari'
  return 'none'
})

/** Fires the native Chromium install prompt. Returns true if the user accepted. */
export async function triggerInstall(): Promise<boolean> {
  const evt = deferredPrompt.value
  if (!evt) return false
  try {
    evt.prompt()
    const choice = await evt.userChoice
    deferredPrompt.value = null
    return choice?.outcome === 'accepted'
  } catch {
    return false
  }
}

export function dismissHint() {
  const now = Date.now()
  try { localStorage.setItem(DISMISS_KEY, String(now)) } catch {}
  dismissedAt.value = now
  // Also clear the captured event — no reason to keep it around.
  deferredPrompt.value = null
}

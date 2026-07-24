import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import en from './locales/en'

const STORAGE_KEY = 'lumen-lang'

function getDefaultLocale(): string {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'en' || saved === 'zh-CN') return saved
  const browserLang = navigator.language
  if (browserLang.startsWith('zh')) return 'zh-CN'
  // Only default to Chinese for explicit Chinese browsers; all others default to 'en'
  return 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: getDefaultLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en': en,
  },
})

export function setLocale(locale: string) {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.lang = locale === 'zh-CN' ? 'zh-CN' : 'en'
}

export const availableLocales = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en', label: 'EN' },
] as const

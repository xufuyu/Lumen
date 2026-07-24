<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale, availableLocales } from '../i18n'
import PrivacyBadge from './PrivacyBadge.vue'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()

const tabs = computed(() => [
  { name: 'home', label: t('nav.home'), title: t('nav.home'), path: '/', icon: 'fa-house' },
  { name: 'timeline', label: t('nav.timeline'), title: t('home.eventsTitle'), path: '/timeline', icon: 'fa-calendar-days' },
  { name: 'tasks', label: t('nav.tasks'), title: t('home.tasksTitle'), path: '/tasks', icon: 'fa-circle-check' },
  { name: 'query', label: t('nav.query'), title: t('nav.query'), path: '/query', icon: 'fa-comment-dots' },
])

const isHome = computed(() => route.path === '/')
const currentTitle = computed(() => {
  const tab = tabs.value.find(t => t.path === route.path)
  return tab ? tab.title : ''
})
const showIcp = computed(() => {
  const host = location.hostname.toLowerCase()
  return host === 'guppy.ltd' || host.endsWith('.guppy.ltd')
})

function switchLang() {
  setLocale(locale.value === 'zh-CN' ? 'en' : 'zh-CN')
}
</script>

<template>
  <div class="h-dvh flex flex-col max-w-lg md:max-w-2xl xl:max-w-none mx-auto bg-white lg:border-x border-stone-100 shadow-lg overflow-hidden">

    <!-- Header -->
    <header class="shrink-0 z-10 bg-white/95 backdrop-blur border-b border-stone-100 px-4 sm:px-6 lg:px-8 py-2.5 flex items-center justify-between">
      <div class="flex items-center gap-2 min-w-0">
        <!-- Back button (sub-pages) -->
        <button v-if="!isHome" @click="router.push('/')"
          class="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-stone-400 hover:text-stone-600 hover:bg-stone-100 transition-colors -ml-1"
          :aria-label="t('nav.back')">
          <i class="fa-solid fa-arrow-left text-sm"></i>
        </button>

        <div class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 overflow-hidden">
          <img src="/favicon.ico" class="w-full h-full object-contain" alt="Lumen" />
        </div>
        <template v-if="isHome">
          <h1 class="text-sm font-bold text-stone-800 tracking-tight leading-none">{{ t('app.title') }}</h1>
          <span v-if="t('app.subtitle')" class="hidden sm:inline text-[10px] text-stone-400">{{ t('app.subtitle') }}</span>
        </template>
        <template v-else>
          <h1 class="text-sm font-semibold text-stone-700 truncate">{{ currentTitle }}</h1>
        </template>

        <!-- Language switcher (next to title) -->
        <button @click="switchLang"
          class="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded text-stone-400 hover:text-violet-500 hover:bg-violet-50 transition-colors"
          :title="locale === 'zh-CN' ? 'Switch to English' : '切换到中文'">
          {{ availableLocales.find(l => l.code === locale)?.label || '中' }}
        </button>
      </div>

      <div class="flex items-center gap-2">
        <!-- Desktop nav tabs -->
        <nav class="hidden lg:flex items-center gap-1 mr-2">
          <button v-for="tab in tabs" :key="tab.name" @click="router.push(tab.path)"
            :class="['text-xs px-3 py-1.5 rounded-lg font-medium transition-colors',
              route.path === tab.path ? 'bg-violet-50 text-violet-600' : 'text-stone-400 hover:text-stone-600 hover:bg-stone-50']">
            <i :class="['fa-solid', tab.icon, 'mr-1 text-[10px]']"></i>{{ tab.label }}
          </button>
        </nav>
        <PrivacyBadge />
      </div>
    </header>

    <!-- Main content -->
    <main class="flex-1 overflow-y-auto overscroll-contain px-4 sm:px-6 lg:px-8 py-4 sm:py-5 lg:py-6">
      <router-view />
    </main>

    <!-- ICP 备案（仅 guppy.ltd 域名显示） -->
    <footer v-if="showIcp" class="shrink-0 text-center py-2.5 border-t border-stone-50">
      <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener" class="text-[11px] text-stone-400 hover:text-stone-600 transition-colors">渝ICP备2023009735号</a>
    </footer>

    <!-- Mobile bottom tabs (only on sub-pages: timeline/tasks/query) -->
    <nav v-if="!isHome" class="lg:hidden shrink-0 bg-white border-t border-stone-100 flex justify-around py-1.5 px-2 pb-[max(0.25rem,env(safe-area-inset-bottom))]">
      <button v-for="tab in tabs" :key="tab.name" @click="router.push(tab.path)"
        :class="['flex flex-col items-center gap-0.5 px-3 py-1 rounded-xl transition-all min-w-0',
          route.path === tab.path ? 'text-violet-600' : 'text-stone-400']">
        <i :class="['fa-solid', tab.icon, 'text-base']"></i>
        <span class="text-[10px] font-semibold">{{ tab.label }}</span>
      </button>
    </nav>
  </div>
</template>

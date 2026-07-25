<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { onMounted, onUnmounted } from 'vue'
import { setLocale, availableLocales } from '../i18n'
import { getUserId, setUserId } from '../user'
import { connectSync, disconnectSync } from '../sync'

const { t, locale } = useI18n()
const showSettings = ref(false)
const settingsMsg = ref('')
const settingsErr = ref(false)

onMounted(connectSync)
onUnmounted(disconnectSync)
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

async function copyUserId() {
  try {
    await navigator.clipboard.writeText(getUserId())
    settingsMsg.value = t('settings.copied')
    settingsErr.value = false
  } catch {
    // Fallback for non-HTTPS contexts
    const ta = document.createElement('textarea')
    ta.value = getUserId()
    ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select(); document.execCommand('copy')
    document.body.removeChild(ta)
    settingsMsg.value = t('settings.copied')
    settingsErr.value = false
  }
}

function handleSwitchId(newUid: string) {
  const oldUid = getUserId()
  if (newUid === oldUid) {
    settingsMsg.value = t('settings.sameId')
    settingsErr.value = true
    return
  }
  setUserId(newUid)
  settingsMsg.value = t('settings.switched', { uid: newUid })
  settingsErr.value = false
  setTimeout(() => { location.reload() }, 1500)
}
</script>

<template>
  <div class="h-screen h-dvh flex flex-col max-w-lg md:max-w-2xl xl:max-w-none mx-auto bg-white lg:border-x border-stone-100 shadow-lg overflow-hidden">

    <!-- Header -->
    <header class="shrink-0 z-10 bg-white border-b border-stone-100 px-4 sm:px-6 lg:px-8 py-2.5 flex items-center justify-between">
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
        <!-- Settings button -->
        <button @click="showSettings = true"
          class="shrink-0 w-7 h-7 flex items-center justify-center rounded-lg text-stone-400 hover:text-violet-500 hover:bg-violet-50 transition-colors"
          title="Settings">
          <i class="fa-solid fa-gear text-xs"></i>
        </button>
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

    <!-- Settings Dialog -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="showSettings" class="fixed inset-0 z-50 flex items-center justify-center" @click.self="showSettings = false">
          <div class="absolute inset-0 bg-black/30" />
          <div class="relative bg-white rounded-2xl shadow-xl w-[380px] max-w-[90vw] mx-4 p-6">
            <div class="flex items-center justify-between mb-5">
              <h2 class="text-sm font-bold text-stone-700"><i class="fa-solid fa-gear mr-2 text-violet-400"></i>{{ t('settings.title') }}</h2>
              <button @click="showSettings = false" class="text-stone-300 hover:text-stone-500"><i class="fa-solid fa-xmark"></i></button>
            </div>

            <!-- Current ID display -->
            <label class="block text-[11px] font-semibold text-stone-400 uppercase tracking-wide mb-1.5">{{ t('settings.uidLabel') }}</label>
            <div class="flex items-center gap-2 mb-3">
              <code class="flex-1 bg-stone-50 rounded-lg px-3 py-2 text-xs text-stone-600 font-mono break-all select-all">{{ getUserId() }}</code>
              <button @click="copyUserId()"
                class="shrink-0 text-xs text-violet-500 hover:text-violet-700 font-medium px-3 py-2 rounded-lg hover:bg-violet-50 transition-colors">
                <i class="fa-solid fa-copy mr-1"></i>{{ t('settings.copy') }}
              </button>
            </div>
            <p class="text-[10px] text-stone-400 mb-4">{{ t('settings.uidTip') }}</p>

            <!-- Change ID (merge) -->
            <label class="block text-[11px] font-semibold text-stone-400 uppercase tracking-wide mb-1.5">{{ t('settings.changeLabel') }}</label>
            <form @submit.prevent="(e) => { const v = (e.target as any).uid.value.trim(); if (v) handleSwitchId(v) }" class="flex gap-2 mb-2">
              <input name="uid" type="text" :placeholder="t('settings.placeholder')"
                class="flex-1 text-xs bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 focus:outline-none focus:border-violet-400"
                maxlength="64" pattern="[a-zA-Z0-9_-]+" />
              <button type="submit"
                class="text-xs bg-violet-500 text-white rounded-lg px-4 py-2 font-medium hover:bg-violet-600 transition-colors">{{ t('settings.save') }}</button>
            </form>
            <p class="text-[10px] text-stone-400 mb-2">{{ t('settings.changeTip') }}</p>

            <!-- Status message -->
            <p v-if="settingsMsg" :class="['text-xs rounded-lg px-3 py-2', settingsErr ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600']">{{ settingsMsg }}</p>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

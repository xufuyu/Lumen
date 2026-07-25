<script setup lang="ts">
/**
 * Gentle install / open-in-browser nudge.
 *
 * Shows exactly one of three modes based on runtime detection (see
 * install.ts). Sits above the mobile bottom nav; can be dismissed with a
 * seven-day cooling-off period. Tone is deliberately low-key — no urgency,
 * no red, no exclamation marks — to match Lumen's "don't push, don't judge"
 * philosophy.
 */
import { useI18n } from 'vue-i18n'
import { hintMode, triggerInstall, dismissHint } from '../install'

const { t } = useI18n()

const iconClass: Record<string, string> = {
  'inapp': 'fa-solid fa-arrow-up-right-from-square',
  'ios-safari': 'fa-solid fa-arrow-up-from-bracket',
  'android-install': 'fa-solid fa-mobile-screen',
}

async function onInstall() {
  const accepted = await triggerInstall()
  if (accepted) dismissHint()
}
</script>

<template>
  <Transition name="install-hint">
    <div v-if="hintMode !== 'none'"
      class="shrink-0 px-3 pt-2 pb-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]"
      role="status" aria-live="polite">
      <div
        class="flex items-start gap-3 rounded-2xl bg-gradient-to-br from-violet-50 to-white border border-violet-100 shadow-sm px-3.5 py-2.5">
        <!-- Icon -->
        <div class="shrink-0 w-8 h-8 flex items-center justify-center rounded-xl bg-violet-100/70 text-violet-500">
          <i :class="iconClass[hintMode]" class="text-sm"></i>
        </div>

        <!-- Text -->
        <div class="flex-1 min-w-0 leading-snug">
          <p class="text-xs font-semibold text-stone-700">{{ t(`installHint.${hintMode}.title`) }}</p>
          <p class="text-[11px] text-stone-500 mt-0.5">{{ t(`installHint.${hintMode}.hint`) }}</p>
        </div>

        <!-- Action + close -->
        <div class="shrink-0 flex items-center gap-1">
          <button v-if="hintMode === 'android-install'"
            @click="onInstall"
            class="text-[11px] font-semibold px-2.5 py-1.5 rounded-lg bg-violet-500 text-white hover:bg-violet-600 transition-colors">
            {{ t('installHint.install') }}
          </button>
          <button @click="dismissHint"
            class="w-7 h-7 flex items-center justify-center rounded-lg text-stone-300 hover:text-stone-500 hover:bg-stone-50 transition-colors"
            :aria-label="t('installHint.dismiss')" :title="t('installHint.dismiss')">
            <i class="fa-solid fa-xmark text-xs"></i>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.install-hint-enter-active,
.install-hint-leave-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.install-hint-enter-from,
.install-hint-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>

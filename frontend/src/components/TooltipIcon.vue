<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

defineProps<{ text: string }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

function toggle(e: Event) {
  e.preventDefault()
  e.stopPropagation()
  open.value = !open.value
}

function onDocClick(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick, true))
onUnmounted(() => document.removeEventListener('click', onDocClick, true))
</script>

<template>
  <span ref="root" class="tooltip-host">
    <button
      type="button"
      class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] text-stone-300 hover:text-stone-500 active:bg-stone-100 transition-colors cursor-help"
      @click.prevent.stop="toggle"
      :aria-label="text"
    >
      <i class="fa-solid fa-circle-question"></i>
    </button>
    <transition name="tip">
      <span v-if="open" role="tooltip" class="tooltip-popover" @click.stop>
        <span class="tooltip-arrow"></span>
        {{ text }}
      </span>
    </transition>
  </span>
</template>

<style scoped>
.tooltip-host { position: relative; display: inline-flex; align-items: center; }
.tooltip-popover {
  position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
  z-index: 50; max-width: 220px; width: max-content;
  background: #292524; color: #fafaf9; font-size: 12px; line-height: 1.5;
  padding: 8px 12px; border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  text-align: left;
}
.tooltip-arrow {
  position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
  width: 0; height: 0;
  border-left: 5px solid transparent; border-right: 5px solid transparent;
  border-top: 5px solid #292524;
}
.tip-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.tip-leave-active { transition: opacity 0.1s ease; }
.tip-enter-from, .tip-leave-to { opacity: 0; transform: translateX(-50%) translateY(4px); }
</style>
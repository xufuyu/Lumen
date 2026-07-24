<script setup lang="ts">
import { ref } from 'vue'
const visible = ref(true)
</script>

<template>
  <div v-if="visible"
    class="flex items-center gap-1.5 text-[11px] text-stone-400 bg-stone-50 rounded-full px-2.5 py-1 cursor-pointer hover:bg-stone-100 transition-colors"
    title="数据仅存储在你的本地设备上" @click="visible = false">
    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>仅本地
  </div>
</template>
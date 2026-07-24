<script setup lang="ts">
import QueryChat from '../components/QueryChat.vue'
import TooltipIcon from '../components/TooltipIcon.vue'
</script>

<template>
  <div>
    <div class="mb-4">
      <div class="flex items-center gap-1.5">
        <h2 class="text-base font-bold text-stone-700"><i class="fa-solid fa-comment-dots mr-2 text-violet-400"></i>问答</h2>
        <TooltipIcon text="基于你的记录回答自然语言问题。回答仅来源于你记录的内容，不会进行推测。涉及医疗话题时会自动附加免责声明。" />
      </div>
      <p class="text-sm text-stone-400 mt-1">基于你的记录，回答关于你近期活动的问题</p>
    </div>
    <QueryChat />
  </div>
</template>
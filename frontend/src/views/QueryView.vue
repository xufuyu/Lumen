<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import QueryChat from '../components/QueryChat.vue'
import TooltipIcon from '../components/TooltipIcon.vue'

const { t } = useI18n()
</script>

<template>
  <div>
    <div class="mb-4">
      <div class="flex items-center gap-1.5">
        <h2 class="text-base font-bold text-stone-700"><i class="fa-solid fa-comment-dots mr-2 text-violet-400"></i>{{ t('query.title') }}</h2>
        <TooltipIcon :text="t('query.tooltip')" />
      </div>
      <p class="text-sm text-stone-400 mt-1">{{ t('query.subtitle') }}</p>
    </div>
    <QueryChat />
  </div>
</template>
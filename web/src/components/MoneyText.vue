<template>
  <span :class="['money', tone]">{{ display }}</span>
</template>

<script setup>
import { computed } from 'vue'
import { money, moneyShort } from '@/utils/format'

const props = defineProps({
  value: { type: [Number, String], default: 0 },
  symbol: { type: Boolean, default: false },
  short: { type: Boolean, default: false },
  colorize: { type: Boolean, default: false }
})

const display = computed(() => {
  const num = Number(props.value ?? 0)
  if (Number.isNaN(num)) return '-'
  return props.short ? moneyShort(num) : money(num, props.symbol)
})

const tone = computed(() => {
  if (!props.colorize) return ''
  const num = Number(props.value ?? 0)
  if (num > 0) return 'positive'
  if (num < 0) return 'negative'
  return ''
})
</script>

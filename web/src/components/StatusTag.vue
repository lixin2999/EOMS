<template>
  <el-tag :type="type" :effect="effect" size="small" round>{{ text }}</el-tag>
</template>

<script setup>
import { computed } from 'vue'
import { STATUS_LABELS, tagType } from '@/utils/constants'

const props = defineProps({
  value: { type: [String, Number], default: '' },
  labels: { type: Object, default: null },
  effect: { type: String, default: 'light' }
})

const text = computed(() => {
  const map = props.labels || STATUS_LABELS
  return map[props.value] || props.value || '-'
})

const type = computed(() => tagType(props.value))
</script>

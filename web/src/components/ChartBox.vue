<template>
  <div ref="el" :class="['chart', size]" />
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  size: { type: String, default: '' }
})

const el = ref(null)
const chart = shallowRef(null)
let observer = null

function render() {
  if (!chart.value) return
  chart.value.setOption(props.option, true)
}

onMounted(() => {
  chart.value = echarts.init(el.value)
  render()
  observer = new ResizeObserver(() => chart.value?.resize())
  observer.observe(el.value)
})

watch(
  () => props.option,
  () => render(),
  { deep: true }
)

onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
  chart.value = null
})
</script>

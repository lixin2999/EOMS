<template>
  <div style="display: inline-flex; align-items: center; gap: 8px">
    <el-button size="small" :loading="uploading" :icon="Upload" @click="pick">
      {{ modelValue ? '重新上传' : label }}
    </el-button>
    <el-link v-if="modelValue" type="primary" :underline="false" @click="download">
      {{ fileName || `文件 #${modelValue}` }}
    </el-link>
    <el-button v-if="modelValue && clearable" link type="danger" size="small" @click="clear">移除</el-button>
    <input ref="inputRef" type="file" :accept="accept" style="display: none" @change="onChange" />
    <el-progress v-if="uploading" :percentage="progress" :stroke-width="4" style="width: 90px" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { fileApi } from '@/api'
import { saveBlob } from '@/utils/download'

const props = defineProps({
  modelValue: { type: Number, default: null },
  bizType: { type: String, default: '' },
  bizId: { type: Number, default: null },
  label: { type: String, default: '上传附件' },
  accept: { type: String, default: '' },
  clearable: { type: Boolean, default: true }
})

const emit = defineEmits(['update:modelValue', 'uploaded'])

const inputRef = ref(null)
const uploading = ref(false)
const progress = ref(0)
const fileName = ref('')

function pick() {
  inputRef.value?.click()
}

async function onChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  if (props.bizType) form.append('biz_type', props.bizType)
  if (props.bizId) form.append('biz_id', String(props.bizId))
  uploading.value = true
  progress.value = 0
  try {
    const data = await fileApi.upload(form, (value) => (progress.value = value))
    fileName.value = data.name
    emit('update:modelValue', data.id)
    emit('uploaded', data)
    ElMessage.success('上传成功')
  } finally {
    uploading.value = false
  }
}

async function download() {
  if (!props.modelValue) return
  const response = await fileApi.download(props.modelValue)
  saveBlob(response, fileName.value || `file-${props.modelValue}`)
}

function clear() {
  fileName.value = ''
  emit('update:modelValue', null)
}
</script>

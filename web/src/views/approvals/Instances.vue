<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>流程实例</h2>
        <p>查看所有审批流程的节点、处理人、流转记录与抄送情况，支持催办、撤回与抄送。</p>
      </div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="form.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="status in ['RUNNING', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'CANCELED']" :key="status" :label="statusLabel(status)" :value="status" />
        </el-select>
        <el-select v-model="form.biz_type" placeholder="全部业务类型" clearable @change="reload">
          <el-option v-for="(label, value) in FLOW_BIZ_TYPES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-checkbox v-model="form.mine" @change="reload">仅我发起</el-checkbox>
        <el-input v-model="form.keyword" placeholder="流程标题 / 发起人" clearable :prefix-icon="Search" @keyup.enter="reload" @clear="reload" />
        <el-button :icon="Search" @click="reload">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="title" label="流程标题" min-width="260" show-overflow-tooltip />
        <el-table-column label="业务类型" width="120">
          <template #default="{ row }">{{ labelOf(FLOW_BIZ_TYPES, row.biz_type) }}</template>
        </el-table-column>
        <el-table-column prop="initiator_name" label="发起人" width="100" />
        <el-table-column prop="current_node" label="当前节点" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" /></template>
        </el-table-column>
        <el-table-column label="发起时间" width="150">
          <template #default="{ row }">{{ datetime(row.start_at) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="150">
          <template #default="{ row }">{{ datetime(row.finish_at) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ durationText(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="open(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>

    <el-drawer v-model="drawerVisible" size="760px" title="流程详情" destroy-on-close>
      <approval-panel v-if="currentId" :instance-id="currentId" @changed="load" />
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { workflowApi } from '@/api'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import StatusTag from '@/components/StatusTag.vue'
import { datetime } from '@/utils/format'
import { FLOW_BIZ_TYPES, labelOf } from '@/utils/constants'

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const form = ref({ status: '', biz_type: '', mine: false, keyword: '' })
const drawerVisible = ref(false)
const currentId = ref(null)

function statusLabel(status) {
  return { RUNNING: '审批中', APPROVED: '已通过', REJECTED: '已驳回', WITHDRAWN: '已撤回', CANCELED: '已取消' }[status] || status
}

function durationText(row) {
  const end = row.finish_at ? dayjs(row.finish_at) : dayjs()
  const hours = end.diff(dayjs(row.start_at), 'hour', true)
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} 分钟`
  if (hours < 48) return `${hours.toFixed(1)} 小时`
  return `${(hours / 24).toFixed(1)} 天`
}

async function reload() {
  page.value = 1
  await load()
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (form.value.status) params.status = form.value.status
    if (form.value.biz_type) params.biz_type = form.value.biz_type
    if (form.value.mine) params.mine = true
    if (form.value.keyword) params.keyword = form.value.keyword
    const data = await workflowApi.instances(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function open(row) {
  currentId.value = row.id
  drawerVisible.value = true
}

onMounted(load)
</script>

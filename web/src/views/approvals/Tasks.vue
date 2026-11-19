<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>我的待办</h2>
        <p>集中处理待审批任务，支持同意、驳回、转办、加签、催办与抄送，全部动作留痕可追溯。</p>
      </div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">我的待办</div>
        <div class="stat-value">{{ pendingCount }}</div>
        <div class="stat-foot">当前账号待处理审批任务</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">超时任务</div>
        <div class="stat-value">{{ overdueCount }}</div>
        <div class="stat-foot">已超过节点处理时限</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">流程状态筛选</div>
        <div class="stat-value small">{{ statusLabel }}</div>
        <div class="stat-foot">{{ form.mine ? '仅看我的任务' : '查看全部任务' }}</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-radio-group v-model="form.mine" @change="reload">
          <el-radio-button :value="true">我的任务</el-radio-button>
          <el-radio-button :value="false">全部任务</el-radio-button>
        </el-radio-group>
        <el-select v-model="form.status" @change="reload">
          <el-option label="待处理" value="PENDING" />
          <el-option label="已同意" value="APPROVED" />
          <el-option label="已驳回" value="REJECTED" />
          <el-option label="已转办" value="TRANSFERRED" />
        </el-select>
        <el-select v-model="form.biz_type" placeholder="全部业务类型" clearable @change="reload">
          <el-option v-for="(label, value) in FLOW_BIZ_TYPES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input v-model="form.keyword" placeholder="流程标题" clearable :prefix-icon="Search" @keyup.enter="reload" @clear="reload" />
        <el-button :icon="Search" @click="reload">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column label="流程标题" min-width="240">
          <template #default="{ row }">
            <div style="font-weight: 600">{{ row.instance?.title || '-' }}</div>
            <div class="muted" style="font-size: 12px; margin-top: 2px">
              {{ labelOf(FLOW_BIZ_TYPES, row.instance?.biz_type) }} · 发起人 {{ row.instance?.initiator_name }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="node_name" label="审批节点" width="130" />
        <el-table-column prop="assignee_name" label="处理人" width="100" />
        <el-table-column label="到达时间" width="150">
          <template #default="{ row }">{{ datetime(row.arrive_at) }}</template>
        </el-table-column>
        <el-table-column label="处理时限" width="190">
          <template #default="{ row }">
            <span :style="{ color: isOverdue(row) ? '#dc2626' : undefined }">{{ datetime(row.due_at) }}</span>
            <el-tag v-if="isOverdue(row)" type="danger" size="small" style="margin-left: 6px">已超时</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="taskTag(row.status)">{{ taskLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="流程状态" width="100">
          <template #default="{ row }"><status-tag :value="row.instance?.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openApprove(row)">审批</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>

    <el-dialog v-model="approveVisible" title="审批处理" width="760px" destroy-on-close>
      <approval-panel v-if="currentInstanceId" :instance-id="currentInstanceId" @changed="onChanged" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
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
const form = ref({ mine: true, status: 'PENDING', biz_type: '', keyword: '' })
const approveVisible = ref(false)
const currentInstanceId = ref(null)

const pendingCount = computed(() => (form.value.status === 'PENDING' ? total.value : rows.value.length))
const overdueCount = computed(() => rows.value.filter((row) => isOverdue(row)).length)
const statusLabel = computed(
  () => ({ PENDING: '待处理', APPROVED: '已同意', REJECTED: '已驳回', TRANSFERRED: '已转办' }[form.value.status] || form.value.status)
)

function isOverdue(row) {
  return row.status === 'PENDING' && row.due_at && dayjs(row.due_at).isBefore(dayjs())
}

function taskLabel(status) {
  return { PENDING: '待处理', APPROVED: '已同意', REJECTED: '已驳回', TRANSFERRED: '已转办', SKIPPED: '已跳过' }[status] || status
}

function taskTag(status) {
  return { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger', TRANSFERRED: 'info' }[status] || 'info'
}

async function reload() {
  page.value = 1
  await load()
}

async function load() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      mine: form.value.mine,
      status: form.value.status || 'PENDING'
    }
    if (form.value.biz_type) params.biz_type = form.value.biz_type
    if (form.value.keyword) params.keyword = form.value.keyword
    const data = await workflowApi.tasks(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function openApprove(row) {
  currentInstanceId.value = row.instance_id || row.instance?.id
  approveVisible.value = true
}

async function onChanged() {
  approveVisible.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>请假管理</h2>
        <p>请假申请走四级审批流程，审批通过后自动扣减假期余额并记录归档。</p>
      </div>
      <el-button v-if="auth.can('approval:leave')" type="primary" :icon="Plus" @click="openCreate">发起请假</el-button>
    </div>

    <div class="stat-grid">
      <div v-for="item in balances" :key="item.id" class="stat-card">
        <div class="stat-label">{{ labelOf(LEAVE_TYPES, item.type) }}余额</div>
        <div class="stat-value small">{{ item.remain }} <span style="font-size: 13px; color: #6b7280">天</span></div>
        <div class="stat-foot">年度额度 {{ item.total }} 天 · 已使用 {{ item.used }} 天</div>
      </div>
      <div v-if="!balances.length" class="stat-card">
        <div class="stat-label">假期余额</div>
        <div class="stat-value small">-</div>
        <div class="stat-foot">暂无额度记录，可先发起申请由审批后核定额度</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="status in ['DRAFT', 'RUNNING', 'REJECTED', 'APPROVED', 'CANCELED']" :key="status" :label="STATUS_LABELS[status]" :value="status" />
        </el-select>
        <el-select v-model="filters.type" placeholder="全部类型" clearable @change="reload">
          <el-option v-for="(label, value) in LEAVE_TYPES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.applicant_id" placeholder="全部申请人" clearable filterable @change="reload">
          <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
        </el-select>
        <div class="grow" />
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="no" label="请假单号" width="170" class-name="mono" />
        <el-table-column prop="applicant_name" label="申请人" width="100" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">{{ labelOf(LEAVE_TYPES, row.type) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ datetime(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="160">
          <template #default="{ row }">{{ datetime(row.end_time) }}</template>
        </el-table-column>
        <el-table-column prop="duration" label="时长（天）" width="100" align="center" />
        <el-table-column prop="reason" label="事由" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" /></template>
        </el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="{ row }">{{ datetime(row.submitted_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openDetail(row)">详情</el-button>
              <el-button v-if="canEdit(row)" link @click="openEdit(row)">编辑</el-button>
              <el-button v-if="canSubmit(row)" link type="success" @click="doAction(row, 'submit')">提交</el-button>
              <el-button v-if="canWithdraw(row)" link type="warning" @click="doAction(row, 'withdraw')">撤回</el-button>
            </div>
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

    <el-dialog v-model="formVisible" :title="editingId ? '编辑请假单' : '发起请假'" width="640px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="92px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="假期类型" prop="type">
              <el-select v-model="form.type" style="width: 100%">
                <el-option v-for="(label, value) in LEAVE_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="时长（天）" prop="duration">
              <el-input-number v-model="form.duration" :min="0.5" :max="365" :step="0.5" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="关联项目">
              <el-select v-model="form.project_id" clearable filterable style="width: 100%" placeholder="可不选">
                <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="开始时间" prop="start_time">
              <el-date-picker v-model="form.start_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束时间" prop="end_time">
              <el-date-picker v-model="form.end_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="工作交接">
          <el-select v-model="form.handover_user_id" clearable filterable style="width: 100%" placeholder="选择交接人">
            <el-option v-for="user in meta.userOptions" :key="user.id" :label="`${user.real_name}（${user.username}）`" :value="user.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="请假事由" prop="reason">
          <el-input v-model="form.reason" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="formVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save(false)">保存草稿</el-button>
          <el-button type="success" :loading="saving" @click="save(true)">保存并提交</el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" size="680px" :title="detail?.no || '请假单详情'" destroy-on-close>
      <div v-if="detail" v-loading="detailLoading">
        <div class="detail-hero" style="margin-bottom: 14px">
          <div>
            <h2>{{ labelOf(LEAVE_TYPES, detail.type) }} · {{ detail.duration }} 天</h2>
            <div class="sub">
              <span>{{ detail.applicant_name }}</span>
              <span>{{ datetime(detail.start_time) }} 至 {{ datetime(detail.end_time) }}</span>
            </div>
          </div>
          <status-tag :value="detail.status" />
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="请假单号">{{ detail.no }}</el-descriptions-item>
          <el-descriptions-item label="关联项目">{{ detail.project_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="工作交接">{{ handoverName }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ datetime(detail.submitted_at) }}</el-descriptions-item>
          <el-descriptions-item label="请假事由" :span="2">{{ detail.reason || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">业务操作</div>
        <div class="tag-row">
          <el-button v-if="canEdit(detail)" size="small" @click="openEdit(detail)">编辑</el-button>
          <el-button v-if="canSubmit(detail)" size="small" type="success" @click="doAction(detail, 'submit')">提交审批</el-button>
          <el-button v-if="canWithdraw(detail)" size="small" type="warning" @click="doAction(detail, 'withdraw')">撤回审批</el-button>
          <el-button v-if="detail.status === 'DRAFT'" size="small" type="danger" plain @click="doAction(detail, 'cancel')">取消单据</el-button>
        </div>

        <template v-if="detail.instance_id">
          <div class="section-title">审批流程</div>
          <approval-panel :instance-id="detail.instance_id" @changed="onApprovalChanged" />
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { leaveApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import StatusTag from '@/components/StatusTag.vue'
import { datetime } from '@/utils/format'
import { LEAVE_TYPES, STATUS_LABELS, labelOf } from '@/utils/constants'

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ status: '', type: '', applicant_id: null })
const balances = ref([])

const formVisible = ref(false)
const formRef = ref()
const saving = ref(false)
const editingId = ref(null)
const editingVersion = ref(null)
const form = ref({ type: 'ANNUAL', start_time: '', end_time: '', duration: 1, reason: '', handover_user_id: null, project_id: null })

const detailVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)

const handoverName = computed(() => {
  if (!detail.value?.handover_user_id) return '-'
  return meta.userOptions.find((item) => item.id === detail.value.handover_user_id)?.real_name || `用户 #${detail.value.handover_user_id}`
})

const formRules = {
  type: [{ required: true, message: '请选择假期类型', trigger: 'change' }],
  start_time: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
  end_time: [
    { required: true, message: '请选择结束时间', trigger: 'change' },
    {
      validator: (_rule, value, callback) => {
        if (value && form.value.start_time && dayjs(value).isBefore(dayjs(form.value.start_time))) {
          callback(new Error('结束时间不能早于开始时间'))
        } else callback()
      },
      trigger: 'change'
    }
  ],
  duration: [{ required: true, message: '请填写请假时长', trigger: 'blur' }],
  reason: [{ required: true, message: '请填写请假事由', trigger: 'blur' }]
}

function canEdit(row) {
  return ['DRAFT', 'REJECTED'].includes(row.status) && (row.creator_id === auth.user.id || auth.user.is_super)
}
function canSubmit(row) {
  return ['DRAFT', 'REJECTED'].includes(row.status) && (row.creator_id === auth.user.id || auth.user.is_super)
}
function canWithdraw(row) {
  return row.status === 'RUNNING' && (row.creator_id === auth.user.id || auth.user.is_super)
}

function openCreate() {
  editingId.value = null
  editingVersion.value = null
  const start = dayjs().hour(9).minute(0).second(0)
  form.value = {
    type: 'ANNUAL',
    start_time: start.format('YYYY-MM-DD HH:mm:ss'),
    end_time: start.add(1, 'day').hour(18).format('YYYY-MM-DD HH:mm:ss'),
    duration: 1,
    reason: '',
    handover_user_id: null,
    project_id: null
  }
  formVisible.value = true
}

function openEdit(row) {
  const data = row.start_time ? row : null
  if (!data) return
  editingId.value = data.id
  editingVersion.value = data.version
  form.value = {
    type: data.type,
    start_time: data.start_time,
    end_time: data.end_time,
    duration: Number(data.duration),
    reason: data.reason || '',
    handover_user_id: data.handover_user_id || null,
    project_id: data.project_id || null
  }
  formVisible.value = true
}

watch(
  () => [form.value.start_time, form.value.end_time],
  ([start, end]) => {
    if (!start || !end) return
    const hours = dayjs(end).diff(dayjs(start), 'hour', true)
    if (hours > 0) {
      const days = Math.max(0.5, Math.round((hours / 8) * 2) / 2)
      form.value.duration = days
    }
  }
)

async function save(submit) {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form.value, version: editingVersion.value }
    let saved
    if (editingId.value) saved = await leaveApi.update(editingId.value, payload)
    else saved = await leaveApi.create(payload)
    if (submit) {
      await leaveApi.submit(saved.id)
      ElMessage.success('请假申请已提交')
    } else {
      ElMessage.success('请假单已保存')
    }
    formVisible.value = false
    await reload()
    await loadBalances()
  } finally {
    saving.value = false
  }
}

async function reload() {
  page.value = 1
  await load()
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    Object.entries(filters.value).forEach(([key, value]) => {
      if (value !== '' && value !== null) params[key] = value
    })
    const data = await leaveApi.list(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadBalances() {
  try {
    balances.value = await leaveApi.balance()
  } catch {
    balances.value = []
  }
}

function reset() {
  filters.value = { status: '', type: '', applicant_id: null }
  reload()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await leaveApi.detail(row.id)
  } finally {
    detailLoading.value = false
  }
}

async function onApprovalChanged() {
  await load()
  await loadBalances()
  if (detail.value?.id) detail.value = await leaveApi.detail(detail.value.id)
}

async function doAction(row, action) {
  const labels = { submit: '提交审批', withdraw: '撤回审批', cancel: '取消单据' }
  try {
    await ElMessageBox.confirm(`确认${labels[action]}「${row.no}」吗？`, '操作确认', { type: 'warning' })
  } catch {
    return
  }
  await leaveApi[action](row.id)
  ElMessage.success(`${labels[action]}成功`)
  await load()
  await loadBalances()
  if (detailVisible.value && detail.value?.id === row.id) {
    detail.value = await leaveApi.detail(row.id)
  }
}

onMounted(async () => {
  await meta.ensure()
  await Promise.all([load(), loadBalances()])
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>审计日志</h2>
        <p>记录登录、权限变更、业务单据流转与配置修改等关键操作，保留变更前后快照、IP、UA 与 trace_id，便于追溯。</p>
      </div>
      <div class="tag-row">
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">日志总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前筛选条件下</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前页操作人</div>
        <div class="stat-value">{{ userCount }}</div>
        <div class="stat-foot">去重后的操作账号</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前页对象类型</div>
        <div class="stat-value">{{ targetTypeCount }}</div>
        <div class="stat-foot">涉及的业务对象种类</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">含变更快照</div>
        <div class="stat-value">{{ snapshotCount }}</div>
        <div class="stat-foot">记录了 before/after 数据</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select
          v-model="filters.action"
          placeholder="操作动作"
          filterable
          allow-create
          default-first-option
          clearable
          style="width: 180px"
          @change="reload"
        >
          <el-option v-for="(label, value) in ACTION_LABELS" :key="value" :label="`${label}（${value}）`" :value="value" />
        </el-select>
        <el-select
          v-model="filters.target_type"
          placeholder="对象类型"
          filterable
          allow-create
          default-first-option
          clearable
          style="width: 160px"
          @change="reload"
        >
          <el-option v-for="value in TARGET_TYPES" :key="value" :label="value" :value="value" />
        </el-select>
        <el-select v-model="filters.user_id" placeholder="操作人" filterable clearable style="width: 180px" @change="reload">
          <el-option
            v-for="user in meta.userOptions"
            :key="user.id"
            :label="`${user.real_name}（${user.username}）`"
            :value="user.id"
          />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          clearable
          style="width: 260px"
          @change="reload"
        />
        <el-input
          v-model="filters.keyword"
          placeholder="动作 / 用户名关键字"
          clearable
          :prefix-icon="Search"
          style="width: 200px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" row-key="id">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="audit-detail">
              <div class="audit-meta">
                <span class="chip mono">trace {{ row.trace_id || '-' }}</span>
                <span class="chip mono">IP {{ row.ip || '-' }}</span>
                <span class="chip">对象 {{ row.target_type || '-' }} #{{ row.target_id || '-' }}</span>
              </div>
              <div v-if="row.ua" class="muted" style="font-size: 12px; margin-bottom: 10px; word-break: break-all">
                UA：{{ row.ua }}
              </div>
              <template v-if="diffRows(row).length">
                <h4 style="margin: 6px 0 8px; font-size: 13px">变更字段（{{ diffRows(row).length }}）</h4>
                <el-table :data="diffRows(row)" size="small" border>
                  <el-table-column prop="key" label="字段" width="220" class-name="mono" />
                  <el-table-column label="变更前" min-width="240">
                    <template #default="{ row: diff }">
                      <span class="diff-before">{{ diff.before }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="变更后" min-width="240">
                    <template #default="{ row: diff }">
                      <span class="diff-after">{{ diff.after }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </template>
              <div class="json-grid">
                <div>
                  <h4>变更前</h4>
                  <pre class="json-block">{{ pretty(row.before_json) }}</pre>
                </div>
                <div>
                  <h4>变更后</h4>
                  <pre class="json-block">{{ pretty(row.after_json) }}</pre>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ datetime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="160">
          <template #default="{ row }">
            <span>{{ row.username || userLabel(row.user_id) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="动作" width="220">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="actionTag(row.action)">{{ actionLabel(row.action) }}</el-tag>
            <div class="mono muted" style="font-size: 11px">{{ row.action }}</div>
          </template>
        </el-table-column>
        <el-table-column label="业务对象" min-width="200">
          <template #default="{ row }">
            <span class="mono">{{ row.target_type || '-' }}</span>
            <span v-if="row.target_id" class="muted"> #{{ row.target_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="IP" width="140" class-name="mono">
          <template #default="{ row }">{{ row.ip || '-' }}</template>
        </el-table-column>
        <el-table-column label="trace_id" width="200" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono muted">{{ row.trace_id || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="变更" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="diffRows(row).length" size="small" type="warning" effect="plain">
              {{ diffRows(row).length }} 项
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { iamApi } from '@/api'
import { useMetaStore } from '@/stores/meta'
import { datetime } from '@/utils/format'

const ACTION_LABELS = {
  LOGIN: '登录',
  LOGOUT: '退出登录',
  LOGIN_FAILED: '登录失败',
  CHANGE_PASSWORD: '修改密码',
  RESET_PASSWORD: '重置密码',
  CREATE_USER: '新建用户',
  UPDATE_USER: '更新用户',
  SAVE_ROLE: '保存角色',
  DELETE_ROLE: '删除角色',
  CREATE_DEPT: '新建部门',
  UPDATE_DEPT: '更新部门',
  CREATE_PROJECT: '新建项目',
  UPDATE_PROJECT: '更新项目',
  SUBMIT_PROJECT: '提交立项',
  APPROVE_PROJECT: '立项审批',
  CREATE_EXPENSE: '新建报销',
  CREATE_LEAVE: '新建请假',
  CREATE_DOCUMENT: '新建文件',
  CREATE_VENDOR: '新建供应商',
  SUBMIT_VENDOR: '提交准入',
  BLACKLIST_VENDOR: '拉黑供应商',
  RESTORE_VENDOR: '恢复供应商',
  CREATE_CONTRACT: '新建合同',
  UPDATE_CONTRACT: '更新合同',
  CREATE_PAYMENT: '新建付款',
  PAY_PAYMENT: '执行付款',
  CANCEL_PAYMENT: '取消付款',
  CREATE_RECEIPT: '登记收款',
  CANCEL_RECEIPT: '作废收款',
  CREATE_REVENUE: '新增计收',
  CONFIRM_REVENUE: '确认计收',
  CANCEL_REVENUE: '取消计收',
  SAVE_BUDGET: '维护预算',
  DELETE_BUDGET: '删除预算',
  CLOSE_PERIOD: '关账',
  REOPEN_PERIOD: '反关账',
  SET_CONFIG: '修改参数',
  SAVE_DICT: '保存字典',
  DELETE_DICT: '删除字典',
  SAVE_WORKFLOW: '保存流程定义',
  APPROVE: '审批同意',
  REJECT: '审批驳回',
  WITHDRAW: '撤回流程',
  TRANSFER: '转办',
  ADD_SIGN: '加签'
}

const TARGET_TYPES = [
  'USER',
  'ROLE',
  'DEPT',
  'PROJECT',
  'EXPENSE',
  'LEAVE',
  'DOCUMENT',
  'VENDOR',
  'CONTRACT',
  'PAYMENT',
  'RECEIPT',
  'REVENUE',
  'BUDGET',
  'PERIOD',
  'WORKFLOW',
  'WORKFLOW_DEFINITION',
  'CONFIG',
  'DICT',
  'CUSTOMER',
  'FILE'
]

const meta = useMetaStore()

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dateRange = ref([])
const filters = ref({ action: '', target_type: '', user_id: null, keyword: '' })

const userCount = computed(() => new Set(rows.value.map((row) => row.username || row.user_id).filter(Boolean)).size)
const targetTypeCount = computed(() => new Set(rows.value.map((row) => row.target_type).filter(Boolean)).size)
const snapshotCount = computed(() => rows.value.filter((row) => row.before_json || row.after_json).length)

function userLabel(id) {
  if (!id) return '系统'
  const user = (meta.userOptions || []).find((item) => item.id === id)
  return user ? user.real_name : `用户 #${id}`
}

function actionLabel(action) {
  return ACTION_LABELS[action] || action || '-'
}

function actionTag(action) {
  if (!action) return 'info'
  if (action.startsWith('DELETE') || action.includes('BLACKLIST') || action.includes('CANCEL')) return 'danger'
  if (action.startsWith('CREATE') || action.includes('APPROVE') || action.includes('PAY')) return 'success'
  if (action.includes('UPDATE') || action.includes('SET') || action.includes('SAVE') || action.includes('RESET')) return 'warning'
  return 'info'
}

function pretty(value) {
  if (value === null || value === undefined) return '—'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function cellText(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function diffRows(row) {
  const before = row.before_json || {}
  const after = row.after_json || {}
  if (typeof before !== 'object' || typeof after !== 'object') return []
  const keys = new Set([...Object.keys(before), ...Object.keys(after)])
  const result = []
  for (const key of keys) {
    const beforeText = cellText(before[key])
    const afterText = cellText(after[key])
    if (beforeText === afterText) continue
    result.push({ key, before: beforeText, after: afterText })
  }
  return result
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
      if (value !== '' && value !== null && value !== undefined) params[key] = value
    })
    if (dateRange.value && dateRange.value.length === 2) {
      params.start = dateRange.value[0]
      params.end = `${dateRange.value[1]} 23:59:59`
    }
    const data = await iamApi.auditLogs(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { action: '', target_type: '', user_id: null, keyword: '' }
  dateRange.value = []
  reload()
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

<style scoped>
.audit-detail {
  padding: 10px 16px 14px;
  background: #fafbfd;
}
.audit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.json-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.json-grid h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #475569;
}
.json-block {
  margin: 0;
  padding: 10px 12px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.diff-before {
  color: #b91c1c;
  text-decoration: line-through;
}
.diff-after {
  color: #15803d;
}
</style>

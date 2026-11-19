<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>预算管理</h2>
        <p>按「项目 + 成本科目 + 年度」维护预算；实际成本按有效成本记录累计，达到阈值自动预警。</p>
      </div>
      <el-button v-if="canBudget && filters.project_id" type="primary" :icon="Plus" @click="openCreate">新增预算</el-button>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.project_id" placeholder="请选择项目" filterable style="width: 280px" @change="load">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-date-picker
          v-model="filters.year"
          type="year"
          value-format="YYYY"
          placeholder="预算年度"
          style="width: 140px"
          @change="load"
        />
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>

      <div v-if="!filters.project_id" class="empty" style="padding: 60px 0">请选择项目查看预算执行情况</div>

      <template v-else>
        <div class="stat-grid" style="margin-bottom: 16px">
          <div class="stat-card">
            <div class="stat-label">年度预算总额</div>
            <div class="stat-value small"><money-text :value="status.total_budget" symbol /></div>
            <div class="stat-foot">{{ filters.year }} 年 · 共 {{ items.length }} 个科目</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">实际发生成本</div>
            <div class="stat-value small"><money-text :value="status.total_actual" symbol /></div>
            <div class="stat-foot">有效成本记录累计</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">整体执行率</div>
            <div class="stat-value" :style="{ color: rateColor(status.rate) }">{{ rawPercent((status.rate || 0) * 100) }}</div>
            <div class="stat-foot">{{ (status.rate || 0) > 1 ? '已超预算' : '预算使用进度' }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">预警科目</div>
            <div class="stat-value" :style="{ color: alertCount ? '#dc2626' : undefined }">{{ alertCount }}</div>
            <div class="stat-foot">达到预警阈值或已超预算</div>
          </div>
        </div>

        <el-alert
          v-if="alertCount"
          type="warning"
          :closable="false"
          style="margin-bottom: 14px"
          :title="`${alertCount} 个科目已达到预算预警阈值，请关注成本支出`"
        >
          <div v-for="row in alertRows" :key="row.account_code" style="font-size: 13px; padding: 3px 0">
            科目 {{ row.account_code }} {{ accountName(row.account_code) }}：预算
            <money-text :value="row.budget" />，实际 <money-text :value="row.actual" />，执行率 {{ rawPercent((row.rate || 0) * 100) }}
          </div>
        </el-alert>

        <el-table v-loading="loading" :data="mergedRows">
          <el-table-column label="科目" width="210">
            <template #default="{ row }">
              <span class="mono">{{ row.account_code }}</span>
              <span style="margin-left: 8px">{{ accountName(row.account_code) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="年度预算" width="160" align="right">
            <template #default="{ row }"><money-text :value="row.budget" symbol /></template>
          </el-table-column>
          <el-table-column label="实际成本" width="160" align="right">
            <template #default="{ row }"><money-text :value="row.actual" symbol /></template>
          </el-table-column>
          <el-table-column label="执行率" min-width="220">
            <template #default="{ row }">
              <div style="display: flex; align-items: center; gap: 10px">
                <el-progress
                  :percentage="Math.min(Number(row.rate || 0) * 100, 100)"
                  :stroke-width="9"
                  :status="Number(row.rate || 0) > 1 ? 'exception' : Number(row.rate || 0) >= 0.8 ? 'warning' : undefined"
                  style="flex: 1"
                />
                <span :class="['money', Number(row.rate || 0) > 1 ? 'negative' : '']" style="width: 62px; text-align: right">
                  {{ rawPercent((row.rate || 0) * 100) }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="Number(row.rate || 0) > 1" size="small" type="danger">超预算</el-tag>
              <el-tag v-else-if="row.alert" size="small" type="warning">预警</el-tag>
              <el-tag v-else-if="row.budget > 0" size="small" type="success">正常</el-tag>
              <span v-else class="muted">未设预算</span>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.remark || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <div v-if="canBudget" class="table-actions">
                <el-button link type="primary" @click="openEdit(row)">{{ row.id ? '调整' : '设置' }}</el-button>
                <el-button v-if="row.id" link type="danger" @click="remove(row)">删除</el-button>
              </div>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>

    <el-dialog v-model="editVisible" :title="form.id ? '调整预算' : '新增预算'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="成本科目" prop="account_code">
          <el-select v-model="form.account_code" filterable style="width: 100%" :disabled="Boolean(form.id)">
            <el-option v-for="account in budgetAccounts" :key="account.code" :label="`${account.code} ${account.name}`" :value="account.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="预算年度">{{ filters.year }} 年</el-form-item>
        <el-form-item label="预算金额" prop="amount">
          <el-input-number v-model="form.amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" maxlength="255" placeholder="预算说明" />
        </el-form-item>
        <el-alert
          v-if="form.id"
          type="info"
          :closable="false"
          :title="`当前实际成本 ${Number(form.actual || 0).toFixed(2)} 元，${Number(form.actual || 0) > Number(form.amount || 0) ? '新预算仍低于实际成本' : '预算充足'}`"
        />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存预算</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { financeApi } from '@/api'
import MoneyText from '@/components/MoneyText.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { rawPercent } from '@/utils/format'

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const status = ref({})
const filters = ref({ project_id: null, year: String(dayjs().year()) })

const canBudget = computed(() => auth.can('finance:budget'))
const budgetAccounts = computed(() =>
  (meta.accountOptions || []).filter((item) => item.type === 'COST' || item.type === 'EXPENSE')
)

const statusRows = computed(() => status.value.rows || [])
const mergedRows = computed(() => {
  const budgetMap = {}
  for (const item of items.value) budgetMap[item.account_code] = item
  const keys = new Set([...Object.keys(budgetMap), ...statusRows.value.map((row) => row.account_code)])
  return [...keys].sort().map((code) => {
    const item = budgetMap[code] || {}
    const stat = statusRows.value.find((row) => row.account_code === code) || {}
    return {
      id: item.id || null,
      account_code: code,
      budget: Number(item.amount || stat.budget || 0),
      actual: Number(stat.actual || 0),
      rate: Number(stat.rate || 0),
      alert: Boolean(stat.alert),
      remark: item.remark || '',
      version: item.version
    }
  })
})
const alertRows = computed(() => mergedRows.value.filter((row) => row.alert || Number(row.rate || 0) > 1))
const alertCount = computed(() => alertRows.value.length)

function accountName(code) {
  const account = (meta.accountOptions || []).find((item) => item.code === code)
  return account ? account.name : ''
}

function rateColor(rate) {
  const value = Number(rate || 0)
  if (value > 1) return '#dc2626'
  if (value >= 0.8) return '#f59e0b'
  return undefined
}

async function load() {
  if (!filters.value.project_id) return
  loading.value = true
  try {
    const data = await financeApi.budgets({ project_id: filters.value.project_id, year: Number(filters.value.year) })
    items.value = data.items || []
    status.value = { ...(data.status || {}), rows: data.rows || [] }
  } finally {
    loading.value = false
  }
}

const editVisible = ref(false)
const formRef = ref()
const form = ref({})

const rules = {
  account_code: [{ required: true, message: '请选择成本科目', trigger: 'change' }],
  amount: [{ required: true, message: '请输入预算金额', trigger: 'blur' }]
}

function openCreate() {
  form.value = { id: null, account_code: '', amount: 0, remark: '', version: null }
  editVisible.value = true
}

function openEdit(row) {
  form.value = {
    id: row.id,
    account_code: row.account_code,
    amount: row.budget,
    actual: row.actual,
    remark: row.remark,
    version: row.version
  }
  editVisible.value = true
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await financeApi.saveBudget({
      project_id: filters.value.project_id,
      account_code: form.value.account_code,
      year: Number(filters.value.year),
      amount: Number(form.value.amount || 0),
      remark: form.value.remark || null,
      version: form.value.id ? form.value.version : null
    })
    ElMessage.success('预算已保存')
    editVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除科目 ${row.account_code} 的年度预算吗？已发生实际成本时不可删除。`, '删除预算', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.deleteBudget(row.id)
  ElMessage.success('预算已删除')
  await load()
}

onMounted(async () => {
  await meta.ensure()
  if (meta.projectOptions.length) filters.value.project_id = meta.projectOptions[0].id
  await load()
})
</script>

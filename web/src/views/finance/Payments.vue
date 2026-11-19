<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>付款管理</h2>
        <p>付款单先登记后执行；执行付款时校验会计期间是否关账，并写入项目成本与现金流。</p>
      </div>
      <el-button v-if="canPay" type="primary" :icon="Plus" @click="openCreate">新建付款单</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">当前页待付款</div>
        <div class="stat-value">{{ pendingCount }}</div>
        <div class="stat-foot">金额 <money-text :value="pendingAmount" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前页已付款</div>
        <div class="stat-value">{{ paidCount }}</div>
        <div class="stat-foot">金额 <money-text :value="paidAmount" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">付款单总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前数据域内可见付款单</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已取消</div>
        <div class="stat-value">{{ canceledCount }}</div>
        <div class="stat-foot">取消后不写入成本</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable filterable style="width: 210px" @change="reload">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-model="filters.vendor_id" placeholder="全部供应商" clearable filterable style="width: 200px" @change="reload">
          <el-option v-for="vendor in meta.vendorOptions" :key="vendor.id" :label="vendor.name" :value="vendor.id" />
        </el-select>
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 140px" @change="reload">
          <el-option v-for="(label, value) in PAY_STATUS" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
        <el-button :icon="Search" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @row-click="openDetail">
        <el-table-column prop="no" label="付款单号" width="175" class-name="mono" />
        <el-table-column prop="project_name" label="项目" min-width="180" show-overflow-tooltip />
        <el-table-column prop="vendor_name" label="供应商" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.vendor_name || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="false" prop="contract_no" label="合同" width="150" />
        <el-table-column label="付款金额" width="150" align="right">
          <template #default="{ row }"><money-text :value="row.amount" symbol /></template>
        </el-table-column>
        <el-table-column label="付款方式" width="110">
          <template #default="{ row }">{{ labelOf(PAYMENT_METHODS, row.method) }}</template>
        </el-table-column>
        <el-table-column label="付款日期" width="112">
          <template #default="{ row }">{{ row.pay_date ? date(row.pay_date) : '-' }}</template>
        </el-table-column>
        <el-table-column prop="applicant_name" label="经办人" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" :labels="PAY_STATUS" /></template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click.stop="openDetail(row)">详情</el-button>
              <el-button v-if="canPay && row.status === 'PENDING'" link type="success" @click.stop="payNow(row)">执行</el-button>
              <el-button v-if="canPay && row.status === 'PENDING'" link type="danger" @click.stop="cancel(row)">取消</el-button>
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
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>

    <!-- 新建付款 -->
    <el-dialog v-model="createVisible" title="新建付款单" width="640px" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="付款类型">
          <el-radio-group v-model="form.mode">
            <el-radio value="VENDOR">供应商 / 合同付款</el-radio>
            <el-radio value="EXPENSE">报销单付款</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.mode === 'EXPENSE'">
          <el-form-item label="关联报销单" prop="expense_id">
            <el-select v-model="form.expense_id" filterable style="width: 100%" placeholder="选择已审批通过的报销单" @change="onExpenseChange">
              <el-option
                v-for="item in approvedExpenses"
                :key="item.id"
                :label="`${item.no}｜${item.payee || '-'}｜￥${Number(item.amount_total || 0).toFixed(2)}`"
                :value="item.id"
              />
            </el-select>
            <div class="form-tip">报销付款金额必须等于报销单金额，付款后仅回写报销单资金日期，不重复计入成本。</div>
          </el-form-item>
        </template>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="关联项目" prop="project_id">
              <el-select v-model="form.project_id" filterable style="width: 100%" placeholder="选择项目">
                <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="付款金额" prop="amount">
              <el-input-number
                v-model="form.amount"
                :min="0"
                :precision="2"
                :step="10000"
                controls-position="right"
                style="width: 100%"
                :disabled="form.mode === 'EXPENSE'"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <template v-if="form.mode === 'VENDOR'">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="供应商">
                <el-select v-model="form.vendor_id" filterable clearable style="width: 100%" placeholder="选择供应商" @change="onVendorChange">
                  <el-option
                    v-for="vendor in availableVendors"
                    :key="vendor.id"
                    :label="vendor.name"
                    :value="vendor.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="关联合同">
                <el-select v-model="form.contract_id" filterable clearable style="width: 100%" placeholder="可不关联合同" @change="onContractChange">
                  <el-option
                    v-for="contract in vendorContracts"
                    :key="contract.id"
                    :label="`${contract.no} ${contract.name}`"
                    :value="contract.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="成本科目">
            <el-select v-model="form.account_code" clearable placeholder="按供应商分类自动匹配" style="width: 100%">
              <el-option v-for="account in costAccounts" :key="account.code" :label="`${account.code} ${account.name}`" :value="account.code" />
            </el-select>
            <div class="form-tip">留空时按供应商分类自动映射：劳务分包 5401 / 材料供应 5402 / 技术服务 5403 / 设备租赁 5404。</div>
          </el-form-item>
        </template>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="付款日期">
              <el-date-picker v-model="form.pay_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="付款方式">
              <el-select v-model="form.method" style="width: 100%">
                <el-option v-for="(label, value) in PAYMENT_METHODS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-alert type="info" :closable="false" title="新建后付款单为「待付款」，需在列表中执行付款才会写入成本。" />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">创建付款单</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-drawer v-model="detailVisible" title="付款单详情" size="520px">
      <div v-loading="detailLoading">
        <div class="detail-hero" style="padding: 0 0 16px; border: none">
          <h2 style="font-size: 20px">{{ detail.no }}</h2>
          <div class="sub">
            <span>{{ detail.project_name }}</span>
            <span>{{ detail.vendor_name || '报销付款' }}</span>
          </div>
          <div class="tag-row" style="margin-top: 10px">
            <status-tag :value="detail.status" :labels="PAY_STATUS" />
            <span class="chip"><money-text :value="detail.amount" symbol /></span>
          </div>
        </div>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="付款单号"><span class="mono">{{ detail.no }}</span></el-descriptions-item>
          <el-descriptions-item label="项目">{{ detail.project_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="供应商">{{ detail.vendor_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="关联合同">{{ detail.contract_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="成本科目"><span class="mono">{{ detail.account_code }}</span></el-descriptions-item>
          <el-descriptions-item label="付款金额"><money-text :value="detail.amount" /></el-descriptions-item>
          <el-descriptions-item label="币种">{{ detail.currency }}</el-descriptions-item>
          <el-descriptions-item label="付款方式">{{ labelOf(PAYMENT_METHODS, detail.method) }}</el-descriptions-item>
          <el-descriptions-item label="付款日期">{{ detail.pay_date ? date(detail.pay_date) : '未付款' }}</el-descriptions-item>
          <el-descriptions-item label="经办人">{{ detail.applicant_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ datetime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.status === 'PENDING' && canPay" class="tag-row" style="margin-top: 18px">
          <el-button type="success" @click="payNow(detail)">执行付款</el-button>
          <el-button type="danger" plain @click="cancel(detail)">取消付款</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { expenseApi, financeApi } from '@/api'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date, datetime, today } from '@/utils/format'
import { labelOf, PAYMENT_METHODS } from '@/utils/constants'

const PAY_STATUS = { PENDING: '待付款', PAID: '已付款', CANCELED: '已取消' }

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ project_id: null, vendor_id: null, status: '' })

const canPay = computed(() => auth.can('finance:payment'))

const pendingCount = computed(() => rows.value.filter((item) => item.status === 'PENDING').length)
const paidCount = computed(() => rows.value.filter((item) => item.status === 'PAID').length)
const canceledCount = computed(() => rows.value.filter((item) => item.status === 'CANCELED').length)
const pendingAmount = computed(() =>
  rows.value.filter((item) => item.status === 'PENDING').reduce((sum, item) => sum + Number(item.amount || 0), 0)
)
const paidAmount = computed(() =>
  rows.value.filter((item) => item.status === 'PAID').reduce((sum, item) => sum + Number(item.amount || 0), 0)
)

const createVisible = ref(false)
const formRef = ref()
const form = ref(emptyForm())
const approvedExpenses = ref([])

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({})

const availableVendors = computed(() => (meta.vendorOptions || []).filter((item) => item.status !== 'BLACKLIST'))
const vendorContracts = computed(() => {
  const list = meta.contractOptions || []
  if (!form.value.vendor_id) return list
  return list.filter((item) => !item.vendor_id || item.vendor_id === form.value.vendor_id)
})
const costAccounts = computed(() => (meta.accountOptions || []).filter((item) => item.type === 'COST' || item.type === 'EXPENSE'))

const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  amount: [{ required: true, message: '请输入付款金额', trigger: 'blur' }],
  expense_id: [{ required: true, message: '请选择报销单', trigger: 'change' }]
}

function emptyForm() {
  return {
    mode: 'VENDOR',
    project_id: null,
    vendor_id: null,
    contract_id: null,
    expense_id: null,
    amount: 0,
    currency: 'CNY',
    pay_date: today(),
    method: 'BANK',
    account_code: '',
    remark: ''
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
      if (value !== '' && value !== null && value !== undefined) params[key] = value
    })
    const data = await financeApi.payments(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { project_id: null, vendor_id: null, status: '' }
  reload()
}

async function openCreate() {
  form.value = emptyForm()
  createVisible.value = true
  try {
    const data = await expenseApi.list({ page: 1, page_size: 100, status: 'APPROVED' })
    approvedExpenses.value = data.items || []
  } catch {
    approvedExpenses.value = []
  }
}

function onExpenseChange(expenseId) {
  const expense = approvedExpenses.value.find((item) => item.id === expenseId)
  if (!expense) return
  form.value.project_id = expense.project_id || null
  form.value.amount = Number(expense.amount_total || 0)
}

function onVendorChange(vendorId) {
  if (form.value.contract_id) {
    const contract = (meta.contractOptions || []).find((item) => item.id === form.value.contract_id)
    if (contract && contract.vendor_id && contract.vendor_id !== vendorId) form.value.contract_id = null
  }
}

function onContractChange(contractId) {
  const contract = (meta.contractOptions || []).find((item) => item.id === contractId)
  if (!contract) return
  if (contract.vendor_id) form.value.vendor_id = contract.vendor_id
  if (contract.project_id) form.value.project_id = contract.project_id
}

async function saveCreate() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!form.value.amount || Number(form.value.amount) <= 0) {
    ElMessage.warning('付款金额必须大于 0')
    return
  }
  if (form.value.mode === 'VENDOR' && !form.value.vendor_id && !form.value.contract_id) {
    ElMessage.warning('请选择供应商或合同')
    return
  }
  const payload = {
    project_id: form.value.project_id,
    vendor_id: form.value.mode === 'VENDOR' ? form.value.vendor_id || null : null,
    contract_id: form.value.mode === 'VENDOR' ? form.value.contract_id || null : null,
    expense_id: form.value.mode === 'EXPENSE' ? form.value.expense_id : null,
    amount: Number(form.value.amount),
    currency: form.value.currency,
    pay_date: form.value.pay_date || null,
    method: form.value.method,
    remark: form.value.remark || null
  }
  if (form.value.mode === 'VENDOR' && form.value.account_code) payload.account_code = form.value.account_code
  saving.value = true
  try {
    await financeApi.createPayment(payload)
    ElMessage.success('付款单已创建，请执行付款')
    createVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function payNow(row) {
  let payDate = row.pay_date || today()
  try {
    const result = await ElMessageBox.prompt('请输入付款日期', '执行付款', {
      inputValue: payDate,
      inputPattern: /^\d{4}-\d{2}-\d{2}$/,
      inputErrorMessage: '日期格式为 YYYY-MM-DD'
    })
    payDate = result.value
  } catch {
    return
  }
  await financeApi.payPayment(row.id, { pay_date: payDate })
  ElMessage.success('付款已完成并写入成本')
  detailVisible.value = false
  await load()
}

async function cancel(row) {
  try {
    await ElMessageBox.confirm(`确认取消付款单「${row.no}」吗？`, '取消付款', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.cancelPayment(row.id)
  ElMessage.success('付款单已取消')
  detailVisible.value = false
  await load()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await financeApi.payment(row.id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

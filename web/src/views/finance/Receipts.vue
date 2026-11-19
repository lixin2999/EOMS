<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>收款管理</h2>
        <p>按项目登记客户回款，收款实时写入银行存款科目并参与现金流；作废将生成冲销记录。</p>
      </div>
      <el-button v-if="canReceipt" type="primary" :icon="Plus" @click="openCreate">登记收款</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">当前页收款合计</div>
        <div class="stat-value small"><money-text :value="pageAmount" symbol /></div>
        <div class="stat-foot">有效收款单金额汇总</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">收款笔数</div>
        <div class="stat-value">{{ rows.length }}</div>
        <div class="stat-foot">当前页有效记录</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已作废</div>
        <div class="stat-value">{{ canceledCount }}</div>
        <div class="stat-foot">作废后自动冲销成本记录</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">收款总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前数据域内可见收款单</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable filterable style="width: 220px" @change="reload">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="收款开始"
          end-placeholder="收款结束"
          clearable
          style="width: 270px"
          @change="reload"
        />
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
        <el-button :icon="Search" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @row-click="openDetail">
        <el-table-column prop="no" label="收款单号" width="180" class-name="mono" />
        <el-table-column prop="project_name" label="项目" min-width="200" show-overflow-tooltip />
        <el-table-column label="客户" min-width="160">
          <template #default="{ row }">{{ customerName(row.customer_id) }}</template>
        </el-table-column>
        <el-table-column label="关联合同" width="150">
          <template #default="{ row }">{{ contractNo(row.contract_id) }}</template>
        </el-table-column>
        <el-table-column label="收款金额" width="160" align="right">
          <template #default="{ row }"><money-text :value="row.amount" symbol /></template>
        </el-table-column>
        <el-table-column label="收款日期" width="120">
          <template #default="{ row }">{{ date(row.receipt_date) }}</template>
        </el-table-column>
        <el-table-column label="收款方式" width="110">
          <template #default="{ row }">{{ labelOf(PAYMENT_METHODS, row.method) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" :labels="RECEIPT_STATUS" /></template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click.stop="openDetail(row)">详情</el-button>
              <el-button
                v-if="canReceipt && row.status === 'REGISTERED'"
                link
                type="danger"
                @click.stop="cancel(row)"
              >作废</el-button>
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

    <el-dialog v-model="createVisible" title="登记收款" width="600px" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="项目" prop="project_id">
          <el-select v-model="form.project_id" filterable style="width: 100%" placeholder="选择收款项目" @change="onProjectChange">
            <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="客户">
              <el-select v-model="form.customer_id" filterable clearable style="width: 100%" placeholder="默认项目客户">
                <el-option v-for="customer in customers" :key="customer.id" :label="customer.name" :value="customer.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联合同">
              <el-select v-model="form.contract_id" filterable clearable style="width: 100%" placeholder="可不关联">
                <el-option v-for="contract in meta.contractOptions" :key="contract.id" :label="`${contract.no} ${contract.name}`" :value="contract.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="收款金额" prop="amount">
              <el-input-number v-model="form.amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="收款日期">
              <el-date-picker v-model="form.receipt_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="收款方式">
              <el-select v-model="form.method" style="width: 100%">
                <el-option v-for="(label, value) in PAYMENT_METHODS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="币种">
              <el-input v-model="form.currency" maxlength="8" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-alert type="info" :closable="false" title="登记收款将实时写入 1002 银行存款并计入现金流量表；作废将生成冲销记录。" />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">确认登记</el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="收款单详情" size="480px">
      <div v-loading="detailLoading">
        <div class="detail-hero" style="padding: 0 0 16px; border: none">
          <h2 style="font-size: 20px">{{ detail.no }}</h2>
          <div class="sub"><span>{{ detail.project_name }}</span></div>
          <div class="tag-row" style="margin-top: 10px">
            <status-tag :value="detail.status" :labels="RECEIPT_STATUS" />
            <span class="chip"><money-text :value="detail.amount" symbol /></span>
          </div>
        </div>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="收款单号"><span class="mono">{{ detail.no }}</span></el-descriptions-item>
          <el-descriptions-item label="项目">{{ detail.project_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ customerName(detail.customer_id) }}</el-descriptions-item>
          <el-descriptions-item label="关联合同">{{ contractNo(detail.contract_id) }}</el-descriptions-item>
          <el-descriptions-item label="收款金额"><money-text :value="detail.amount" /></el-descriptions-item>
          <el-descriptions-item label="收款日期">{{ date(detail.receipt_date) }}</el-descriptions-item>
          <el-descriptions-item label="收款方式">{{ labelOf(PAYMENT_METHODS, detail.method) }}</el-descriptions-item>
          <el-descriptions-item label="币种">{{ detail.currency }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ datetime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.status === 'REGISTERED' && canReceipt" style="margin-top: 18px">
          <el-button type="danger" plain @click="cancel(detail)">作废收款</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { financeApi, iamApi } from '@/api'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date, datetime, today } from '@/utils/format'
import { labelOf, PAYMENT_METHODS } from '@/utils/constants'

const RECEIPT_STATUS = { REGISTERED: '已登记', CANCELED: '已作废' }

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ project_id: null })
const dateRange = ref([])
const customers = ref([])

const canReceipt = computed(() => auth.can('finance:receipt'))
const pageAmount = computed(() =>
  rows.value.filter((item) => item.status === 'REGISTERED').reduce((sum, item) => sum + Number(item.amount || 0), 0)
)
const canceledCount = computed(() => rows.value.filter((item) => item.status === 'CANCELED').length)

const createVisible = ref(false)
const formRef = ref()
const form = ref(emptyForm())

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({})

const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  amount: [{ required: true, message: '请输入收款金额', trigger: 'blur' }]
}

function emptyForm() {
  return {
    project_id: null,
    customer_id: null,
    contract_id: null,
    amount: 0,
    currency: 'CNY',
    receipt_date: today(),
    method: 'BANK',
    remark: ''
  }
}

function customerName(id) {
  if (!id) return '-'
  const item = customers.value.find((customer) => customer.id === id)
  return item ? item.name : `客户 #${id}`
}

function contractNo(id) {
  if (!id) return '-'
  const item = (meta.contractOptions || []).find((contract) => contract.id === id)
  return item ? item.no : `#${id}`
}

async function reload() {
  page.value = 1
  await load()
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filters.value.project_id) params.project_id = filters.value.project_id
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const data = await financeApi.receipts(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { project_id: null }
  dateRange.value = []
  reload()
}

async function loadCustomers() {
  try {
    customers.value = (await iamApi.customers()) || []
  } catch {
    customers.value = []
  }
}

async function openCreate() {
  form.value = emptyForm()
  createVisible.value = true
  if (!customers.value.length) await loadCustomers()
}

function onProjectChange(projectId) {
  const project = (meta.projectOptions || []).find((item) => item.id === projectId)
  if (project?.customer_id) form.value.customer_id = project.customer_id
}

async function saveCreate() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!form.value.amount || Number(form.value.amount) <= 0) {
    ElMessage.warning('收款金额必须大于 0')
    return
  }
  saving.value = true
  try {
    await financeApi.createReceipt({
      ...form.value,
      customer_id: form.value.customer_id || null,
      contract_id: form.value.contract_id || null,
      amount: Number(form.value.amount),
      receipt_date: form.value.receipt_date || null,
      remark: form.value.remark || null
    })
    ElMessage.success('收款已登记')
    createVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function cancel(row) {
  try {
    await ElMessageBox.confirm(`确认作废收款单「${row.no}」吗？作废后将生成冲销成本记录。`, '作废收款', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.cancelReceipt(row.id)
  ElMessage.success('收款已作废并冲销')
  detailVisible.value = false
  await load()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await financeApi.receipt(row.id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await Promise.allSettled([load(), loadCustomers()])
})
</script>

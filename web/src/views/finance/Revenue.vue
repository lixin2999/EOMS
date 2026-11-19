<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>计收确认</h2>
        <p>按完工进度或里程碑确认营收；确认后写入 6001 主营业务收入，取消时生成冲销记录。</p>
      </div>
      <el-button v-if="canRevenue" type="primary" :icon="Plus" @click="openCreate">新增计收</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">当前页已确认</div>
        <div class="stat-value small"><money-text :value="confirmedAmount" symbol /></div>
        <div class="stat-foot">已写入收入台账</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">待确认</div>
        <div class="stat-value">{{ draftCount }}</div>
        <div class="stat-foot">草稿计收不进入报表</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前页确认笔数</div>
        <div class="stat-value">{{ confirmedCount }}</div>
        <div class="stat-foot">含历史已确认记录</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">计收单总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前数据域内可见</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable filterable style="width: 220px" @change="reload">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-date-picker
          v-model="filters.period"
          type="month"
          value-format="YYYY-MM"
          placeholder="会计期间"
          clearable
          style="width: 150px"
          @change="reload"
        />
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 140px" @change="reload">
          <el-option v-for="(label, value) in REVENUE_STATUS" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
        <el-button :icon="Search" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @row-click="openDetail">
        <el-table-column prop="no" label="计收单号" width="180" class-name="mono" />
        <el-table-column prop="period" label="期间" width="92" class-name="mono" />
        <el-table-column prop="project_name" label="项目" min-width="200" show-overflow-tooltip />
        <el-table-column label="客户" min-width="150">
          <template #default="{ row }">{{ customerName(row.customer_id) }}</template>
        </el-table-column>
        <el-table-column label="计收金额" width="160" align="right">
          <template #default="{ row }"><money-text :value="row.amount" symbol /></template>
        </el-table-column>
        <el-table-column label="确认日期" width="120">
          <template #default="{ row }">{{ date(row.confirm_date) }}</template>
        </el-table-column>
        <el-table-column prop="source_type" label="来源" width="100">
          <template #default="{ row }">{{ row.source_type === 'MANUAL' ? '手工录入' : row.source_type }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" :labels="REVENUE_STATUS" /></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click.stop="openDetail(row)">详情</el-button>
              <el-button v-if="canRevenue && row.status === 'DRAFT'" link type="success" @click.stop="confirm(row)">确认</el-button>
              <el-button
                v-if="canRevenue && row.status !== 'CANCELED'"
                link
                type="danger"
                @click.stop="cancel(row)"
              >取消</el-button>
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

    <el-dialog v-model="createVisible" title="新增计收" width="600px" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="项目" prop="project_id">
          <el-select v-model="form.project_id" filterable style="width: 100%" placeholder="选择计收项目" @change="onProjectChange">
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
            <el-form-item label="计收金额" prop="amount">
              <el-input-number v-model="form.amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="确认日期">
              <el-date-picker v-model="form.confirm_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="确认方式">
          <el-radio-group v-model="form.confirm">
            <el-radio :value="true">保存并立即确认（写入收入）</el-radio>
            <el-radio :value="false">仅保存草稿</el-radio>
          </el-radio-group>
          <div class="form-tip">确认后会计入项目损益与营收报表；关闭期间不允许确认。</div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="1000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">保存计收</el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="计收单详情" size="480px">
      <div v-loading="detailLoading">
        <div class="detail-hero" style="padding: 0 0 16px; border: none">
          <h2 style="font-size: 20px">{{ detail.no }}</h2>
          <div class="sub"><span>{{ detail.project_name }}</span><span>期间 {{ detail.period }}</span></div>
          <div class="tag-row" style="margin-top: 10px">
            <status-tag :value="detail.status" :labels="REVENUE_STATUS" />
            <span class="chip"><money-text :value="detail.amount" symbol /></span>
          </div>
        </div>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="计收单号"><span class="mono">{{ detail.no }}</span></el-descriptions-item>
          <el-descriptions-item label="项目">{{ detail.project_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ customerName(detail.customer_id) }}</el-descriptions-item>
          <el-descriptions-item label="关联合同"><span v-if="detail.contract_id">{{ contractNo(detail.contract_id) }}</span><span v-else>-</span></el-descriptions-item>
          <el-descriptions-item label="计收金额"><money-text :value="detail.amount" /></el-descriptions-item>
          <el-descriptions-item label="确认日期">{{ date(detail.confirm_date) }}</el-descriptions-item>
          <el-descriptions-item label="会计期间">{{ detail.period }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ detail.source_type }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ datetime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="canRevenue && detail.status !== 'CANCELED'" class="tag-row" style="margin-top: 18px">
          <el-button v-if="detail.status === 'DRAFT'" type="success" @click="confirm(detail)">确认计收</el-button>
          <el-button type="danger" plain @click="cancel(detail)">取消计收</el-button>
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

const REVENUE_STATUS = { DRAFT: '草稿', CONFIRMED: '已确认', CANCELED: '已取消' }

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ project_id: null, period: '', status: '' })
const customers = ref([])

const canRevenue = computed(() => auth.can('finance:revenue'))
const confirmedAmount = computed(() =>
  rows.value.filter((item) => item.status === 'CONFIRMED').reduce((sum, item) => sum + Number(item.amount || 0), 0)
)
const confirmedCount = computed(() => rows.value.filter((item) => item.status === 'CONFIRMED').length)
const draftCount = computed(() => rows.value.filter((item) => item.status === 'DRAFT').length)

const createVisible = ref(false)
const formRef = ref()
const form = ref(emptyForm())

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref({})

const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  amount: [{ required: true, message: '请输入计收金额', trigger: 'blur' }]
}

function emptyForm() {
  return {
    project_id: null,
    customer_id: null,
    contract_id: null,
    amount: 0,
    currency: 'CNY',
    confirm_date: today(),
    confirm: true,
    remark: ''
  }
}

function customerName(id) {
  if (!id) return '-'
  const item = customers.value.find((customer) => customer.id === id)
  return item ? item.name : `客户 #${id}`
}

function contractNo(id) {
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
    Object.entries(filters.value).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) params[key] = value
    })
    const data = await financeApi.revenue(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { project_id: null, period: '', status: '' }
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
    ElMessage.warning('计收金额必须大于 0')
    return
  }
  saving.value = true
  try {
    await financeApi.createRevenue({
      ...form.value,
      customer_id: form.value.customer_id || null,
      contract_id: form.value.contract_id || null,
      amount: Number(form.value.amount),
      confirm_date: form.value.confirm_date || null,
      remark: form.value.remark || null
    })
    ElMessage.success(form.value.confirm ? '计收已创建并确认' : '计收草稿已保存')
    createVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function confirm(row) {
  try {
    await ElMessageBox.confirm(`确认计收「${row.no}」并写入收入台账吗？`, '确认计收', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.confirmRevenue(row.id)
  ElMessage.success('计收已确认')
  detailVisible.value = false
  await load()
}

async function cancel(row) {
  try {
    await ElMessageBox.confirm(`确认取消计收「${row.no}」吗？取消后将生成冲销记录。`, '取消计收', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.cancelRevenue(row.id)
  ElMessage.success('计收已取消并冲销')
  detailVisible.value = false
  await load()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await financeApi.revenueDetail(row.id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await Promise.allSettled([load(), loadCustomers()])
})
</script>

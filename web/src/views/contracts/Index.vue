<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>合同管理</h2>
        <p>供应商合同主档、付款条款、到期预警与超付风险统一管理；合同金额计入供应商支出分析。</p>
      </div>
      <el-button v-if="canManage" type="primary" :icon="Plus" @click="openCreate">新建合同</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">合同总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前数据域内可见合同</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">生效中</div>
        <div class="stat-value">{{ statusCount.ACTIVE || 0 }}</div>
        <div class="stat-foot">草稿 {{ statusCount.DRAFT || 0 }} · 已到期 {{ statusCount.EXPIRED || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前页合同额</div>
        <div class="stat-value small"><money-text :value="pageAmount" symbol /></div>
        <div class="stat-foot">按当前页合同金额汇总</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">到期 / 超付风险</div>
        <div class="stat-value" :style="{ color: risks.length ? '#f59e0b' : undefined }">{{ risks.length }}</div>
        <div class="stat-foot">45 天内到期或已超合同金额</div>
      </div>
    </div>

    <el-alert
      v-if="risks.length"
      type="warning"
      :closable="false"
      style="margin-bottom: 16px"
      :title="`存在 ${risks.length} 项合同风险，请及时处理`"
    >
      <div v-for="(item, index) in risks.slice(0, 5)" :key="index" class="risk-item" style="padding: 6px 0">
        <span class="risk-dot" :class="`level-${item.level}`" />
        <div style="flex: 1; font-size: 13px">
          {{ item.message }}
          <el-link type="primary" :underline="false" style="margin-left: 8px" @click="$router.push(`/contracts/${item.contract_id}`)">查看合同</el-link>
        </div>
      </div>
    </el-alert>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="(label, value) in CONTRACT_STATUS" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.vendor_id" placeholder="全部供应商" clearable filterable @change="reload">
          <el-option v-for="vendor in meta.vendorOptions" :key="vendor.id" :label="vendor.name" :value="vendor.id" />
        </el-select>
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable filterable @change="reload">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="合同名称 / 编号"
          clearable
          :prefix-icon="Search"
          style="width: 220px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-input-number v-model="filters.expiring_days" :min="0" :max="365" :step="15" placeholder="到期天数" controls-position="right" style="width: 140px" @change="reload" />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @row-click="goDetail">
        <el-table-column prop="no" label="合同编号" width="160" class-name="mono" />
        <el-table-column prop="name" label="合同名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }"><el-link type="primary" :underline="false">{{ row.name }}</el-link></template>
        </el-table-column>
        <el-table-column prop="vendor_name" label="供应商" min-width="180" show-overflow-tooltip />
        <el-table-column prop="project_name" label="关联项目" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.project_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="合同金额" width="150" align="right">
          <template #default="{ row }"><money-text :value="row.amount" symbol /></template>
        </el-table-column>
        <el-table-column label="签订日期" width="120">
          <template #default="{ row }">{{ date(row.sign_date) }}</template>
        </el-table-column>
        <el-table-column label="有效期" width="190">
          <template #default="{ row }"><span class="muted">{{ date(row.start_date) }} ~ {{ date(row.end_date) }}</span></template>
        </el-table-column>
        <el-table-column label="剩余天数" width="100" align="right">
          <template #default="{ row }">
            <span :class="['money', remainingDays(row) < 0 ? 'negative' : remainingDays(row) <= 45 ? 'negative' : '']">
              {{ row.end_date ? remainingDays(row) : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" :labels="CONTRACT_STATUS" /></template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click.stop="goDetail(row)">详情</el-button>
              <el-button v-if="canManage && row.status === 'DRAFT'" link type="success" @click.stop="activate(row)">生效</el-button>
              <el-button v-if="canManage && row.status !== 'TERMINATED'" link type="danger" @click.stop="terminate(row)">终止</el-button>
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

    <el-dialog v-model="createVisible" title="新建合同" width="820px" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="createRef" :model="form" :rules="rules" label-width="98px">
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="合同名称" prop="name">
              <el-input v-model="form.name" maxlength="255" placeholder="请输入合同名称" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="合同金额" prop="amount">
              <el-input-number v-model="form.amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="供应商" prop="vendor_id">
              <el-select v-model="form.vendor_id" filterable style="width: 100%" placeholder="选择供应商">
                <el-option
                  v-for="vendor in availableVendors"
                  :key="vendor.id"
                  :label="`${vendor.name}（${vendor.code || '-'}）`"
                  :value="vendor.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联项目">
              <el-select v-model="form.project_id" filterable clearable style="width: 100%" placeholder="可不关联项目">
                <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="签订日期">
              <el-date-picker v-model="form.sign_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="开始日期">
              <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="结束日期">
              <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="合同文本">
          <file-upload v-model="form.file_id" biz-type="CONTRACT" label="上传合同" />
        </el-form-item>
        <el-form-item label="付款条款">
          <div class="items-editor" style="width: 100%">
            <div class="toolbar" style="margin-bottom: 8px">
              <span class="muted">按付款节点拆分，比例合计建议为 100%。</span>
              <div class="grow" />
              <el-button size="small" :icon="Plus" @click="addTerm">添加条款</el-button>
            </div>
            <el-table :data="form.pay_terms" size="small" border>
              <el-table-column label="节点名称" min-width="150">
                <template #default="{ row }"><el-input v-model="row.name" maxlength="64" placeholder="如 预付款" /></template>
              </el-table-column>
              <el-table-column label="比例(%)" width="120">
                <template #default="{ row }"><el-input-number v-model="row.ratio" :min="0" :max="100" :precision="2" controls-position="right" style="width: 100%" @change="syncTermAmount(row)" /></template>
              </el-table-column>
              <el-table-column label="节点金额" width="150">
                <template #default="{ row }"><el-input-number v-model="row.amount" :min="0" :precision="2" controls-position="right" style="width: 100%" /></template>
              </el-table-column>
              <el-table-column label="约定付款日" width="150">
                <template #default="{ row }"><el-date-picker v-model="row.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></template>
              </el-table-column>
              <el-table-column label="备注" min-width="140">
                <template #default="{ row }"><el-input v-model="row.remark" maxlength="255" placeholder="备注" /></template>
              </el-table-column>
              <el-table-column label="操作" width="66">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="form.pay_terms.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!form.pay_terms.length" class="empty">暂无付款条款</div>
          </div>
        </el-form-item>
        <el-form-item label="合同备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-form-item label="创建后状态">
          <el-radio-group v-model="form.activate">
            <el-radio :value="false">保存为草稿</el-radio>
            <el-radio :value="true">直接生效</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">创建合同</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { contractApi } from '@/api'
import FileUpload from '@/components/FileUpload.vue'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date, today } from '@/utils/format'
import { CONTRACT_STATUS } from '@/utils/constants'

const router = useRouter()
const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ status: '', vendor_id: null, project_id: null, keyword: '', expiring_days: undefined })
const risks = ref([])

const createVisible = ref(false)
const createRef = ref()
const form = ref(emptyForm())

const canManage = computed(() => auth.can('contract:manage'))

const statusCount = computed(() => {
  const result = {}
  for (const row of rows.value) result[row.status] = (result[row.status] || 0) + 1
  return result
})
const pageAmount = computed(() => rows.value.reduce((sum, row) => sum + Number(row.amount || 0), 0))
const availableVendors = computed(() => (meta.vendorOptions || []).filter((item) => item.status !== 'BLACKLIST'))

const rules = {
  name: [{ required: true, message: '请输入合同名称', trigger: 'blur' }],
  vendor_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  amount: [{ required: true, message: '请输入合同金额', trigger: 'blur' }]
}

function emptyForm() {
  return {
    vendor_id: null,
    project_id: null,
    name: '',
    amount: 0,
    currency: 'CNY',
    sign_date: today(),
    start_date: today(),
    end_date: '',
    pay_terms: [],
    file_id: null,
    remark: '',
    activate: true
  }
}

function remainingDays(row) {
  if (!row.end_date) return 9999
  return dayjs(row.end_date).startOf('day').diff(dayjs().startOf('day'), 'day')
}

function goDetail(row) {
  router.push(`/contracts/${row.id}`)
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
    const data = await contractApi.list(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadRisks() {
  try {
    risks.value = (await contractApi.risks(45)) || []
  } catch {
    risks.value = []
  }
}

function reset() {
  filters.value = { status: '', vendor_id: null, project_id: null, keyword: '', expiring_days: undefined }
  reload()
}

function openCreate() {
  form.value = emptyForm()
  if (availableVendors.value.length === 1) form.value.vendor_id = availableVendors.value[0].id
  createVisible.value = true
}

function addTerm() {
  form.value.pay_terms.push({ name: '', ratio: 0, amount: 0, due_date: '', remark: '' })
}

function syncTermAmount(row) {
  row.amount = Number((Number(form.value.amount || 0) * Number(row.ratio || 0)) / 100)
}

async function saveCreate() {
  try {
    await createRef.value.validate()
  } catch {
    return
  }
  if (form.value.start_date && form.value.end_date && form.value.end_date < form.value.start_date) {
    ElMessage.warning('合同结束日期不能早于开始日期')
    return
  }
  const ratioSum = form.value.pay_terms.reduce((sum, item) => sum + Number(item.ratio || 0), 0)
  if (form.value.pay_terms.length && Math.round(ratioSum) !== 100) {
    try {
      await ElMessageBox.confirm(`付款条款比例合计为 ${ratioSum}%，是否继续保存？`, '付款条款提示', { type: 'warning' })
    } catch {
      return
    }
  }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      sign_date: form.value.sign_date || null,
      start_date: form.value.start_date || null,
      end_date: form.value.end_date || null,
      file_id: form.value.file_id || null,
      remark: form.value.remark || null,
      pay_terms: form.value.pay_terms.map((item) => ({
        name: item.name || '付款节点',
        ratio: Number(item.ratio || 0),
        amount: Number(item.amount || 0),
        due_date: item.due_date || '',
        remark: item.remark || ''
      }))
    }
    const data = await contractApi.create(payload)
    ElMessage.success('合同已创建')
    createVisible.value = false
    await Promise.all([load(), loadRisks()])
    if (data?.id) router.push(`/contracts/${data.id}`)
  } finally {
    saving.value = false
  }
}

async function activate(row) {
  try {
    await ElMessageBox.confirm(`确认将合同「${row.name}」置为生效中吗？`, '合同生效', { type: 'warning' })
  } catch {
    return
  }
  await contractApi.status(row.id, { status: 'ACTIVE' })
  ElMessage.success('合同已生效')
  await load()
}

async function terminate(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请输入终止原因（不少于 3 个字）', '终止合同', {
      type: 'warning',
      inputType: 'textarea',
      inputValidator: (value) => (value && value.trim().length >= 3 ? true : '请填写不少于 3 个字的原因')
    })
    reason = result.value
  } catch {
    return
  }
  await contractApi.status(row.id, { status: 'TERMINATED', reason: reason.trim() })
  ElMessage.success('合同已终止')
  await load()
}

onMounted(async () => {
  await meta.ensure()
  await Promise.allSettled([load(), loadRisks()])
})
</script>

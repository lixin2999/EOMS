<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>费用报销</h2>
        <p>报销审批通过后自动计入项目成本，付款后登记现金流出，审批与成本在同一事务内保持一致。</p>
      </div>
      <el-button v-if="auth.can('approval:expense')" type="primary" :icon="Plus" @click="openCreate">新建报销</el-button>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="status in ['DRAFT', 'RUNNING', 'REJECTED', 'APPROVED', 'VERIFIED', 'PAID', 'ARCHIVED', 'CANCELED']" :key="status" :label="STATUS_LABELS[status]" :value="status" />
        </el-select>
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable filterable @change="reload">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-model="filters.applicant_id" placeholder="全部申请人" clearable filterable @change="reload">
          <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 240px"
          @change="reload"
        />
        <el-input v-model="filters.keyword" placeholder="单号 / 备注 / 收款人" clearable :prefix-icon="Search" @keyup.enter="reload" @clear="reload" />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="default">
        <el-table-column prop="no" label="报销单号" width="170" class-name="mono" />
        <el-table-column prop="applicant_name" label="申请人" width="100" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ labelOf(EXPENSE_TYPES, row.type) }}</template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目" min-width="170" show-overflow-tooltip />
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }"><money-text :value="row.amount_total" symbol /></template>
        </el-table-column>
        <el-table-column prop="payee" label="收款人" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" /></template>
        </el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="{ row }">{{ datetime(row.submitted_at) }}</template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openDetail(row)">详情</el-button>
              <el-button v-if="canEdit(row)" link type="primary" @click="openEdit(row)">编辑</el-button>
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
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>

    <el-dialog v-model="formVisible" :title="editingId ? '编辑报销单' : '新建报销单'" width="760px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="92px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="所属项目" prop="project_id">
              <el-select v-model="form.project_id" filterable style="width: 100%" placeholder="选择项目">
                <el-option v-for="project in meta.projectOptions" :key="project.id" :label="`${project.no} ${project.name}`" :value="project.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="报销类型" prop="type">
              <el-select v-model="form.type" style="width: 100%">
                <el-option v-for="(label, value) in EXPENSE_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="币种">
              <el-select v-model="form.currency" style="width: 100%">
                <el-option label="CNY 人民币" value="CNY" />
                <el-option label="USD 美元" value="USD" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="费用明细" required>
          <div class="items-editor" style="width: 100%">
            <div v-for="(item, index) in form.items" :key="index" class="row">
              <el-select v-model="item.category" style="width: 130px" placeholder="类别">
                <el-option v-for="(label, value) in EXPENSE_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
              <el-date-picker v-model="item.occur_date" type="date" value-format="YYYY-MM-DD" placeholder="发生日期" style="width: 140px" />
              <el-input-number v-model="item.amount" :min="0.01" :precision="2" :step="100" controls-position="right" style="width: 140px" placeholder="金额" />
              <el-input v-model="item.description" placeholder="费用说明" maxlength="200" />
              <el-button :icon="Delete" circle plain type="danger" :disabled="form.items.length === 1" @click="form.items.splice(index, 1)" />
            </div>
            <el-button link type="primary" :icon="Plus" @click="addItem">添加明细</el-button>
            <div style="text-align: right; margin-top: 6px">
              合计：<money-text :value="formTotal" symbol style="font-size: 16px" />
            </div>
          </div>
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="收款人">
              <el-input v-model="form.payee" maxlength="64" placeholder="默认本人" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="发票附件">
              <file-upload v-model="invoiceFileId" biz-type="EXPENSE" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
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

    <el-drawer v-model="detailVisible" size="720px" :title="detail?.no || '报销单详情'" destroy-on-close>
      <div v-if="detail" v-loading="detailLoading">
        <div class="detail-hero" style="margin-bottom: 14px">
          <div>
            <h2><money-text :value="detail.amount_total" symbol /></h2>
            <div class="sub">
              <span>{{ labelOf(EXPENSE_TYPES, detail.type) }}</span>
              <span>{{ detail.project_name }}</span>
              <span>申请人：{{ detail.applicant_name }}</span>
            </div>
          </div>
          <status-tag :value="detail.status" />
        </div>

        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="单号">{{ detail.no }}</el-descriptions-item>
          <el-descriptions-item label="收款人">{{ detail.payee || '-' }}</el-descriptions-item>
          <el-descriptions-item label="币种">{{ detail.currency }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ datetime(detail.submitted_at) }}</el-descriptions-item>
          <el-descriptions-item label="复核时间">{{ datetime(detail.verified_at) }}</el-descriptions-item>
          <el-descriptions-item label="付款时间">{{ datetime(detail.paid_at) }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="3">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">费用明细</div>
        <el-table :data="detail.items || []" size="small" border>
          <el-table-column label="类别" width="120">
            <template #default="{ row }">{{ labelOf(EXPENSE_TYPES, row.category) }}</template>
          </el-table-column>
          <el-table-column label="发生日期" width="120">
            <template #default="{ row }">{{ date(row.occur_date) }}</template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="180" />
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }"><money-text :value="row.amount" /></template>
          </el-table-column>
        </el-table>

        <div class="section-title">发票附件</div>
        <div v-if="detail.invoices && detail.invoices.length" class="tag-row">
          <el-link v-for="file in detail.invoices" :key="file.id" type="primary" @click="downloadFile(file)">{{ file.name }}</el-link>
        </div>
        <div v-else class="muted" style="font-size: 13px">未上传发票</div>

        <div class="section-title">业务操作</div>
        <div class="tag-row">
          <el-button v-if="canEdit(detail)" size="small" @click="openEdit(detail)">编辑</el-button>
          <el-button v-if="canSubmit(detail)" size="small" type="success" @click="doAction(detail, 'submit')">提交审批</el-button>
          <el-button v-if="canWithdraw(detail)" size="small" type="warning" @click="doAction(detail, 'withdraw')">撤回审批</el-button>
          <el-button v-if="detail.status === 'DRAFT'" size="small" type="danger" plain @click="doAction(detail, 'cancel')">取消单据</el-button>
          <el-button v-if="detail.status === 'APPROVED' && auth.can('approval:expense')" size="small" type="primary" @click="doAction(detail, 'verify')">财务复核</el-button>
          <el-button v-if="detail.status === 'VERIFIED' && auth.can('finance:payment')" size="small" type="primary" @click="$router.push('/finance/payments')">前往付款</el-button>
          <el-button v-if="detail.status === 'PAID'" size="small" @click="doAction(detail, 'archive')">归档</el-button>
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
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { expenseApi, fileApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import FileUpload from '@/components/FileUpload.vue'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { date, datetime, today } from '@/utils/format'
import { EXPENSE_TYPES, STATUS_LABELS, labelOf } from '@/utils/constants'
import { saveBlob } from '@/utils/download'

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ status: '', project_id: null, applicant_id: null, keyword: '' })
const dateRange = ref([])

const formVisible = ref(false)
const formRef = ref()
const saving = ref(false)
const editingId = ref(null)
const editingVersion = ref(null)
const form = ref({ project_id: null, type: 'TRAVEL', currency: 'CNY', payee: '', remark: '', items: [] })
const invoiceFileId = ref(null)

const detailVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)

const formTotal = computed(() =>
  (form.value.items || []).reduce((sum, item) => sum + Number(item.amount || 0), 0)
)

const formRules = {
  project_id: [{ required: true, message: '请选择所属项目', trigger: 'change' }],
  type: [{ required: true, message: '请选择报销类型', trigger: 'change' }]
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

function addItem() {
  form.value.items.push({ category: form.value.type, amount: null, occur_date: today(), description: '' })
}

function defaultForm() {
  return {
    project_id: meta.projectOptions[0]?.id || null,
    type: 'TRAVEL',
    currency: 'CNY',
    payee: auth.user.real_name || '',
    remark: '',
    items: [{ category: 'TRAVEL', amount: null, occur_date: today(), description: '' }]
  }
}

function openCreate() {
  editingId.value = null
  editingVersion.value = null
  invoiceFileId.value = null
  form.value = defaultForm()
  formVisible.value = true
}

async function openEdit(row) {
  const data = row.items ? row : await expenseApi.detail(row.id)
  editingId.value = data.id
  editingVersion.value = data.version
  invoiceFileId.value = (data.invoices_file_ids || [])[0] || null
  form.value = {
    project_id: data.project_id,
    type: data.type,
    currency: data.currency,
    payee: data.payee || '',
    remark: data.remark || '',
    items: (data.items || data.items_json || []).map((item) => ({
      category: item.category,
      amount: Number(item.amount),
      occur_date: item.occur_date,
      description: item.description || ''
    }))
  }
  if (!form.value.items.length) addItem()
  formVisible.value = true
}

async function save(submit) {
  await formRef.value.validate()
  const items = form.value.items.filter((item) => Number(item.amount) > 0)
  if (!items.length) {
    ElMessage.warning('请至少填写一条金额大于 0 的明细')
    return
  }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      items,
      invoices_file_ids: invoiceFileId.value ? [invoiceFileId.value] : [],
      version: editingVersion.value
    }
    let saved
    if (editingId.value) saved = await expenseApi.update(editingId.value, payload)
    else saved = await expenseApi.create(payload)
    if (submit) {
      await expenseApi.submit(saved.id)
      ElMessage.success('报销单已提交审批')
    } else {
      ElMessage.success('报销单已保存')
    }
    formVisible.value = false
    await reload()
    if (detailVisible.value && detail.value?.id === saved.id) await loadDetail(saved.id)
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
    const params = {
      page: page.value,
      page_size: pageSize.value,
      ...Object.fromEntries(Object.entries(filters.value).filter(([, value]) => value !== '' && value !== null))
    }
    if (dateRange.value?.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const data = await expenseApi.list(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { status: '', project_id: null, applicant_id: null, keyword: '' }
  dateRange.value = []
  reload()
}

async function openDetail(row) {
  detailVisible.value = true
  await loadDetail(row.id)
}

async function loadDetail(id) {
  detailLoading.value = true
  try {
    detail.value = await expenseApi.detail(id)
  } finally {
    detailLoading.value = false
  }
}

async function onApprovalChanged() {
  await load()
  if (detail.value?.id) await loadDetail(detail.value.id)
}

async function doAction(row, action) {
  const labels = { submit: '提交审批', withdraw: '撤回审批', cancel: '取消单据', verify: '财务复核', archive: '归档' }
  try {
    await ElMessageBox.confirm(`确认${labels[action]}「${row.no}」吗？`, '操作确认', { type: 'warning' })
  } catch {
    return
  }
  await expenseApi[action](row.id)
  ElMessage.success(`${labels[action]}成功`)
  await load()
  if (detailVisible.value && detail.value?.id === row.id) await loadDetail(row.id)
}

async function downloadFile(file) {
  const response = await fileApi.download(file.id)
  saveBlob(response, file.name)
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

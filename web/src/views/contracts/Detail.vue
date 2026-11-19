<template>
  <div v-loading="loading" class="page">
    <div class="card">
      <div class="detail-hero">
        <div>
          <div class="tag-row" style="margin-bottom: 8px">
            <el-button link :icon="ArrowLeft" @click="$router.push('/contracts')">返回合同列表</el-button>
            <span class="mono muted">{{ contract.no }}</span>
          </div>
          <h2>{{ contract.name }}</h2>
          <div class="sub">
            <span>供应商：{{ contract.vendor_name || '-' }}</span>
            <span>项目：{{ contract.project_name || '未关联项目' }}</span>
            <span>签订：{{ date(contract.sign_date) }}</span>
            <span>有效期：{{ date(contract.start_date) }} ~ {{ date(contract.end_date) }}</span>
          </div>
          <div class="tag-row" style="margin-top: 10px">
            <status-tag :value="contract.status" :labels="CONTRACT_STATUS" />
            <span class="chip">合同额 <money-text :value="contract.amount" short /></span>
            <span class="chip success">已付比例 {{ rawPercent(contract.payment_ratio) }}</span>
            <span v-if="remainingDays < 0 && contract.status === 'ACTIVE'" class="chip danger">已过期 {{ Math.abs(remainingDays) }} 天</span>
            <span v-else-if="remainingDays <= 45 && contract.status === 'ACTIVE'" class="chip warn">剩余 {{ remainingDays }} 天到期</span>
          </div>
        </div>
        <div class="tag-row" style="justify-content: flex-end">
          <el-button v-if="canManage && contract.status === 'DRAFT'" type="success" @click="changeStatus('ACTIVE')">置为生效</el-button>
          <el-button v-if="canManage && contract.status === 'ACTIVE'" type="warning" plain @click="changeStatus('EXPIRED')">标记到期</el-button>
          <el-button v-if="canManage && contract.status !== 'TERMINATED'" type="danger" plain @click="terminate">终止合同</el-button>
          <el-button v-if="canManage" :icon="Edit" @click="openEdit">编辑</el-button>
          <el-button v-if="auth.can('finance:payment')" type="primary" :icon="Wallet" @click="openPayment">发起付款</el-button>
        </div>
      </div>
    </div>

    <div class="stat-grid" style="margin-top: 16px">
      <div class="stat-card">
        <div class="stat-label">合同金额</div>
        <div class="stat-value small"><money-text :value="contract.amount" symbol /></div>
        <div class="stat-foot">币种 {{ contract.currency || 'CNY' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已付款</div>
        <div class="stat-value small"><money-text :value="contract.paid_amount" symbol /></div>
        <div class="stat-foot">已付款比例 {{ rawPercent(contract.payment_ratio) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">未付款</div>
        <div class="stat-value small"><money-text :value="contract.unpaid_amount" symbol /></div>
        <div class="stat-foot" :style="{ color: Number(contract.unpaid_amount || 0) < 0 ? '#dc2626' : undefined }">
          {{ Number(contract.unpaid_amount || 0) < 0 ? '已超合同金额' : '剩余可付款额度' }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">付款记录</div>
        <div class="stat-value">{{ (contract.payments || []).length }}</div>
        <div class="stat-foot">待付款 {{ pendingPayments }} 笔 · 已付款 {{ paidPayments }} 笔</div>
      </div>
    </div>

    <div class="card tabs-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="合同信息" name="info">
          <div class="split-2">
            <div>
              <div class="section-title" style="margin-top: 0">基本信息</div>
              <div class="info-grid">
                <div class="info-item"><span class="label">合同编号</span><span class="value mono">{{ contract.no }}</span></div>
                <div class="info-item"><span class="label">合同名称</span><span class="value">{{ contract.name }}</span></div>
                <div class="info-item"><span class="label">供应商</span><span class="value">{{ contract.vendor_name || '-' }}</span></div>
                <div class="info-item"><span class="label">关联项目</span><span class="value">{{ contract.project_name || '-' }}</span></div>
                <div class="info-item"><span class="label">合同金额</span><span class="value"><money-text :value="contract.amount" /></span></div>
                <div class="info-item"><span class="label">币种</span><span class="value">{{ contract.currency }}</span></div>
                <div class="info-item"><span class="label">签订日期</span><span class="value">{{ date(contract.sign_date) }}</span></div>
                <div class="info-item"><span class="label">开始日期</span><span class="value">{{ date(contract.start_date) }}</span></div>
                <div class="info-item"><span class="label">结束日期</span><span class="value">{{ date(contract.end_date) }}</span></div>
                <div class="info-item"><span class="label">合同状态</span><span class="value">{{ labelOf(CONTRACT_STATUS, contract.status) }}</span></div>
                <div class="info-item"><span class="label">创建时间</span><span class="value">{{ datetime(contract.created_at) }}</span></div>
                <div class="info-item"><span class="label">版本号</span><span class="value">{{ contract.version }}</span></div>
              </div>
              <div class="section-title">合同备注</div>
              <div class="desc-block">{{ contract.remark || '暂无备注' }}</div>
            </div>
            <div>
              <div class="section-title" style="margin-top: 0">合同文本</div>
              <div class="card" style="margin: 0">
                <div v-if="contract.file?.id" class="tag-row">
                  <el-link type="primary" :underline="false" @click="downloadFile(contract.file)">{{ contract.file.name }}</el-link>
                  <span class="muted">{{ fileSize(contract.file.size) }}</span>
                </div>
                <div v-else class="empty">未上传合同文本</div>
              </div>
              <div class="section-title">付款进度</div>
              <div class="card" style="margin: 0">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px">
                  <strong>已付 / 合同额</strong>
                  <span>{{ rawPercent(contract.payment_ratio) }}</span>
                </div>
                <el-progress
                  :percentage="Math.min(Number(contract.payment_ratio || 0), 100)"
                  :stroke-width="10"
                  :status="Number(contract.payment_ratio || 0) > 100 ? 'exception' : undefined"
                />
                <el-descriptions :column="1" border size="small" style="margin-top: 16px">
                  <el-descriptions-item label="合同金额"><money-text :value="contract.amount" /></el-descriptions-item>
                  <el-descriptions-item label="累计已付"><money-text :value="contract.paid_amount" /></el-descriptions-item>
                  <el-descriptions-item label="未付金额"><money-text :value="contract.unpaid_amount" colorize /></el-descriptions-item>
                  <el-descriptions-item label="付款条款">{{ (contract.pay_terms_json || []).length }} 个节点</el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`付款条款（${(contract.pay_terms_json || []).length}）`" name="terms">
          <el-table :data="contract.pay_terms_json || []" size="small" border>
            <el-table-column label="节点名称" min-width="180">
              <template #default="{ row }">{{ row.name || row.phase || '-' }}</template>
            </el-table-column>
            <el-table-column label="比例" width="110" align="right">
              <template #default="{ row }">{{ row.ratio !== undefined ? `${Number(row.ratio || 0).toFixed(2)}%` : '-' }}</template>
            </el-table-column>
            <el-table-column label="节点金额" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.amount" /></template>
            </el-table-column>
            <el-table-column label="约定付款日" width="130">
              <template #default="{ row }">{{ row.due_date ? date(row.due_date) : row.days ? `${row.days} 天内` : '-' }}</template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`付款记录（${(contract.payments || []).length}）`" name="payments">
          <div class="toolbar">
            <span class="muted">仅「已付款」记录计入合同已付金额与项目成本。</span>
            <div class="grow" />
            <el-button v-if="auth.can('finance:payment')" type="primary" :icon="Plus" @click="openPayment">发起付款</el-button>
          </div>
          <el-table :data="contract.payments || []" size="small" border>
            <el-table-column prop="no" label="付款单号" width="170" class-name="mono" />
            <el-table-column label="付款金额" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.amount" /></template>
            </el-table-column>
            <el-table-column label="付款日期" width="120">
              <template #default="{ row }">{{ date(row.pay_date) }}</template>
            </el-table-column>
            <el-table-column label="付款方式" width="110">
              <template #default="{ row }">{{ labelOf(PAYMENT_METHODS, row.method) }}</template>
            </el-table-column>
            <el-table-column prop="account_code" label="成本科目" width="110" class-name="mono" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><status-tag :value="row.status" /></template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-button v-if="row.status === 'PENDING' && auth.can('finance:payment')" link type="success" @click="payNow(row)">执行付款</el-button>
                <el-button v-if="row.status === 'PENDING' && auth.can('finance:payment')" link type="danger" @click="cancelPayment(row)">取消</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="editVisible" title="编辑合同" width="760px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="98px">
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="合同名称" required><el-input v-model="editForm.name" maxlength="255" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="合同金额" required>
              <el-input-number v-model="editForm.amount" :min="0" :precision="2" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="关联项目">
              <el-select v-model="editForm.project_id" filterable clearable style="width: 100%">
                <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同文本">
              <file-upload v-model="editForm.file_id" biz-type="CONTRACT" :biz-id="contractId" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="签订日期"><el-date-picker v-model="editForm.sign_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="开始日期"><el-date-picker v-model="editForm.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="结束日期"><el-date-picker v-model="editForm.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="付款条款">
          <div class="items-editor" style="width: 100%">
            <div class="toolbar" style="margin-bottom: 8px">
              <div class="grow" />
              <el-button size="small" :icon="Plus" @click="addEditTerm">添加条款</el-button>
            </div>
            <el-table :data="editForm.pay_terms" size="small" border>
              <el-table-column label="节点名称" min-width="150">
                <template #default="{ row }"><el-input v-model="row.name" maxlength="64" /></template>
              </el-table-column>
              <el-table-column label="比例(%)" width="120">
                <template #default="{ row }"><el-input-number v-model="row.ratio" :min="0" :max="100" :precision="2" controls-position="right" style="width: 100%" /></template>
              </el-table-column>
              <el-table-column label="节点金额" width="150">
                <template #default="{ row }"><el-input-number v-model="row.amount" :min="0" :precision="2" controls-position="right" style="width: 100%" /></template>
              </el-table-column>
              <el-table-column label="约定付款日" width="150">
                <template #default="{ row }"><el-date-picker v-model="row.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></template>
              </el-table-column>
              <el-table-column label="操作" width="66">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="editForm.pay_terms.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-form-item>
        <el-form-item label="合同备注"><el-input v-model="editForm.remark" type="textarea" :rows="3" maxlength="1000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="paymentVisible" title="发起合同付款" width="560px">
      <el-form :model="paymentForm" label-width="98px">
        <el-form-item label="关联项目" required>
          <el-select v-model="paymentForm.project_id" filterable style="width: 100%">
            <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="付款金额" required>
          <el-input-number v-model="paymentForm.amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="付款日期"><el-date-picker v-model="paymentForm.pay_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="付款方式">
              <el-select v-model="paymentForm.method" style="width: 100%">
                <el-option v-for="(label, value) in PAYMENT_METHODS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="成本科目">
          <el-select v-model="paymentForm.account_code" clearable placeholder="按供应商分类自动匹配" style="width: 100%">
            <el-option v-for="account in meta.accountOptions" :key="account.code" :label="`${account.code} ${account.name}`" :value="account.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="paymentForm.remark" type="textarea" :rows="2" maxlength="1000" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="paymentVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="savePayment">创建付款单</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Edit, Plus, Wallet } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { contractApi, fileApi, financeApi } from '@/api'
import FileUpload from '@/components/FileUpload.vue'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date, datetime, rawPercent, today } from '@/utils/format'
import { CONTRACT_STATUS, labelOf, PAYMENT_METHODS } from '@/utils/constants'
import { saveBlob } from '@/utils/download'

const route = useRoute()
const auth = useAuthStore()
const meta = useMetaStore()
const contractId = computed(() => Number(route.params.id))

const loading = ref(false)
const saving = ref(false)
const activeTab = ref('info')
const contract = ref({})

const canManage = computed(() => auth.can('contract:manage'))
const pendingPayments = computed(() => (contract.value.payments || []).filter((item) => item.status === 'PENDING').length)
const paidPayments = computed(() => (contract.value.payments || []).filter((item) => item.status === 'PAID').length)
const remainingDays = computed(() => {
  if (!contract.value.end_date) return 9999
  return dayjs(contract.value.end_date).startOf('day').diff(dayjs().startOf('day'), 'day')
})

async function load() {
  loading.value = true
  try {
    contract.value = await contractApi.detail(contractId.value)
  } finally {
    loading.value = false
  }
}

function fileSize(size) {
  const value = Number(size || 0)
  if (!value) return ''
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

/* ---------------------------------------------------------------- 状态 */
async function changeStatus(status) {
  const labels = { ACTIVE: '将合同置为生效中', EXPIRED: '将合同标记为已到期' }
  try {
    await ElMessageBox.confirm(`确认${labels[status]}吗？`, '合同状态', { type: 'warning' })
  } catch {
    return
  }
  await contractApi.status(contractId.value, { status })
  ElMessage.success('合同状态已更新')
  await load()
}

async function terminate() {
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
  await contractApi.status(contractId.value, { status: 'TERMINATED', reason: reason.trim() })
  ElMessage.success('合同已终止')
  await load()
}

/* ---------------------------------------------------------------- 编辑 */
const editVisible = ref(false)
const editForm = ref({})

function openEdit() {
  editForm.value = {
    vendor_id: contract.value.vendor_id,
    project_id: contract.value.project_id,
    name: contract.value.name,
    amount: Number(contract.value.amount || 0),
    currency: contract.value.currency || 'CNY',
    sign_date: contract.value.sign_date,
    start_date: contract.value.start_date,
    end_date: contract.value.end_date,
    file_id: contract.value.file_id,
    remark: contract.value.remark || '',
    version: contract.value.version,
    pay_terms: (contract.value.pay_terms_json || []).map((item) => ({
      name: item.name || item.phase || '',
      ratio: Number(item.ratio || 0),
      amount: Number(item.amount || 0),
      due_date: item.due_date || '',
      remark: item.remark || ''
    }))
  }
  editVisible.value = true
}

function addEditTerm() {
  editForm.value.pay_terms.push({ name: '', ratio: 0, amount: 0, due_date: '', remark: '' })
}

async function saveEdit() {
  if (!editForm.value.name) {
    ElMessage.warning('请输入合同名称')
    return
  }
  saving.value = true
  try {
    await contractApi.update(contractId.value, {
      ...editForm.value,
      sign_date: editForm.value.sign_date || null,
      start_date: editForm.value.start_date || null,
      end_date: editForm.value.end_date || null,
      file_id: editForm.value.file_id || null
    })
    ElMessage.success('合同已更新')
    editVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 付款 */
const paymentVisible = ref(false)
const paymentForm = ref({})

function openPayment() {
  paymentForm.value = {
    project_id: contract.value.project_id || null,
    vendor_id: contract.value.vendor_id,
    contract_id: contractId.value,
    amount: Math.max(Number(contract.value.unpaid_amount || 0), 0),
    currency: contract.value.currency || 'CNY',
    pay_date: today(),
    method: 'BANK',
    account_code: '5401',
    remark: ''
  }
  paymentVisible.value = true
}

async function savePayment() {
  if (!paymentForm.value.project_id) {
    ElMessage.warning('请选择关联项目')
    return
  }
  if (!paymentForm.value.amount || Number(paymentForm.value.amount) <= 0) {
    ElMessage.warning('付款金额必须大于 0')
    return
  }
  saving.value = true
  try {
    await financeApi.createPayment(paymentForm.value)
    ElMessage.success('付款单已创建，请前往付款管理执行付款')
    paymentVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function payNow(row) {
  try {
    await ElMessageBox.confirm(`确认执行付款「${row.no}」吗？执行后将写入项目成本。`, '执行付款', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.payPayment(row.id, { pay_date: today() })
  ElMessage.success('付款已完成')
  await load()
}

async function cancelPayment(row) {
  try {
    await ElMessageBox.confirm(`确认取消付款单「${row.no}」吗？`, '取消付款', { type: 'warning' })
  } catch {
    return
  }
  await financeApi.cancelPayment(row.id)
  ElMessage.success('付款单已取消')
  await load()
}

async function downloadFile(file) {
  const response = await fileApi.download(file.id)
  saveBlob(response, file.name || `contract-${contractId.value}`)
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

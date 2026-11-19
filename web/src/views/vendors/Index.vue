<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>供应商管理</h2>
        <p>覆盖供应商准入、资质、账户、合作项目与年度评价；黑名单供应商禁止发生付款。</p>
      </div>
      <el-button v-if="auth.can('vendor:create')" type="primary" :icon="Plus" @click="openCreate">新建供应商</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">供应商总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前数据域内可见供应商</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">合作中</div>
        <div class="stat-value">{{ statusCount.ACTIVE || 0 }}</div>
        <div class="stat-foot">待准入 {{ statusCount.PENDING || 0 }} · 暂停 {{ statusCount.SUSPENDED || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">黑名单</div>
        <div class="stat-value" :style="{ color: (statusCount.BLACKLIST || 0) > 0 ? '#dc2626' : undefined }">
          {{ statusCount.BLACKLIST || 0 }}
        </div>
        <div class="stat-foot">黑名单供应商将阻断付款</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">资质 / 合同风险</div>
        <div class="stat-value" :style="{ color: risks.length ? '#f59e0b' : undefined }">{{ risks.length }}</div>
        <div class="stat-foot">30 天内到期或已超付</div>
      </div>
    </div>

    <el-alert
      v-if="risks.length"
      type="warning"
      :closable="false"
      style="margin-bottom: 16px"
      :title="`存在 ${risks.length} 项供应商风险，请及时处理`"
    >
      <div v-for="(item, index) in risks.slice(0, 4)" :key="index" class="risk-item" style="padding: 6px 0">
        <span class="risk-dot" :class="`level-${item.level}`" />
        <div style="flex: 1; font-size: 13px">
          {{ item.title || item.message }}
          <el-link type="primary" :underline="false" style="margin-left: 8px" @click="goDetailById(item.vendor_id)">查看供应商</el-link>
        </div>
      </div>
    </el-alert>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="(label, value) in VENDOR_STATUS" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.vendor_type" placeholder="全部分类" clearable @change="reload">
          <el-option v-for="(label, value) in VENDOR_TYPES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.level" placeholder="全部等级" clearable @change="reload">
          <el-option v-for="(label, value) in VENDOR_LEVELS" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="供应商名称 / 编号"
          clearable
          :prefix-icon="Search"
          style="width: 220px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @row-click="goDetail">
        <el-table-column prop="code" label="供应商编号" width="150" class-name="mono" />
        <el-table-column prop="name" label="供应商名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="110">
          <template #default="{ row }">{{ labelOf(VENDOR_TYPES, row.type) }}</template>
        </el-table-column>
        <el-table-column label="等级" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.level" size="small" :type="levelType(row.level)" effect="plain">{{ row.level }} 级</el-tag>
            <span v-else class="muted">未评级</span>
          </template>
        </el-table-column>
        <el-table-column label="综合评分" width="112" align="right">
          <template #default="{ row }">
            <span :class="['money', Number(row.score || 0) >= 85 ? 'positive' : Number(row.score || 0) < 60 ? 'negative' : '']">
              {{ Number(row.score || 0).toFixed(1) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="负责人" width="110" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" :labels="VENDOR_STATUS" /></template>
        </el-table-column>
        <el-table-column prop="intro" label="简介" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click.stop="goDetail(row)">详情</el-button>
              <el-button
                v-if="auth.can('vendor:manage') && row.status !== 'BLACKLIST' && row.status !== 'ACTIVE'"
                link
                type="success"
                @click.stop="submitVendor(row)"
              >提交准入</el-button>
              <el-button
                v-if="auth.can('vendor:manage') && row.status !== 'BLACKLIST'"
                link
                type="danger"
                @click.stop="openBlacklist(row)"
              >拉黑</el-button>
              <el-button
                v-if="auth.can('vendor:manage') && row.status === 'BLACKLIST'"
                link
                type="warning"
                @click.stop="restoreVendor(row)"
              >恢复</el-button>
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

    <el-dialog v-model="createVisible" title="新建供应商" width="860px" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="createRef" :model="form" :rules="rules" label-width="98px">
        <el-tabs v-model="createTab">
          <el-tab-pane label="基本信息" name="base">
            <el-row :gutter="12">
              <el-col :span="16">
                <el-form-item label="供应商名称" prop="name">
                  <el-input v-model="form.name" maxlength="255" placeholder="请输入营业执照名称" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="供应商分类">
                  <el-select v-model="form.type" style="width: 100%">
                    <el-option v-for="(label, value) in VENDOR_TYPES" :key="value" :label="label" :value="value" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="纳税人识别号">
                  <el-input v-model="form.tax_no" maxlength="64" placeholder="统一社会信用代码" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="负责人">
                  <el-select v-model="form.owner_user_id" filterable style="width: 100%">
                    <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="供应商简介">
              <el-input v-model="form.intro" type="textarea" :rows="3" maxlength="2000" show-word-limit />
            </el-form-item>
            <el-form-item label="准入方式">
              <el-radio-group v-model="form.submit">
                <el-radio :value="true">创建并提交准入审批</el-radio>
                <el-radio :value="false">仅保存草稿（状态待准入）</el-radio>
              </el-radio-group>
              <div class="form-tip">准入审批通过后供应商状态变更为合作中，方可建立合同与付款。</div>
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane :label="`联系人（${form.contacts.length}）`" name="contacts">
            <div class="toolbar">
              <span class="muted">至少填写一个业务联系人，默认联系人用于合同与付款通知。</span>
              <div class="grow" />
              <el-button size="small" :icon="Plus" @click="addRow('contacts')">添加联系人</el-button>
            </div>
            <el-table :data="form.contacts" size="small" border>
              <el-table-column label="姓名" width="130">
                <template #default="{ row }"><el-input v-model="row.name" maxlength="64" placeholder="姓名" /></template>
              </el-table-column>
              <el-table-column label="职务" width="130">
                <template #default="{ row }"><el-input v-model="row.title" maxlength="64" placeholder="职务" /></template>
              </el-table-column>
              <el-table-column label="手机号" width="150">
                <template #default="{ row }"><el-input v-model="row.phone" maxlength="20" placeholder="手机号" /></template>
              </el-table-column>
              <el-table-column label="邮箱" min-width="170">
                <template #default="{ row }"><el-input v-model="row.email" maxlength="128" placeholder="邮箱" /></template>
              </el-table-column>
              <el-table-column label="默认" width="70" align="center">
                <template #default="{ row }"><el-radio v-model="defaultContact" :value="row" /></template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="form.contacts.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!form.contacts.length" class="empty">暂无联系人</div>
          </el-tab-pane>

          <el-tab-pane :label="`银行账户（${form.banks.length}）`" name="banks">
            <div class="toolbar">
              <span class="muted">银行账号将加密存储，无敏感权限用户仅可查看脱敏账号。</span>
              <div class="grow" />
              <el-button size="small" :icon="Plus" @click="addRow('banks')">添加账户</el-button>
            </div>
            <el-table :data="form.banks" size="small" border>
              <el-table-column label="开户行" min-width="170">
                <template #default="{ row }"><el-input v-model="row.bank_name" maxlength="128" placeholder="开户银行" /></template>
              </el-table-column>
              <el-table-column label="账号" width="200">
                <template #default="{ row }"><el-input v-model="row.account_no" maxlength="64" placeholder="银行账号" /></template>
              </el-table-column>
              <el-table-column label="账户名称" min-width="150">
                <template #default="{ row }"><el-input v-model="row.account_name" maxlength="128" placeholder="账户名称" /></template>
              </el-table-column>
              <el-table-column label="默认" width="70" align="center">
                <template #default="{ row }"><el-radio v-model="defaultBank" :value="row" /></template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="form.banks.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!form.banks.length" class="empty">暂无银行账户</div>
          </el-tab-pane>

          <el-tab-pane :label="`资质证照（${form.licenses.length}）`" name="licenses">
            <div class="toolbar">
              <span class="muted">资质到期前 30 天将进入风险提醒；请上传扫描件。</span>
              <div class="grow" />
              <el-button size="small" :icon="Plus" @click="addRow('licenses')">添加资质</el-button>
            </div>
            <el-table :data="form.licenses" size="small" border>
              <el-table-column label="证照名称" min-width="170">
                <template #default="{ row }"><el-input v-model="row.name" maxlength="128" placeholder="如 安全生产许可证" /></template>
              </el-table-column>
              <el-table-column label="证照编号" width="160">
                <template #default="{ row }"><el-input v-model="row.no" maxlength="64" placeholder="编号" /></template>
              </el-table-column>
              <el-table-column label="有效期起" width="135">
                <template #default="{ row }">
                  <el-date-picker v-model="row.valid_from" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
                </template>
              </el-table-column>
              <el-table-column label="有效期止" width="135">
                <template #default="{ row }">
                  <el-date-picker v-model="row.valid_to" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
                </template>
              </el-table-column>
              <el-table-column label="扫描件" min-width="180">
                <template #default="{ row }">
                  <file-upload v-model="row.file_id" biz-type="VENDOR" label="上传" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="form.licenses.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!form.licenses.length" class="empty">暂未上传资质证照</div>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">创建供应商</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="blacklistVisible" title="加入黑名单" width="480px">
      <el-alert type="error" :closable="false" title="加入黑名单后该供应商禁止新增付款，且不可修改主档。" />
      <el-form style="margin-top: 14px" label-width="90px">
        <el-form-item label="拉黑原因" required>
          <el-input v-model="blacklistReason" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="不少于 3 个字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="blacklistVisible = false">取消</el-button>
          <el-button type="danger" :loading="saving" @click="confirmBlacklist">确认拉黑</el-button>
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
import { vendorApi } from '@/api'
import FileUpload from '@/components/FileUpload.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { labelOf, VENDOR_LEVELS, VENDOR_STATUS, VENDOR_TYPES } from '@/utils/constants'

const router = useRouter()
const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ status: '', vendor_type: '', level: '', keyword: '' })
const risks = ref([])

const createVisible = ref(false)
const createTab = ref('base')
const createRef = ref()
const form = ref(emptyForm())
const defaultContact = ref(null)
const defaultBank = ref(null)

const blacklistVisible = ref(false)
const blacklistTarget = ref(null)
const blacklistReason = ref('')

const rules = {
  name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }]
}

const statusCount = computed(() => {
  const result = {}
  for (const row of rows.value) result[row.status] = (result[row.status] || 0) + 1
  return result
})

function emptyForm() {
  return {
    name: '',
    type: 'SERVICE',
    tax_no: '',
    owner_user_id: null,
    intro: '',
    submit: true,
    contacts: [],
    banks: [],
    licenses: []
  }
}

function goDetail(row) {
  router.push(`/vendors/${row.id}`)
}

function goDetailById(id) {
  if (id) router.push(`/vendors/${id}`)
}

function levelType(level) {
  if (level === 'A') return 'success'
  if (level === 'B') return ''
  return 'warning'
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
      if (value) params[key] = value
    })
    const data = await vendorApi.list(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadRisks() {
  try {
    risks.value = (await vendorApi.risks()) || []
  } catch {
    risks.value = []
  }
}

function reset() {
  filters.value = { status: '', vendor_type: '', level: '', keyword: '' }
  reload()
}

function openCreate() {
  form.value = emptyForm()
  form.value.owner_user_id = auth.user.id
  defaultContact.value = null
  defaultBank.value = null
  createTab.value = 'base'
  createVisible.value = true
}

function addRow(kind) {
  if (kind === 'contacts') {
    const row = { name: '', title: '', phone: '', email: '', is_default: false }
    form.value.contacts.push(row)
    if (!defaultContact.value) setDefaultContact(row)
  } else if (kind === 'banks') {
    const row = { bank_name: '', account_no: '', account_name: '', is_default: false }
    form.value.banks.push(row)
    if (!defaultBank.value) setDefaultBank(row)
  } else {
    form.value.licenses.push({ name: '', no: '', file_id: null, valid_from: '', valid_to: '' })
  }
}

function setDefaultContact(row) {
  defaultContact.value = row
  form.value.contacts.forEach((item) => (item.is_default = item === row))
}

function setDefaultBank(row) {
  defaultBank.value = row
  form.value.banks.forEach((item) => (item.is_default = item === row))
}

async function saveCreate() {
  try {
    await createRef.value.validate()
  } catch {
    createTab.value = 'base'
    return
  }
  for (const contact of form.value.contacts) {
    if (!contact.name) {
      createTab.value = 'contacts'
      ElMessage.warning('联系人姓名不能为空')
      return
    }
  }
  for (const bank of form.value.banks) {
    if (!bank.bank_name || !bank.account_no || !bank.account_name) {
      createTab.value = 'banks'
      ElMessage.warning('银行账户开户行、账号、账户名称均为必填')
      return
    }
  }
  for (const license of form.value.licenses) {
    if (!license.name) {
      createTab.value = 'licenses'
      ElMessage.warning('资质证照名称不能为空')
      return
    }
  }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      owner_user_id: form.value.owner_user_id || auth.user.id,
      tax_no: form.value.tax_no || null,
      intro: form.value.intro || null,
      contacts: form.value.contacts.map((item) => ({
        name: item.name,
        title: item.title || null,
        phone: item.phone || null,
        email: item.email || null,
        is_default: Boolean(item.is_default)
      })),
      banks: form.value.banks.map((item) => ({
        bank_name: item.bank_name,
        account_no: item.account_no,
        account_name: item.account_name,
        is_default: Boolean(item.is_default)
      })),
      licenses: form.value.licenses.map((item) => ({
        name: item.name,
        no: item.no || null,
        file_id: item.file_id || null,
        valid_from: item.valid_from || null,
        valid_to: item.valid_to || null
      }))
    }
    const data = await vendorApi.create(payload)
    ElMessage.success(form.value.submit ? '供应商已创建并提交准入' : '供应商草稿已保存')
    createVisible.value = false
    await load()
    if (data?.id) router.push(`/vendors/${data.id}`)
  } finally {
    saving.value = false
  }
}

async function submitVendor(row) {
  try {
    await ElMessageBox.confirm(`确认提交「${row.name}」的准入审批吗？`, '提交准入', { type: 'warning' })
  } catch {
    return
  }
  await vendorApi.submit(row.id)
  ElMessage.success('准入审批已提交')
  await load()
}

function openBlacklist(row) {
  blacklistTarget.value = row
  blacklistReason.value = ''
  blacklistVisible.value = true
}

async function confirmBlacklist() {
  if ((blacklistReason.value || '').trim().length < 3) {
    ElMessage.warning('请填写不少于 3 个字的拉黑原因')
    return
  }
  saving.value = true
  try {
    await vendorApi.blacklist(blacklistTarget.value.id, { reason: blacklistReason.value.trim() })
    ElMessage.success('供应商已加入黑名单')
    blacklistVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function restoreVendor(row) {
  try {
    await ElMessageBox.confirm(`确认解除「${row.name}」的黑名单吗？`, '解除黑名单', { type: 'warning' })
  } catch {
    return
  }
  await vendorApi.restore(row.id)
  ElMessage.success('供应商已恢复')
  await load()
}

onMounted(async () => {
  await meta.ensure()
  await Promise.allSettled([load(), loadRisks()])
})
</script>

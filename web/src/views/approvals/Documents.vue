<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>文件审批</h2>
        <p>制度、通知、用印与合同文本统一走审批流，按密级控制可见范围并保留完整流转记录。</p>
      </div>
      <el-button v-if="auth.can('approval:document')" type="primary" :icon="Plus" @click="openCreate">新建文件</el-button>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="status in ['DRAFT', 'RUNNING', 'REJECTED', 'APPROVED', 'CANCELED']" :key="status" :label="STATUS_LABELS[status]" :value="status" />
        </el-select>
        <el-select v-model="filters.category" placeholder="全部分类" clearable @change="reload">
          <el-option v-for="(label, value) in DOCUMENT_CATEGORIES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="标题 / 文号" clearable :prefix-icon="Search" style="width: 220px" @keyup.enter="reload" @clear="reload" />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="doc_no" label="文号" width="180" class-name="mono" />
        <el-table-column prop="title" label="文件标题" min-width="260" show-overflow-tooltip />
        <el-table-column label="分类" width="120">
          <template #default="{ row }">{{ labelOf(DOCUMENT_CATEGORIES, row.category) }}</template>
        </el-table-column>
        <el-table-column label="密级" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.secret_level === 'SECRET' ? 'danger' : row.secret_level === 'INTERNAL' ? 'warning' : 'info'" effect="plain">
              {{ labelOf(SECRET_LEVELS, row.secret_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="创建人" width="100" />
        <el-table-column label="生效日期" width="120">
          <template #default="{ row }">{{ date(row.effect_date) }}</template>
        </el-table-column>
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

    <el-dialog v-model="formVisible" :title="editingId ? '编辑文件' : '新建文件'" width="680px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="92px">
        <el-form-item label="文件标题" prop="title">
          <el-input v-model="form.title" maxlength="255" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="文件分类">
              <el-select v-model="form.category" style="width: 100%">
                <el-option v-for="(label, value) in DOCUMENT_CATEGORIES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="密级">
              <el-select v-model="form.secret_level" style="width: 100%">
                <el-option v-for="(label, value) in SECRET_LEVELS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="生效日期">
              <el-date-picker v-model="form.effect_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="关联项目">
          <el-select v-model="form.project_id" clearable filterable style="width: 100%" placeholder="可不选">
            <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件正文">
          <el-input v-model="form.content" type="textarea" :rows="5" maxlength="5000" show-word-limit />
        </el-form-item>
        <el-form-item label="文件附件">
          <file-upload v-model="form.file_id" biz-type="DOCUMENT" />
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

    <el-drawer v-model="detailVisible" size="680px" :title="detail?.doc_no || '文件详情'" destroy-on-close>
      <div v-if="detail" v-loading="detailLoading">
        <div class="detail-hero" style="margin-bottom: 14px">
          <div>
            <h2>{{ detail.title }}</h2>
            <div class="sub">
              <span>{{ labelOf(DOCUMENT_CATEGORIES, detail.category) }}</span>
              <span>{{ labelOf(SECRET_LEVELS, detail.secret_level) }}</span>
              <span>创建人：{{ detail.creator_name }}</span>
            </div>
          </div>
          <status-tag :value="detail.status" />
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文号">{{ detail.doc_no }}</el-descriptions-item>
          <el-descriptions-item label="生效日期">{{ date(detail.effect_date) }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ datetime(detail.submitted_at) }}</el-descriptions-item>
          <el-descriptions-item label="归档时间">{{ datetime(detail.archived_at) }}</el-descriptions-item>
        </el-descriptions>
        <div class="section-title">文件正文</div>
        <div class="desc-block">{{ detail.content || '暂无正文内容' }}</div>
        <div class="section-title">附件</div>
        <el-link v-if="detail.file && detail.file.id" type="primary" @click="downloadFile(detail.file)">{{ detail.file.name }}</el-link>
        <span v-else class="muted" style="font-size: 13px">未上传附件</span>

        <div class="section-title">业务操作</div>
        <div class="tag-row">
          <el-button v-if="canEdit(detail)" size="small" @click="openEdit(detail)">编辑</el-button>
          <el-button v-if="canSubmit(detail)" size="small" type="success" @click="doAction(detail, 'submit')">提交审批</el-button>
          <el-button v-if="canWithdraw(detail)" size="small" type="warning" @click="doAction(detail, 'withdraw')">撤回审批</el-button>
          <el-button v-if="detail.status === 'DRAFT'" size="small" type="danger" plain @click="doAction(detail, 'cancel')">取消文件</el-button>
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
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { documentApi, fileApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import FileUpload from '@/components/FileUpload.vue'
import StatusTag from '@/components/StatusTag.vue'
import { date, datetime, today } from '@/utils/format'
import { DOCUMENT_CATEGORIES, SECRET_LEVELS, STATUS_LABELS, labelOf } from '@/utils/constants'
import { saveBlob } from '@/utils/download'

const auth = useAuthStore()
const meta = useMetaStore()
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ status: '', category: '', keyword: '' })

const formVisible = ref(false)
const formRef = ref()
const saving = ref(false)
const editingId = ref(null)
const editingVersion = ref(null)
const form = ref({ title: '', category: 'INSTITUTION', secret_level: 'INTERNAL', content: '', file_id: null, effect_date: '', project_id: null })

const detailVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)

const formRules = {
  title: [{ required: true, message: '请输入文件标题', trigger: 'blur' }]
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
  form.value = {
    title: '',
    category: 'INSTITUTION',
    secret_level: 'INTERNAL',
    content: '',
    file_id: null,
    effect_date: today(),
    project_id: null
  }
  formVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  editingVersion.value = row.version
  form.value = {
    title: row.title,
    category: row.category,
    secret_level: row.secret_level,
    content: row.content || '',
    file_id: row.file_id,
    effect_date: row.effect_date,
    project_id: row.project_id
  }
  formVisible.value = true
}

async function save(submit) {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form.value, version: editingVersion.value }
    let saved
    if (editingId.value) saved = await documentApi.update(editingId.value, payload)
    else saved = await documentApi.create(payload)
    if (submit) {
      await documentApi.submit(saved.id)
      ElMessage.success('文件已提交审批')
    } else {
      ElMessage.success('文件已保存')
    }
    formVisible.value = false
    await reload()
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
      if (value) params[key] = value
    })
    const data = await documentApi.list(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { status: '', category: '', keyword: '' }
  reload()
}

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await documentApi.detail(row.id)
  } finally {
    detailLoading.value = false
  }
}

async function onApprovalChanged() {
  await load()
  if (detail.value?.id) detail.value = await documentApi.detail(detail.value.id)
}

async function doAction(row, action) {
  const labels = { submit: '提交审批', withdraw: '撤回审批', cancel: '取消文件' }
  try {
    await ElMessageBox.confirm(`确认${labels[action]}「${row.title}」吗？`, '操作确认', { type: 'warning' })
  } catch {
    return
  }
  await documentApi[action](row.id)
  ElMessage.success(`${labels[action]}成功`)
  await load()
  if (detailVisible.value && detail.value?.id === row.id) detail.value = await documentApi.detail(row.id)
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

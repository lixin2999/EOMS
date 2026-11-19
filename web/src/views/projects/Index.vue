<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>项目管理</h2>
        <p>覆盖立项、计划、执行、收尾与归档全周期；进度、成本、变更与验收统一归集到项目损益。</p>
      </div>
      <div class="tag-row">
        <el-button v-if="auth.can('project:create')" :icon="Promotion" @click="openInitiation">发起立项</el-button>
        <el-button v-if="auth.can('project:create')" type="primary" :icon="Plus" @click="openCreate">新建项目</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">项目总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前数据域内可见项目</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">执行中</div>
        <div class="stat-value">{{ stageCount.EXECUTE || 0 }}</div>
        <div class="stat-foot">立项 {{ stageCount.LAUNCH || 0 }} · 计划 {{ stageCount.PLAN || 0 }} · 收尾 {{ stageCount.CLOSE || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">合同总额</div>
        <div class="stat-value small"><money-text :value="sumContract" symbol /></div>
        <div class="stat-foot">预算总额 <money-text :value="sumBudget" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">平均进度</div>
        <div class="stat-value">{{ avgProgress }}%</div>
        <div class="stat-foot">按当前页项目简单平均</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.stage" placeholder="全部阶段" clearable @change="reload">
          <el-option v-for="(label, value) in PROJECT_STAGES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="reload">
          <el-option v-for="status in ['DRAFT', 'PENDING', 'ACTIVE', 'SUSPENDED', 'CLOSED', 'CANCELED']" :key="status" :label="STATUS_LABELS[status]" :value="status" />
        </el-select>
        <el-select v-model="filters.manager_id" placeholder="全部项目经理" clearable filterable @change="reload">
          <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
        </el-select>
        <el-select v-model="filters.dept_id" placeholder="全部部门" clearable filterable @change="reload">
          <el-option v-for="dept in deptOptions" :key="dept.id" :label="dept.label" :value="dept.id" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="项目名称 / 编号" clearable :prefix-icon="Search" style="width: 220px" @keyup.enter="reload" @clear="reload" />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
        <div class="grow" />
        <el-radio-group v-model="viewMode">
          <el-radio-button value="table">列表</el-radio-button>
          <el-radio-button value="card">卡片</el-radio-button>
        </el-radio-group>
      </div>

      <el-table v-if="viewMode === 'table'" v-loading="loading" :data="rows" @row-click="goDetail">
        <el-table-column prop="no" label="项目编号" width="160" class-name="mono" />
        <el-table-column prop="name" label="项目名称" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false">{{ row.name }}</el-link>
            <el-tag v-if="row.secret_level === 'SECRET'" type="danger" size="small" effect="plain" style="margin-left: 6px">机密</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ labelOf(PROJECT_TYPES, row.type) }}</template>
        </el-table-column>
        <el-table-column label="阶段" width="110">
          <template #default="{ row }"><status-tag :value="row.stage" :labels="PROJECT_STAGES" /></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><status-tag :value="row.status" /></template>
        </el-table-column>
        <el-table-column prop="manager_name" label="项目经理" width="110" />
        <el-table-column prop="dept_name" label="责任部门" width="120" />
        <el-table-column label="计划周期" width="190">
          <template #default="{ row }">
            <span class="muted">{{ date(row.plan_start) }} ~ {{ date(row.plan_end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140">
          <template #default="{ row }">
            <div class="progress-line">
              <el-progress :percentage="Number(row.progress || 0)" :stroke-width="6" :show-text="false" />
              <span style="font-size: 12px">{{ row.progress || 0 }}%</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="合同额" width="130" align="right">
          <template #default="{ row }"><money-text :value="row.contract_amount" short /></template>
        </el-table-column>
        <el-table-column label="预算" width="130" align="right">
          <template #default="{ row }"><money-text :value="row.budget_amount" short /></template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="goDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-else v-loading="loading" class="split-3">
        <div v-for="row in rows" :key="row.id" class="card" style="cursor: pointer" @click="goDetail(row)">
          <div style="display: flex; justify-content: space-between; gap: 10px; align-items: flex-start">
            <div>
              <div style="font-weight: 700; font-size: 15px">{{ row.name }}</div>
              <div class="muted mono" style="font-size: 12px; margin-top: 4px">{{ row.no }}</div>
            </div>
            <status-tag :value="row.stage" :labels="PROJECT_STAGES" />
          </div>
          <div class="tag-row" style="margin: 12px 0">
            <span class="chip">{{ labelOf(PROJECT_TYPES, row.type) }}</span>
            <span class="chip">{{ row.manager_name || '-' }}</span>
            <span class="chip">{{ row.dept_name || '-' }}</span>
          </div>
          <div class="progress-line">
            <el-progress :percentage="Number(row.progress || 0)" :stroke-width="8" :show-text="false" />
            <span style="font-size: 12px">{{ row.progress || 0 }}%</span>
          </div>
          <div style="display: flex; justify-content: space-between; margin-top: 12px; font-size: 12.5px">
            <span class="muted">合同额</span>
            <money-text :value="row.contract_amount" short />
          </div>
          <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 12.5px">
            <span class="muted">预算</span>
            <money-text :value="row.budget_amount" short />
          </div>
        </div>
      </div>

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

    <el-dialog v-model="createVisible" title="新建项目" width="720px" :close-on-click-modal="false">
      <el-form ref="createRef" :model="createForm" :rules="createRules" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="项目名称" prop="name">
              <el-input v-model="createForm.name" maxlength="128" placeholder="请输入项目名称" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="项目类型">
              <el-select v-model="createForm.type" style="width: 100%">
                <el-option v-for="(label, value) in PROJECT_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="客户">
              <el-select v-model="createForm.customer_id" filterable clearable style="width: 100%" placeholder="选择客户">
                <el-option v-for="customer in meta.options.customers || []" :key="customer.id" :label="customer.name" :value="customer.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目经理">
              <el-select v-model="createForm.manager_id" filterable style="width: 100%" placeholder="默认本人">
                <el-option v-for="user in meta.userOptions" :key="user.id" :label="`${user.real_name}（${user.username}）`" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="责任部门">
              <el-select v-model="createForm.dept_id" filterable style="width: 100%" placeholder="默认本人部门">
                <el-option v-for="dept in deptOptions" :key="dept.id" :label="dept.label" :value="dept.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密级">
              <el-select v-model="createForm.secret_level" style="width: 100%">
                <el-option v-for="(label, value) in SECRET_LEVELS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="计划开始">
              <el-date-picker v-model="createForm.plan_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计划结束">
              <el-date-picker v-model="createForm.plan_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="预算金额">
              <el-input-number v-model="createForm.budget_amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同金额">
              <el-input-number v-model="createForm.contract_amount" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="项目描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" maxlength="1000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">创建项目</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="initiationVisible" title="发起项目立项" width="760px" :close-on-click-modal="false">
      <el-form ref="initiateRef" :model="initiationForm" :rules="initiationRules" label-width="96px">
        <el-form-item label="关联项目">
          <el-select v-model="initiationForm.project_id" filterable clearable style="width: 100%" placeholder="不选则同步创建新项目">
            <el-option v-for="project in draftProjects" :key="project.id" :label="`${project.no} ${project.name}`" :value="project.id" />
          </el-select>
          <div class="form-tip">仅能为本人负责的草稿/已取消项目发起立项；不选择则按下列信息同步创建项目。</div>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="项目名称" prop="name">
              <el-input v-model="initiationForm.name" maxlength="128" :disabled="Boolean(initiationForm.project_id)" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="项目类型">
              <el-select v-model="initiationForm.type" style="width: 100%">
                <el-option v-for="(label, value) in PROJECT_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="项目经理">
              <el-select v-model="initiationForm.manager_id" filterable style="width: 100%" placeholder="默认本人">
                <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计划周期">
              <el-date-picker
                v-model="initiationPlanRange"
                type="daterange"
                value-format="YYYY-MM-DD"
                start-placeholder="开始"
                end-placeholder="结束"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="预估成本">
              <el-input-number v-model="initiationForm.estimate_cost" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预估收入">
              <el-input-number v-model="initiationForm.estimate_income" :min="0" :precision="2" :step="10000" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="立项背景" prop="background">
          <el-input v-model="initiationForm.background" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item label="立项目标" prop="goal">
          <el-input v-model="initiationForm.goal" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item label="风险说明">
          <el-input v-model="initiationForm.risk_desc" type="textarea" :rows="2" maxlength="2000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="initiationVisible = false">取消</el-button>
          <el-button :loading="saving" @click="saveInitiation(false)">保存草稿</el-button>
          <el-button type="success" :loading="saving" @click="saveInitiation(true)">保存并提交审批</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Promotion, Refresh, Search } from '@element-plus/icons-vue'
import { projectApi } from '@/api'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date } from '@/utils/format'
import { PROJECT_STAGES, PROJECT_TYPES, SECRET_LEVELS, STATUS_LABELS, labelOf } from '@/utils/constants'

const router = useRouter()
const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const viewMode = ref('table')
const filters = ref({ stage: '', status: '', manager_id: null, dept_id: null, keyword: '' })

const createVisible = ref(false)
const createRef = ref()
const saving = ref(false)
const createForm = ref({})

const initiationVisible = ref(false)
const initiateRef = ref()
const initiationForm = ref({})
const initiationPlanRange = ref([])

const deptOptions = computed(() => {
  const result = []
  const walk = (nodes, depth = 0) => {
    for (const node of nodes || []) {
      result.push({ id: node.id, label: `${'　'.repeat(depth)}${node.name}` })
      walk(node.children, depth + 1)
    }
  }
  walk(meta.options.depts || [])
  return result
})

const stageCount = computed(() => {
  const result = {}
  for (const row of rows.value) result[row.stage] = (result[row.stage] || 0) + 1
  return result
})
const sumContract = computed(() => rows.value.reduce((sum, row) => sum + Number(row.contract_amount || 0), 0))
const sumBudget = computed(() => rows.value.reduce((sum, row) => sum + Number(row.budget_amount || 0), 0))
const avgProgress = computed(() => {
  if (!rows.value.length) return 0
  return Math.round(rows.value.reduce((sum, row) => sum + Number(row.progress || 0), 0) / rows.value.length)
})
const draftProjects = computed(() => rows.value.filter((row) => ['DRAFT', 'CANCELED'].includes(row.status)))

const createRules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }]
}
const initiationRules = {
  name: [
    {
      validator: (_rule, value, callback) => {
        if (!initiationForm.value.project_id && !value) callback(new Error('请输入项目名称'))
        else callback()
      },
      trigger: 'blur'
    }
  ],
  background: [{ required: true, message: '请填写立项背景', trigger: 'blur' }],
  goal: [{ required: true, message: '请填写立项目标', trigger: 'blur' }]
}

function goDetail(row) {
  router.push(`/projects/${row.id}`)
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
    const data = await projectApi.list(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { stage: '', status: '', manager_id: null, dept_id: null, keyword: '' }
  reload()
}

function openCreate() {
  createForm.value = {
    name: '',
    type: 'CONSTRUCTION',
    customer_id: meta.options.customers?.[0]?.id || null,
    manager_id: auth.user.id,
    dept_id: auth.user.dept_id || deptOptions.value[0]?.id || null,
    plan_start: '',
    plan_end: '',
    budget_amount: 0,
    contract_amount: 0,
    secret_level: 'INTERNAL',
    description: ''
  }
  createVisible.value = true
}

async function saveCreate() {
  await createRef.value.validate()
  saving.value = true
  try {
    const data = await projectApi.create({ ...createForm.value })
    ElMessage.success('项目已创建')
    createVisible.value = false
    await load()
    router.push(`/projects/${data.id}`)
  } finally {
    saving.value = false
  }
}

function openInitiation() {
  initiationForm.value = {
    project_id: null,
    name: '',
    type: 'CONSTRUCTION',
    manager_id: auth.user.id,
    plan_start: '',
    plan_end: '',
    estimate_cost: 0,
    estimate_income: 0,
    background: '',
    goal: '',
    risk_desc: ''
  }
  initiationPlanRange.value = []
  initiationVisible.value = true
}

watch(initiationPlanRange, (range) => {
  initiationForm.value.plan_start = range?.[0] || ''
  initiationForm.value.plan_end = range?.[1] || ''
})

watch(
  () => initiationForm.value.project_id,
  (projectId) => {
    if (!projectId) return
    const project = rows.value.find((item) => item.id === projectId)
    if (!project) return
    initiationForm.value.name = project.name
    initiationForm.value.type = project.type
    initiationForm.value.manager_id = project.manager_id
    initiationForm.value.estimate_cost = Number(project.budget_amount || 0)
    initiationForm.value.estimate_income = Number(project.contract_amount || 0)
    initiationPlanRange.value = [project.plan_start, project.plan_end].filter(Boolean)
  }
)

async function saveInitiation(submit) {
  await initiateRef.value.validate()
  saving.value = true
  try {
    await projectApi.createInitiation({ ...initiationForm.value, submit })
    ElMessage.success(submit ? '立项审批已提交' : '立项草稿已保存')
    initiationVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

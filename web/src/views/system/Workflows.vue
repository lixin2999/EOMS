<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>流程定义</h2>
        <p>维护费用报销、请假、用印、项目立项/变更/验收、供应商准入等审批流；保存自动递增版本，历史版本不可修改。</p>
      </div>
      <div class="tag-row">
        <el-button :icon="MagicStick" @click="openTemplates">内置模板</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">启用流程</div>
        <div class="stat-value">{{ currentRows.length }}</div>
        <div class="stat-foot">每类业务一条生效定义</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">定义版本总数</div>
        <div class="stat-value">{{ rows.length }}</div>
        <div class="stat-foot">含历史版本</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">审批节点</div>
        <div class="stat-value">{{ approvalNodeCount }}</div>
        <div class="stat-foot">启用流程中的 APPROVAL 节点</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">审批模式</div>
        <div class="stat-value small">{{ modeSummary }}</div>
        <div class="stat-foot">会签 ALL / 或签 ANY</div>
      </div>
    </div>

    <div class="card">
      <el-table v-loading="loading" :data="currentRows">
        <el-table-column label="业务编码" width="190">
          <template #default="{ row }"><span class="mono">{{ row.code }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="流程名称" min-width="240" show-overflow-tooltip />
        <el-table-column label="当前版本" width="110" align="center">
          <template #default="{ row }"><el-tag size="small" effect="plain">v{{ row.version }}</el-tag></template>
        </el-table-column>
        <el-table-column label="节点" width="180">
          <template #default="{ row }">
            <span class="muted">
              共 {{ (row.nodes_json?.nodes || []).length }} 个 · 审批 {{ countApproval(row.nodes_json) }} 个
            </span>
          </template>
        </el-table-column>
        <el-table-column label="流程预览" min-width="260">
          <template #default="{ row }">
            <span class="node-path">
              <template v-for="(node, index) in row.nodes_json?.nodes || []" :key="node.code">
                <span :class="['chip', node.type === 'APPROVAL' ? 'chip-approval' : '']">{{ node.name }}</span>
                <span v-if="index < (row.nodes_json?.nodes || []).length - 1" class="arrow">→</span>
              </template>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" round>{{ row.enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ datetime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="primary" @click="openHistory(row)">版本</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && !currentRows.length" class="empty" style="padding: 50px 0">
        暂无流程定义，点击右上角「内置模板」载入系统模板。
      </div>
    </div>

    <!-- 内置模板 -->
    <el-dialog v-model="templatesVisible" title="系统内置流程模板" width="680px">
      <el-table :data="templates" size="small" border>
        <el-table-column prop="code" label="业务编码" width="190" class-name="mono" />
        <el-table-column prop="name" label="模板名称" min-width="220" show-overflow-tooltip />
        <el-table-column label="节点" width="90" align="center">
          <template #default="{ row }">{{ (row.nodes_json?.nodes || []).length }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="useTemplate(row)">载入</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="muted" style="margin-top: 10px; font-size: 13px">
        载入模板后将打开编辑器，保存时自动生成新版本；同一业务编码仅启用最新版本。
      </div>
    </el-dialog>

    <!-- 版本历史 -->
    <el-dialog v-model="historyVisible" :title="`版本历史 · ${historyCode}`" width="760px">
      <el-table :data="historyRows" size="small" border>
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }"><span class="mono">v{{ row.version }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="节点数" width="90" align="center">
          <template #default="{ row }">{{ (row.nodes_json?.nodes || []).length }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" round>{{ row.enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ datetime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="copyVersion(row)">基于此版本编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 编辑 -->
    <el-dialog
      v-model="editVisible"
      :title="form.id ? `编辑流程（当前 v${form.version}，保存生成 v${form.version + 1}）` : '新建流程定义'"
      width="1000px"
      :close-on-click-modal="false"
      destroy-on-close
      top="5vh"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="业务编码" prop="code">
              <el-input v-model="form.code" maxlength="64" placeholder="如 EXPENSE" :disabled="Boolean(form.id)" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="流程名称" prop="name">
              <el-input v-model="form.name" maxlength="128" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="启用">
              <el-switch v-model="form.enabled" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remark" maxlength="255" placeholder="变更说明，便于审计追溯" />
        </el-form-item>

        <el-form-item label="编辑方式">
          <el-radio-group v-model="editorMode" @change="switchMode">
            <el-radio-button value="VISUAL">可视化编辑</el-radio-button>
            <el-radio-button value="JSON">JSON 源码</el-radio-button>
          </el-radio-group>
          <span class="muted" style="margin-left: 12px; font-size: 13px">
            首节点必须为 START，末节点必须为 END；保存后立即生效。
          </span>
        </el-form-item>

        <template v-if="editorMode === 'VISUAL'">
          <div class="editor-panel">
            <div class="panel-title">
              <h4>流程设置</h4>
              <span class="muted">审批超时按节点计算，超时后自动提醒审批人。</span>
            </div>
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="驳回后" label-width="80px">
                  <el-select v-model="draft.settings.reject_mode" style="width: 100%">
                    <el-option label="退回发起人" value="INITIATOR" />
                    <el-option label="退回上一节点" value="PREVIOUS" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="超时(小时)" label-width="92px">
                  <el-input-number v-model="draft.settings.due_hours" :min="1" :max="720" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="允许撤回" label-width="84px">
                  <el-switch v-model="draft.settings.allow_withdraw" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="允许转办" label-width="80px">
                  <el-switch v-model="draft.settings.allow_transfer" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="允许加签" label-width="84px">
                  <el-switch v-model="draft.settings.allow_add_sign" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="节点总数" label-width="84px">
                  <span class="mono">{{ draft.nodes.length }}</span>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <div class="editor-panel">
            <div class="panel-title">
              <h4>节点预览</h4>
              <span class="muted">条件不满足的审批节点将自动跳过。</span>
            </div>
            <el-steps :active="draft.nodes.length" align-center finish-status="success" style="padding: 8px 0 4px">
              <el-step
                v-for="node in draft.nodes"
                :key="node.code"
                :title="node.name"
                :description="nodeDescription(node)"
              />
            </el-steps>
          </div>

          <div class="editor-panel">
            <div class="panel-title">
              <h4>审批节点</h4>
              <div class="grow" />
              <el-button size="small" type="primary" plain :icon="Plus" @click="addNode">新增审批节点</el-button>
            </div>

            <div v-if="!approvalNodes.length" class="empty" style="padding: 24px 0">
              当前流程没有审批节点，提交后将直接归档。
            </div>

            <div v-for="node in approvalNodes" :key="node.code" class="node-card">
              <div class="node-head">
                <el-tag type="primary" effect="dark" size="small">{{ node.code }}</el-tag>
                <el-input v-model="node.name" size="small" maxlength="64" style="width: 190px" placeholder="节点名称" />
                <div class="grow" />
                <el-button link :icon="ArrowUp" :disabled="isFirstApproval(node)" @click="moveNode(node, -1)">上移</el-button>
                <el-button link :icon="ArrowDown" :disabled="isLastApproval(node)" @click="moveNode(node, 1)">下移</el-button>
                <el-button link type="danger" :icon="Delete" @click="removeNode(node)">删除</el-button>
              </div>
              <el-row :gutter="12">
                <el-col :span="7">
                  <el-form-item label="审批人类型" label-width="92px">
                    <el-select v-model="node.assignee.type" style="width: 100%" @change="onAssigneeTypeChange(node)">
                      <el-option v-for="(label, value) in ASSIGNEE_TYPES" :key="value" :label="label" :value="value" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="9">
                  <el-form-item v-if="node.assignee.type === 'USER'" label="指定用户" label-width="86px">
                    <el-select v-model="node.assignee.value" filterable clearable style="width: 100%" placeholder="选择用户">
                      <el-option
                        v-for="user in meta.userOptions"
                        :key="user.id"
                        :label="`${user.real_name}（${user.username}）`"
                        :value="user.id"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item v-else-if="node.assignee.type === 'ROLE'" label="指定角色" label-width="86px">
                    <el-select v-model="node.assignee.value" filterable clearable style="width: 100%" placeholder="选择角色">
                      <el-option
                        v-for="role in meta.roleOptions"
                        :key="role.code"
                        :label="`${role.name}（${role.code}）`"
                        :value="role.code"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item v-else label="说明" label-width="86px">
                    <span class="muted" style="font-size: 13px">{{ assigneeHint(node.assignee.type) }}</span>
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="审批模式" label-width="86px">
                    <el-radio-group v-model="node.mode">
                      <el-radio value="ANY">或签</el-radio>
                      <el-radio value="ALL">会签</el-radio>
                    </el-radio-group>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="7">
                  <el-form-item label="金额下限" label-width="92px">
                    <el-input-number
                      v-model="node.condition.min_amount"
                      :min="0"
                      :precision="2"
                      :controls="false"
                      :value-on-clear="null"
                      placeholder="不限"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="7">
                  <el-form-item label="金额上限" label-width="92px">
                    <el-input-number
                      v-model="node.condition.max_amount"
                      :min="0"
                      :precision="2"
                      :controls="false"
                      :value-on-clear="null"
                      placeholder="不限"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="6">
                  <el-form-item label="天数下限" label-width="86px">
                    <el-input-number
                      v-model="node.condition.min_days"
                      :min="0"
                      :precision="1"
                      :controls="false"
                      :value-on-clear="null"
                      placeholder="不限"
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="4">
                  <el-form-item label="条件" label-width="52px">
                    <el-tag :type="hasCondition(node) ? 'warning' : 'info'" size="small" effect="plain">
                      {{ hasCondition(node) ? '条件节点' : '必经' }}
                    </el-tag>
                  </el-form-item>
                </el-col>
              </el-row>
              <div v-if="extraConditionText(node)" class="muted" style="font-size: 12px; margin: -4px 0 4px 92px">
                附加条件：{{ extraConditionText(node) }}
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="json-panel">
            <div class="panel-title">
              <h4>JSON 源码</h4>
              <div class="grow" />
              <el-button size="small" @click="formatJson">格式化</el-button>
              <el-button size="small" @click="syncJsonToVisual">校验并转可视化</el-button>
            </div>
            <el-input v-model="jsonText" type="textarea" :rows="20" class="json-textarea" spellcheck="false" />
            <div class="muted" style="font-size: 12px; margin-top: 6px">
              结构：{ settings: { reject_mode, allow_withdraw, due_hours, allow_transfer, allow_add_sign }, nodes: [...] }
            </div>
          </div>
        </template>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存新版本</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, ArrowUp, Delete, MagicStick, Plus, Refresh } from '@element-plus/icons-vue'
import { workflowApi } from '@/api'
import { useMetaStore } from '@/stores/meta'
import { datetime } from '@/utils/format'

const ASSIGNEE_TYPES = {
  DEPT_LEADER: '部门负责人',
  ROLE: '指定角色',
  USER: '指定用户',
  DEPT_MANAGER: '部门负责人 + 经理',
  PM: '项目经理',
  SUPERIOR: '上级负责人',
  CREATOR: '发起人本人'
}

const TYPE_LABELS = { START: '开始', APPROVAL: '审批', CC: '抄送', END: '结束' }

const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const templates = ref([])

const templatesVisible = ref(false)
const historyVisible = ref(false)
const historyCode = ref('')
const historyRows = ref([])

const editVisible = ref(false)
const editorMode = ref('VISUAL')
const formRef = ref()
const jsonText = ref('')
const draft = reactive({ settings: defaultSettings(), nodes: [] })
const form = reactive(emptyForm())

const rules = {
  code: [
    { required: true, message: '请输入业务编码', trigger: 'blur' },
    { pattern: /^[A-Z][A-Z0-9_]{1,63}$/, message: '编码需为大写字母、数字或下划线', trigger: 'blur' }
  ],
  name: [{ required: true, message: '请输入流程名称', trigger: 'blur' }]
}

const currentRows = computed(() => {
  const latest = {}
  for (const row of rows.value) {
    const current = latest[row.code]
    if (!current) {
      latest[row.code] = row
      continue
    }
    if (row.enabled && !current.enabled) latest[row.code] = row
    else if (Boolean(row.enabled) === Boolean(current.enabled) && Number(row.version || 0) > Number(current.version || 0)) {
      latest[row.code] = row
    }
  }
  return Object.values(latest).sort((a, b) => String(a.code).localeCompare(String(b.code)))
})

const approvalNodeCount = computed(() =>
  currentRows.value.reduce((sum, row) => sum + countApproval(row.nodes_json), 0)
)

const modeSummary = computed(() => {
  let any = 0
  let all = 0
  for (const row of currentRows.value) {
    for (const node of row.nodes_json?.nodes || []) {
      if (node.type !== 'APPROVAL') continue
      if ((node.mode || 'ANY') === 'ALL') all += 1
      else any += 1
    }
  }
  return `${all} / ${any}`
})

const approvalNodes = computed(() => draft.nodes.filter((node) => node.type === 'APPROVAL'))

function defaultSettings() {
  return {
    reject_mode: 'INITIATOR',
    allow_withdraw: true,
    due_hours: 24,
    allow_transfer: true,
    allow_add_sign: true
  }
}

function emptyForm() {
  return { id: null, code: '', name: '', version: 0, enabled: true, remark: '' }
}

function countApproval(nodesJson) {
  return (nodesJson?.nodes || []).filter((node) => node.type === 'APPROVAL').length
}

function nodeDescription(node) {
  if (node.type !== 'APPROVAL') return TYPE_LABELS[node.type] || node.type
  const assignee = node.assignee || {}
  const label = ASSIGNEE_TYPES[assignee.type] || assignee.type
  const mode = node.mode === 'ALL' ? '会签' : '或签'
  return `${label} · ${mode}`
}

function assigneeHint(type) {
  return {
    DEPT_LEADER: '由发起人所属部门的负责人审批',
    DEPT_MANAGER: '部门负责人与 MANAGER 角色共同审批',
    PM: '由项目负责人审批，项目缺失时自动兜底',
    SUPERIOR: '由发起人所在部门负责人审批',
    CREATOR: '审批人固定为发起人本人'
  }[type] || ''
}

function hasCondition(node) {
  const condition = node.condition || {}
  return ['min_amount', 'max_amount', 'min_days', 'secret_levels', 'categories', 'types'].some(
    (key) => condition[key] !== undefined && condition[key] !== null && condition[key] !== ''
  )
}

function extraConditionText(node) {
  const condition = node.condition || {}
  const parts = []
  if (condition.secret_levels) parts.push(`密级 ${condition.secret_levels.join('/')}`)
  if (condition.categories) parts.push(`类别 ${condition.categories.join('/')}`)
  if (condition.types) parts.push(`业务 ${condition.types.join('/')}`)
  return parts.join('；')
}

function normalizeNodes(nodesJson) {
  const result = {
    settings: { ...defaultSettings(), ...(nodesJson?.settings || {}) },
    nodes: JSON.parse(JSON.stringify(nodesJson?.nodes || []))
  }
  if (!result.nodes.length) {
    result.nodes = [
      { code: 'START', name: '发起人提交', type: 'START' },
      { code: 'APPROVER_1', name: '部门负责人', type: 'APPROVAL', assignee: { type: 'DEPT_LEADER' }, mode: 'ANY', condition: {} },
      { code: 'END', name: '归档', type: 'END' }
    ]
  }
  for (const node of result.nodes) {
    if (node.type === 'APPROVAL') {
      node.assignee = node.assignee || { type: 'DEPT_LEADER' }
      node.mode = node.mode || 'ANY'
      node.condition = node.condition || {}
      if (node.assignee.value === undefined) node.assignee.value = null
    }
  }
  return result
}

function applyDraft(source) {
  const normalized = normalizeNodes(source)
  draft.settings = normalized.settings
  draft.nodes = normalized.nodes
  jsonText.value = JSON.stringify(normalized, null, 2)
}

async function load() {
  loading.value = true
  try {
    const data = await workflowApi.definitions()
    rows.value = data.items || []
  } finally {
    loading.value = false
  }
}

async function openTemplates() {
  templatesVisible.value = true
  if (templates.value.length) return
  try {
    templates.value = (await workflowApi.defaults()) || []
  } catch {
    templates.value = []
  }
}

function useTemplate(template) {
  Object.assign(form, emptyForm())
  form.code = template.code
  form.name = template.name
  form.enabled = true
  applyDraft(template.nodes_json)
  editorMode.value = 'VISUAL'
  templatesVisible.value = false
  editVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    code: row.code,
    name: row.name,
    version: Number(row.version || 0),
    enabled: Boolean(row.enabled),
    remark: row.remark || ''
  })
  applyDraft(row.nodes_json)
  editorMode.value = 'VISUAL'
  editVisible.value = true
}

function openHistory(row) {
  historyCode.value = row.code
  historyRows.value = rows.value
    .filter((item) => item.code === row.code)
    .sort((a, b) => Number(b.version) - Number(a.version))
  historyVisible.value = true
}

function copyVersion(row) {
  historyVisible.value = false
  openEdit(row)
}

function switchMode(mode) {
  if (mode === 'JSON') {
    jsonText.value = JSON.stringify({ settings: draft.settings, nodes: draft.nodes }, null, 2)
    return
  }
  try {
    syncJsonToVisual()
  } catch {
    editorMode.value = 'JSON'
  }
}

function formatJson() {
  try {
    jsonText.value = JSON.stringify(JSON.parse(jsonText.value), null, 2)
    ElMessage.success('JSON 已格式化')
  } catch (error) {
    ElMessage.error(`JSON 格式错误：${error.message}`)
  }
}

function syncJsonToVisual() {
  const parsed = JSON.parse(jsonText.value)
  if (!Array.isArray(parsed?.nodes)) throw new Error('nodes 必须为数组')
  validateDefinition(parsed)
  applyDraft(parsed)
  editorMode.value = 'VISUAL'
  ElMessage.success('校验通过，已切换可视化编辑')
}

function nextNodeCode() {
  const codes = new Set(draft.nodes.map((node) => node.code))
  let index = 1
  while (codes.has(`APPROVER_${index}`)) index += 1
  return `APPROVER_${index}`
}

function addNode() {
  const endIndex = draft.nodes.findIndex((node) => node.type === 'END')
  const node = {
    code: nextNodeCode(),
    name: '新增审批节点',
    type: 'APPROVAL',
    assignee: { type: 'DEPT_LEADER', value: null },
    mode: 'ANY',
    condition: {}
  }
  draft.nodes.splice(endIndex < 0 ? draft.nodes.length : endIndex, 0, node)
}

function removeNode(node) {
  const index = draft.nodes.indexOf(node)
  if (index >= 0) draft.nodes.splice(index, 1)
}

function moveNode(node, offset) {
  const index = draft.nodes.indexOf(node)
  const target = index + offset
  if (index < 0 || target <= 0 || target >= draft.nodes.length - 1) return
  if (draft.nodes[target].type !== 'APPROVAL') return
  const [item] = draft.nodes.splice(index, 1)
  draft.nodes.splice(target, 0, item)
}

function isFirstApproval(node) {
  return approvalNodes.value[0] === node
}

function isLastApproval(node) {
  return approvalNodes.value[approvalNodes.value.length - 1] === node
}

function onAssigneeTypeChange(node) {
  if (node.assignee.type === 'USER' || node.assignee.type === 'ROLE') {
    if (!node.assignee.value) node.assignee.value = node.assignee.type === 'ROLE' ? 'MANAGER' : null
  } else {
    node.assignee.value = null
  }
}

function cleanCondition(condition) {
  const result = {}
  for (const [key, value] of Object.entries(condition || {})) {
    if (value === null || value === '' || value === undefined) continue
    result[key] = value
  }
  return result
}

function buildNodesJson() {
  return {
    settings: {
      reject_mode: draft.settings.reject_mode || 'INITIATOR',
      allow_withdraw: Boolean(draft.settings.allow_withdraw),
      due_hours: Number(draft.settings.due_hours || 24),
      allow_transfer: Boolean(draft.settings.allow_transfer),
      allow_add_sign: Boolean(draft.settings.allow_add_sign)
    },
    nodes: draft.nodes.map((node) => {
      const row = { code: String(node.code || '').trim(), name: String(node.name || '').trim(), type: node.type }
      if (node.type === 'APPROVAL') {
        row.assignee = { type: node.assignee?.type || 'DEPT_LEADER' }
        if (['USER', 'ROLE'].includes(row.assignee.type)) row.assignee.value = node.assignee?.value ?? null
        row.mode = node.mode || 'ANY'
        row.condition = cleanCondition(node.condition)
      }
      return row
    })
  }
}

function validateDefinition(nodesJson) {
  const nodes = nodesJson?.nodes
  if (!Array.isArray(nodes) || nodes.length < 2) throw new Error('流程至少需要 START 与 END 两个节点')
  if (nodes[0]?.type !== 'START') throw new Error('首个节点必须为 START')
  if (nodes[nodes.length - 1]?.type !== 'END') throw new Error('最后一个节点必须为 END')
  const codes = new Set()
  for (const node of nodes) {
    if (!node.code || !node.name) throw new Error('每个节点都必须填写编码与名称')
    if (codes.has(node.code)) throw new Error(`节点编码重复：${node.code}`)
    codes.add(node.code)
    if (!['START', 'APPROVAL', 'CC', 'END'].includes(node.type)) throw new Error(`节点类型非法：${node.type}`)
    if (node.type === 'APPROVAL') {
      const assignee = node.assignee || {}
      if (!ASSIGNEE_TYPES[assignee.type]) throw new Error(`节点 ${node.code} 的审批人类型非法`)
      if (['USER', 'ROLE'].includes(assignee.type) && !assignee.value) {
        throw new Error(`节点 ${node.code} 需要指定${assignee.type === 'ROLE' ? '角色' : '用户'}`)
      }
      if (!['ANY', 'ALL'].includes(node.mode || 'ANY')) throw new Error(`节点 ${node.code} 审批模式非法`)
    }
  }
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  let nodesJson
  if (editorMode.value === 'JSON') {
    try {
      const parsed = JSON.parse(jsonText.value)
      if (!Array.isArray(parsed?.nodes)) throw new Error('nodes 必须为数组')
      draft.settings = { ...defaultSettings(), ...(parsed.settings || {}) }
      validateDefinition(parsed)
      nodesJson = parsed
    } catch (error) {
      ElMessage.error(`JSON 校验失败：${error.message}`)
      return
    }
  } else {
    nodesJson = buildNodesJson()
    try {
      validateDefinition(nodesJson)
    } catch (error) {
      ElMessage.warning(error.message)
      return
    }
  }

  if (form.id && form.enabled) {
    try {
      await ElMessageBox.confirm(
        `保存后将生成 v${form.version + 1} 并启用，历史 v${form.version} 版本保留但不再用于新流程。`,
        '保存新版本',
        { type: 'warning' }
      )
    } catch {
      return
    }
  }

  saving.value = true
  try {
    await workflowApi.saveDefinition({
      code: form.code.trim().toUpperCase(),
      name: form.name.trim(),
      nodes_json: nodesJson,
      enabled: Boolean(form.enabled),
      remark: form.remark || null
    })
    ElMessage.success('流程定义已保存')
    editVisible.value = false
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

<style scoped>
.node-path {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.node-path .arrow {
  color: #94a3b8;
  font-size: 12px;
}
.chip-approval {
  background: #eff6ff;
  color: #1d4ed8;
  border-color: #bfdbfe;
}
.editor-panel {
  border: 1px solid var(--eoms-border);
  border-radius: 10px;
  padding: 12px 14px 4px;
  margin-bottom: 12px;
  background: #fafcff;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.panel-title h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.panel-title .muted {
  font-size: 12px;
}
.node-card {
  border: 1px solid var(--eoms-border);
  border-radius: 8px;
  background: #fff;
  padding: 10px 12px 0;
  margin-bottom: 10px;
}
.node-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.node-card :deep(.el-form-item) {
  margin-bottom: 10px;
}
.json-panel {
  border: 1px solid var(--eoms-border);
  border-radius: 10px;
  padding: 12px 14px;
  background: #fafcff;
}
.json-textarea :deep(textarea) {
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
</style>

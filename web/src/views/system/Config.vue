<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>系统配置</h2>
        <p>维护业务字典、系统参数与客户主档；字典用于下拉选项，参数以 JSON 存储并即时生效，客户手机号加密保存、列表脱敏展示。</p>
      </div>
      <el-button :icon="Refresh" @click="reloadAll">刷新</el-button>
    </div>

    <el-tabs v-model="activeTab" class="config-tabs">
      <!-- 字典 -->
      <el-tab-pane label="数据字典" name="DICT">
        <div class="split-2" style="align-items: start">
          <div class="card">
            <div class="card-title">
              <h3>字典分类</h3>
              <div class="grow" />
              <el-tag size="small" effect="plain">{{ dictTypes.length }} 类</el-tag>
            </div>
            <div class="type-list">
              <div :class="['type-item', dictType === '' ? 'active' : '']" @click="selectType('')">
                <span>全部字典</span>
                <span class="count">{{ dicts.length }}</span>
              </div>
              <div
                v-for="item in dictTypes"
                :key="item.type"
                :class="['type-item', dictType === item.type ? 'active' : '']"
                @click="selectType(item.type)"
              >
                <span class="mono">{{ item.type }}</span>
                <span class="count">{{ item.count }}</span>
              </div>
              <div v-if="!dictTypes.length && !dictLoading" class="empty" style="padding: 24px 0">暂无字典</div>
            </div>
          </div>

          <div class="card">
            <div class="toolbar">
              <el-input
                v-model="dictKeyword"
                placeholder="标签 / 值关键字"
                clearable
                :prefix-icon="Search"
                style="width: 200px"
              />
              <div class="grow" />
              <span class="muted">{{ dictType || '全部字典' }} · {{ filteredDicts.length }} 条</span>
              <el-button v-if="canConfig" type="primary" :icon="Plus" @click="openDictCreate">新增字典项</el-button>
            </div>

            <el-table v-loading="dictLoading" :data="filteredDicts">
              <el-table-column prop="dict_type" label="字典类型" width="170" class-name="mono" show-overflow-tooltip />
              <el-table-column prop="label" label="标签" min-width="150" show-overflow-tooltip />
              <el-table-column prop="value" label="值" width="150" class-name="mono" show-overflow-tooltip />
              <el-table-column prop="sort" label="排序" width="72" align="right" />
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small" round>
                    {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip>
                <template #default="{ row }">{{ row.remark || '-' }}</template>
              </el-table-column>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }">
                  <div v-if="canConfig" class="table-actions">
                    <el-button link type="primary" @click="openDictEdit(row)">编辑</el-button>
                    <el-button link type="danger" @click="removeDict(row)">删除</el-button>
                  </div>
                  <span v-else class="muted">-</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!dictLoading && !filteredDicts.length" class="empty" style="padding: 34px 0">
              当前分类下暂无字典项
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 参数 -->
      <el-tab-pane label="系统参数" name="CONFIG">
        <div class="card">
          <div class="toolbar">
            <span class="muted">参数以 JSON 值存储，修改后立即生效并写入审计日志。</span>
            <div class="grow" />
            <el-button v-if="canConfig" type="primary" :icon="Plus" @click="openConfigCreate">新增参数</el-button>
          </div>

          <el-table v-loading="configLoading" :data="configs">
            <el-table-column label="参数键" width="260">
              <template #default="{ row }"><span class="mono">{{ row.key }}</span></template>
            </el-table-column>
            <el-table-column label="当前值" min-width="260" show-overflow-tooltip>
              <template #default="{ row }"><code class="value-code">{{ compact(row.value) }}</code></template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.description || '-' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="110">
              <template #default="{ row }">{{ userLabel(row.updated_by) }}</template>
            </el-table-column>
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{ row.updated_at ? datetime(row.updated_at) : '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button v-if="canConfig" link type="primary" @click="openConfigEdit(row)">编辑</el-button>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!configLoading && !configs.length" class="empty" style="padding: 40px 0">暂无系统参数</div>
        </div>
      </el-tab-pane>

      <!-- 客户 -->
      <el-tab-pane label="客户主档" name="CUSTOMER">
        <div class="card">
          <div class="toolbar">
            <el-input
              v-model="customerKeyword"
              placeholder="客户名称关键字"
              clearable
              :prefix-icon="Search"
              style="width: 240px"
              @keyup.enter="loadCustomers"
              @clear="loadCustomers"
            />
            <el-button type="primary" :icon="Search" @click="loadCustomers">查询</el-button>
            <div class="grow" />
            <el-button v-if="canCustomer" type="primary" :icon="Plus" @click="openCustomerCreate">新建客户</el-button>
          </div>

          <el-table v-loading="customerLoading" :data="customers">
            <el-table-column prop="name" label="客户名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="code" label="客户编码" width="140" class-name="mono">
              <template #default="{ row }">{{ row.code || '-' }}</template>
            </el-table-column>
            <el-table-column prop="contact" label="联系人" width="120">
              <template #default="{ row }">{{ row.contact || '-' }}</template>
            </el-table-column>
            <el-table-column label="联系电话" width="150" class-name="mono">
              <template #default="{ row }">{{ row.phone || '-' }}</template>
            </el-table-column>
            <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.email || '-' }}</template>
            </el-table-column>
            <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.address || '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small" round>
                  {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button v-if="canCustomer" link type="primary" @click="openCustomerEdit(row)">编辑</el-button>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!customerLoading && !customers.length" class="empty" style="padding: 40px 0">
            暂无客户，点击右上角新建客户。
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 字典编辑 -->
    <el-dialog v-model="dictVisible" :title="dictForm.id ? '编辑字典项' : '新增字典项'" width="520px" destroy-on-close>
      <el-form ref="dictFormRef" :model="dictForm" :rules="dictRules" label-width="90px">
        <el-form-item label="字典类型" prop="dict_type">
          <el-select
            v-model="dictForm.dict_type"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入类型"
            style="width: 100%"
          >
            <el-option v-for="item in dictTypes" :key="item.type" :label="item.type" :value="item.type" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="标签" prop="label"><el-input v-model="dictForm.label" maxlength="128" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="值" prop="value"><el-input v-model="dictForm.value" maxlength="128" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="排序">
              <el-input-number v-model="dictForm.sort" :min="0" :max="9999" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="dictForm.status" style="width: 100%">
                <el-option label="启用" value="ACTIVE" />
                <el-option label="停用" value="INACTIVE" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="dictForm.remark" maxlength="255" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dictVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveDict">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 参数编辑 -->
    <el-dialog v-model="configVisible" :title="configForm.isNew ? '新增参数' : '编辑参数'" width="620px" destroy-on-close>
      <el-form ref="configFormRef" :model="configForm" :rules="configRules" label-width="90px">
        <el-form-item label="参数键" prop="key">
          <el-input v-model="configForm.key" maxlength="128" :disabled="!configForm.isNew" placeholder="如 budget.alert_threshold" />
        </el-form-item>
        <el-form-item label="参数值" prop="valueText">
          <el-input v-model="configForm.valueText" type="textarea" :rows="8" class="value-textarea" spellcheck="false" />
          <div class="muted" style="font-size: 12px; line-height: 1.6; margin-top: 4px">
            支持 JSON 对象/数组/字符串/数字/布尔值；示例：{ "enabled": true, "threshold": 0.8 }
          </div>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="configForm.description" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="configVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存参数</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 客户编辑 -->
    <el-dialog v-model="customerVisible" :title="customerForm.id ? '编辑客户' : '新建客户'" width="620px" destroy-on-close>
      <el-form ref="customerFormRef" :model="customerForm" :rules="customerRules" label-width="90px">
        <el-row :gutter="12">
          <el-col :span="14">
            <el-form-item label="客户名称" prop="name">
              <el-input v-model="customerForm.name" maxlength="128" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="客户编码">
              <el-input v-model="customerForm.code" maxlength="64" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="联系人"><el-input v-model="customerForm.contact" maxlength="64" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系电话">
              <el-input v-model="customerForm.phone" maxlength="20" placeholder="留空表示不修改" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="邮箱"><el-input v-model="customerForm.email" maxlength="128" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="customerForm.address" maxlength="255" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="customerForm.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
        <el-alert
          v-if="customerForm.id"
          type="info"
          :closable="false"
          title="联系电话以加密方式保存，列表展示为脱敏值；留空则保持原号码不变。"
        />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="customerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCustomer">保存客户</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { iamApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { datetime } from '@/utils/format'

const auth = useAuthStore()
const meta = useMetaStore()

const activeTab = ref('DICT')
const saving = ref(false)

const dictLoading = ref(false)
const dicts = ref([])
const dictType = ref('')
const dictKeyword = ref('')
const dictTypes = ref([])
const dictVisible = ref(false)
const dictFormRef = ref()
const dictForm = ref(emptyDict())

const configLoading = ref(false)
const configs = ref([])
const configVisible = ref(false)
const configFormRef = ref()
const configForm = ref(emptyConfig())

const customerLoading = ref(false)
const customers = ref([])
const customerKeyword = ref('')
const customerVisible = ref(false)
const customerFormRef = ref()
const customerForm = ref(emptyCustomer())

const canConfig = computed(() => auth.can('system:config'))
const canCustomer = computed(() => auth.can('project:create'))

const dictRules = {
  dict_type: [{ required: true, message: '请选择或输入字典类型', trigger: 'change' }],
  label: [{ required: true, message: '请输入标签', trigger: 'blur' }],
  value: [{ required: true, message: '请输入值', trigger: 'blur' }]
}

const configRules = {
  key: [{ required: true, message: '请输入参数键', trigger: 'blur' }],
  valueText: [{ required: true, message: '请输入参数值', trigger: 'blur' }]
}

const customerRules = {
  name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }]
}

const filteredDicts = computed(() => {
  const keyword = dictKeyword.value.trim().toLowerCase()
  return dicts.value
    .filter((item) => (dictType.value ? item.dict_type === dictType.value : true))
    .filter((item) =>
      keyword ? `${item.label} ${item.value}`.toLowerCase().includes(keyword) : true
    )
})

function emptyDict() {
  return { id: null, dict_type: '', label: '', value: '', sort: 0, status: 'ACTIVE', remark: '' }
}

function emptyConfig() {
  return { isNew: true, key: '', valueText: '{}', description: '' }
}

function emptyCustomer() {
  return { id: null, name: '', code: '', contact: '', phone: '', email: '', address: '', status: 'ACTIVE' }
}

function userLabel(id) {
  if (!id) return '-'
  const user = (meta.userOptions || []).find((item) => item.id === id)
  return user ? user.real_name : `用户 #${id}`
}

function compact(value) {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function selectType(type) {
  dictType.value = type
}

function buildDictTypes() {
  const map = new Map()
  for (const item of dicts.value) {
    map.set(item.dict_type, (map.get(item.dict_type) || 0) + 1)
  }
  dictTypes.value = [...map.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => a.type.localeCompare(b.type))
}

async function loadDicts() {
  dictLoading.value = true
  try {
    dicts.value = (await iamApi.dicts()) || []
    buildDictTypes()
  } finally {
    dictLoading.value = false
  }
}

async function loadConfigs() {
  configLoading.value = true
  try {
    configs.value = (await iamApi.configs()) || []
  } finally {
    configLoading.value = false
  }
}

async function loadCustomers() {
  customerLoading.value = true
  try {
    customers.value = (await iamApi.customers(customerKeyword.value.trim() || undefined)) || []
  } finally {
    customerLoading.value = false
  }
}

function reloadAll() {
  const jobs = [loadDicts(), loadConfigs()]
  if (activeTab.value === 'CUSTOMER') jobs.push(loadCustomers())
  return Promise.allSettled(jobs)
}

function openDictCreate() {
  dictForm.value = emptyDict()
  dictForm.value.dict_type = dictType.value || ''
  dictVisible.value = true
}

function openDictEdit(row) {
  dictForm.value = {
    id: row.id,
    dict_type: row.dict_type,
    label: row.label,
    value: row.value,
    sort: row.sort || 0,
    status: row.status,
    remark: row.remark || ''
  }
  dictVisible.value = true
}

async function saveDict() {
  try {
    await dictFormRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      dict_type: dictForm.value.dict_type.trim(),
      label: dictForm.value.label.trim(),
      value: dictForm.value.value.trim(),
      sort: Number(dictForm.value.sort || 0),
      status: dictForm.value.status,
      remark: dictForm.value.remark || null
    }
    if (dictForm.value.id) await iamApi.updateDict(dictForm.value.id, payload)
    else await iamApi.createDict(payload)
    ElMessage.success('字典已保存')
    dictVisible.value = false
    await loadDicts()
    await meta.refreshOptions()
  } finally {
    saving.value = false
  }
}

async function removeDict(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除字典项「${row.label}」（${row.dict_type} / ${row.value}）吗？前端下拉选项将立即失效。`,
      '删除字典',
      { type: 'warning' }
    )
  } catch {
    return
  }
  await iamApi.deleteDict(row.id)
  ElMessage.success('字典项已删除')
  await loadDicts()
}

function openConfigCreate() {
  configForm.value = emptyConfig()
  configVisible.value = true
}

function openConfigEdit(row) {
  configForm.value = {
    isNew: false,
    key: row.key,
    valueText: JSON.stringify(row.value ?? null, null, 2),
    description: row.description || ''
  }
  configVisible.value = true
}

async function saveConfig() {
  try {
    await configFormRef.value.validate()
  } catch {
    return
  }
  let parsed
  try {
    parsed = JSON.parse(configForm.value.valueText)
  } catch (error) {
    ElMessage.error(`参数值必须为合法 JSON：${error.message}`)
    return
  }
  const key = configForm.value.key.trim()
  if (!key) {
    ElMessage.warning('请输入参数键')
    return
  }
  saving.value = true
  try {
    await iamApi.setConfig(key, { value: parsed, description: configForm.value.description || null })
    ElMessage.success('参数已保存')
    configVisible.value = false
    await loadConfigs()
  } finally {
    saving.value = false
  }
}

function openCustomerCreate() {
  customerForm.value = emptyCustomer()
  customerVisible.value = true
}

function openCustomerEdit(row) {
  customerForm.value = {
    id: row.id,
    name: row.name,
    code: row.code || '',
    contact: row.contact || '',
    phone: row.phone && !row.phone.includes('*') ? row.phone : '',
    email: row.email || '',
    address: row.address || '',
    status: row.status || 'ACTIVE'
  }
  customerVisible.value = true
}

async function saveCustomer() {
  try {
    await customerFormRef.value.validate()
  } catch {
    return
  }
  const payload = {
    name: customerForm.value.name.trim(),
    code: customerForm.value.code || null,
    contact: customerForm.value.contact || null,
    email: customerForm.value.email || null,
    address: customerForm.value.address || null,
    status: customerForm.value.status
  }
  if (customerForm.value.phone && !customerForm.value.phone.includes('*')) {
    payload.phone = customerForm.value.phone.trim()
  }
  saving.value = true
  try {
    if (customerForm.value.id) await iamApi.updateCustomer(customerForm.value.id, payload)
    else await iamApi.createCustomer(payload)
    ElMessage.success(customerForm.value.id ? '客户已更新' : '客户已创建')
    customerVisible.value = false
    await loadCustomers()
    await meta.refreshOptions()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await Promise.allSettled([loadDicts(), loadConfigs(), loadCustomers()])
})
</script>

<style scoped>
.config-tabs :deep(.el-tabs__header) {
  margin-bottom: 14px;
}
.type-list {
  border: 1px solid var(--eoms-border);
  border-radius: 8px;
  overflow: auto;
  max-height: 520px;
}
.type-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 12px;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 1px solid #f1f5f9;
}
.type-item:last-child {
  border-bottom: none;
}
.type-item:hover {
  background: #f8fafc;
}
.type-item.active {
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
}
.type-item .count {
  font-size: 12px;
  color: #64748b;
}
.value-code {
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  color: #334155;
}
.value-textarea :deep(textarea) {
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
</style>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>用户管理</h2>
        <p>维护用户、部门、岗位与角色；重置密码后用户下次登录将强制改密，敏感手机号按权限脱敏展示。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建用户</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">用户总数</div>
        <div class="stat-value">{{ total }}</div>
        <div class="stat-foot">当前公司用户</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">启用中</div>
        <div class="stat-value">{{ rows.filter((item) => item.status === 'ACTIVE').length }}</div>
        <div class="stat-foot">当前页启用用户</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">停用</div>
        <div class="stat-value">{{ rows.filter((item) => item.status !== 'ACTIVE').length }}</div>
        <div class="stat-foot">停用后无法登录</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">待首登改密</div>
        <div class="stat-value">{{ rows.filter((item) => item.first_login).length }}</div>
        <div class="stat-foot">首次登录强制修改密码</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-tree-select
          v-model="filters.dept_id"
          :data="meta.deptOptions"
          :props="{ label: 'name', children: 'children' }"
          node-key="id"
          check-strictly
          clearable
          placeholder="全部部门"
          style="width: 200px"
          @change="reload"
        />
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px" @change="reload">
          <el-option label="启用" value="ACTIVE" />
          <el-option label="停用" value="DISABLED" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="用户名 / 姓名"
          clearable
          :prefix-icon="Search"
          style="width: 200px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column prop="username" label="用户名" width="130" class-name="mono" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="dept_name" label="部门" width="140" />
        <el-table-column prop="position" label="岗位" width="150" />
        <el-table-column prop="phone" label="手机号" width="140" class-name="mono" />
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column label="角色" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="roleId in row.role_ids" :key="roleId" size="small" effect="plain" style="margin-right: 4px; margin-bottom: 3px">
              {{ roleName(roleId) }}
            </el-tag>
            <span v-if="!row.role_ids?.length" class="muted">未分配角色</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small" round>
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近登录" width="170">
          <template #default="{ row }">{{ row.last_login_at ? datetime(row.last_login_at) : '从未登录' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="warning" @click="openReset(row)">重置密码</el-button>
              <el-tag v-if="row.is_super" size="small" type="danger" effect="dark">超管</el-tag>
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

    <el-dialog v-model="createVisible" title="新建用户" width="620px" :close-on-click-modal="false" destroy-on-close>
      <el-form ref="createRef" :model="form" :rules="createRules" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username"><el-input v-model="form.username" maxlength="64" placeholder="登录账号" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="real_name"><el-input v-model="form.real_name" maxlength="64" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="初始密码" prop="password">
              <el-input v-model="form.password" type="password" show-password maxlength="64" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="岗位"><el-input v-model="form.position" maxlength="64" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="部门">
              <el-tree-select
                v-model="form.dept_id"
                :data="meta.deptOptions"
                :props="{ label: 'name', children: 'children' }"
                node-key="id"
                check-strictly
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="启用" value="ACTIVE" />
                <el-option label="停用" value="DISABLED" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="手机号"><el-input v-model="form.phone" maxlength="20" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱"><el-input v-model="form.email" maxlength="128" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="角色">
          <el-select v-model="form.role_ids" multiple filterable style="width: 100%" placeholder="选择角色">
            <el-option v-for="role in meta.roleOptions" :key="role.id" :label="`${role.name}（${role.code}）`" :value="role.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="首次登录">
          <el-switch v-model="form.first_login" />
          <span class="muted" style="margin-left: 10px">开启后用户首次登录必须修改密码</span>
        </el-form-item>
        <el-alert type="info" :closable="false" title="新建用户默认密码建议使用统一演示密码 Eoms@2026，并要求首次登录改密。" />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveCreate">创建用户</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑用户" width="620px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="用户名"><el-input :model-value="editForm.username" disabled /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名"><el-input v-model="editForm.real_name" maxlength="64" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="部门">
              <el-tree-select
                v-model="editForm.dept_id"
                :data="meta.deptOptions"
                :props="{ label: 'name', children: 'children' }"
                node-key="id"
                check-strictly
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="岗位"><el-input v-model="editForm.position" maxlength="64" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="手机号"><el-input v-model="editForm.phone" maxlength="20" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱"><el-input v-model="editForm.email" maxlength="128" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="角色">
          <el-select v-model="editForm.role_ids" multiple filterable style="width: 100%">
            <el-option v-for="role in meta.roleOptions" :key="role.id" :label="`${role.name}（${role.code}）`" :value="role.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="DISABLED" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="460px">
      <el-alert type="warning" :closable="false" :title="`为「${resetTarget.real_name || ''}」重置密码后，用户下次登录必须修改密码。`" />
      <el-form style="margin-top: 14px" label-width="90px">
        <el-form-item label="新密码" required>
          <el-input v-model="newPassword" type="password" show-password maxlength="64" placeholder="至少 8 位，含大小写与数字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="resetVisible = false">取消</el-button>
          <el-button type="warning" :loading="saving" @click="confirmReset">确认重置</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { iamApi } from '@/api'
import { useMetaStore } from '@/stores/meta'
import { datetime } from '@/utils/format'

const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ keyword: '', dept_id: null, status: '' })

const createVisible = ref(false)
const createRef = ref()
const form = ref(emptyForm())

const editVisible = ref(false)
const editForm = ref({})

const resetVisible = ref(false)
const resetTarget = ref({})
const newPassword = ref('')

const createRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密码至少 8 位', trigger: 'blur' }]
}

function emptyForm() {
  return {
    username: '',
    real_name: '',
    password: 'Eoms@2026',
    dept_id: null,
    position: '',
    phone: '',
    email: '',
    role_ids: [],
    status: 'ACTIVE',
    first_login: true
  }
}

function roleName(roleId) {
  const role = (meta.roleOptions || []).find((item) => item.id === roleId)
  return role ? role.name : `角色 #${roleId}`
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
    const data = await iamApi.users(params)
    rows.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { keyword: '', dept_id: null, status: '' }
  reload()
}

function openCreate() {
  form.value = emptyForm()
  createVisible.value = true
}

async function saveCreate() {
  try {
    await createRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await iamApi.createUser({
      ...form.value,
      dept_id: form.value.dept_id || null,
      position: form.value.position || null,
      phone: form.value.phone || null,
      email: form.value.email || null
    })
    ElMessage.success('用户已创建')
    createVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function openEdit(row) {
  editForm.value = {
    id: row.id,
    username: row.username,
    real_name: row.real_name,
    dept_id: row.dept_id,
    position: row.position,
    phone: row.phone && !row.phone.includes('*') ? row.phone : '',
    email: row.email,
    role_ids: [...(row.role_ids || [])],
    status: row.status,
    version: row.version
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editForm.value.real_name) {
    ElMessage.warning('请输入姓名')
    return
  }
  saving.value = true
  try {
    await iamApi.updateUser(editForm.value.id, {
      real_name: editForm.value.real_name,
      dept_id: editForm.value.dept_id || null,
      position: editForm.value.position || null,
      phone: editForm.value.phone || null,
      email: editForm.value.email || null,
      role_ids: editForm.value.role_ids,
      status: editForm.value.status,
      version: editForm.value.version
    })
    ElMessage.success('用户已更新')
    editVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function openReset(row) {
  resetTarget.value = row
  newPassword.value = 'Eoms@2026'
  resetVisible.value = true
}

async function confirmReset() {
  if (!newPassword.value || newPassword.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  saving.value = true
  try {
    await iamApi.resetPassword(resetTarget.value.id, { new_password: newPassword.value })
    ElMessage.success('密码已重置，用户下次登录需强制改密')
    resetVisible.value = false
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

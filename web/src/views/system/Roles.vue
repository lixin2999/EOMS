<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>角色权限</h2>
        <p>角色由「数据域 + 权限点」构成；多角色权限取并集，数据域按公司边界收敛。内置角色仅超级管理员可修改。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建角色</el-button>
    </div>

    <div class="split-2" style="align-items: start">
      <div class="card">
        <div class="card-title">
          <h3>角色列表</h3>
          <div class="grow" />
          <el-button size="small" :icon="Refresh" @click="loadRoles">刷新</el-button>
        </div>
        <el-table v-loading="loading" :data="roles" highlight-current-row @row-click="selectRole">
          <el-table-column prop="code" label="编码" width="130" class-name="mono" />
          <el-table-column prop="name" label="角色名称" min-width="120" />
          <el-table-column label="数据域" width="140">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="row.data_scope === 'ALL' ? 'danger' : row.data_scope === 'COMPANY' ? 'warning' : 'info'">
                {{ labelOf(DATA_SCOPES, row.data_scope) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="权限数" width="80" align="right">
            <template #default="{ row }">{{ row.permission_ids?.length || 0 }}</template>
          </el-table-column>
          <el-table-column label="类型" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_builtin" size="small" type="warning">内置</el-tag>
              <span v-else class="muted">自定义</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button link type="primary" @click.stop="openEdit(row)">编辑</el-button>
                <el-button
                  v-if="!row.is_builtin"
                  link
                  type="danger"
                  @click.stop="remove(row)"
                >删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!loading && !roles.length" class="empty" style="padding: 30px 0">暂无角色</div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>权限视图</h3>
          <div class="grow" />
          <span class="muted">{{ currentRole ? `${currentRole.name}：${currentRole.permission_ids?.length || 0} 个权限点` : '点击左侧角色查看' }}</span>
        </div>
        <el-tree
          ref="viewTreeRef"
          :data="permissionTree"
          :props="{ label: 'name', children: 'children' }"
          node-key="id"
          show-checkbox
          default-expand-all
          :expand-on-click-node="false"
        >
          <template #default="{ data }">
            <span style="display: flex; align-items: center; gap: 8px">
              <span>{{ data.name }}</span>
              <span class="mono muted" style="font-size: 12px">{{ data.code }}</span>
              <el-tag size="small" :type="data.type === 'menu' ? 'success' : 'info'" effect="plain">
                {{ data.type === 'menu' ? '菜单' : '操作' }}
              </el-tag>
              <el-tag v-if="data.path" size="small" effect="plain">{{ data.path }}</el-tag>
            </span>
          </template>
        </el-tree>
      </div>
    </div>

    <el-dialog v-model="editVisible" :title="form.id ? '编辑角色' : '新建角色'" width="720px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="角色编码" prop="code">
              <el-input v-model="form.code" maxlength="64" placeholder="如 AUDITOR" :disabled="Boolean(form.id && form.is_builtin)" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="角色名称" prop="name">
              <el-input v-model="form.name" maxlength="64" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="数据域">
              <el-select v-model="form.data_scope" style="width: 100%">
                <el-option v-for="(label, value) in DATA_SCOPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="启用" value="ACTIVE" />
                <el-option label="停用" value="INACTIVE" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remark" maxlength="255" />
        </el-form-item>
        <el-form-item label="权限点">
          <div class="perm-panel">
            <div class="toolbar" style="margin-bottom: 8px">
              <span class="muted">勾选操作权限会自动授予上级菜单；保存后立即生效并失效权限缓存。</span>
              <div class="grow" />
              <el-button size="small" @click="checkAll(true)">全选</el-button>
              <el-button size="small" @click="checkAll(false)">清空</el-button>
            </div>
            <el-tree
              ref="editTreeRef"
              :data="permissionTree"
              :props="{ label: 'name', children: 'children' }"
              node-key="id"
              show-checkbox
              default-expand-all
              :expand-on-click-node="false"
            >
              <template #default="{ data }">
                <span style="display: flex; align-items: center; gap: 8px">
                  <span>{{ data.name }}</span>
                  <span class="mono muted" style="font-size: 12px">{{ data.code }}</span>
                  <el-tag size="small" :type="data.type === 'menu' ? 'success' : 'info'" effect="plain">
                    {{ data.type === 'menu' ? '菜单' : '操作' }}
                  </el-tag>
                </span>
              </template>
            </el-tree>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存角色</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { iamApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { DATA_SCOPES, labelOf } from '@/utils/constants'

const auth = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const roles = ref([])
const permissionTree = ref([])
const currentRole = ref(null)
const viewTreeRef = ref()

const editVisible = ref(false)
const editTreeRef = ref()
const formRef = ref()
const form = ref(emptyForm())

const rules = {
  code: [{ required: true, message: '请输入角色编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }]
}

function emptyForm() {
  return {
    id: null,
    code: '',
    name: '',
    data_scope: 'SELF',
    status: 'ACTIVE',
    remark: '',
    is_builtin: false
  }
}

function flatten(nodes, result = []) {
  for (const node of nodes || []) {
    result.push(node)
    flatten(node.children, result)
  }
  return result
}

function leafIds() {
  const result = []
  const walk = (nodes) => {
    for (const node of nodes || []) {
      if (node.children && node.children.length) walk(node.children)
      else result.push(node.id)
    }
  }
  walk(permissionTree.value)
  return result
}

function selectRole(row) {
  currentRole.value = row
  nextTick(() => {
    const ids = new Set(row.permission_ids || [])
    const leaves = leafIds().filter((id) => ids.has(id))
    viewTreeRef.value?.setCheckedKeys(leaves)
  })
}

async function loadRoles() {
  loading.value = true
  try {
    roles.value = (await iamApi.roles()) || []
    if (!currentRole.value && roles.value.length) selectRole(roles.value[0])
  } finally {
    loading.value = false
  }
}

async function loadPermissionTree() {
  permissionTree.value = (await iamApi.permissionTree()) || []
}

function openCreate() {
  form.value = emptyForm()
  editVisible.value = true
  nextTick(() => editTreeRef.value?.setCheckedKeys([]))
}

function openEdit(row) {
  form.value = {
    id: row.id,
    code: row.code,
    name: row.name,
    data_scope: row.data_scope,
    status: row.status,
    remark: row.remark || '',
    is_builtin: row.is_builtin
  }
  editVisible.value = true
  nextTick(() => {
    const ids = new Set(row.permission_ids || [])
    editTreeRef.value?.setCheckedKeys(leafIds().filter((id) => ids.has(id)))
  })
}

function checkAll(checked) {
  editTreeRef.value?.setCheckedKeys(checked ? leafIds() : [])
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (form.value.is_builtin && !auth.isSuper) {
    ElMessage.warning('内置角色仅超级管理员可修改')
    return
  }
  const checked = editTreeRef.value?.getCheckedKeys() || []
  const halfChecked = editTreeRef.value?.getHalfCheckedKeys() || []
  const permissionIds = [...new Set([...checked, ...halfChecked])]
  saving.value = true
  try {
    const payload = {
      code: form.value.code.trim().toUpperCase(),
      name: form.value.name.trim(),
      data_scope: form.value.data_scope,
      status: form.value.status,
      remark: form.value.remark || null,
      permission_ids: permissionIds
    }
    if (form.value.id) await iamApi.updateRole(form.value.id, payload)
    else await iamApi.createRole(payload)
    ElMessage.success(form.value.id ? '角色已更新' : '角色已创建')
    editVisible.value = false
    await loadRoles()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除角色「${row.name}」吗？已被用户使用时不可删除。`, '删除角色', { type: 'warning' })
  } catch {
    return
  }
  await iamApi.deleteRole(row.id)
  ElMessage.success('角色已删除')
  if (currentRole.value?.id === row.id) currentRole.value = null
  await loadRoles()
}

onMounted(async () => {
  await Promise.all([loadPermissionTree(), loadRoles()])
  if (roles.value.length) selectRole(roles.value[0])
})
</script>

<style scoped>
.perm-panel {
  width: 100%;
  border: 1px solid var(--eoms-border);
  border-radius: 8px;
  padding: 10px 12px;
  max-height: 380px;
  overflow: auto;
}
</style>

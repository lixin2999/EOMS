<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>部门管理</h2>
        <p>维护公司组织架构与部门负责人；部门路径用于数据域 DEPT_TREE 的向下收敛。</p>
      </div>
      <div class="tag-row">
        <el-button :icon="Plus" @click="openCreate(null)">新增根部门</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">部门总数</div>
        <div class="stat-value">{{ flatDepts.length }}</div>
        <div class="stat-foot">含各级子部门</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">根部门</div>
        <div class="stat-value">{{ depts.length }}</div>
        <div class="stat-foot">一级组织单元</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已设负责人</div>
        <div class="stat-value">{{ flatDepts.filter((item) => item.leader_user_id).length }}</div>
        <div class="stat-foot">负责人用于审批路由</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">停用部门</div>
        <div class="stat-value">{{ flatDepts.filter((item) => item.status !== 'ACTIVE').length }}</div>
        <div class="stat-foot">停用部门仍保留历史数据</div>
      </div>
    </div>

    <div class="card">
      <el-table
        v-loading="loading"
        :data="depts"
        row-key="id"
        default-expand-all
        :tree-props="{ children: 'children' }"
      >
        <el-table-column prop="name" label="部门名称" min-width="260">
          <template #default="{ row }">
            <span style="font-weight: 600">{{ row.name }}</span>
            <span v-if="row.code" class="mono muted" style="margin-left: 8px; font-size: 12px">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="层级路径" width="180" class-name="mono" />
        <el-table-column label="负责人" width="140">
          <template #default="{ row }">{{ userLabel(row.leader_user_id) }}</template>
        </el-table-column>
        <el-table-column prop="sort" label="排序" width="80" align="right" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small" round>
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" @click="openCreate(row)">新增子部门</el-button>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && !depts.length" class="empty" style="padding: 40px 0">暂无部门数据</div>
    </div>

    <el-dialog v-model="editVisible" :title="form.id ? '编辑部门' : '新增部门'" width="540px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="部门名称" prop="name">
          <el-input v-model="form.name" maxlength="128" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="部门编码">
              <el-input v-model="form.code" maxlength="64" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序">
              <el-input-number v-model="form.sort" :min="0" :max="9999" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="上级部门">
          <el-tree-select
            v-model="form.parent_id"
            :data="parentOptions"
            :props="{ label: 'name', children: 'children' }"
            node-key="id"
            check-strictly
            clearable
            placeholder="不选则为根部门"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="部门负责人">
          <el-select v-model="form.leader_user_id" filterable clearable style="width: 100%" placeholder="选择负责人">
            <el-option v-for="user in meta.userOptions" :key="user.id" :label="`${user.real_name}（${user.username}）`" :value="user.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="save">保存部门</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { iamApi } from '@/api'
import { useMetaStore } from '@/stores/meta'

const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const depts = ref([])

const editVisible = ref(false)
const formRef = ref()
const form = ref(emptyForm())

const rules = {
  name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }]
}

const flatDepts = computed(() => {
  const result = []
  const walk = (nodes) => {
    for (const node of nodes || []) {
      result.push(node)
      walk(node.children)
    }
  }
  walk(depts.value)
  return result
})

const parentOptions = computed(() => {
  if (!form.value.id) return depts.value
  const prune = (nodes) =>
    (nodes || [])
      .filter((node) => node.id !== form.value.id)
      .map((node) => ({ ...node, children: prune(node.children) }))
  return prune(depts.value)
})

function emptyForm() {
  return { id: null, name: '', code: '', parent_id: null, leader_user_id: null, sort: 0, status: 'ACTIVE' }
}

function userLabel(id) {
  if (!id) return '-'
  const user = (meta.userOptions || []).find((item) => item.id === id)
  return user ? user.real_name : `用户 #${id}`
}

async function load() {
  loading.value = true
  try {
    depts.value = (await iamApi.depts()) || []
  } finally {
    loading.value = false
  }
}

function openCreate(parent) {
  form.value = emptyForm()
  form.value.parent_id = parent ? parent.id : null
  editVisible.value = true
}

function openEdit(row) {
  form.value = {
    id: row.id,
    name: row.name,
    code: row.code || '',
    parent_id: row.parent_id,
    leader_user_id: row.leader_user_id,
    sort: row.sort || 0,
    status: row.status
  }
  editVisible.value = true
}

async function save() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      code: form.value.code || null,
      parent_id: form.value.parent_id || null,
      leader_user_id: form.value.leader_user_id || null,
      sort: Number(form.value.sort || 0),
      status: form.value.status
    }
    if (form.value.id) await iamApi.updateDept(form.value.id, payload)
    else await iamApi.createDept(payload)
    ElMessage.success(form.value.id ? '部门已更新' : '部门已创建')
    editVisible.value = false
    await load()
    await meta.refreshOptions()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除部门「${row.name}」吗？存在子部门或仍有用户归属时不允许删除。`,
      '删除部门',
      { type: 'warning' }
    )
  } catch {
    return
  }
  await iamApi.deleteDept(row.id)
  ElMessage.success('部门已删除')
  await load()
  await meta.refreshOptions()
}

onMounted(async () => {
  await meta.ensure()
  await load()
})
</script>

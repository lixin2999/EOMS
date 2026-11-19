<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>财务期间</h2>
        <p>关账后该期间将拒绝新增付款、报销入账与计收确认，并自动生成项目损益快照；反关账需填写原因。</p>
      </div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">已开启期间</div>
        <div class="stat-value">{{ openCount }}</div>
        <div class="stat-foot">可正常发生财务业务</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已关账期间</div>
        <div class="stat-value">{{ closedCount }}</div>
        <div class="stat-foot">财务数据已锁定</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">期间总数</div>
        <div class="stat-value">{{ rows.length }}</div>
        <div class="stat-foot">按期间倒序展示</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前开放期间</div>
        <div class="stat-value small">{{ latestOpen || '-' }}</div>
        <div class="stat-foot">最新未关账期间</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-date-picker
          v-model="year"
          type="year"
          value-format="YYYY"
          placeholder="全部年度"
          clearable
          style="width: 150px"
          @change="load"
        />
        <div class="grow" />
        <span class="muted">关账将同步生成项目损益快照，请确认当期业务已全部入账。</span>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column label="会计期间" width="160">
          <template #default="{ row }"><span class="mono" style="font-size: 15px">{{ row.period }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'CLOSED' ? 'info' : 'success'" size="small" round>
              {{ row.status === 'CLOSED' ? '已关账' : '开启中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关账时间" width="180">
          <template #default="{ row }">{{ row.closed_at ? datetime(row.closed_at) : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">{{ userLabel(row.closed_by) }}</template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div v-if="canPeriod" class="table-actions">
              <el-button v-if="row.status === 'OPEN'" link type="warning" @click="openClose(row)">关账</el-button>
              <el-button v-else link type="primary" @click="openReopen(row)">反关账</el-button>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && !rows.length" class="empty" style="padding: 50px 0">暂无会计期间数据</div>
    </div>

    <el-dialog v-model="closeVisible" title="关账确认" width="500px">
      <el-alert
        type="warning"
        :closable="false"
        :title="`确认关闭会计期间 ${target.period} 吗？关账后该期间不可再入账。`"
      />
      <el-form style="margin-top: 14px" label-width="88px">
        <el-form-item label="关账备注">
          <el-input v-model="remark" type="textarea" :rows="3" maxlength="255" show-word-limit placeholder="如：2026 年 10 月月结" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="closeVisible = false">取消</el-button>
          <el-button type="warning" :loading="saving" @click="confirmClose">确认关账</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="reopenVisible" title="反关账" width="500px">
      <el-alert type="error" :closable="false" :title="`反关账将重新开启期间 ${target.period}，请谨慎操作。`" />
      <el-form style="margin-top: 14px" label-width="88px">
        <el-form-item label="反关账原因" required>
          <el-input v-model="remark" type="textarea" :rows="3" maxlength="255" show-word-limit placeholder="不少于 3 个字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="reopenVisible = false">取消</el-button>
          <el-button type="danger" :loading="saving" @click="confirmReopen">确认反关账</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { financeApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { datetime } from '@/utils/format'

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const year = ref(String(dayjs().year()))

const canPeriod = computed(() => auth.can('finance:period'))
const openCount = computed(() => rows.value.filter((item) => item.status === 'OPEN').length)
const closedCount = computed(() => rows.value.filter((item) => item.status === 'CLOSED').length)
const latestOpen = computed(() => rows.value.find((item) => item.status === 'OPEN')?.period || '')

const closeVisible = ref(false)
const reopenVisible = ref(false)
const target = ref({})
const remark = ref('')

function userLabel(id) {
  if (!id) return '-'
  const user = (meta.userOptions || []).find((item) => item.id === id)
  return user ? user.real_name : `用户 #${id}`
}

async function load() {
  loading.value = true
  try {
    rows.value = (await financeApi.periods(year.value ? Number(year.value) : undefined)) || []
  } finally {
    loading.value = false
  }
}

function openClose(row) {
  target.value = row
  remark.value = ''
  closeVisible.value = true
}

async function confirmClose() {
  saving.value = true
  try {
    await financeApi.closePeriod({ period: target.value.period, remark: remark.value || null })
    ElMessage.success(`期间 ${target.value.period} 已关账`)
    closeVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function openReopen(row) {
  target.value = row
  remark.value = ''
  reopenVisible.value = true
}

async function confirmReopen() {
  if ((remark.value || '').trim().length < 3) {
    ElMessage.warning('请填写不少于 3 个字的反关账原因')
    return
  }
  saving.value = true
  try {
    await financeApi.reopenPeriod({ period: target.value.period, remark: remark.value.trim() })
    ElMessage.success(`期间 ${target.value.period} 已反关账`)
    reopenVisible.value = false
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

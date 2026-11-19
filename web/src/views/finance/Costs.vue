<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>成本台账</h2>
        <p>统一记录计收、收款、付款、报销四类成本事件；冲销采用红字反向记录，不物理删除。</p>
      </div>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">计收合计（当前页）</div>
        <div class="stat-value small"><money-text :value="totals.RECEIVABLE" symbol /></div>
        <div class="stat-foot">已确认计收写入 6001</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">收款合计（当前页）</div>
        <div class="stat-value small"><money-text :value="totals.RECEIPT" symbol /></div>
        <div class="stat-foot">收款写入 1002</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">付款合计（当前页）</div>
        <div class="stat-value small"><money-text :value="totals.PAYMENT" symbol /></div>
        <div class="stat-foot">仅已执行付款写入成本</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">报销合计（当前页）</div>
        <div class="stat-value small"><money-text :value="totals.EXPENSE" symbol /></div>
        <div class="stat-foot">审批通过即计入成本</div>
      </div>
    </div>

    <div class="card">
      <div class="toolbar">
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable filterable style="width: 200px" @change="reload">
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-model="filters.biz_type" placeholder="全部业务类型" clearable style="width: 150px" @change="reload">
          <el-option v-for="(label, value) in COST_BIZ_TYPES" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.account_code" placeholder="全部科目" clearable style="width: 190px" @change="reload">
          <el-option v-for="account in meta.accountOptions" :key="account.code" :label="`${account.code} ${account.name}`" :value="account.code" />
        </el-select>
        <el-date-picker
          v-model="filters.period"
          type="month"
          value-format="YYYY-MM"
          placeholder="会计期间"
          clearable
          style="width: 150px"
          @change="reload"
        />
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          clearable
          style="width: 250px"
          @change="reload"
        />
        <el-input
          v-model="filters.keyword"
          placeholder="来源单号"
          clearable
          :prefix-icon="Search"
          style="width: 180px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-button :icon="Search" @click="reload">查询</el-button>
        <el-button :icon="Refresh" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows">
        <el-table-column label="发生日期" width="112">
          <template #default="{ row }">{{ date(row.occur_date) }}</template>
        </el-table-column>
        <el-table-column prop="period" label="期间" width="92" class-name="mono" />
        <el-table-column prop="source_no" label="来源单号" width="180" class-name="mono">
          <template #default="{ row }">
            <span :class="{ 'reversal-text': row.is_reversal }">{{ row.source_no || `#${row.biz_id}` }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="bizTagType(row.biz_type)">{{ labelOf(COST_BIZ_TYPES, row.biz_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link v-if="row.project_id" type="primary" :underline="false" @click="$router.push(`/projects/${row.project_id}`)">
              {{ row.project_name || `项目 #${row.project_id}` }}
            </el-link>
            <span v-else class="muted">公司级</span>
          </template>
        </el-table-column>
        <el-table-column label="科目" width="150">
          <template #default="{ row }">
            <span class="mono">{{ row.account_code }}</span>
            <span class="muted" style="margin-left: 6px">{{ accountName(row.account_code) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="150" align="right">
          <template #default="{ row }">
            <span :class="['money', row.is_reversal ? 'negative' : '']">
              {{ row.is_reversal ? '-' : '' }}<money-text :value="row.amount" />
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="vendor_name" label="供应商" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.vendor_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="资金日期" width="112">
          <template #default="{ row }">{{ row.cash_date ? date(row.cash_date) : '未收付' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_reversal" size="small" type="warning" round>冲销</el-tag>
            <el-tag v-else-if="row.status === 'REVERSED'" size="small" type="info" round>已冲销</el-tag>
            <el-tag v-else size="small" type="success" round>有效</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_reversal && row.status === 'ACTIVE' && auth.can('finance:cost')"
              link
              type="danger"
              @click="openReverse(row)"
            >冲销</el-button>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="reload"
          @current-change="load"
        />
      </div>
    </div>

    <el-dialog v-model="reverseVisible" title="冲销成本记录" width="500px">
      <el-alert
        type="warning"
        :closable="false"
        title="冲销将生成一条红字反向记录，原记录保留并标记为已冲销。"
      />
      <el-descriptions :column="1" border size="small" style="margin-top: 14px">
        <el-descriptions-item label="来源单号">{{ target.source_no || `#${target.biz_id}` }}</el-descriptions-item>
        <el-descriptions-item label="业务类型">{{ labelOf(COST_BIZ_TYPES, target.biz_type) }}</el-descriptions-item>
        <el-descriptions-item label="金额"><money-text :value="target.amount" symbol /></el-descriptions-item>
        <el-descriptions-item label="会计期间">{{ target.period }}</el-descriptions-item>
      </el-descriptions>
      <el-form style="margin-top: 14px" label-width="80px">
        <el-form-item label="冲销原因" required>
          <el-input v-model="reverseReason" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="不少于 2 个字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="reverseVisible = false">取消</el-button>
          <el-button type="danger" :loading="saving" @click="confirmReverse">确认冲销</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { financeApi } from '@/api'
import MoneyText from '@/components/MoneyText.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date } from '@/utils/format'
import { COST_BIZ_TYPES, labelOf } from '@/utils/constants'

const auth = useAuthStore()
const meta = useMetaStore()

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const totals = ref({})
const dateRange = ref([])
const filters = ref({ project_id: null, biz_type: '', account_code: '', period: '', keyword: '' })

const reverseVisible = ref(false)
const reverseTarget = ref({})
const reverseReason = ref('')
const target = computed(() => reverseTarget.value)

function accountName(code) {
  const account = (meta.accountOptions || []).find((item) => item.code === code)
  return account ? account.name : ''
}

function bizTagType(type) {
  return { RECEIVABLE: 'success', RECEIPT: '', PAYMENT: 'warning', EXPENSE: 'danger' }[type] || 'info'
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
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const data = await financeApi.costs(params)
    rows.value = data.items || []
    total.value = data.total || 0
    totals.value = data.totals || {}
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.value = { project_id: null, biz_type: '', account_code: '', period: '', keyword: '' }
  dateRange.value = []
  reload()
}

function openReverse(row) {
  reverseTarget.value = row
  reverseReason.value = ''
  reverseVisible.value = true
}

async function confirmReverse() {
  if ((reverseReason.value || '').trim().length < 2) {
    ElMessage.warning('请填写不少于 2 个字的冲销原因')
    return
  }
  saving.value = true
  try {
    await financeApi.reverseCost(reverseTarget.value.id, { reason: reverseReason.value.trim() })
    ElMessage.success('成本记录已冲销')
    reverseVisible.value = false
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
.reversal-text {
  color: #dc2626;
  text-decoration: line-through;
}
</style>

<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <h2>{{ greeting }}，{{ auth.user.real_name || auth.user.username }}</h2>
        <p>今天是 {{ date(todayDate) }}，以下是公司经营与项目运行概况。</p>
      </div>
      <div class="tag-row">
        <el-button v-if="auth.can('approval:expense')" :icon="Plus" @click="$router.push('/approvals/expenses')">发起报销</el-button>
        <el-button v-if="auth.can('approval:leave')" :icon="Calendar" @click="$router.push('/approvals/leaves')">发起请假</el-button>
        <el-button v-if="auth.can('project:view')" type="primary" :icon="Folder" @click="$router.push('/projects')">项目看板</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">年度营收（计收）</div>
        <div class="stat-value"><money-text :value="overview.revenue" symbol /></div>
        <div class="stat-foot">已收款 <money-text :value="overview.receipt" short /> · 应收余额 <money-text :value="overview.receivable_balance" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">年度成本（付款 + 报销）</div>
        <div class="stat-value"><money-text :value="overview.cost" symbol /></div>
        <div class="stat-foot">付款 <money-text :value="overview.payment" short /> · 报销 <money-text :value="overview.expense" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">毛利 / 毛利率</div>
        <div class="stat-value"><money-text :value="overview.gross_profit" symbol /></div>
        <div class="stat-foot">毛利率 <strong>{{ rawPercent(overview.gross_margin) }}</strong> · 应付余额 <money-text :value="overview.payable_balance" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">我的待办</div>
        <div class="stat-value">{{ counts.pending_tasks }} <span style="font-size: 14px; font-weight: 500; color: #6b7280">项审批</span></div>
        <div class="stat-foot">
          未读通知 {{ counts.unread_notifications }} · 我发起在途 {{ counts.my_running }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">项目健康</div>
        <div class="stat-value">{{ healthyCount }} / {{ projects.length }}</div>
        <div class="stat-foot">
          <span v-if="delayedCount" class="down">{{ delayedCount }} 个项目延期</span>
          <span v-else class="up">全部项目按期推进</span>
        </div>
      </div>
    </div>

    <div class="split-2">
      <div class="card">
        <div class="card-title">
          <h3>经营趋势（月度）</h3>
          <el-button link type="primary" @click="$router.push('/reports')">查看报表</el-button>
        </div>
        <chart-box :option="trendOption" size="lg" />
      </div>
      <div class="card">
        <div class="card-title"><h3>待处理事项</h3></div>
        <el-tabs v-model="taskTab">
          <el-tab-pane :label="`我的待办 (${recentTasks.length})`" name="tasks">
            <div v-if="!recentTasks.length" class="empty">暂无待办，保持高效 👍</div>
            <div v-for="task in recentTasks" :key="task.id" class="risk-item" style="cursor: pointer" @click="$router.push('/approvals/tasks')">
              <span class="risk-dot level-MEDIUM" />
              <div style="flex: 1">
                <div style="font-weight: 600">{{ task.instance?.title || task.node_name }}</div>
                <div class="muted" style="font-size: 12.5px; margin-top: 3px">
                  {{ task.node_name }} · 到达 {{ fromNow(task.arrive_at) }}
                </div>
              </div>
              <el-tag size="small" type="warning">审批</el-tag>
            </div>
          </el-tab-pane>
          <el-tab-pane :label="`风险提醒 (${risks.length})`" name="risks">
            <div v-if="!risks.length" class="empty">暂无到期风险</div>
            <div v-for="(risk, index) in risks" :key="index" class="risk-item">
              <span class="risk-dot" :class="`level-${risk.level || 'MEDIUM'}`" />
              <div style="flex: 1">
                <div style="font-weight: 600">{{ risk.title || risk.message }}</div>
                <div class="muted" style="font-size: 12.5px; margin-top: 3px">
                  {{ risk.type === 'LICENSE_EXPIRING' ? '供应商资质到期' : '合同到期' }}
                  <template v-if="risk.date || risk.days"> · {{ risk.date || `剩余 ${risk.days} 天` }}</template>
                </div>
              </div>
              <el-tag size="small" :type="risk.level === 'HIGH' ? 'danger' : 'warning'">{{ risk.level || 'MEDIUM' }}</el-tag>
            </div>
          </el-tab-pane>
          <el-tab-pane :label="`最近通知 (${recentNotifications.length})`" name="notices">
            <div v-if="!recentNotifications.length" class="empty">暂无通知</div>
            <div v-for="notice in recentNotifications" :key="notice.id" class="risk-item">
              <span class="risk-dot level-LOW" />
              <div style="flex: 1">
                <div style="font-weight: 600">{{ notice.title }}</div>
                <div class="muted" style="font-size: 12.5px; margin-top: 3px">{{ notice.content }}</div>
              </div>
              <span class="muted" style="font-size: 12px">{{ fromNow(notice.created_at) }}</span>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <div class="split-2" style="margin-top: 16px">
      <div class="card">
        <div class="card-title">
          <h3>项目健康度</h3>
          <el-button link type="primary" @click="$router.push('/projects')">全部项目</el-button>
        </div>
        <el-table :data="projects" size="small" @row-click="(row) => $router.push(`/projects/${row.id}`)">
          <el-table-column prop="no" label="项目编号" width="150" class-name="mono" />
          <el-table-column prop="name" label="项目名称" min-width="180" show-overflow-tooltip />
          <el-table-column label="阶段" width="90">
            <template #default="{ row }">
              <status-tag :value="row.stage" :labels="PROJECT_STAGES" />
            </template>
          </el-table-column>
          <el-table-column label="进度" width="150">
            <template #default="{ row }">
              <div class="progress-line">
                <el-progress :percentage="Number(row.progress || 0)" :stroke-width="6" :show-text="false" />
                <span style="font-size: 12px">{{ row.progress || 0 }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="健康" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.delay_days > 0" type="danger" size="small">延期 {{ row.delay_days }} 天</el-tag>
              <el-tag v-else type="success" size="small">正常</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="预算" width="110" align="right">
            <template #default="{ row }"><money-text :value="row.budget_amount" short /></template>
          </el-table-column>
        </el-table>
      </div>
      <div class="card">
        <div class="card-title"><h3>现金流趋势</h3></div>
        <chart-box :option="cashOption" size="sm" />
        <div class="section-title" style="margin-top: 8px">快捷入口</div>
        <div class="tag-row">
          <el-button v-if="auth.can('finance:payment')" size="small" @click="$router.push('/finance/payments')">付款管理</el-button>
          <el-button v-if="auth.can('finance:receipt')" size="small" @click="$router.push('/finance/receipts')">收款登记</el-button>
          <el-button v-if="auth.can('finance:budget')" size="small" @click="$router.push('/finance/budgets')">预算执行</el-button>
          <el-button v-if="auth.can('contract:view')" size="small" @click="$router.push('/contracts')">合同台账</el-button>
          <el-button v-if="auth.can('vendor:view')" size="small" @click="$router.push('/vendors')">供应商</el-button>
          <el-button v-if="auth.can('report:view')" size="small" type="primary" plain @click="$router.push('/reports')">经营报表</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Calendar, Folder, Plus } from '@element-plus/icons-vue'
import { dashboardApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { date, fromNow, moneyShort, rawPercent, today } from '@/utils/format'
import { PROJECT_STAGES } from '@/utils/constants'

const auth = useAuthStore()
const loading = ref(false)
const counts = ref({ pending_tasks: 0, my_running: 0, unread_notifications: 0 })
const overview = ref({ monthly: [] })
const projects = ref([])
const risks = ref([])
const recentTasks = ref([])
const recentNotifications = ref([])
const taskTab = ref('risks')
const todayDate = today()

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 9) return '早上好'
  if (hour < 12) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const delayedCount = computed(() => projects.value.filter((item) => Number(item.delay_days) > 0).length)
const healthyCount = computed(() => projects.value.length - delayedCount.value)

const trendOption = computed(() => {
  const rows = overview.value.monthly || []
  return {
    tooltip: { trigger: 'axis', valueFormatter: (value) => `¥${Number(value || 0).toLocaleString('zh-CN')}` },
    legend: { top: 0, data: ['营收', '成本', '毛利'] },
    grid: { left: 12, right: 16, top: 42, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: rows.map((item) => item.period), axisLine: { lineStyle: { color: '#e5e7eb' } } },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value) => moneyShort(value) },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    series: [
      { name: '营收', type: 'bar', barWidth: 14, itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, data: rows.map((item) => item.revenue) },
      { name: '成本', type: 'bar', barWidth: 14, itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] }, data: rows.map((item) => item.cost) },
      {
        name: '毛利',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        lineStyle: { color: '#16a34a', width: 2 },
        itemStyle: { color: '#16a34a' },
        areaStyle: { color: 'rgba(22,163,74,0.08)' },
        data: rows.map((item) => item.profit)
      }
    ]
  }
})

const cashOption = computed(() => {
  const rows = overview.value.monthly || []
  return {
    tooltip: { trigger: 'axis', valueFormatter: (value) => `¥${Number(value || 0).toLocaleString('zh-CN')}` },
    legend: { top: 0, data: ['现金流入', '现金流出'] },
    grid: { left: 12, right: 12, top: 40, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: rows.map((item) => item.period), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: (value) => moneyShort(value) }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [
      {
        name: '现金流入',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#0ea5e9', width: 2 },
        areaStyle: { color: 'rgba(14,165,233,0.12)' },
        data: rows.map((item) => item.cash_in)
      },
      {
        name: '现金流出',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#ef4444', width: 2 },
        areaStyle: { color: 'rgba(239,68,68,0.08)' },
        data: rows.map((item) => item.cash_out)
      }
    ]
  }
})

async function load() {
  loading.value = true
  try {
    const data = await dashboardApi.all()
    counts.value = data.counts || {}
    overview.value = data.overview || { monthly: [] }
    projects.value = data.projects || []
    risks.value = data.risks || []
    recentTasks.value = data.recent_tasks || []
    recentNotifications.value = data.recent_notifications || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

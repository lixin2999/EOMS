<template>
  <div v-loading="loading" class="page">
    <div class="card">
      <div class="detail-hero">
        <div>
          <div class="tag-row" style="margin-bottom: 8px">
            <el-button link :icon="ArrowLeft" @click="$router.push('/projects')">返回项目列表</el-button>
            <span class="mono muted">{{ project.no }}</span>
          </div>
          <h2>{{ project.name }}</h2>
          <div class="sub">
            <span>{{ labelOf(PROJECT_TYPES, project.type) }}</span>
            <span>{{ project.dept_name || '-' }}</span>
            <span>项目经理：{{ project.manager_name || '-' }}</span>
            <span>客户：{{ project.customer_name || '-' }}</span>
            <span>计划：{{ date(project.plan_start) }} ~ {{ date(project.plan_end) }}</span>
          </div>
          <div class="tag-row" style="margin-top: 10px">
            <status-tag :value="project.stage" :labels="PROJECT_STAGES" />
            <status-tag :value="project.status" />
            <el-tag v-if="project.secret_level === 'SECRET'" type="danger" effect="plain" size="small">机密项目</el-tag>
            <span class="chip">{{ project.progress || 0 }}% 完成</span>
          </div>
        </div>
        <div class="tag-row" style="justify-content: flex-end">
          <el-button v-if="canManage && ['LAUNCH', 'PLAN'].includes(project.stage)" type="primary" @click="doAction('confirmPlan')">确认计划并生成基线</el-button>
          <el-button v-if="canManage && project.stage === 'PLAN_CONFIRMED'" type="success" @click="doAction('startExecution')">进入执行阶段</el-button>
          <el-button v-if="canClose && project.status === 'ACTIVE'" type="warning" plain @click="openClose">关闭项目</el-button>
          <el-button v-if="canClose && project.status === 'CLOSED'" type="primary" plain @click="doAction('archive')">归档项目</el-button>
          <el-button v-if="canManage" :icon="Edit" @click="openEditProject">编辑项目</el-button>
        </div>
      </div>
    </div>

    <div class="stat-grid" style="margin-top: 16px">
      <div class="stat-card">
        <div class="stat-label">合同金额</div>
        <div class="stat-value small"><money-text :value="project.contract_amount" symbol /></div>
        <div class="stat-foot">预算 <money-text :value="project.budget_amount" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计计收</div>
        <div class="stat-value small"><money-text :value="pnl.revenue" symbol /></div>
        <div class="stat-foot">毛利率 <strong>{{ percent(pnl.gross_margin) }}</strong></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计成本</div>
        <div class="stat-value small"><money-text :value="Number(pnl.cost || 0) + Number(pnl.expense || 0)" symbol /></div>
        <div class="stat-foot">付款 <money-text :value="pnl.cost" short /> · 报销 <money-text :value="pnl.expense" short /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">项目毛利</div>
        <div class="stat-value small"><money-text :value="pnl.gross_profit" symbol colorize /></div>
        <div class="stat-foot">预算使用率 {{ rawPercent(Number(pnl.budget_usage || 0) * 100) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">任务完成</div>
        <div class="stat-value">{{ deviation.task_done || 0 }} / {{ deviation.task_total || 0 }}</div>
        <div class="stat-foot">延期 {{ deviation.task_delayed || 0 }} 个 · 完成率 {{ percent(deviation.completion_rate) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">里程碑达成</div>
        <div class="stat-value">{{ percent(pnl.milestone_rate) }}</div>
        <div class="stat-foot">进度偏差 {{ deviation.schedule_variance ?? 0 }} 天</div>
      </div>
    </div>

    <div class="card tabs-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="概览" name="overview">
          <div class="split-2">
            <div>
              <div class="section-title">项目信息</div>
              <div class="info-grid">
                <div class="info-item"><span class="label">项目编号</span><span class="value mono">{{ project.no }}</span></div>
                <div class="info-item"><span class="label">项目名称</span><span class="value">{{ project.name }}</span></div>
                <div class="info-item"><span class="label">项目类型</span><span class="value">{{ labelOf(PROJECT_TYPES, project.type) }}</span></div>
                <div class="info-item"><span class="label">当前阶段</span><span class="value">{{ labelOf(PROJECT_STAGES, project.stage) }}</span></div>
                <div class="info-item"><span class="label">项目状态</span><span class="value">{{ labelOf(STATUS_LABELS, project.status) }}</span></div>
                <div class="info-item"><span class="label">客户</span><span class="value">{{ project.customer_name || '-' }}</span></div>
                <div class="info-item"><span class="label">项目经理</span><span class="value">{{ project.manager_name || '-' }}</span></div>
                <div class="info-item"><span class="label">责任部门</span><span class="value">{{ project.dept_name || '-' }}</span></div>
                <div class="info-item"><span class="label">计划开始</span><span class="value">{{ date(project.plan_start) }}</span></div>
                <div class="info-item"><span class="label">计划结束</span><span class="value">{{ date(project.plan_end) }}</span></div>
                <div class="info-item"><span class="label">实际开始</span><span class="value">{{ date(project.actual_start) }}</span></div>
                <div class="info-item"><span class="label">实际结束</span><span class="value">{{ date(project.actual_end) }}</span></div>
                <div class="info-item"><span class="label">合同金额</span><span class="value"><money-text :value="project.contract_amount" /></span></div>
                <div class="info-item"><span class="label">预算金额</span><span class="value"><money-text :value="project.budget_amount" /></span></div>
                <div class="info-item"><span class="label">密级</span><span class="value">{{ labelOf(SECRET_LEVELS, project.secret_level) }}</span></div>
                <div class="info-item"><span class="label">创建时间</span><span class="value">{{ datetime(project.created_at) }}</span></div>
                <div v-if="project.close_reason" class="info-item" style="grid-column: span 2">
                  <span class="label">关闭原因</span><span class="value">{{ project.close_reason }}</span>
                </div>
              </div>
              <div class="section-title">项目描述</div>
              <div class="desc-block">{{ project.description || '暂无项目描述' }}</div>
            </div>
            <div>
              <div class="section-title">进度与偏差</div>
              <div class="card">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px">
                  <strong>整体进度</strong>
                  <span>{{ project.progress || 0 }}%</span>
                </div>
                <el-progress :percentage="Number(project.progress || 0)" :stroke-width="10" />
                <el-descriptions :column="1" border size="small" style="margin-top: 16px">
                  <el-descriptions-item label="任务总数">{{ deviation.task_total || 0 }}</el-descriptions-item>
                  <el-descriptions-item label="已完成任务">{{ deviation.task_done || 0 }}</el-descriptions-item>
                  <el-descriptions-item label="延期任务">{{ deviation.task_delayed || 0 }}</el-descriptions-item>
                  <el-descriptions-item label="计划工时">{{ deviation.planned_hours || 0 }} 小时</el-descriptions-item>
                  <el-descriptions-item label="实际工时">{{ deviation.actual_hours || 0 }} 小时</el-descriptions-item>
                  <el-descriptions-item label="成本偏差"><money-text :value="deviation.cost_variance" colorize /></el-descriptions-item>
                </el-descriptions>
              </div>
              <div class="section-title">成员（{{ project.members?.length || 0 }}）</div>
              <div class="tag-row">
                <span v-for="member in project.members || []" :key="member.id" class="chip primary">
                  {{ member.user_name }} · {{ memberRoleLabel(member.role) }}
                </span>
                <span v-if="!(project.members || []).length" class="muted">暂无成员</span>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="损益" name="pnl">
          <div class="split-2">
            <div class="card">
              <div class="card-title"><h3>月度趋势</h3></div>
              <chart-box :option="pnlTrendOption" size="lg" />
            </div>
            <div class="card">
              <div class="card-title"><h3>口径说明</h3></div>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="累计计收"><money-text :value="pnl.revenue" /></el-descriptions-item>
                <el-descriptions-item label="累计付款"><money-text :value="pnl.cost" /></el-descriptions-item>
                <el-descriptions-item label="累计报销"><money-text :value="pnl.expense" /></el-descriptions-item>
                <el-descriptions-item label="项目毛利"><money-text :value="pnl.gross_profit" colorize /></el-descriptions-item>
                <el-descriptions-item label="毛利率">{{ percent(pnl.gross_margin) }}</el-descriptions-item>
                <el-descriptions-item label="预算金额"><money-text :value="pnl.budget_amount" /></el-descriptions-item>
                <el-descriptions-item label="成本偏差"><money-text :value="pnl.cost_variance" colorize /></el-descriptions-item>
                <el-descriptions-item label="预算使用率">{{ rawPercent(Number(pnl.budget_usage || 0) * 100) }}</el-descriptions-item>
              </el-descriptions>
              <div class="section-title">科目构成</div>
              <div class="tag-row">
                <span v-for="(amount, code) in pnl.revenue_by_account || {}" :key="`r-${code}`" class="chip success">收入 {{ code }}：<money-text :value="amount" /></span>
                <span v-for="(amount, code) in pnl.cost_by_account || {}" :key="`c-${code}`" class="chip warn">成本 {{ code }}：<money-text :value="amount" /></span>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="立项" name="initiation">
          <div v-if="project.initiation">
            <div class="tag-row" style="margin-bottom: 14px">
              <status-tag :value="project.initiation.status" />
              <span class="chip">申请人：{{ project.initiation.applicant_id ? `#${project.initiation.applicant_id}` : '-' }}</span>
              <span class="chip">预估成本 <money-text :value="project.initiation.estimate_cost" short /></span>
              <span class="chip">预估收入 <money-text :value="project.initiation.estimate_income" short /></span>
            </div>
            <div class="section-title">立项背景</div>
            <div class="desc-block">{{ project.initiation.background || '-' }}</div>
            <div class="section-title">立项目标</div>
            <div class="desc-block">{{ project.initiation.goal || '-' }}</div>
            <div class="section-title">风险说明</div>
            <div class="desc-block">{{ project.initiation.risk_desc || '-' }}</div>
            <div class="tag-row" style="margin-top: 16px">
              <el-button v-if="project.initiation.status === 'DRAFT' && canCreate" type="success" @click="submitInitiation">提交立项审批</el-button>
              <el-button v-if="project.initiation.instance_id" @click="openInstance(project.initiation.instance_id)">查看审批流程</el-button>
            </div>
          </div>
          <div v-else class="empty">
            该项目尚未发起立项申请。
            <el-button v-if="canCreate" link type="primary" @click="$router.push('/projects')">返回列表发起立项</el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="成员" name="members">
          <div class="toolbar">
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openMember">添加成员</el-button>
          </div>
          <el-table :data="project.members || []" size="small" border>
            <el-table-column prop="user_name" label="成员" width="140" />
            <el-table-column label="项目角色" width="120">
              <template #default="{ row }">{{ memberRoleLabel(row.role) }}</template>
            </el-table-column>
            <el-table-column label="加入时间" width="130">
              <template #default="{ row }">{{ date(row.join_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button v-if="canManage && row.role !== 'PM'" link type="danger" @click="removeMember(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="WBS" name="wbs">
          <div class="toolbar">
            <span class="muted">工作分解结构，支持多级树形与里程碑标记。</span>
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openWbs()">新增 WBS</el-button>
          </div>
          <el-table :data="wbsTree" row-key="id" :tree-props="{ children: 'children' }" size="small" border default-expand-all>
            <el-table-column prop="code" label="编码" width="100" />
            <el-table-column prop="name" label="工作项" min-width="200">
              <template #default="{ row }">
                {{ row.name }}
                <el-tag v-if="row.is_milestone" size="small" type="warning" style="margin-left: 6px">里程碑</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="owner_name" label="负责人" width="110" />
            <el-table-column label="计划开始" width="120">
              <template #default="{ row }">{{ date(row.plan_start) }}</template>
            </el-table-column>
            <el-table-column label="计划结束" width="120">
              <template #default="{ row }">{{ date(row.plan_end) }}</template>
            </el-table-column>
            <el-table-column label="进度" width="140">
              <template #default="{ row }">
                <div class="progress-line">
                  <el-progress :percentage="Number(row.progress || 0)" :stroke-width="6" :show-text="false" />
                  <span style="font-size: 12px">{{ row.progress || 0 }}%</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button v-if="canManage" link type="primary" @click="openWbs(row)">编辑</el-button>
                <el-button v-if="canManage" link type="danger" @click="removeWbs(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="任务" name="tasks">
          <div class="toolbar">
            <el-select v-model="taskFilter.status" placeholder="全部状态" clearable @change="loadTasks">
              <el-option v-for="status in ['TODO', 'DOING', 'DONE', 'BLOCKED']" :key="status" :label="STATUS_LABELS[status]" :value="status" />
            </el-select>
            <el-select v-model="taskFilter.owner_id" placeholder="全部负责人" clearable filterable @change="loadTasks">
              <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
            </el-select>
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openTask()">新增任务</el-button>
          </div>
          <el-table :data="tasks" size="small" border>
            <el-table-column prop="name" label="任务名称" min-width="180" />
            <el-table-column prop="owner_name" label="负责人" width="100" />
            <el-table-column label="计划周期" width="190">
              <template #default="{ row }"><span class="muted">{{ date(row.plan_start) }} ~ {{ date(row.plan_end) }}</span></template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><status-tag :value="row.status" /></template>
            </el-table-column>
            <el-table-column label="优先级" width="90">
              <template #default="{ row }"><status-tag :value="row.priority" :labels="PRIORITIES" /></template>
            </el-table-column>
            <el-table-column label="进度" width="130">
              <template #default="{ row }">
                <div class="progress-line">
                  <el-progress :percentage="Number(row.progress || 0)" :stroke-width="6" :show-text="false" />
                  <span style="font-size: 12px">{{ row.progress || 0 }}%</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="工时" width="110">
              <template #default="{ row }">{{ row.actual_hours || 0 }} / {{ row.estimate_hours || 0 }}h</template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button v-if="canManage" link type="primary" @click="openTask(row)">编辑</el-button>
                <el-button v-if="canManage" link type="danger" @click="removeTask(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="里程碑" name="milestones">
          <div class="toolbar">
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openMilestone">新增里程碑</el-button>
          </div>
          <el-table :data="milestones" size="small" border>
            <el-table-column prop="name" label="里程碑" min-width="180" />
            <el-table-column label="计划日期" width="120">
              <template #default="{ row }">{{ date(row.plan_date) }}</template>
            </el-table-column>
            <el-table-column label="实际完成" width="120">
              <template #default="{ row }">{{ date(row.actual_date) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><status-tag :value="row.status" /></template>
            </el-table-column>
            <el-table-column label="验收文件" min-width="140">
              <template #default="{ row }">
                <el-link v-if="row.acceptance_file?.id" type="primary" @click="downloadFile(row.acceptance_file)">{{ row.acceptance_file.name }}</el-link>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140">
              <template #default="{ row }">
                <el-button v-if="canManage && row.status !== 'DONE'" link type="success" @click="completeMilestone(row)">完成</el-button>
                <el-button v-if="canManage" link type="danger" @click="removeMilestone(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="变更" name="changes">
          <div class="toolbar">
            <span class="muted">变更需走审批流，审批通过后自动更新项目主档。</span>
            <div class="grow" />
            <el-button v-if="canChange" type="primary" :icon="Plus" @click="openChange">发起变更</el-button>
          </div>
          <el-table :data="changes" size="small" border>
            <el-table-column label="变更类型" width="110">
              <template #default="{ row }">{{ labelOf(CHANGE_TYPES, row.type) }}</template>
            </el-table-column>
            <el-table-column label="变更前" min-width="160">
              <template #default="{ row }"><span class="mono muted">{{ JSON.stringify(row.before_json || {}) }}</span></template>
            </el-table-column>
            <el-table-column label="变更后" min-width="160">
              <template #default="{ row }"><span class="mono">{{ JSON.stringify(row.after_json || {}) }}</span></template>
            </el-table-column>
            <el-table-column prop="reason" label="变更原因" min-width="180" show-overflow-tooltip />
            <el-table-column prop="applicant_name" label="申请人" width="100" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><status-tag :value="row.status" /></template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button v-if="row.instance_id" link type="primary" @click="openInstance(row.instance_id)">流程</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="问题与风险" name="issues">
          <div class="split-2">
            <div class="card">
              <div class="card-title">
                <h3>问题跟踪</h3>
                <el-button v-if="canManage" size="small" :icon="Plus" @click="openIssue()">新增问题</el-button>
              </div>
              <div v-if="!issues.length" class="empty">暂无问题</div>
              <div v-for="item in issues" :key="item.id" class="risk-item">
                <span class="risk-dot" :class="`level-${item.level}`" />
                <div style="flex: 1">
                  <div style="font-weight: 600">{{ item.title }}</div>
                  <div class="muted" style="font-size: 12.5px; margin-top: 3px">
                    {{ item.owner_name || '-' }} · 截止 {{ date(item.due_date) }} · {{ item.solution || '暂无解决方案' }}
                  </div>
                </div>
                <status-tag :value="item.status" :labels="{ OPEN: '待处理', PROCESSING: '处理中', CLOSED: '已关闭' }" />
                <el-button v-if="canManage" link type="primary" @click="openIssue(item)">编辑</el-button>
              </div>
            </div>
            <div class="card">
              <div class="card-title">
                <h3>风险登记</h3>
                <el-button v-if="canManage" size="small" :icon="Plus" @click="openRisk()">新增风险</el-button>
              </div>
              <div v-if="!risks.length" class="empty">暂无风险</div>
              <div v-for="item in risks" :key="item.id" class="risk-item">
                <span class="risk-dot" :class="`level-${item.level}`" />
                <div style="flex: 1">
                  <div style="font-weight: 600">{{ item.title }}</div>
                  <div class="muted" style="font-size: 12.5px; margin-top: 3px">
                    {{ item.owner_name || '-' }} · 截止 {{ date(item.due_date) }} · {{ item.solution || '暂无应对措施' }}
                  </div>
                </div>
                <status-tag :value="item.status" :labels="{ OPEN: '待处理', PROCESSING: '处理中', CLOSED: '已关闭' }" />
                <el-button v-if="canManage" link type="primary" @click="openRisk(item)">编辑</el-button>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="周报" name="reports">
          <div class="toolbar">
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openReport">提交周报/月报</el-button>
          </div>
          <el-timeline v-if="reports.length">
            <el-timeline-item v-for="item in reports" :key="item.id" :timestamp="`${item.period} · ${datetime(item.created_at)}`" placement="top">
              <div style="font-weight: 600">{{ item.type === 'MONTHLY' ? '月报' : '周报' }} · 进度 {{ item.progress || 0 }}% · {{ item.reporter_name }}</div>
              <div class="desc-block" style="margin-top: 8px">{{ item.content || '-' }}</div>
              <div class="muted" style="margin-top: 6px; font-size: 12.5px">问题：{{ item.issues || '-' }}</div>
              <div class="muted" style="font-size: 12.5px">下阶段计划：{{ item.next_plan || '-' }}</div>
            </el-timeline-item>
          </el-timeline>
          <div v-else class="empty">暂无周报/月报</div>
        </el-tab-pane>

        <el-tab-pane label="验收" name="acceptances">
          <div class="toolbar">
            <span class="muted">验收审批通过后自动生成计收并归档验收单。</span>
            <div class="grow" />
            <el-button v-if="canAccept" type="primary" :icon="Plus" @click="openAcceptance">提交验收</el-button>
          </div>
          <el-table :data="acceptances" size="small" border>
            <el-table-column prop="acceptor" label="验收人" width="120" />
            <el-table-column label="验收结果" width="110">
              <template #default="{ row }"><status-tag :value="row.result" :labels="{ PASS: '通过', CONDITIONAL: '有条件通过', FAIL: '未通过' }" /></template>
            </el-table-column>
            <el-table-column label="验收日期" width="120">
              <template #default="{ row }">{{ date(row.accept_date) }}</template>
            </el-table-column>
            <el-table-column label="验收金额" width="140" align="right">
              <template #default="{ row }"><money-text :value="row.accept_amount" /></template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><status-tag :value="row.status" /></template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button v-if="row.instance_id" link type="primary" @click="openInstance(row.instance_id)">流程</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="归档" name="archives">
          <div class="toolbar">
            <div class="grow" />
            <el-button v-if="canClose" type="primary" :icon="Plus" @click="openArchive">添加归档资料</el-button>
          </div>
          <el-table :data="archives" size="small" border>
            <el-table-column label="资料类型" width="140">
              <template #default="{ row }">{{ ARCHIVE_TYPES[row.doc_type] || row.doc_type }}</template>
            </el-table-column>
            <el-table-column label="文件" min-width="220">
              <template #default="{ row }">
                <el-link v-if="row.file?.id" type="primary" @click="downloadFile(row.file)">{{ row.file.name }}</el-link>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="archived_by_name" label="归档人" width="120" />
            <el-table-column label="归档时间" width="160">
              <template #default="{ row }">{{ datetime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="基线" name="baseline">
          <el-table :data="baseline" size="small" border>
            <el-table-column prop="name" label="任务" min-width="180" />
            <el-table-column prop="wbs_code" label="WBS 编码" width="110" />
            <el-table-column label="基线计划开始" width="140">
              <template #default="{ row }">{{ date(row.plan_start) }}</template>
            </el-table-column>
            <el-table-column label="基线计划结束" width="140">
              <template #default="{ row }">{{ date(row.plan_end) }}</template>
            </el-table-column>
            <el-table-column prop="estimate_hours" label="计划工时" width="110" />
            <el-table-column prop="baseline_version" label="基线版本" width="100" />
            <el-table-column label="生成时间" width="160">
              <template #default="{ row }">{{ datetime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 编辑项目 -->
    <el-dialog v-model="editVisible" title="编辑项目" width="680px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="92px">
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="项目名称" required><el-input v-model="editForm.name" maxlength="128" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="项目类型">
              <el-select v-model="editForm.type" style="width: 100%">
                <el-option v-for="(label, value) in PROJECT_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="项目经理">
              <el-select v-model="editForm.manager_id" filterable style="width: 100%">
                <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="责任部门">
              <el-select v-model="editForm.dept_id" filterable style="width: 100%">
                <el-option v-for="dept in deptOptions" :key="dept.id" :label="dept.label" :value="dept.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="计划开始"><el-date-picker v-model="editForm.plan_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计划结束"><el-date-picker v-model="editForm.plan_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="预算金额"><el-input-number v-model="editForm.budget_amount" :min="0" :precision="2" controls-position="right" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同金额"><el-input-number v-model="editForm.contract_amount" :min="0" :precision="2" controls-position="right" style="width: 100%" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="密级">
          <el-select v-model="editForm.secret_level" style="width: 100%">
            <el-option v-for="(label, value) in SECRET_LEVELS" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目描述"><el-input v-model="editForm.description" type="textarea" :rows="3" maxlength="1000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveProject">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 关闭项目 -->
    <el-dialog v-model="closeVisible" title="关闭项目" width="560px">
      <div class="section-title" style="margin-top: 0">关闭校验</div>
      <el-alert v-if="closeCheck.can_close" type="success" :closable="false" title="校验通过，可以正常关闭项目" />
      <el-alert v-else type="warning" :closable="false" title="存在阻塞项，需处理或强制关闭">
        <div v-for="(item, index) in closeCheck.blockers" :key="index">· {{ item }}</div>
      </el-alert>
      <el-form style="margin-top: 14px" label-width="90px">
        <el-form-item label="强制关闭">
          <el-switch v-model="closeForm.force" :disabled="closeCheck.can_close" />
          <span class="form-tip" style="margin-left: 10px">强制关闭需具备强制关闭权限并填写原因</span>
        </el-form-item>
        <el-form-item label="关闭原因">
          <el-input v-model="closeForm.reason" type="textarea" :rows="3" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="closeVisible = false">取消</el-button>
          <el-button type="danger" :loading="saving" @click="submitClose">确认关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- WBS -->
    <el-dialog v-model="wbsVisible" :title="wbsForm.id ? '编辑 WBS' : '新增 WBS'" width="620px">
      <el-form :model="wbsForm" label-width="92px">
        <el-form-item label="工作项名称" required><el-input v-model="wbsForm.name" maxlength="200" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="编码"><el-input v-model="wbsForm.code" maxlength="32" /></el-form-item></el-col>
          <el-col :span="8">
            <el-form-item label="上级">
              <el-select v-model="wbsForm.parent_id" clearable style="width: 100%">
                <el-option v-for="item in wbsItems" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8"><el-form-item label="排序"><el-input-number v-model="wbsForm.sort" :min="0" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="wbsForm.owner_id" filterable clearable style="width: 100%">
                <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="里程碑"><el-switch v-model="wbsForm.is_milestone" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="计划开始"><el-date-picker v-model="wbsForm.plan_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="计划结束"><el-date-picker v-model="wbsForm.plan_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="进度"><el-slider v-model="wbsForm.progress" :max="100" show-input /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="wbsVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveWbs">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 任务 -->
    <el-dialog v-model="taskVisible" :title="taskForm.id ? '编辑任务' : '新增任务'" width="680px">
      <el-form :model="taskForm" label-width="92px">
        <el-form-item label="任务名称" required><el-input v-model="taskForm.name" maxlength="200" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="所属 WBS">
              <el-select v-model="taskForm.wbs_id" clearable style="width: 100%">
                <el-option v-for="item in wbsItems" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="taskForm.owner_id" filterable clearable style="width: 100%">
                <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="计划开始"><el-date-picker v-model="taskForm.plan_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="计划结束"><el-date-picker v-model="taskForm.plan_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="实际开始"><el-date-picker v-model="taskForm.actual_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="实际结束"><el-date-picker v-model="taskForm.actual_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="taskForm.status" style="width: 100%">
                <el-option v-for="status in ['TODO', 'DOING', 'DONE', 'BLOCKED']" :key="status" :label="STATUS_LABELS[status]" :value="status" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="taskForm.priority" style="width: 100%">
                <el-option v-for="(label, value) in PRIORITIES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8"><el-form-item label="预估工时"><el-input-number v-model="taskForm.estimate_hours" :min="0" :precision="1" controls-position="right" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="实际工时"><el-input-number v-model="taskForm.actual_hours" :min="0" :precision="1" controls-position="right" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="进度"><el-slider v-model="taskForm.progress" :max="100" show-input /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="taskVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveTask">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 里程碑 -->
    <el-dialog v-model="milestoneVisible" title="新增里程碑" width="480px">
      <el-form :model="milestoneForm" label-width="90px">
        <el-form-item label="里程碑名称" required><el-input v-model="milestoneForm.name" maxlength="200" /></el-form-item>
        <el-form-item label="计划日期" required><el-date-picker v-model="milestoneForm.plan_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="milestoneVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveMilestone">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="completeVisible" title="完成里程碑" width="480px">
      <el-form :model="completeForm" label-width="90px">
        <el-form-item label="实际日期"><el-date-picker v-model="completeForm.actual_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
        <el-form-item label="验收文件"><file-upload v-model="completeForm.acceptance_file_id" biz-type="PROJECT" :biz-id="project.id" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="completeVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitMilestoneComplete">确认完成</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 变更 -->
    <el-dialog v-model="changeVisible" title="发起项目变更" width="560px">
      <el-form :model="changeForm" label-width="90px">
        <el-form-item label="变更类型">
          <el-select v-model="changeForm.type" style="width: 100%">
            <el-option v-for="(label, value) in CHANGE_TYPES" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <template v-if="changeForm.type === 'BUDGET'">
          <el-form-item label="变更后预算" required>
            <el-input-number v-model="changeForm.after.budget_amount" :min="0" :precision="2" controls-position="right" style="width: 100%" />
          </el-form-item>
        </template>
        <template v-else-if="changeForm.type === 'SCHEDULE'">
          <el-form-item label="计划开始" required><el-date-picker v-model="changeForm.after.plan_start" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          <el-form-item label="计划结束" required><el-date-picker v-model="changeForm.after.plan_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="变更后名称" required><el-input v-model="changeForm.after.name" maxlength="128" /></el-form-item>
          <el-form-item label="变更后描述"><el-input v-model="changeForm.after.description" type="textarea" :rows="3" maxlength="2000" /></el-form-item>
        </template>
        <el-form-item label="变更原因" required><el-input v-model="changeForm.reason" type="textarea" :rows="3" maxlength="1000" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="changeVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveChange">提交审批</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 问题/风险 -->
    <el-dialog v-model="issueVisible" :title="issueMode === 'risk' ? '风险登记' : '问题跟踪'" width="520px">
      <el-form :model="issueForm" label-width="90px">
        <el-form-item label="标题" required><el-input v-model="issueForm.title" maxlength="200" /></el-form-item>
        <el-form-item label="等级">
          <el-select v-model="issueForm.level" style="width: 100%">
            <el-option v-for="(label, value) in PRIORITIES" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="issueForm.owner_id" filterable clearable style="width: 100%">
            <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="issueForm.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="issueForm.status" style="width: 100%">
            <el-option label="待处理" value="OPEN" />
            <el-option label="处理中" value="PROCESSING" />
            <el-option label="已关闭" value="CLOSED" />
          </el-select>
        </el-form-item>
        <el-form-item label="解决方案"><el-input v-model="issueForm.solution" type="textarea" :rows="3" maxlength="1000" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="issueVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveIssue">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 周报 -->
    <el-dialog v-model="reportVisible" title="提交周报/月报" width="600px">
      <el-form :model="reportForm" label-width="90px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="报告类型">
              <el-select v-model="reportForm.type" style="width: 100%">
                <el-option label="周报" value="WEEKLY" />
                <el-option label="月报" value="MONTHLY" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8"><el-form-item label="期间" required><el-input v-model="reportForm.period" placeholder="如 2026-W45" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="进度"><el-input-number v-model="reportForm.progress" :min="0" :max="100" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="本周进展" required><el-input v-model="reportForm.content" type="textarea" :rows="3" maxlength="2000" /></el-form-item>
        <el-form-item label="存在问题"><el-input v-model="reportForm.issues" type="textarea" :rows="2" maxlength="2000" /></el-form-item>
        <el-form-item label="下阶段计划"><el-input v-model="reportForm.next_plan" type="textarea" :rows="2" maxlength="2000" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="reportVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveReport">提交</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 验收 -->
    <el-dialog v-model="acceptanceVisible" title="提交项目验收" width="600px">
      <el-form :model="acceptanceForm" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="验收人" required><el-input v-model="acceptanceForm.acceptor" maxlength="128" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="验收结果">
              <el-select v-model="acceptanceForm.result" style="width: 100%">
                <el-option label="通过" value="PASS" />
                <el-option label="有条件通过" value="CONDITIONAL" />
                <el-option label="未通过" value="FAIL" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="验收日期"><el-date-picker v-model="acceptanceForm.accept_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="验收金额">
              <el-input-number v-model="acceptanceForm.accept_amount" :min="0" :precision="2" :disabled="acceptanceForm.result === 'FAIL'" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="签署文件" required>
          <file-upload v-model="acceptanceForm.sign_file_id" biz-type="ACCEPTANCE" :biz-id="project.id" />
          <div class="form-tip">验收必须上传客户签署文件，审批通过后作为归档依据。</div>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="acceptanceForm.remark" type="textarea" :rows="3" maxlength="1000" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="acceptanceVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveAcceptance">提交验收审批</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 归档 -->
    <el-dialog v-model="archiveVisible" title="添加归档资料" width="500px">
      <el-form :model="archiveForm" label-width="90px">
        <el-form-item label="资料类型">
          <el-select v-model="archiveForm.doc_type" style="width: 100%">
            <el-option v-for="(label, value) in ARCHIVE_TYPES" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件">
          <file-upload v-model="archiveForm.file_id" biz-type="ARCHIVE" :biz-id="project.id" :clearable="false" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="archiveVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveArchive">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 成员 -->
    <el-dialog v-model="memberVisible" title="添加项目成员" width="460px">
      <el-form :model="memberForm" label-width="90px">
        <el-form-item label="成员" required>
          <el-select v-model="memberForm.user_id" filterable style="width: 100%">
            <el-option v-for="user in meta.userOptions" :key="user.id" :label="`${user.real_name}（${user.username}）`" :value="user.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目角色">
          <el-radio-group v-model="memberForm.role">
            <el-radio value="MEMBER">成员</el-radio>
            <el-radio value="OBSERVER">观察者</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="memberVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveMember">添加</el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="instanceVisible" size="760px" title="审批流程" destroy-on-close>
      <approval-panel v-if="instanceId" :instance-id="instanceId" @changed="onInstanceChanged" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Edit, Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { fileApi, projectApi } from '@/api'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import ChartBox from '@/components/ChartBox.vue'
import FileUpload from '@/components/FileUpload.vue'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date, datetime, moneyShort, percent, rawPercent, today } from '@/utils/format'
import { CHANGE_TYPES, PRIORITIES, PROJECT_STAGES, PROJECT_TYPES, SECRET_LEVELS, STATUS_LABELS, labelOf } from '@/utils/constants'
import { saveBlob } from '@/utils/download'

const ARCHIVE_TYPES = {
  INITIATION: '立项资料',
  CONTRACT: '合同文本',
  ACCEPTANCE: '验收单',
  SETTLEMENT: '结算资料',
  SUMMARY: '复盘总结',
  OTHER: '其他资料'
}
const MEMBER_ROLES = { PM: '项目经理', MEMBER: '成员', OBSERVER: '观察者' }

const route = useRoute()
const auth = useAuthStore()
const meta = useMetaStore()
const projectId = computed(() => Number(route.params.id))

const loading = ref(false)
const saving = ref(false)
const activeTab = ref('overview')
const project = ref({})
const pnl = ref({})
const deviation = ref({})
const wbsItems = ref([])
const wbsTree = ref([])
const tasks = ref([])
const milestones = ref([])
const changes = ref([])
const issues = ref([])
const risks = ref([])
const reports = ref([])
const acceptances = ref([])
const archives = ref([])
const baseline = ref([])
const taskFilter = ref({ status: '', owner_id: null })

const canManage = computed(() => auth.can('project:manage'))
const canCreate = computed(() => auth.can('project:create'))
const canChange = computed(() => auth.can('project:change'))
const canAccept = computed(() => auth.can('project:acceptance'))
const canClose = computed(() => auth.can('project:close'))

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

const pnlTrendOption = computed(() => {
  const rows = pnl.value.trend || []
  return {
    tooltip: { trigger: 'axis', valueFormatter: (value) => `¥${Number(value || 0).toLocaleString('zh-CN')}` },
    legend: { top: 0, data: ['计收', '付款', '报销', '毛利'] },
    grid: { left: 12, right: 18, top: 44, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: rows.map((item) => item.period) },
    yAxis: { type: 'value', axisLabel: { formatter: (value) => moneyShort(value) }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [
      { name: '计收', type: 'bar', barWidth: 12, itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, data: rows.map((item) => item.revenue) },
      { name: '付款', type: 'bar', barWidth: 12, itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] }, data: rows.map((item) => item.cost) },
      { name: '报销', type: 'bar', barWidth: 12, itemStyle: { color: '#ef4444', borderRadius: [4, 4, 0, 0] }, data: rows.map((item) => item.expense) },
      {
        name: '毛利',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        lineStyle: { color: '#16a34a', width: 2 },
        itemStyle: { color: '#16a34a' },
        data: rows.map((item) => item.gross_profit)
      }
    ]
  }
})

function memberRoleLabel(role) {
  return MEMBER_ROLES[role] || role || '-'
}

async function loadProject() {
  project.value = await projectApi.detail(projectId.value)
  deviation.value = project.value.deviation || {}
}

async function loadPnl() {
  try {
    pnl.value = await projectApi.pnl(projectId.value)
  } catch {
    pnl.value = {}
  }
}

async function loadWbs() {
  const data = await projectApi.wbs(projectId.value)
  wbsItems.value = data.items || []
  wbsTree.value = data.tree || []
}

async function loadTasks() {
  const params = {}
  if (taskFilter.value.status) params.status = taskFilter.value.status
  if (taskFilter.value.owner_id) params.owner_id = taskFilter.value.owner_id
  tasks.value = await projectApi.tasks(projectId.value, params)
}

async function loadMilestones() {
  milestones.value = await projectApi.milestones(projectId.value)
}

async function loadChanges() {
  changes.value = await projectApi.changes(projectId.value)
}

async function loadIssues() {
  ;[issues.value, risks.value] = await Promise.all([
    projectApi.issues(projectId.value),
    projectApi.risks(projectId.value)
  ])
}

async function loadReports() {
  reports.value = await projectApi.reports(projectId.value)
}

async function loadAcceptances() {
  acceptances.value = await projectApi.acceptances(projectId.value)
}

async function loadArchives() {
  const [archiveRows, baselineRows] = await Promise.all([
    projectApi.archives(projectId.value),
    projectApi.baseline(projectId.value)
  ])
  archives.value = archiveRows || []
  baseline.value = baselineRows || []
}

async function loadAll() {
  loading.value = true
  try {
    await loadProject()
    await Promise.allSettled([
      loadPnl(),
      loadWbs(),
      loadTasks(),
      loadMilestones(),
      loadChanges(),
      loadIssues(),
      loadReports(),
      loadAcceptances(),
      loadArchives()
    ])
  } finally {
    loading.value = false
  }
}

/* ---------------------------------------------------------------- 主档操作 */
const editVisible = ref(false)
const editForm = ref({})

function openEditProject() {
  editForm.value = {
    name: project.value.name,
    type: project.value.type,
    manager_id: project.value.manager_id,
    dept_id: project.value.dept_id,
    plan_start: project.value.plan_start,
    plan_end: project.value.plan_end,
    budget_amount: Number(project.value.budget_amount || 0),
    contract_amount: Number(project.value.contract_amount || 0),
    secret_level: project.value.secret_level,
    description: project.value.description || '',
    version: project.value.version
  }
  editVisible.value = true
}

async function saveProject() {
  if (!editForm.value.name) {
    ElMessage.warning('请输入项目名称')
    return
  }
  saving.value = true
  try {
    await projectApi.update(projectId.value, editForm.value)
    ElMessage.success('项目已更新')
    editVisible.value = false
    await loadProject()
  } finally {
    saving.value = false
  }
}

async function doAction(action) {
  const labels = { confirmPlan: '确认项目计划并生成基线', startExecution: '进入执行阶段', archive: '归档项目' }
  try {
    await ElMessageBox.confirm(`确认${labels[action]}吗？`, '操作确认', { type: 'warning' })
  } catch {
    return
  }
  await projectApi[action](projectId.value)
  ElMessage.success(`${labels[action]}成功`)
  await loadAll()
}

const closeVisible = ref(false)
const closeCheck = ref({ blockers: [], can_close: false })
const closeForm = ref({ force: false, reason: '' })

async function openClose() {
  closeCheck.value = await projectApi.closeCheck(projectId.value)
  closeForm.value = { force: false, reason: '' }
  closeVisible.value = true
}

async function submitClose() {
  if (closeForm.value.force && (!closeForm.value.reason || closeForm.value.reason.trim().length < 5)) {
    ElMessage.warning('强制关闭需填写不少于 5 个字的关闭原因')
    return
  }
  saving.value = true
  try {
    await projectApi.close(projectId.value, closeForm.value)
    ElMessage.success('项目已关闭')
    closeVisible.value = false
    await loadAll()
  } finally {
    saving.value = false
  }
}

async function submitInitiation() {
  if (!project.value.initiation?.id) return
  await projectApi.submitInitiation(project.value.initiation.id)
  ElMessage.success('立项审批已提交')
  await loadProject()
}

/* ---------------------------------------------------------------- 成员 */
const memberVisible = ref(false)
const memberForm = ref({ user_id: null, role: 'MEMBER' })

function openMember() {
  memberForm.value = { user_id: null, role: 'MEMBER' }
  memberVisible.value = true
}

async function saveMember() {
  if (!memberForm.value.user_id) {
    ElMessage.warning('请选择成员')
    return
  }
  saving.value = true
  try {
    await projectApi.addMember(projectId.value, memberForm.value)
    ElMessage.success('成员已添加')
    memberVisible.value = false
    await loadProject()
  } finally {
    saving.value = false
  }
}

async function removeMember(row) {
  try {
    await ElMessageBox.confirm(`确认移除成员「${row.user_name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await projectApi.removeMember(projectId.value, row.id)
  ElMessage.success('成员已移除')
  await loadProject()
}

/* ---------------------------------------------------------------- WBS */
const wbsVisible = ref(false)
const wbsForm = ref({})

function openWbs(row = null) {
  wbsForm.value = row
    ? {
        id: row.id,
        name: row.name,
        code: row.code || '',
        parent_id: row.parent_id,
        owner_id: row.owner_id,
        plan_start: row.plan_start,
        plan_end: row.plan_end,
        progress: Number(row.progress || 0),
        is_milestone: Boolean(row.is_milestone),
        sort: Number(row.sort || 0)
      }
    : { name: '', code: '', parent_id: null, owner_id: auth.user.id, plan_start: '', plan_end: '', progress: 0, is_milestone: false, sort: wbsItems.value.length }
  wbsVisible.value = true
}

async function saveWbs() {
  if (!wbsForm.value.name) {
    ElMessage.warning('请输入工作项名称')
    return
  }
  saving.value = true
  try {
    const { id, ...payload } = wbsForm.value
    if (id) await projectApi.updateWbs(id, payload)
    else await projectApi.createWbs(projectId.value, payload)
    ElMessage.success('WBS 已保存')
    wbsVisible.value = false
    await Promise.all([loadWbs(), loadProject()])
  } finally {
    saving.value = false
  }
}

async function removeWbs(row) {
  try {
    await ElMessageBox.confirm(`确认删除 WBS「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await projectApi.deleteWbs(row.id)
  ElMessage.success('WBS 已删除')
  await loadWbs()
}

/* ---------------------------------------------------------------- 任务 */
const taskVisible = ref(false)
const taskForm = ref({})

function openTask(row = null) {
  taskForm.value = row
    ? { ...row }
    : {
        name: '',
        wbs_id: wbsItems.value[0]?.id || null,
        owner_id: auth.user.id,
        plan_start: '',
        plan_end: '',
        actual_start: '',
        actual_end: '',
        progress: 0,
        status: 'TODO',
        priority: 'MEDIUM',
        estimate_hours: 0,
        actual_hours: 0
      }
  taskVisible.value = true
}

async function saveTask() {
  if (!taskForm.value.name) {
    ElMessage.warning('请输入任务名称')
    return
  }
  saving.value = true
  try {
    const { id, ...payload } = taskForm.value
    if (id) await projectApi.updateTask(id, payload)
    else await projectApi.createTask(projectId.value, payload)
    ElMessage.success('任务已保存')
    taskVisible.value = false
    await Promise.all([loadTasks(), loadProject()])
  } finally {
    saving.value = false
  }
}

async function removeTask(row) {
  try {
    await ElMessageBox.confirm(`确认删除任务「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await projectApi.deleteTask(row.id)
  ElMessage.success('任务已删除')
  await Promise.all([loadTasks(), loadProject()])
}

/* ---------------------------------------------------------------- 里程碑 */
const milestoneVisible = ref(false)
const milestoneForm = ref({ name: '', plan_date: '' })
const completeVisible = ref(false)
const completeTarget = ref(null)
const completeForm = ref({ actual_date: '', acceptance_file_id: null })

function openMilestone() {
  milestoneForm.value = { name: '', plan_date: today() }
  milestoneVisible.value = true
}

async function saveMilestone() {
  if (!milestoneForm.value.name || !milestoneForm.value.plan_date) {
    ElMessage.warning('请填写里程碑名称与计划日期')
    return
  }
  saving.value = true
  try {
    await projectApi.createMilestone(projectId.value, milestoneForm.value)
    ElMessage.success('里程碑已创建')
    milestoneVisible.value = false
    await Promise.all([loadMilestones(), loadPnl()])
  } finally {
    saving.value = false
  }
}

function completeMilestone(row) {
  completeTarget.value = row
  completeForm.value = { actual_date: today(), acceptance_file_id: null }
  completeVisible.value = true
}

async function submitMilestoneComplete() {
  saving.value = true
  try {
    await projectApi.completeMilestone(completeTarget.value.id, completeForm.value)
    ElMessage.success('里程碑已完成')
    completeVisible.value = false
    await Promise.all([loadMilestones(), loadPnl()])
  } finally {
    saving.value = false
  }
}

async function removeMilestone(row) {
  try {
    await ElMessageBox.confirm(`确认删除里程碑「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await projectApi.deleteMilestone(row.id)
  ElMessage.success('里程碑已删除')
  await Promise.all([loadMilestones(), loadPnl()])
}

/* ---------------------------------------------------------------- 变更 */
const changeVisible = ref(false)
const changeForm = ref({ type: 'BUDGET', after: {}, reason: '' })

function openChange() {
  changeForm.value = {
    type: 'BUDGET',
    after: { budget_amount: Number(project.value.budget_amount || 0) },
    reason: ''
  }
  changeVisible.value = true
}

async function saveChange() {
  if (!changeForm.value.reason || changeForm.value.reason.trim().length < 5) {
    ElMessage.warning('变更原因不得少于 5 个字')
    return
  }
  saving.value = true
  try {
    await projectApi.createChange(projectId.value, changeForm.value)
    ElMessage.success('变更已提交审批')
    changeVisible.value = false
    await loadChanges()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 问题 / 风险 */
const issueVisible = ref(false)
const issueMode = ref('issue')
const issueForm = ref({})

function openIssue(row = null) {
  issueMode.value = 'issue'
  issueForm.value = row
    ? { ...row }
    : { title: '', level: 'MEDIUM', owner_id: auth.user.id, due_date: today(), status: 'OPEN', solution: '' }
  issueVisible.value = true
}

function openRisk(row = null) {
  issueMode.value = 'risk'
  issueForm.value = row
    ? { ...row }
    : { title: '', level: 'MEDIUM', owner_id: auth.user.id, due_date: today(), status: 'OPEN', solution: '' }
  issueVisible.value = true
}

async function saveIssue() {
  if (!issueForm.value.title) {
    ElMessage.warning('请输入标题')
    return
  }
  saving.value = true
  try {
    const isRisk = issueMode.value === 'risk'
    if (issueForm.value.id) {
      if (isRisk) await projectApi.updateRisk(issueForm.value.id, issueForm.value)
      else await projectApi.updateIssue(issueForm.value.id, issueForm.value)
    } else if (isRisk) {
      await projectApi.createRisk(projectId.value, issueForm.value)
    } else {
      await projectApi.createIssue(projectId.value, issueForm.value)
    }
    ElMessage.success('已保存')
    issueVisible.value = false
    await loadIssues()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 周报 */
const reportVisible = ref(false)
const reportForm = ref({})

function openReport() {
  reportForm.value = {
    type: 'WEEKLY',
    period: dayjs().format('YYYY-[W]WW'),
    progress: Number(project.value.progress || 0),
    content: '',
    issues: '',
    next_plan: ''
  }
  reportVisible.value = true
}

async function saveReport() {
  if (!reportForm.value.period || !reportForm.value.content) {
    ElMessage.warning('请填写报告期间与本周进展')
    return
  }
  saving.value = true
  try {
    await projectApi.createReport(projectId.value, reportForm.value)
    ElMessage.success('报告已提交')
    reportVisible.value = false
    await loadReports()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 验收 */
const acceptanceVisible = ref(false)
const acceptanceForm = ref({})

function openAcceptance() {
  acceptanceForm.value = {
    acceptor: project.value.customer_name || '',
    result: 'PASS',
    sign_file_id: null,
    accept_date: today(),
    accept_amount: Number(project.value.contract_amount || 0),
    remark: ''
  }
  acceptanceVisible.value = true
}

async function saveAcceptance() {
  if (!acceptanceForm.value.acceptor) {
    ElMessage.warning('请填写验收人')
    return
  }
  if (!acceptanceForm.value.sign_file_id) {
    ElMessage.warning('请上传验收签署文件')
    return
  }
  saving.value = true
  try {
    await projectApi.createAcceptance(projectId.value, acceptanceForm.value)
    ElMessage.success('验收已提交审批')
    acceptanceVisible.value = false
    await loadAcceptances()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 归档 */
const archiveVisible = ref(false)
const archiveForm = ref({ doc_type: 'ACCEPTANCE', file_id: null })

function openArchive() {
  archiveForm.value = { doc_type: 'ACCEPTANCE', file_id: null }
  archiveVisible.value = true
}

async function saveArchive() {
  if (!archiveForm.value.file_id) {
    ElMessage.warning('请上传归档文件')
    return
  }
  saving.value = true
  try {
    await projectApi.addArchive(projectId.value, archiveForm.value)
    ElMessage.success('归档资料已保存')
    archiveVisible.value = false
    await loadArchives()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 审批抽屉 */
const instanceVisible = ref(false)
const instanceId = ref(null)

function openInstance(id) {
  instanceId.value = id
  instanceVisible.value = true
}

async function onInstanceChanged() {
  await loadAll()
}

async function downloadFile(file) {
  const response = await fileApi.download(file.id)
  saveBlob(response, file.name)
}

onMounted(async () => {
  await meta.ensure()
  await loadAll()
})
</script>

<style scoped>
.detail-hero h2 {
  margin: 0 0 6px;
}
</style>

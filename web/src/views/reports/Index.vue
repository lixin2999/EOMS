<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>报表中心</h2>
        <p>经营总览、营收、现金流、利润、项目损益、供应商支出与审批效率七类报表，支持在线查看、Excel/PDF 导出与月度快照。</p>
      </div>
      <div class="tag-row">
        <el-button v-if="auth.can('report:export')" :icon="Download" :loading="exporting" @click="exportReport('excel')">
          导出 Excel
        </el-button>
        <el-button v-if="auth.can('report:export')" :icon="Document" :loading="exporting" @click="exportReport('pdf')">
          导出 PDF
        </el-button>
        <el-button v-if="auth.can('report:snapshot')" type="primary" :icon="Camera" @click="generateSnapshot">
          生成快照
        </el-button>
      </div>
    </div>

    <div class="card" style="padding: 14px 18px">
      <el-radio-group v-model="code" @change="onCodeChange">
        <el-radio-button v-for="(label, value) in REPORT_NAMES" :key="value" :value="value">{{ label }}</el-radio-button>
      </el-radio-group>
    </div>

    <div class="card">
      <div class="toolbar">
        <template v-if="code === 'OVERVIEW'">
          <span class="muted">统计年度</span>
          <el-date-picker v-model="filters.year" type="year" value-format="YYYY" style="width: 130px" @change="load" />
        </template>
        <template v-else>
          <span class="muted">统计区间</span>
          <el-date-picker
            v-model="filters.start"
            type="month"
            value-format="YYYY-MM"
            placeholder="开始期间"
            style="width: 140px"
          />
          <span class="muted">至</span>
          <el-date-picker
            v-model="filters.end"
            type="month"
            value-format="YYYY-MM"
            placeholder="结束期间"
            style="width: 140px"
          />
        </template>
        <el-select
          v-if="['REVENUE', 'PROFIT'].includes(code)"
          v-model="filters.group_by"
          placeholder="分组维度"
          style="width: 150px"
        >
          <el-option label="按期间" value="period" />
          <el-option label="按项目" value="project" />
          <el-option v-if="code === 'REVENUE'" label="按客户" value="customer" />
        </el-select>
        <el-select
          v-if="['CASHFLOW', 'PROFIT', 'PROJECT_PNL'].includes(code)"
          v-model="filters.project_id"
          placeholder="全部项目"
          clearable
          filterable
          style="width: 220px"
        >
          <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="load">查询</el-button>
        <el-button :icon="Refresh" @click="resetFilters">重置</el-button>
        <div class="grow" />
        <span class="muted">数据口径：计收 − 付款 − 报销；现金流：收款 −（已付款 PAYMENT + 已付款 EXPENSE）</span>
      </div>
    </div>

    <div v-loading="loading" style="min-height: 320px">
      <!-- 经营总览 -->
      <template v-if="code === 'OVERVIEW'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">确认营收</div>
            <div class="stat-value small"><money-text :value="data.revenue" symbol /></div>
            <div class="stat-foot">{{ data.year }} 年度累计计收</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">总成本</div>
            <div class="stat-value small"><money-text :value="data.cost" symbol /></div>
            <div class="stat-foot">付款 {{ moneyShort(data.payment) }} · 报销 {{ moneyShort(data.expense) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">毛利 / 毛利率</div>
            <div class="stat-value small"><money-text :value="data.gross_profit" :colorize="true" symbol /></div>
            <div class="stat-foot">毛利率 {{ rawPercent(data.gross_margin) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">项目数量</div>
            <div class="stat-value">{{ data.project_count || 0 }}</div>
            <div class="stat-foot">进行中 / 待启动 / 暂停</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">收款总额</div>
            <div class="stat-value small"><money-text :value="data.receipt" symbol /></div>
            <div class="stat-foot">计入现金流流入</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">应收账款余额</div>
            <div class="stat-value small"><money-text :value="data.receivable_balance" :colorize="true" symbol /></div>
            <div class="stat-foot">营收 − 收款</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">应付账款余额</div>
            <div class="stat-value small"><money-text :value="data.payable_balance" symbol /></div>
            <div class="stat-foot">合同额 − 已付款</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">现金净额</div>
            <div class="stat-value small"><money-text :value="cashNet" :colorize="true" symbol /></div>
            <div class="stat-foot">收款 − 付款 − 报销</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>月度经营趋势</h3></div>
          <chart-box :option="overviewOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>月度明细</h3></div>
          <el-table :data="data.monthly || []" size="small" border>
            <el-table-column prop="period" label="期间" width="110" class-name="mono" />
            <el-table-column label="计收营收" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.revenue" /></template>
            </el-table-column>
            <el-table-column label="付款" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.payment" /></template>
            </el-table-column>
            <el-table-column label="报销" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.expense" /></template>
            </el-table-column>
            <el-table-column label="成本合计" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.cost" /></template>
            </el-table-column>
            <el-table-column label="毛利" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.profit" colorize /></template>
            </el-table-column>
            <el-table-column label="收款" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.receipt" /></template>
            </el-table-column>
            <el-table-column label="现金流净额" width="150" align="right">
              <template #default="{ row }">
                <money-text :value="Number(row.cash_in || 0) - Number(row.cash_out || 0)" colorize />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 营收报表 -->
      <template v-else-if="code === 'REVENUE'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">区间确认营收</div>
            <div class="stat-value small"><money-text :value="data.total" symbol /></div>
            <div class="stat-foot">{{ data.start }} ~ {{ data.end }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">确认笔数</div>
            <div class="stat-value">{{ revenueCount }}</div>
            <div class="stat-foot">已确认计收单数</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">单笔均值</div>
            <div class="stat-value small"><money-text :value="revenueAverage" symbol /></div>
            <div class="stat-foot">区间营收 / 笔数</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">分组维度</div>
            <div class="stat-value small">{{ groupByLabel }}</div>
            <div class="stat-foot">可在筛选栏切换</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>营收分布</h3></div>
          <chart-box :option="revenueOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>营收明细</h3></div>
          <el-table :data="data.items || []" size="small" border>
            <el-table-column :label="groupByLabel" min-width="220">
              <template #default="{ row }">{{ revenueDimension(row) }}</template>
            </el-table-column>
            <el-table-column v-if="filters.group_by === 'period'" prop="period" label="期间" width="120" class-name="mono" />
            <el-table-column label="确认金额" width="180" align="right">
              <template #default="{ row }"><money-text :value="row.amount" symbol /></template>
            </el-table-column>
            <el-table-column prop="count" label="笔数" width="100" align="right" />
          </el-table>
        </div>
      </template>

      <!-- 现金流量表 -->
      <template v-else-if="code === 'CASHFLOW'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">现金流入</div>
            <div class="stat-value small"><money-text :value="data.total_inflow" symbol /></div>
            <div class="stat-foot">客户收款合计</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">现金流出</div>
            <div class="stat-value small"><money-text :value="data.total_outflow" symbol /></div>
            <div class="stat-foot">已付款 + 已付款报销</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">现金净额</div>
            <div class="stat-value small"><money-text :value="data.net" :colorize="true" symbol /></div>
            <div class="stat-foot">{{ data.start }} ~ {{ data.end }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">净现金流率</div>
            <div class="stat-value">{{ cashflowRate }}</div>
            <div class="stat-foot">净额 / 流入</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>月度现金流量</h3></div>
          <chart-box :option="cashflowOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>现金流量明细</h3></div>
          <el-table :data="data.items || []" size="small" border>
            <el-table-column prop="period" label="期间" width="120" class-name="mono" />
            <el-table-column label="流入" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.inflow" /></template>
            </el-table-column>
            <el-table-column label="流出" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.outflow" /></template>
            </el-table-column>
            <el-table-column label="净额" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.net" colorize /></template>
            </el-table-column>
            <el-table-column label="累计净额" width="170" align="right">
              <template #default="{ row }"><money-text :value="row.cumulative" colorize /></template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 利润表 -->
      <template v-else-if="code === 'PROFIT'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">营业收入</div>
            <div class="stat-value small"><money-text :value="data.revenue" symbol /></div>
            <div class="stat-foot">{{ data.start }} ~ {{ data.end }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">营业成本</div>
            <div class="stat-value small"><money-text :value="data.cost" symbol /></div>
            <div class="stat-foot">付款 + 报销</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">利润总额</div>
            <div class="stat-value small"><money-text :value="data.profit" :colorize="true" symbol /></div>
            <div class="stat-foot">收入 − 成本</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">利润率</div>
            <div class="stat-value" :style="{ color: Number(data.profit || 0) < 0 ? '#dc2626' : undefined }">
              {{ rawPercent(data.margin) }}
            </div>
            <div class="stat-foot">利润 / 收入</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>{{ filters.group_by === 'project' ? '项目利润排行' : '月度利润趋势' }}</h3></div>
          <chart-box :option="profitOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>利润明细</h3></div>
          <el-table :data="data.items || []" size="small" border>
            <el-table-column :label="filters.group_by === 'project' ? '项目' : '期间'" min-width="200">
              <template #default="{ row }">
                <template v-if="filters.group_by === 'project'">{{ projectName(row.project_id) }}</template>
                <span v-else class="mono">{{ row.period }}</span>
              </template>
            </el-table-column>
            <el-table-column label="营业收入" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.revenue" /></template>
            </el-table-column>
            <el-table-column label="营业成本" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.cost" /></template>
            </el-table-column>
            <el-table-column label="利润" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.profit" colorize /></template>
            </el-table-column>
            <el-table-column label="利润率" width="120" align="right">
              <template #default="{ row }">
                {{ row.margin !== undefined ? rawPercent(row.margin) : rawPercent(row.revenue ? (row.profit / row.revenue) * 100 : 0) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 项目损益 -->
      <template v-else-if="code === 'PROJECT_PNL'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">项目数量</div>
            <div class="stat-value">{{ (data.items || []).length }}</div>
            <div class="stat-foot">区间内有损益快照的项目</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">累计营收</div>
            <div class="stat-value small"><money-text :value="pnlTotal('revenue')" symbol /></div>
            <div class="stat-foot">同一项目取区间内最新快照</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">累计毛利</div>
            <div class="stat-value small"><money-text :value="pnlTotal('gross_profit')" :colorize="true" symbol /></div>
            <div class="stat-foot">营收 − 付款 − 报销</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">成本偏差合计</div>
            <div class="stat-value small"><money-text :value="pnlTotal('cost_variance')" :colorize="true" symbol /></div>
            <div class="stat-foot">预算 − 实际成本（正数为节约）</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>项目毛利对比</h3></div>
          <chart-box :option="pnlOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>项目损益明细</h3></div>
          <el-table :data="data.items || []" size="small" border>
            <el-table-column label="项目" min-width="220">
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="$router.push(`/projects/${row.project_id}`)">
                  {{ row.project_name || projectName(row.project_id) }}
                </el-link>
                <div class="muted mono" style="font-size: 12px">{{ row.project_no }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="period" label="快照期间" width="100" class-name="mono" />
            <el-table-column label="营收" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.revenue" /></template>
            </el-table-column>
            <el-table-column label="付款成本" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.cost" /></template>
            </el-table-column>
            <el-table-column label="报销费用" width="130" align="right">
              <template #default="{ row }"><money-text :value="row.expense" /></template>
            </el-table-column>
            <el-table-column label="毛利" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.gross_profit" colorize /></template>
            </el-table-column>
            <el-table-column label="毛利率" width="100" align="right">
              <template #default="{ row }">{{ rawPercent(Number(row.gross_margin || 0) * 100) }}</template>
            </el-table-column>
            <el-table-column label="预算" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.budget_amount" /></template>
            </el-table-column>
            <el-table-column label="成本偏差" width="140" align="right">
              <template #default="{ row }"><money-text :value="row.cost_variance" colorize /></template>
            </el-table-column>
            <el-table-column label="里程碑完成率" width="130">
              <template #default="{ row }">
                <el-progress :percentage="Math.min(Number(row.milestone_rate || 0) * 100, 100)" :stroke-width="8" />
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!(data.items || []).length" class="empty" style="padding: 40px 0">
            区间内暂无项目损益快照，请在财务期间关账时生成，或在下方生成报表快照。
          </div>
        </div>
      </template>

      <!-- 供应商支出 -->
      <template v-else-if="code === 'VENDOR_SPEND'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">供应商支出合计</div>
            <div class="stat-value small"><money-text :value="data.total" symbol /></div>
            <div class="stat-foot">{{ data.start }} ~ {{ data.end }} 付款 + 报销</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">合作供应商数</div>
            <div class="stat-value">{{ (data.items || []).length }}</div>
            <div class="stat-foot">区间内发生支出的供应商</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Top1 集中度</div>
            <div class="stat-value">{{ topVendorRatio }}</div>
            <div class="stat-foot">{{ topVendorName }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">平均客单价</div>
            <div class="stat-value small"><money-text :value="vendorAverage" symbol /></div>
            <div class="stat-foot">支出 / 供应商数</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>支出结构（Top 8）</h3></div>
          <chart-box :option="vendorOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>供应商支出明细</h3></div>
          <el-table :data="data.items || []" size="small" border>
            <el-table-column prop="vendor_name" label="供应商" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="$router.push(`/vendors/${row.vendor_id}`)">{{ row.vendor_name }}</el-link>
              </template>
            </el-table-column>
            <el-table-column prop="level" label="等级" width="80" align="center" />
            <el-table-column label="评分" width="90" align="right">
              <template #default="{ row }">{{ Number(row.score || 0).toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="支出金额" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.spend" symbol /></template>
            </el-table-column>
            <el-table-column prop="count" label="发生笔数" width="100" align="right" />
            <el-table-column label="合同总额" width="160" align="right">
              <template #default="{ row }"><money-text :value="row.contract_amount" /></template>
            </el-table-column>
            <el-table-column label="支出占比" width="110" align="right">
              <template #default="{ row }">{{ rawPercent(row.ratio) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 审批效率 -->
      <template v-else-if="code === 'APPROVAL_EFFICIENCY'">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-label">审批实例总数</div>
            <div class="stat-value">{{ data.total_instances || 0 }}</div>
            <div class="stat-foot">{{ data.start }} ~ {{ data.end }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">平均办结时长</div>
            <div class="stat-value">{{ Number(data.avg_hours || 0).toFixed(1) }} <span style="font-size: 13px">小时</span></div>
            <div class="stat-foot">已通过 / 已驳回实例</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">超时任务数</div>
            <div class="stat-value">{{ approvalOverdue }}</div>
            <div class="stat-foot">按业务类型汇总</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">整体驳回率</div>
            <div class="stat-value">{{ approvalRejectRate }}</div>
            <div class="stat-foot">驳回 / 已办结</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title"><h3>审批效率对比</h3></div>
          <chart-box :option="approvalOption" />
        </div>

        <div class="card">
          <div class="card-title"><h3>业务类型明细</h3></div>
          <el-table :data="data.items || []" size="small" border>
            <el-table-column label="业务类型" min-width="180">
              <template #default="{ row }">{{ labelOf(FLOW_BIZ_TYPES, row.biz_type) }}</template>
            </el-table-column>
            <el-table-column prop="total" label="实例数" width="100" align="right" />
            <el-table-column prop="approved" label="通过" width="100" align="right" />
            <el-table-column prop="rejected" label="驳回" width="100" align="right" />
            <el-table-column label="平均时长" width="130" align="right">
              <template #default="{ row }">{{ Number(row.avg_hours || 0).toFixed(1) }} 小时</template>
            </el-table-column>
            <el-table-column label="驳回率" width="110" align="right">
              <template #default="{ row }">{{ rawPercent(row.reject_rate) }}</template>
            </el-table-column>
            <el-table-column prop="overdue_tasks" label="超时任务" width="110" align="right" />
            <el-table-column label="超时率" width="110" align="right">
              <template #default="{ row }">{{ rawPercent(row.overdue_rate) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </div>

    <div class="card">
      <div class="card-title">
        <h3>报表快照</h3>
        <div class="grow" />
        <el-tag size="small" effect="plain">{{ REPORT_NAMES[code] }}</el-tag>
      </div>
      <el-table v-loading="snapshotLoading" :data="snapshots" size="small" border>
        <el-table-column prop="period" label="快照期间" width="120" class-name="mono" />
        <el-table-column prop="report_code" label="报表编码" width="220" class-name="mono" />
        <el-table-column prop="dim_type" label="维度" width="120" />
        <el-table-column label="生成时间" width="190">
          <template #default="{ row }">{{ datetime(row.generated_at) }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80" align="center" />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewSnapshot(row)">查看快照</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!snapshotLoading && !snapshots.length" class="empty" style="padding: 26px 0">
        暂无快照，可在右上角「生成快照」按月固化报表数据。
      </div>
    </div>

    <el-dialog v-model="snapshotVisible" title="报表快照详情" width="860px">
      <div class="tag-row" style="margin-bottom: 12px">
        <el-tag type="primary">{{ REPORT_NAMES[snapshotView.report_code] || snapshotView.report_code }}</el-tag>
        <span class="chip">期间 {{ snapshotView.period }}</span>
        <span class="chip">生成时间 {{ datetime(snapshotView.generated_at) }}</span>
        <span class="chip">版本 v{{ snapshotView.version }}</span>
      </div>
      <div v-if="snapshotItems.length">
        <el-table :data="snapshotItems" size="small" border max-height="460">
          <el-table-column v-for="key in snapshotColumns" :key="key" :prop="key" :label="key" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ snapshotCell(row[key]) }}</template>
          </el-table-column>
        </el-table>
      </div>
      <el-descriptions v-else :column="1" border size="small">
        <el-descriptions-item v-for="(value, key) in snapshotScalars" :key="key" :label="key">
          {{ snapshotCell(value) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera, Document, Download, Refresh, Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { iamApi, reportApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import MoneyText from '@/components/MoneyText.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { datetime, moneyShort, rawPercent } from '@/utils/format'
import { FLOW_BIZ_TYPES, labelOf, REPORT_NAMES } from '@/utils/constants'
import { saveBlob } from '@/utils/download'

const auth = useAuthStore()
const meta = useMetaStore()

const current = dayjs()
const code = ref('OVERVIEW')
const loading = ref(false)
const exporting = ref(false)
const data = ref({})
const customers = ref([])
const filters = reactive({
  year: String(current.year()),
  start: `${current.year()}-01`,
  end: `${current.year()}-12`,
  group_by: 'period',
  project_id: null
})

const snapshots = ref([])
const snapshotLoading = ref(false)
const snapshotVisible = ref(false)
const snapshotView = ref({})

const GROUP_LABELS = { period: '期间', project: '项目', customer: '客户' }
const groupByLabel = computed(() => GROUP_LABELS[filters.group_by] || '期间')

const cashNet = computed(() => Number(data.value.receipt || 0) - Number(data.value.payment || 0) - Number(data.value.expense || 0))
const cashflowRate = computed(() => {
  const inflow = Number(data.value.total_inflow || 0)
  return inflow ? rawPercent((Number(data.value.net || 0) / inflow) * 100) : '0.00%'
})

const revenueCount = computed(() => (data.value.items || []).reduce((sum, item) => sum + Number(item.count || 0), 0))
const revenueAverage = computed(() => {
  const count = revenueCount.value
  return count ? Number(data.value.total || 0) / count : 0
})

const topVendor = computed(() => (data.value.items || [])[0] || {})
const topVendorName = computed(() => topVendor.value.vendor_name || '-')
const topVendorRatio = computed(() => rawPercent(topVendor.value.ratio || 0))
const vendorAverage = computed(() => {
  const count = (data.value.items || []).length
  return count ? Number(data.value.total || 0) / count : 0
})

const approvalOverdue = computed(() => (data.value.items || []).reduce((sum, item) => sum + Number(item.overdue_tasks || 0), 0))
const approvalRejectRate = computed(() => {
  const items = data.value.items || []
  const rejected = items.reduce((sum, item) => sum + Number(item.rejected || 0), 0)
  const finished = items.reduce((sum, item) => sum + Number(item.approved || 0) + Number(item.rejected || 0), 0)
  return finished ? rawPercent((rejected / finished) * 100) : '0.00%'
})

function projectName(id) {
  if (!id) return '公司级'
  const project = (meta.projectOptions || []).find((item) => item.id === id)
  return project ? project.name : `项目 #${id}`
}

function customerName(id) {
  if (!id) return '-'
  const customer = customers.value.find((item) => item.id === id)
  return customer ? customer.name : `客户 #${id}`
}

function revenueDimension(row) {
  if (filters.group_by === 'project') return projectName(row.project_id)
  if (filters.group_by === 'customer') return customerName(row.customer_id)
  return row.period
}

function pnlTotal(field) {
  return (data.value.items || []).reduce((sum, item) => sum + Number(item[field] || 0), 0)
}

function currentParams() {
  if (code.value === 'OVERVIEW') return { year: Number(filters.year) }
  const params = { start: filters.start || null, end: filters.end || null }
  if (['REVENUE', 'PROFIT'].includes(code.value)) params.group_by = filters.group_by
  if (['CASHFLOW', 'PROFIT', 'PROJECT_PNL'].includes(code.value) && filters.project_id) params.project_id = filters.project_id
  return params
}

async function load() {
  loading.value = true
  try {
    data.value = await reportApi.data(code.value, currentParams())
  } finally {
    loading.value = false
  }
}

async function loadSnapshots() {
  snapshotLoading.value = true
  try {
    snapshots.value = (await reportApi.snapshots({ report_code: code.value, limit: 24 })) || []
  } finally {
    snapshotLoading.value = false
  }
}

function onCodeChange() {
  data.value = {}
  if (!['REVENUE', 'PROFIT'].includes(code.value)) filters.group_by = 'period'
  load()
  loadSnapshots()
}

function resetFilters() {
  filters.year = String(current.year())
  filters.start = `${current.year()}-01`
  filters.end = `${current.year()}-12`
  filters.group_by = 'period'
  filters.project_id = null
  load()
}

async function exportReport(format) {
  exporting.value = true
  try {
    const response = await reportApi.export(code.value, { ...currentParams(), format })
    saveBlob(response, `${REPORT_NAMES[code.value]}.${format === 'pdf' ? 'pdf' : 'xlsx'}`)
    ElMessage.success('报表已导出')
  } finally {
    exporting.value = false
  }
}

async function generateSnapshot() {
  let period = current.format('YYYY-MM')
  try {
    const result = await ElMessageBox.prompt('请输入快照期间（YYYY-MM）', '生成报表快照', {
      inputValue: period,
      inputPattern: /^\d{4}-\d{2}$/,
      inputErrorMessage: '期间格式为 YYYY-MM'
    })
    period = result.value
  } catch {
    return
  }
  const result = await reportApi.generateSnapshot(period)
  ElMessage.success(`已生成 ${result?.count ?? 0} 张报表快照`)
  await loadSnapshots()
}

function viewSnapshot(row) {
  snapshotView.value = row
  snapshotVisible.value = true
}

const snapshotItems = computed(() => {
  const items = snapshotView.value?.payload?.items
  return Array.isArray(items) ? items : []
})

const snapshotColumns = computed(() => {
  const first = snapshotItems.value[0]
  if (!first) return []
  return Object.keys(first).slice(0, 9)
})

const snapshotScalars = computed(() => {
  const payload = snapshotView.value?.payload || {}
  const result = {}
  for (const [key, value] of Object.entries(payload)) {
    if (value === null || typeof value !== 'object') result[key] = value
  }
  return result
})

function snapshotCell(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return text.length > 120 ? `${text.slice(0, 120)}...` : text
  }
  return String(value)
}

/* ---------------------------------------------------------------- 图表 */
const baseAxis = {
  tooltip: { trigger: 'axis' },
  grid: { left: 14, right: 20, top: 44, bottom: 10, containLabel: true }
}

const overviewOption = computed(() => {
  const rows = data.value.monthly || []
  return {
    ...baseAxis,
    legend: { top: 0, data: ['计收营收', '付款', '报销', '毛利'] },
    xAxis: { type: 'category', data: rows.map((row) => row.period) },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value) => moneyShort(value) },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    series: [
      { name: '计收营收', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#2563eb', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.revenue) },
      { name: '付款', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#f59e0b', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.payment) },
      { name: '报销', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#ef4444', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.expense) },
      { name: '毛利', type: 'line', smooth: true, symbolSize: 6, lineStyle: { width: 2.5, color: '#16a34a' }, itemStyle: { color: '#16a34a' }, data: rows.map((row) => row.profit) }
    ]
  }
})

const revenueOption = computed(() => {
  const rows = data.value.items || []
  return {
    ...baseAxis,
    legend: { top: 0, data: ['确认金额'] },
    xAxis: {
      type: 'category',
      data: rows.map((row) => revenueDimension(row)),
      axisLabel: { interval: 0, rotate: rows.length > 8 ? 28 : 0 }
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value) => moneyShort(value) },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    series: [
      {
        name: '确认金额',
        type: 'bar',
        barMaxWidth: 32,
        itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] },
        data: rows.map((row) => row.amount)
      }
    ]
  }
})

const cashflowOption = computed(() => {
  const rows = data.value.items || []
  return {
    ...baseAxis,
    legend: { top: 0, data: ['现金流入', '现金流出', '累计净额'] },
    xAxis: { type: 'category', data: rows.map((row) => row.period) },
    yAxis: [
      {
        type: 'value',
        axisLabel: { formatter: (value) => moneyShort(value) },
        splitLine: { lineStyle: { color: '#f1f5f9' } }
      }
    ],
    series: [
      { name: '现金流入', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#16a34a', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.inflow) },
      { name: '现金流出', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#ef4444', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.outflow) },
      { name: '累计净额', type: 'line', smooth: true, symbolSize: 6, lineStyle: { width: 2.5, color: '#2563eb' }, itemStyle: { color: '#2563eb' }, data: rows.map((row) => row.cumulative) }
    ]
  }
})

const profitOption = computed(() => {
  const rows = data.value.items || []
  if (filters.group_by === 'project') {
    return {
      ...baseAxis,
      legend: { top: 0, data: ['利润'] },
      xAxis: {
        type: 'category',
        data: rows.map((row) => projectName(row.project_id)),
        axisLabel: { interval: 0, rotate: rows.length > 6 ? 26 : 0 }
      },
      yAxis: {
        type: 'value',
        axisLabel: { formatter: (value) => moneyShort(value) },
        splitLine: { lineStyle: { color: '#f1f5f9' } }
      },
      series: [
        {
          name: '利润',
          type: 'bar',
          barMaxWidth: 34,
          itemStyle: { color: '#16a34a', borderRadius: [4, 4, 0, 0] },
          data: rows.map((row) => row.profit)
        }
      ]
    }
  }
  return {
    ...baseAxis,
    legend: { top: 0, data: ['营业收入', '营业成本', '利润'] },
    xAxis: { type: 'category', data: rows.map((row) => row.period) },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value) => moneyShort(value) },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    },
    series: [
      { name: '营业收入', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#2563eb', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.revenue) },
      { name: '营业成本', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#f59e0b', borderRadius: [3, 3, 0, 0] }, data: rows.map((row) => row.cost) },
      { name: '利润', type: 'line', smooth: true, symbolSize: 6, lineStyle: { width: 2.5, color: '#16a34a' }, itemStyle: { color: '#16a34a' }, data: rows.map((row) => row.profit) }
    ]
  }
})

const pnlOption = computed(() => {
  const rows = data.value.items || []
  return {
    ...baseAxis,
    legend: { top: 0, data: ['毛利', '毛利率'] },
    xAxis: {
      type: 'category',
      data: rows.map((row) => row.project_name || projectName(row.project_id)),
      axisLabel: { interval: 0, rotate: rows.length > 6 ? 26 : 0 }
    },
    yAxis: [
      {
        type: 'value',
        name: '毛利',
        axisLabel: { formatter: (value) => moneyShort(value) },
        splitLine: { lineStyle: { color: '#f1f5f9' } }
      },
      { type: 'value', name: '毛利率', axisLabel: { formatter: (value) => `${value}%` }, splitLine: { show: false } }
    ],
    series: [
      { name: '毛利', type: 'bar', barMaxWidth: 34, itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, data: rows.map((row) => row.gross_profit) },
      {
        name: '毛利率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
        data: rows.map((row) => Number((Number(row.gross_margin || 0) * 100).toFixed(2)))
      }
    ]
  }
})

const vendorOption = computed(() => {
  const rows = (data.value.items || []).slice(0, 8)
  return {
    tooltip: { trigger: 'item', formatter: '{b}<br/>支出：{c} 元（{d}%）' },
    legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
    series: [
      {
        name: '供应商支出',
        type: 'pie',
        radius: ['38%', '68%'],
        center: ['38%', '52%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{d}%' },
        data: rows.map((row) => ({ name: row.vendor_name, value: row.spend }))
      }
    ]
  }
})

const approvalOption = computed(() => {
  const rows = data.value.items || []
  return {
    ...baseAxis,
    legend: { top: 0, data: ['平均办结时长', '驳回率', '超时率'] },
    xAxis: {
      type: 'category',
      data: rows.map((row) => labelOf(FLOW_BIZ_TYPES, row.biz_type)),
      axisLabel: { interval: 0, rotate: rows.length > 5 ? 26 : 0 }
    },
    yAxis: [
      { type: 'value', name: '小时', splitLine: { lineStyle: { color: '#f1f5f9' } } },
      { type: 'value', name: '%', max: 100, splitLine: { show: false } }
    ],
    series: [
      { name: '平均办结时长', type: 'bar', barMaxWidth: 28, itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, data: rows.map((row) => row.avg_hours) },
      { name: '驳回率', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, lineStyle: { width: 2, color: '#ef4444' }, itemStyle: { color: '#ef4444' }, data: rows.map((row) => row.reject_rate) },
      { name: '超时率', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, lineStyle: { width: 2, color: '#f59e0b' }, itemStyle: { color: '#f59e0b' }, data: rows.map((row) => row.overdue_rate) }
    ]
  }
})

onMounted(async () => {
  await meta.ensure()
  try {
    customers.value = (await iamApi.customers()) || []
  } catch {
    customers.value = []
  }
  await Promise.allSettled([load(), loadSnapshots()])
})
</script>

<style scoped>
:deep(.el-radio-group) {
  flex-wrap: wrap;
  gap: 6px;
}
</style>

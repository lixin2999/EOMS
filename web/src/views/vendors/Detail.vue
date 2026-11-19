<template>
  <div v-loading="loading" class="page">
    <div class="card">
      <div class="detail-hero">
        <div>
          <div class="tag-row" style="margin-bottom: 8px">
            <el-button link :icon="ArrowLeft" @click="$router.push('/vendors')">返回供应商列表</el-button>
            <span class="mono muted">{{ vendor.code }}</span>
          </div>
          <h2>{{ vendor.name }}</h2>
          <div class="sub">
            <span>{{ labelOf(VENDOR_TYPES, vendor.type) }}</span>
            <span>负责人：{{ vendor.owner_name || '-' }}</span>
            <span>税号：{{ vendor.tax_no || '-' }}</span>
            <span>创建时间：{{ datetime(vendor.created_at) }}</span>
          </div>
          <div class="tag-row" style="margin-top: 10px">
            <status-tag :value="vendor.status" :labels="VENDOR_STATUS" />
            <el-tag v-if="vendor.level" size="small" effect="plain" :type="vendor.level === 'A' ? 'success' : vendor.level === 'C' ? 'warning' : ''">
              {{ labelOf(VENDOR_LEVELS, vendor.level) }}
            </el-tag>
            <span class="chip">综合评分 {{ Number(vendor.score || 0).toFixed(1) }}</span>
            <span class="chip">合作项目 {{ (vendor.projects || []).length }}</span>
            <span class="chip">合同 {{ (vendor.contracts || []).length }}</span>
          </div>
        </div>
        <div class="tag-row" style="justify-content: flex-end">
          <el-button
            v-if="canManage && vendor.status !== 'BLACKLIST' && vendor.status !== 'ACTIVE'"
            type="success"
            @click="submitVendor"
          >提交准入审批</el-button>
          <el-button v-if="canManage && vendor.status !== 'BLACKLIST'" :icon="Edit" @click="openEdit">编辑</el-button>
          <el-button v-if="canManage && vendor.status !== 'BLACKLIST'" type="danger" plain @click="openBlacklist">加入黑名单</el-button>
          <el-button v-if="canManage && vendor.status === 'BLACKLIST'" type="warning" @click="restoreVendor">解除黑名单</el-button>
        </div>
      </div>
      <el-alert
        v-if="vendor.status === 'BLACKLIST'"
        type="error"
        :closable="false"
        style="margin-top: 14px"
        :title="`该供应商已加入黑名单：${vendor.blacklist_reason || '原因未披露或无敏感权限'}`"
      />
    </div>

    <div class="stat-grid" style="margin-top: 16px">
      <div class="stat-card">
        <div class="stat-label">合作项目数</div>
        <div class="stat-value">{{ (vendor.projects || []).length }}</div>
        <div class="stat-foot">关联合同 {{ (vendor.contracts || []).length }} 份</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">合同总额</div>
        <div class="stat-value small"><money-text :value="contractTotal" symbol /></div>
        <div class="stat-foot">按供应商全部合同汇总</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计付款</div>
        <div class="stat-value small"><money-text :value="paidTotal" symbol /></div>
        <div class="stat-foot">合作项目累计已付款</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">风险资质</div>
        <div class="stat-value" :style="{ color: licenseRiskCount ? '#dc2626' : undefined }">{{ licenseRiskCount }}</div>
        <div class="stat-foot">已过期或 30 天内到期</div>
      </div>
    </div>

    <div class="card tabs-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="概览" name="overview">
          <div class="split-2">
            <div>
              <div class="section-title" style="margin-top: 0">基本信息</div>
              <div class="info-grid">
                <div class="info-item"><span class="label">供应商编号</span><span class="value mono">{{ vendor.code }}</span></div>
                <div class="info-item"><span class="label">供应商名称</span><span class="value">{{ vendor.name }}</span></div>
                <div class="info-item"><span class="label">供应商分类</span><span class="value">{{ labelOf(VENDOR_TYPES, vendor.type) }}</span></div>
                <div class="info-item"><span class="label">供应商等级</span><span class="value">{{ labelOf(VENDOR_LEVELS, vendor.level) }}</span></div>
                <div class="info-item"><span class="label">状态</span><span class="value">{{ labelOf(VENDOR_STATUS, vendor.status) }}</span></div>
                <div class="info-item"><span class="label">负责人</span><span class="value">{{ vendor.owner_name || '-' }}</span></div>
                <div class="info-item"><span class="label">纳税人识别号</span><span class="value mono">{{ vendor.tax_no || '-' }}</span></div>
                <div class="info-item"><span class="label">综合评分</span><span class="value">{{ Number(vendor.score || 0).toFixed(1) }}</span></div>
              </div>
              <div class="section-title">供应商简介</div>
              <div class="desc-block">{{ vendor.intro || '暂无供应商简介' }}</div>
            </div>
            <div>
              <div class="section-title" style="margin-top: 0">合作概况</div>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="合作项目">{{ (vendor.projects || []).length }} 个</el-descriptions-item>
                <el-descriptions-item label="合同数量">{{ (vendor.contracts || []).length }} 份</el-descriptions-item>
                <el-descriptions-item label="合同总额"><money-text :value="contractTotal" /></el-descriptions-item>
                <el-descriptions-item label="累计付款"><money-text :value="paidTotal" /></el-descriptions-item>
                <el-descriptions-item label="评价次数">{{ evaluations.length }} 次</el-descriptions-item>
                <el-descriptions-item label="最近评价">{{ evaluations[0] ? date(evaluations[0].eval_date) : '-' }}</el-descriptions-item>
              </el-descriptions>
              <div class="section-title">待关注资质</div>
              <div v-if="riskLicenses.length">
                <div v-for="item in riskLicenses" :key="item.id" class="risk-item">
                  <span class="risk-dot" :class="licenseLevel(item) === 'HIGH' ? 'level-HIGH' : 'level-MEDIUM'" />
                  <div style="flex: 1">
                    <div style="font-weight: 600">{{ item.name }}</div>
                    <div class="muted" style="font-size: 12.5px">有效期至 {{ date(item.valid_to) }} · {{ item.no || '无编号' }}</div>
                  </div>
                </div>
              </div>
              <div v-else class="empty">暂无到期风险</div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`联系人（${(vendor.contacts || []).length}）`" name="contacts">
          <div class="toolbar">
            <span class="muted">手机号默认脱敏显示，具备敏感信息权限的用户可查看完整号码。</span>
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openContact">新增联系人</el-button>
          </div>
          <el-table :data="vendor.contacts || []" size="small" border>
            <el-table-column prop="name" label="姓名" width="120" />
            <el-table-column prop="title" label="职务" width="140" />
            <el-table-column prop="phone" label="手机号" width="150" />
            <el-table-column prop="email" label="邮箱" min-width="180" />
            <el-table-column label="默认联系人" width="110" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" size="small" type="success">默认</el-tag>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`银行账户（${(vendor.banks || []).length}）`" name="banks">
          <div class="toolbar">
            <span class="muted">银行账号加密存储，无敏感权限时仅展示脱敏账号。</span>
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openBank">新增账户</el-button>
          </div>
          <el-table :data="vendor.banks || []" size="small" border>
            <el-table-column prop="bank_name" label="开户银行" min-width="200" />
            <el-table-column prop="account_no" label="银行账号" width="200" class-name="mono" />
            <el-table-column prop="account_name" label="账户名称" min-width="180" />
            <el-table-column label="默认账户" width="110" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" size="small" type="success">默认</el-tag>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`资质证照（${(vendor.licenses || []).length}）`" name="licenses">
          <div class="toolbar">
            <span class="muted">资质到期前 30 天自动进入风险提醒。</span>
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openLicense">新增资质</el-button>
          </div>
          <el-table :data="vendor.licenses || []" size="small" border>
            <el-table-column prop="name" label="证照名称" min-width="180" />
            <el-table-column prop="no" label="证照编号" width="160" class-name="mono" />
            <el-table-column label="有效期起" width="120">
              <template #default="{ row }">{{ date(row.valid_from) }}</template>
            </el-table-column>
            <el-table-column label="有效期止" width="120">
              <template #default="{ row }">
                <span :style="{ color: licenseLevel(row) === 'HIGH' ? '#dc2626' : undefined }">{{ date(row.valid_to) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="剩余天数" width="100" align="right">
              <template #default="{ row }">
                <span :class="['money', licenseDays(row) < 0 ? 'negative' : licenseDays(row) <= 30 ? 'negative' : '']">
                  {{ row.valid_to ? licenseDays(row) : '-' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="扫描件" min-width="160">
              <template #default="{ row }">
                <el-link v-if="row.file?.id" type="primary" :underline="false" @click="downloadFile(row.file)">{{ row.file.name }}</el-link>
                <span v-else class="muted">未上传</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`合作项目（${(vendor.projects || []).length}）`" name="projects">
          <div class="toolbar">
            <span class="muted">合作项目与合同金额用于供应商支出分析。</span>
            <div class="grow" />
            <el-button v-if="canManage" type="primary" :icon="Plus" @click="openBindProject">关联项目</el-button>
          </div>
          <el-table :data="vendor.projects || []" size="small" border>
            <el-table-column label="项目" min-width="220">
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="$router.push(`/projects/${row.project_id}`)">{{ row.project_name || `项目 #${row.project_id}` }}</el-link>
              </template>
            </el-table-column>
            <el-table-column prop="role" label="合作角色" width="120" />
            <el-table-column label="合同" width="160">
              <template #default="{ row }">
                <el-link v-if="row.contract_id" type="primary" :underline="false" @click="$router.push(`/contracts/${row.contract_id}`)">#{{ row.contract_id }}</el-link>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="合同金额" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.contract_amount" /></template>
            </el-table-column>
            <el-table-column label="已付款" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.paid_amount" /></template>
            </el-table-column>
            <el-table-column label="已结算" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.settled_amount" /></template>
            </el-table-column>
            <el-table-column label="评分" width="90" align="right">
              <template #default="{ row }">{{ Number(row.score || 0).toFixed(1) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`合同（${(vendor.contracts || []).length}）`" name="contracts">
          <el-table :data="vendor.contracts || []" size="small" border>
            <el-table-column prop="no" label="合同编号" width="160" class-name="mono" />
            <el-table-column prop="name" label="合同名称" min-width="220" />
            <el-table-column label="金额" width="150" align="right">
              <template #default="{ row }"><money-text :value="row.amount" /></template>
            </el-table-column>
            <el-table-column label="签订日期" width="120">
              <template #default="{ row }">{{ date(row.sign_date) }}</template>
            </el-table-column>
            <el-table-column label="有效期" width="190">
              <template #default="{ row }"><span class="muted">{{ date(row.start_date) }} ~ {{ date(row.end_date) }}</span></template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><status-tag :value="row.status" :labels="CONTRACT_STATUS" /></template>
            </el-table-column>
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(`/contracts/${row.id}`)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`评价（${evaluations.length}）`" name="evaluations">
          <div class="toolbar">
            <el-select v-model="evaluationYear" placeholder="全部年度" clearable style="width: 140px" @change="loadEvaluations">
              <el-option v-for="year in yearOptions" :key="year" :label="`${year} 年`" :value="year" />
            </el-select>
            <div class="grow" />
            <el-button v-if="auth.can('vendor:evaluate')" type="primary" :icon="Plus" @click="openEvaluation">新增评价</el-button>
          </div>
          <div class="split-2">
            <el-table :data="evaluations" size="small" border>
              <el-table-column label="评价日期" width="120">
                <template #default="{ row }">{{ date(row.eval_date) }}</template>
              </el-table-column>
              <el-table-column prop="project_name" label="关联项目" min-width="160" />
              <el-table-column label="质量" width="80" align="right">
                <template #default="{ row }">{{ Number(row.quality_score || 0).toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="进度" width="80" align="right">
                <template #default="{ row }">{{ Number(row.schedule_score || 0).toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="配合" width="80" align="right">
                <template #default="{ row }">{{ Number(row.cooperate_score || 0).toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="总分" width="90" align="right">
                <template #default="{ row }">
                  <span :class="['money', Number(row.total_score || 0) >= 85 ? 'positive' : Number(row.total_score || 0) < 60 ? 'negative' : '']">
                    {{ Number(row.total_score || 0).toFixed(1) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="grade" label="等级" width="70" align="center" />
              <el-table-column prop="evaluator_name" label="评价人" width="100" />
              <el-table-column prop="comment" label="评语" min-width="180" show-overflow-tooltip />
            </el-table>
            <div class="card" style="margin: 0">
              <div class="card-title"><h3>评价趋势</h3></div>
              <chart-box :option="evaluationTrendOption" size="sm" />
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="年度评价报告" name="annual">
          <div class="toolbar">
            <el-select v-model="annualYear" style="width: 140px" @change="loadAnnual">
              <el-option v-for="year in yearOptions" :key="year" :label="`${year} 年`" :value="year" />
            </el-select>
            <div class="grow" />
          </div>
          <div class="stat-grid">
            <div class="stat-card">
              <div class="stat-label">年度综合评分</div>
              <div class="stat-value">{{ Number(annual.average_score || 0).toFixed(1) }}</div>
              <div class="stat-foot">评价 {{ annual.evaluation_count || 0 }} 次 · 等级 {{ annual.grade || '-' }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">年度合同额</div>
              <div class="stat-value small"><money-text :value="annual.contract_amount" symbol /></div>
              <div class="stat-foot">按签订日期归集</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">累计付款</div>
              <div class="stat-value small"><money-text :value="annual.paid_amount" symbol /></div>
              <div class="stat-foot">全部合作项目累计</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">等级分布</div>
              <div class="stat-value small">
                A {{ annual.grade_distribution?.A || 0 }} · B {{ annual.grade_distribution?.B || 0 }} · C {{ annual.grade_distribution?.C || 0 }}
              </div>
              <div class="stat-foot">按评价总分自动评级</div>
            </div>
          </div>
          <div class="card">
            <div class="card-title"><h3>年度月度评价趋势</h3></div>
            <chart-box :option="annualTrendOption" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 编辑供应商 -->
    <el-dialog v-model="editVisible" title="编辑供应商" width="560px">
      <el-form :model="editForm" label-width="96px">
        <el-form-item label="供应商名称" required><el-input v-model="editForm.name" maxlength="255" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="供应商分类">
              <el-select v-model="editForm.type" style="width: 100%">
                <el-option v-for="(label, value) in VENDOR_TYPES" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="供应商等级">
              <el-select v-model="editForm.level" clearable style="width: 100%">
                <el-option v-for="(label, value) in VENDOR_LEVELS" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="纳税人识别号"><el-input v-model="editForm.tax_no" maxlength="64" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="editForm.owner_user_id" filterable style="width: 100%">
                <el-option v-for="user in meta.userOptions" :key="user.id" :label="user.real_name" :value="user.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="供应商简介"><el-input v-model="editForm.intro" type="textarea" :rows="4" maxlength="2000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 联系人 -->
    <el-dialog v-model="contactVisible" title="新增联系人" width="480px">
      <el-form :model="contactForm" label-width="86px">
        <el-form-item label="姓名" required><el-input v-model="contactForm.name" maxlength="64" /></el-form-item>
        <el-form-item label="职务"><el-input v-model="contactForm.title" maxlength="64" /></el-form-item>
        <el-form-item label="手机号"><el-input v-model="contactForm.phone" maxlength="20" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="contactForm.email" maxlength="128" /></el-form-item>
        <el-form-item label="默认联系人"><el-switch v-model="contactForm.is_default" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="contactVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveContact">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 银行账户 -->
    <el-dialog v-model="bankVisible" title="新增银行账户" width="520px">
      <el-form :model="bankForm" label-width="90px">
        <el-form-item label="开户银行" required><el-input v-model="bankForm.bank_name" maxlength="128" /></el-form-item>
        <el-form-item label="银行账号" required><el-input v-model="bankForm.account_no" maxlength="64" /></el-form-item>
        <el-form-item label="账户名称" required><el-input v-model="bankForm.account_name" maxlength="128" /></el-form-item>
        <el-form-item label="默认账户"><el-switch v-model="bankForm.is_default" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="bankVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveBank">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 资质 -->
    <el-dialog v-model="licenseVisible" title="新增资质证照" width="540px">
      <el-form :model="licenseForm" label-width="90px">
        <el-form-item label="证照名称" required><el-input v-model="licenseForm.name" maxlength="128" /></el-form-item>
        <el-form-item label="证照编号"><el-input v-model="licenseForm.no" maxlength="64" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="有效期起"><el-date-picker v-model="licenseForm.valid_from" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="有效期止"><el-date-picker v-model="licenseForm.valid_to" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="扫描件"><file-upload v-model="licenseForm.file_id" biz-type="VENDOR" :biz-id="vendorId" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="licenseVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveLicense">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 关联项目 -->
    <el-dialog v-model="projectVisible" title="关联合作项目" width="520px">
      <el-form :model="projectForm" label-width="90px">
        <el-form-item label="项目" required>
          <el-select v-model="projectForm.project_id" filterable style="width: 100%">
            <el-option v-for="project in meta.projectOptions" :key="project.id" :label="`${project.name}${project.no ? `（${project.no}）` : ''}`" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联合同">
          <el-select v-model="projectForm.contract_id" filterable clearable style="width: 100%">
            <el-option v-for="contract in vendorContracts" :key="contract.id" :label="`${contract.no} ${contract.name}`" :value="contract.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="合作角色"><el-input v-model="projectForm.role" maxlength="32" /></el-form-item>
        <el-form-item label="合同金额"><el-input-number v-model="projectForm.contract_amount" :min="0" :precision="2" controls-position="right" style="width: 100%" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="projectVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveBindProject">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 评价 -->
    <el-dialog v-model="evaluationVisible" title="新增供应商评价" width="540px">
      <el-form :model="evaluationForm" label-width="96px">
        <el-form-item label="关联项目">
          <el-select v-model="evaluationForm.project_id" filterable clearable style="width: 100%">
            <el-option v-for="project in meta.projectOptions" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="质量评分" required><el-slider v-model="evaluationForm.quality_score" :max="100" show-input /></el-form-item>
        <el-form-item label="进度评分" required><el-slider v-model="evaluationForm.schedule_score" :max="100" show-input /></el-form-item>
        <el-form-item label="配合评分" required><el-slider v-model="evaluationForm.cooperate_score" :max="100" show-input /></el-form-item>
        <el-form-item label="评价日期"><el-date-picker v-model="evaluationForm.eval_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
        <el-form-item label="评价意见"><el-input v-model="evaluationForm.comment" type="textarea" :rows="3" maxlength="1000" show-word-limit /></el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="evaluationVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEvaluation">提交评价</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="blacklistVisible" title="加入黑名单" width="480px">
      <el-alert type="error" :closable="false" title="加入黑名单后该供应商禁止新增付款，且不可修改主档。" />
      <el-form style="margin-top: 14px" label-width="90px">
        <el-form-item label="拉黑原因" required>
          <el-input v-model="blacklistReason" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="不少于 3 个字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="blacklistVisible = false">取消</el-button>
          <el-button type="danger" :loading="saving" @click="confirmBlacklist">确认拉黑</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Edit, Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { fileApi, vendorApi } from '@/api'
import ChartBox from '@/components/ChartBox.vue'
import FileUpload from '@/components/FileUpload.vue'
import MoneyText from '@/components/MoneyText.vue'
import StatusTag from '@/components/StatusTag.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { date, datetime, today } from '@/utils/format'
import { CONTRACT_STATUS, labelOf, VENDOR_LEVELS, VENDOR_STATUS, VENDOR_TYPES } from '@/utils/constants'
import { saveBlob } from '@/utils/download'

const route = useRoute()
const auth = useAuthStore()
const meta = useMetaStore()
const vendorId = computed(() => Number(route.params.id))

const loading = ref(false)
const saving = ref(false)
const activeTab = ref('overview')
const vendor = ref({})
const evaluations = ref([])
const evaluationYear = ref(null)
const annualYear = ref(dayjs().year())
const annual = ref({})
const blacklistReason = ref('')

const canManage = computed(() => auth.can('vendor:manage'))

const yearOptions = computed(() => {
  const current = dayjs().year()
  return [current, current - 1, current - 2, current - 3]
})

const contractTotal = computed(() =>
  (vendor.value.contracts || []).reduce((sum, item) => sum + Number(item.amount || 0), 0)
)
const paidTotal = computed(() =>
  (vendor.value.projects || []).reduce((sum, item) => sum + Number(item.paid_amount || 0), 0)
)

function licenseDays(row) {
  if (!row.valid_to) return 9999
  return dayjs(row.valid_to).startOf('day').diff(dayjs().startOf('day'), 'day')
}

function licenseLevel(row) {
  const days = licenseDays(row)
  if (days < 0 || days <= 7) return 'HIGH'
  return days <= 30 ? 'MEDIUM' : 'LOW'
}

const riskLicenses = computed(() =>
  (vendor.value.licenses || []).filter((item) => item.valid_to && licenseDays(item) <= 30)
)
const licenseRiskCount = computed(() => riskLicenses.value.length)

const vendorContracts = computed(() => vendor.value.contracts || [])

const evaluationTrendOption = computed(() => {
  const rows = [...evaluations.value].reverse()
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['总分', '质量', '进度', '配合'] },
    grid: { left: 12, right: 18, top: 40, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: rows.map((item) => date(item.eval_date)) },
    yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [
      { name: '总分', type: 'line', smooth: true, symbolSize: 6, lineStyle: { width: 2.5, color: '#2563eb' }, itemStyle: { color: '#2563eb' }, data: rows.map((item) => item.total_score) },
      { name: '质量', type: 'line', smooth: true, symbolSize: 4, lineStyle: { width: 1.5, color: '#16a34a' }, itemStyle: { color: '#16a34a' }, data: rows.map((item) => item.quality_score) },
      { name: '进度', type: 'line', smooth: true, symbolSize: 4, lineStyle: { width: 1.5, color: '#f59e0b' }, itemStyle: { color: '#f59e0b' }, data: rows.map((item) => item.schedule_score) },
      { name: '配合', type: 'line', smooth: true, symbolSize: 4, lineStyle: { width: 1.5, color: '#8b5cf6' }, itemStyle: { color: '#8b5cf6' }, data: rows.map((item) => item.cooperate_score) }
    ]
  }
})

const annualTrendOption = computed(() => {
  const rows = annual.value.monthly_trend || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['综合得分', '质量', '进度', '配合'] },
    grid: { left: 12, right: 18, top: 40, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: rows.map((item) => item.period) },
    yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [
      { name: '综合得分', type: 'bar', barWidth: 18, itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] }, data: rows.map((item) => item.total_score) },
      { name: '质量', type: 'line', smooth: true, itemStyle: { color: '#16a34a' }, data: rows.map((item) => item.quality_score) },
      { name: '进度', type: 'line', smooth: true, itemStyle: { color: '#f59e0b' }, data: rows.map((item) => item.schedule_score) },
      { name: '配合', type: 'line', smooth: true, itemStyle: { color: '#8b5cf6' }, data: rows.map((item) => item.cooperate_score) }
    ]
  }
})

async function loadVendor() {
  vendor.value = await vendorApi.detail(vendorId.value)
}

async function loadEvaluations() {
  evaluations.value = await vendorApi.evaluations(vendorId.value, evaluationYear.value || undefined)
}

async function loadAnnual() {
  try {
    annual.value = await vendorApi.annualReport(vendorId.value, annualYear.value)
  } catch {
    annual.value = {}
  }
}

async function loadAll() {
  loading.value = true
  try {
    await loadVendor()
    await Promise.allSettled([loadEvaluations(), loadAnnual()])
  } finally {
    loading.value = false
  }
}

async function submitVendor() {
  try {
    await ElMessageBox.confirm('确认提交该供应商的准入审批吗？', '提交准入', { type: 'warning' })
  } catch {
    return
  }
  await vendorApi.submit(vendorId.value)
  ElMessage.success('准入审批已提交')
  await loadVendor()
}

async function restoreVendor() {
  try {
    await ElMessageBox.confirm('确认解除该供应商的黑名单吗？', '解除黑名单', { type: 'warning' })
  } catch {
    return
  }
  await vendorApi.restore(vendorId.value)
  ElMessage.success('供应商已恢复')
  await loadVendor()
}

/* ---------------------------------------------------------------- 编辑 */
const editVisible = ref(false)
const editForm = ref({})

function openEdit() {
  editForm.value = {
    name: vendor.value.name,
    type: vendor.value.type,
    tax_no: vendor.value.tax_no || '',
    owner_user_id: vendor.value.owner_user_id,
    intro: vendor.value.intro || '',
    level: vendor.value.level,
    version: vendor.value.version
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editForm.value.name) {
    ElMessage.warning('请输入供应商名称')
    return
  }
  saving.value = true
  try {
    await vendorApi.update(vendorId.value, editForm.value)
    ElMessage.success('供应商已更新')
    editVisible.value = false
    await loadVendor()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 联系人 */
const contactVisible = ref(false)
const contactForm = ref({})

function openContact() {
  contactForm.value = { name: '', title: '', phone: '', email: '', is_default: false }
  contactVisible.value = true
}

async function saveContact() {
  if (!contactForm.value.name) {
    ElMessage.warning('请输入联系人姓名')
    return
  }
  saving.value = true
  try {
    await vendorApi.addContact(vendorId.value, contactForm.value)
    ElMessage.success('联系人已添加')
    contactVisible.value = false
    await loadVendor()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 银行 */
const bankVisible = ref(false)
const bankForm = ref({})

function openBank() {
  bankForm.value = { bank_name: '', account_no: '', account_name: vendor.value.name, is_default: false }
  bankVisible.value = true
}

async function saveBank() {
  if (!bankForm.value.bank_name || !bankForm.value.account_no || !bankForm.value.account_name) {
    ElMessage.warning('开户行、账号、账户名称均为必填')
    return
  }
  saving.value = true
  try {
    await vendorApi.addBank(vendorId.value, bankForm.value)
    ElMessage.success('银行账户已添加')
    bankVisible.value = false
    await loadVendor()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 资质 */
const licenseVisible = ref(false)
const licenseForm = ref({})

function openLicense() {
  licenseForm.value = { name: '', no: '', file_id: null, valid_from: '', valid_to: '' }
  licenseVisible.value = true
}

async function saveLicense() {
  if (!licenseForm.value.name) {
    ElMessage.warning('请输入证照名称')
    return
  }
  saving.value = true
  try {
    await vendorApi.addLicense(vendorId.value, licenseForm.value)
    ElMessage.success('资质已添加')
    licenseVisible.value = false
    await loadVendor()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 项目 */
const projectVisible = ref(false)
const projectForm = ref({})

function openBindProject() {
  projectForm.value = { project_id: null, contract_id: null, role: '分包商', contract_amount: 0 }
  projectVisible.value = true
}

async function saveBindProject() {
  if (!projectForm.value.project_id) {
    ElMessage.warning('请选择项目')
    return
  }
  saving.value = true
  try {
    await vendorApi.bindProject(vendorId.value, projectForm.value)
    ElMessage.success('项目关联已建立')
    projectVisible.value = false
    await loadVendor()
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 评价 */
const evaluationVisible = ref(false)
const evaluationForm = ref({})

function openEvaluation() {
  evaluationForm.value = {
    project_id: null,
    quality_score: 80,
    schedule_score: 80,
    cooperate_score: 80,
    comment: '',
    eval_date: today()
  }
  evaluationVisible.value = true
}

async function saveEvaluation() {
  saving.value = true
  try {
    await vendorApi.addEvaluation(vendorId.value, evaluationForm.value)
    ElMessage.success('评价已提交')
    evaluationVisible.value = false
    await Promise.all([loadEvaluations(), loadAnnual()])
  } finally {
    saving.value = false
  }
}

/* ---------------------------------------------------------------- 黑名单 */
const blacklistVisible = ref(false)

function openBlacklist() {
  blacklistReason.value = ''
  blacklistVisible.value = true
}

async function confirmBlacklist() {
  if ((blacklistReason.value || '').trim().length < 3) {
    ElMessage.warning('请填写不少于 3 个字的拉黑原因')
    return
  }
  saving.value = true
  try {
    await vendorApi.blacklist(vendorId.value, { reason: blacklistReason.value.trim() })
    ElMessage.success('供应商已加入黑名单')
    blacklistVisible.value = false
    await loadVendor()
  } finally {
    saving.value = false
  }
}

async function downloadFile(file) {
  const response = await fileApi.download(file.id)
  saveBlob(response, file.name || `license-${file.id}`)
}

onMounted(async () => {
  await meta.ensure()
  await loadAll()
})
</script>

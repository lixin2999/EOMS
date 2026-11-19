export const STATUS_LABELS = {
  DRAFT: '草稿',
  RUNNING: '审批中',
  REJECTED: '已驳回',
  APPROVED: '已通过',
  VERIFIED: '已复核',
  PAID: '已付款',
  ARCHIVED: '已归档',
  CANCELED: '已取消',
  PENDING: '待处理',
  REGISTERED: '已登记',
  CONFIRMED: '已确认',
  ACTIVE: '生效',
  EXPIRED: '已到期',
  TERMINATED: '已终止',
  BLACKLIST: '黑名单',
  SUSPENDED: '已暂停',
  LAUNCH: '立项',
  PLAN: '计划',
  PLAN_CONFIRMED: '计划已确认',
  EXECUTE: '执行',
  CLOSE: '收尾',
  TODO: '待开始',
  DOING: '进行中',
  DONE: '已完成',
  BLOCKED: '受阻',
  OPEN: '待处理',
  PROCESSING: '处理中',
  CLOSED: '已关闭',
  COMPLETED: '已完成',
  INACTIVE: '停用'
}

export const STATUS_TAG = {
  DRAFT: 'info',
  RUNNING: 'warning',
  REJECTED: 'danger',
  APPROVED: 'success',
  VERIFIED: '',
  PAID: 'success',
  ARCHIVED: 'info',
  CANCELED: 'info',
  PENDING: 'warning',
  REGISTERED: '',
  CONFIRMED: 'success',
  ACTIVE: 'success',
  EXPIRED: 'danger',
  TERMINATED: 'danger',
  BLACKLIST: 'danger',
  SUSPENDED: 'warning',
  TODO: 'info',
  DOING: 'warning',
  DONE: 'success',
  BLOCKED: 'danger',
  OPEN: 'warning',
  PROCESSING: '',
  CLOSED: 'info',
  PASS: 'success',
  CONDITIONAL: 'warning',
  FAIL: 'danger',
  HIGH: 'danger',
  MEDIUM: 'warning',
  LOW: 'success',
  URGENT: 'danger',
  NORMAL: 'info'
}

export const EXPENSE_TYPES = {
  TRAVEL: '差旅费',
  ENTERTAIN: '业务招待费',
  OFFICE: '办公费',
  SUBCONTRACT: '分包费',
  MATERIAL: '材料费',
  OTHER: '其他'
}

export const LEAVE_TYPES = {
  ANNUAL: '年假',
  PERSONAL: '事假',
  SICK: '病假',
  COMP: '调休'
}

export const DOCUMENT_CATEGORIES = {
  INSTITUTION: '制度文件',
  DISPATCH: '通知公告',
  SEAL: '用印申请',
  CONTRACT: '合同文本'
}

export const SECRET_LEVELS = {
  PUBLIC: '公开',
  INTERNAL: '内部',
  SECRET: '机密'
}

export const PROJECT_TYPES = {
  CONSTRUCTION: '建设项目',
  SERVICE: '服务项目',
  PRODUCT: '产品项目',
  OTHER: '其他'
}

export const PROJECT_STAGES = {
  LAUNCH: '立项',
  PLAN: '计划',
  PLAN_CONFIRMED: '计划已确认',
  EXECUTE: '执行',
  CLOSE: '收尾',
  ARCHIVED: '已归档'
}

export const CHANGE_TYPES = {
  SCOPE: '范围变更',
  SCHEDULE: '进度变更',
  BUDGET: '预算变更'
}

export const VENDOR_TYPES = {
  SUBCONTRACT: '劳务分包',
  MATERIAL: '材料供应',
  SERVICE: '技术服务',
  LEASE: '设备租赁'
}

export const VENDOR_STATUS = {
  PENDING: '待准入',
  ACTIVE: '合作中',
  SUSPENDED: '已暂停',
  BLACKLIST: '黑名单'
}

export const VENDOR_LEVELS = {
  A: 'A 级（优选）',
  B: 'B 级（合格）',
  C: 'C 级（观察）'
}

export const CONTRACT_STATUS = {
  DRAFT: '草稿',
  ACTIVE: '生效中',
  EXPIRED: '已到期',
  TERMINATED: '已终止'
}

export const PAYMENT_METHODS = {
  BANK: '银行转账',
  CASH: '现金',
  OTHER: '其他'
}

export const ACCOUNT_TYPES = {
  ASSET: '资产',
  LIABILITY: '负债',
  EQUITY: '权益',
  REVENUE: '收入',
  COST: '成本',
  EXPENSE: '费用'
}

export const COST_BIZ_TYPES = {
  RECEIVABLE: '计收',
  RECEIPT: '收款',
  PAYMENT: '付款',
  EXPENSE: '报销'
}

export const FLOW_BIZ_TYPES = {
  EXPENSE: '费用报销',
  LEAVE: '请假',
  DOCUMENT: '文件审批',
  PROJECT_INITIATION: '项目立项',
  PROJECT_CHANGE: '项目变更',
  PROJECT_ACCEPTANCE: '项目验收',
  VENDOR_ONBOARD: '供应商准入'
}

export const DATA_SCOPES = {
  ALL: '全公司（ALL）',
  COMPANY: '本公司（COMPANY）',
  DEPT_TREE: '部门及下级（DEPT_TREE）',
  DEPT: '本部门（DEPT）',
  PROJECT: '参与项目（PROJECT）',
  SELF: '仅本人（SELF）'
}

export const PRIORITIES = {
  LOW: '低',
  MEDIUM: '中',
  HIGH: '高',
  URGENT: '紧急'
}

export const ASSIGNEE_TYPES = {
  USER: '指定用户',
  ROLE: '指定角色',
  DEPT_LEADER: '部门负责人',
  PROJECT_MANAGER: '项目经理',
  INITIATOR_LEADER: '发起人上级'
}

export const REPORT_NAMES = {
  OVERVIEW: '经营总览',
  REVENUE: '营收报表',
  CASHFLOW: '现金流量表',
  PROFIT: '利润表',
  PROJECT_PNL: '项目损益表',
  VENDOR_SPEND: '供应商支出分析',
  APPROVAL_EFFICIENCY: '审批效率报表'
}

export const WORKFLOW_ACTIONS = {
  APPROVE: '同意',
  REJECT: '驳回',
  TRANSFER: '转办',
  ADD_SIGN: '加签',
  WITHDRAW: '撤回',
  URGE: '催办',
  CC: '抄送',
  SUBMIT: '提交'
}

export function labelOf(map, value, fallback = '') {
  if (value === null || value === undefined || value === '') return fallback || '-'
  return map[value] || String(value)
}

export function tagType(value) {
  return STATUS_TAG[value] || 'info'
}

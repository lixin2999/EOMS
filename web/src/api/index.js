import { api, rawGet } from './http'

export const authApi = {
  captcha: () => api.get('/auth/captcha'),
  login: (payload) => api.post('/auth/login', payload),
  logout: () => api.post('/auth/logout', {}),
  me: () => api.get('/auth/me'),
  changePassword: (payload) => api.put('/auth/password', payload)
}

export const metaApi = {
  enums: () => api.get('/meta/enums'),
  options: (keyword) => api.get('/meta/options', keyword ? { keyword } : undefined),
  dicts: (dictType) => api.get('/meta/dicts', dictType ? { dict_type: dictType } : undefined),
  me: () => api.get('/meta/me')
}

export const dashboardApi = {
  all: () => api.get('/dashboard'),
  overview: (year) => api.get('/dashboard/overview', year ? { year } : undefined),
  health: (limit = 10) => api.get('/dashboard/health', { limit }),
  alerts: (days = 30) => api.get('/dashboard/alerts', { days })
}

export const expenseApi = {
  list: (params) => api.get('/approvals/expenses', params),
  detail: (id) => api.get(`/approvals/expenses/${id}`),
  create: (payload) => api.post('/approvals/expenses', payload),
  update: (id, payload) => api.put(`/approvals/expenses/${id}`, payload),
  submit: (id) => api.post(`/approvals/expenses/${id}/submit`),
  cancel: (id) => api.post(`/approvals/expenses/${id}/cancel`),
  withdraw: (id) => api.post(`/approvals/expenses/${id}/withdraw`),
  verify: (id) => api.post(`/approvals/expenses/${id}/verify`),
  archive: (id) => api.post(`/approvals/expenses/${id}/archive`)
}

export const leaveApi = {
  list: (params) => api.get('/approvals/leaves', params),
  balance: (year) => api.get('/approvals/leaves/balance', year ? { year } : undefined),
  detail: (id) => api.get(`/approvals/leaves/${id}`),
  create: (payload) => api.post('/approvals/leaves', payload),
  update: (id, payload) => api.put(`/approvals/leaves/${id}`, payload),
  submit: (id) => api.post(`/approvals/leaves/${id}/submit`),
  cancel: (id) => api.post(`/approvals/leaves/${id}/cancel`),
  withdraw: (id) => api.post(`/approvals/leaves/${id}/withdraw`)
}

export const documentApi = {
  list: (params) => api.get('/approvals/documents', params),
  detail: (id) => api.get(`/approvals/documents/${id}`),
  create: (payload) => api.post('/approvals/documents', payload),
  update: (id, payload) => api.put(`/approvals/documents/${id}`, payload),
  submit: (id) => api.post(`/approvals/documents/${id}/submit`),
  cancel: (id) => api.post(`/approvals/documents/${id}/cancel`),
  withdraw: (id) => api.post(`/approvals/documents/${id}/withdraw`)
}

export const workflowApi = {
  instances: (params) => api.get('/workflow/instances', params),
  instance: (id) => api.get(`/workflow/instances/${id}`),
  action: (id, payload) => api.post(`/workflow/instances/${id}/actions`, payload),
  tasks: (params) => api.get('/workflow/tasks', params),
  definitions: () => api.get('/workflow/definitions'),
  saveDefinition: (payload) => api.post('/workflow/definitions', payload),
  defaults: () => api.get('/workflow/definitions/defaults')
}

export const projectApi = {
  list: (params) => api.get('/projects', params),
  create: (payload) => api.post('/projects', payload),
  detail: (id) => api.get(`/projects/${id}`),
  update: (id, payload) => api.put(`/projects/${id}`, payload),
  initiation: (id) => api.get(`/projects/${id}/initiation`),
  createInitiation: (payload) => api.post('/projects/initiations', payload),
  submitInitiation: (id) => api.post(`/projects/initiations/${id}/submit`),
  confirmPlan: (id) => api.post(`/projects/${id}/confirm-plan`),
  startExecution: (id) => api.post(`/projects/${id}/start-execution`),
  baseline: (id) => api.get(`/projects/${id}/baseline`),
  deviation: (id) => api.get(`/projects/${id}/deviation`),
  closeCheck: (id) => api.get(`/projects/${id}/close-check`),
  close: (id, payload) => api.post(`/projects/${id}/close`, payload),
  archive: (id) => api.post(`/projects/${id}/archive`),
  archives: (id) => api.get(`/projects/${id}/archives`),
  addArchive: (id, payload) => api.post(`/projects/${id}/archives`, payload),
  members: (id) => api.get(`/projects/${id}/members`),
  addMember: (id, payload) => api.post(`/projects/${id}/members`, payload),
  removeMember: (id, memberId) => api.del(`/projects/${id}/members/${memberId}`),
  wbs: (id) => api.get(`/projects/${id}/wbs`),
  createWbs: (id, payload) => api.post(`/projects/${id}/wbs`, payload),
  updateWbs: (wbsId, payload) => api.put(`/projects/wbs/${wbsId}`, payload),
  deleteWbs: (wbsId) => api.del(`/projects/wbs/${wbsId}`),
  tasks: (id, params) => api.get(`/projects/${id}/tasks`, params),
  createTask: (id, payload) => api.post(`/projects/${id}/tasks`, payload),
  updateTask: (taskId, payload) => api.put(`/projects/tasks/${taskId}`, payload),
  deleteTask: (taskId) => api.del(`/projects/tasks/${taskId}`),
  milestones: (id) => api.get(`/projects/${id}/milestones`),
  createMilestone: (id, payload) => api.post(`/projects/${id}/milestones`, payload),
  completeMilestone: (milestoneId, payload) => api.post(`/projects/milestones/${milestoneId}/complete`, payload),
  deleteMilestone: (milestoneId) => api.del(`/projects/milestones/${milestoneId}`),
  changes: (id) => api.get(`/projects/${id}/changes`),
  createChange: (id, payload) => api.post(`/projects/${id}/changes`, payload),
  issues: (id) => api.get(`/projects/${id}/issues`),
  createIssue: (id, payload) => api.post(`/projects/${id}/issues`, payload),
  updateIssue: (issueId, payload) => api.put(`/projects/issues/${issueId}`, payload),
  risks: (id) => api.get(`/projects/${id}/risks`),
  createRisk: (id, payload) => api.post(`/projects/${id}/risks`, payload),
  updateRisk: (riskId, payload) => api.put(`/projects/risks/${riskId}`, payload),
  reports: (id) => api.get(`/projects/${id}/reports`),
  createReport: (id, payload) => api.post(`/projects/${id}/reports`, payload),
  acceptances: (id) => api.get(`/projects/${id}/acceptances`),
  createAcceptance: (id, payload) => api.post(`/projects/${id}/acceptances`, payload),
  acceptance: (id) => api.get(`/projects/acceptances/${id}`),
  pnl: (id) => api.get(`/projects/${id}/pnl`)
}

export const vendorApi = {
  list: (params) => api.get('/vendors', params),
  create: (payload) => api.post('/vendors', payload),
  detail: (id) => api.get(`/vendors/${id}`),
  update: (id, payload) => api.put(`/vendors/${id}`, payload),
  submit: (id) => api.post(`/vendors/${id}/submit`),
  blacklist: (id, payload) => api.post(`/vendors/${id}/blacklist`, payload),
  restore: (id) => api.post(`/vendors/${id}/restore`),
  risks: () => api.get('/vendors/risks'),
  contacts: (id) => api.get(`/vendors/${id}/contacts`),
  addContact: (id, payload) => api.post(`/vendors/${id}/contacts`, payload),
  banks: (id) => api.get(`/vendors/${id}/banks`),
  addBank: (id, payload) => api.post(`/vendors/${id}/banks`, payload),
  licenses: (id) => api.get(`/vendors/${id}/licenses`),
  addLicense: (id, payload) => api.post(`/vendors/${id}/licenses`, payload),
  projects: (id) => api.get(`/vendors/${id}/projects`),
  bindProject: (id, payload) => api.post(`/vendors/${id}/projects`, payload),
  evaluations: (id, year) => api.get(`/vendors/${id}/evaluations`, year ? { year } : undefined),
  addEvaluation: (id, payload) => api.post(`/vendors/${id}/evaluations`, payload),
  annualReport: (id, year) => api.get(`/vendors/${id}/annual-report`, year ? { year } : undefined)
}

export const contractApi = {
  list: (params) => api.get('/contracts', params),
  create: (payload) => api.post('/contracts', payload),
  detail: (id) => api.get(`/contracts/${id}`),
  update: (id, payload) => api.put(`/contracts/${id}`, payload),
  status: (id, payload) => api.post(`/contracts/${id}/status`, payload),
  risks: (warningDays) => api.get('/contracts/risks', { warning_days: warningDays }),
  payments: (id) => api.get(`/contracts/${id}/payments`)
}

export const financeApi = {
  costs: (params) => api.get('/finance/costs', params),
  cost: (id) => api.get(`/finance/costs/${id}`),
  reverseCost: (id, payload) => api.post(`/finance/costs/${id}/reverse`, payload),
  payments: (params) => api.get('/finance/payments', params),
  payment: (id) => api.get(`/finance/payments/${id}`),
  createPayment: (payload) => api.post('/finance/payments', payload),
  payPayment: (id, payload) => api.post(`/finance/payments/${id}/pay`, payload),
  cancelPayment: (id) => api.post(`/finance/payments/${id}/cancel`),
  receipts: (params) => api.get('/finance/receipts', params),
  receipt: (id) => api.get(`/finance/receipts/${id}`),
  createReceipt: (payload) => api.post('/finance/receipts', payload),
  cancelReceipt: (id) => api.post(`/finance/receipts/${id}/cancel`),
  revenue: (params) => api.get('/finance/revenue', params),
  revenueDetail: (id) => api.get(`/finance/revenue/${id}`),
  createRevenue: (payload) => api.post('/finance/revenue', payload),
  confirmRevenue: (id) => api.post(`/finance/revenue/${id}/confirm`),
  cancelRevenue: (id) => api.post(`/finance/revenue/${id}/cancel`),
  budgets: (params) => api.get('/finance/budgets', params),
  saveBudget: (payload) => api.post('/finance/budgets', payload),
  deleteBudget: (id) => api.del(`/finance/budgets/${id}`),
  budgetStatus: (params) => api.get('/finance/budget-status', params),
  periods: (year) => api.get('/finance/periods', year ? { year } : undefined),
  closePeriod: (payload) => api.post('/finance/periods/close', payload),
  reopenPeriod: (payload) => api.post('/finance/periods/reopen', payload),
  accounts: () => api.get('/finance/accounts'),
  projectSummary: (id) => api.get(`/finance/projects/${id}/summary`),
  projectPnl: (id) => api.get(`/finance/projects/${id}/pnl`),
  projectBudget: (id, year) => api.get(`/finance/projects/${id}/budget`, year ? { year } : undefined)
}

export const reportApi = {
  catalog: () => api.get('/reports/catalog'),
  data: (code, params) => api.get(`/reports/${code}`, params),
  snapshots: (params) => api.get('/reports/snapshots', params),
  snapshot: (code, period) => api.get(`/reports/snapshots/${code}`, period ? { period } : undefined),
  generateSnapshot: (period) => api.post('/reports/snapshots/generate', null, { params: period ? { period } : {} }),
  export: (code, params) => rawGet(`/reports/${code}/export`, params)
}

export const fileApi = {
  upload: (formData, onProgress) => api.upload('/files/upload', formData, onProgress),
  list: (params) => api.get('/files', params),
  detail: (id) => api.get(`/files/${id}`),
  remove: (id) => api.del(`/files/${id}`),
  download: (id) => rawGet(`/files/${id}/download`)
}

export const notificationApi = {
  list: (params) => api.get('/notifications', params),
  unreadCount: () => api.get('/notifications/unread-count'),
  read: (payload) => api.post('/notifications/read', payload),
  readOne: (id) => api.post(`/notifications/${id}/read`)
}

export const iamApi = {
  users: (params) => api.get('/iam/users', params),
  user: (id) => api.get(`/iam/users/${id}`),
  createUser: (payload) => api.post('/iam/users', payload),
  updateUser: (id, payload) => api.put(`/iam/users/${id}`, payload),
  resetPassword: (id, payload) => api.post(`/iam/users/${id}/reset-password`, payload),
  roles: () => api.get('/iam/roles'),
  createRole: (payload) => api.post('/iam/roles', payload),
  updateRole: (id, payload) => api.put(`/iam/roles/${id}`, payload),
  deleteRole: (id) => api.del(`/iam/roles/${id}`),
  permissionTree: () => api.get('/iam/permissions/tree'),
  depts: () => api.get('/iam/depts/tree'),
  createDept: (payload) => api.post('/iam/depts', payload),
  updateDept: (id, payload) => api.put(`/iam/depts/${id}`, payload),
  deleteDept: (id) => api.del(`/iam/depts/${id}`),
  auditLogs: (params) => api.get('/iam/audit-logs', params),
  dicts: (dictType) => api.get('/iam/dicts', dictType ? { dict_type: dictType } : undefined),
  createDict: (payload) => api.post('/iam/dicts', payload),
  updateDict: (id, payload) => api.put(`/iam/dicts/${id}`, payload),
  deleteDict: (id) => api.del(`/iam/dicts/${id}`),
  configs: () => api.get('/iam/configs'),
  setConfig: (key, payload) => api.put(`/iam/configs/${key}`, payload),
  customers: (keyword) => api.get('/iam/customers', keyword ? { keyword } : undefined),
  createCustomer: (payload) => api.post('/iam/customers', payload),
  updateCustomer: (id, payload) => api.put(`/iam/customers/${id}`, payload)
}

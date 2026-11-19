import { createRouter, createWebHashHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { setUnauthorizedHandler } from '@/api/http'

const MainLayout = () => import('@/layouts/MainLayout.vue')

export const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('@/views/ChangePassword.vue'),
    meta: { public: false, title: '修改密码', allowFirstLogin: true }
  },
  {
    path: '/',
    component: MainLayout,
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '工作台', perm: 'dashboard' }
      },
      {
        path: 'approvals/expenses',
        name: 'expenses',
        component: () => import('@/views/approvals/Expenses.vue'),
        meta: { title: '费用报销', perm: 'approval:expense' }
      },
      {
        path: 'approvals/leaves',
        name: 'leaves',
        component: () => import('@/views/approvals/Leaves.vue'),
        meta: { title: '请假管理', perm: 'approval:leave' }
      },
      {
        path: 'approvals/documents',
        name: 'documents',
        component: () => import('@/views/approvals/Documents.vue'),
        meta: { title: '文件审批', perm: 'approval:document' }
      },
      {
        path: 'approvals/tasks',
        name: 'tasks',
        component: () => import('@/views/approvals/Tasks.vue'),
        meta: { title: '我的待办', perm: 'workflow:task' }
      },
      {
        path: 'approvals/instances',
        name: 'instances',
        component: () => import('@/views/approvals/Instances.vue'),
        meta: { title: '流程实例', perm: 'workflow:instance' }
      },
      {
        path: 'projects',
        name: 'projects',
        component: () => import('@/views/projects/Index.vue'),
        meta: { title: '项目管理', perm: 'project:view' }
      },
      {
        path: 'projects/:id',
        name: 'project-detail',
        component: () => import('@/views/projects/Detail.vue'),
        meta: { title: '项目详情', perm: 'project:view' }
      },
      {
        path: 'vendors',
        name: 'vendors',
        component: () => import('@/views/vendors/Index.vue'),
        meta: { title: '供应商管理', perm: 'vendor:view' }
      },
      {
        path: 'vendors/:id',
        name: 'vendor-detail',
        component: () => import('@/views/vendors/Detail.vue'),
        meta: { title: '供应商详情', perm: 'vendor:view' }
      },
      {
        path: 'contracts',
        name: 'contracts',
        component: () => import('@/views/contracts/Index.vue'),
        meta: { title: '合同管理', perm: 'contract:view' }
      },
      {
        path: 'contracts/:id',
        name: 'contract-detail',
        component: () => import('@/views/contracts/Detail.vue'),
        meta: { title: '合同详情', perm: 'contract:view' }
      },
      {
        path: 'finance/costs',
        name: 'costs',
        component: () => import('@/views/finance/Costs.vue'),
        meta: { title: '成本台账', perm: 'finance:cost' }
      },
      {
        path: 'finance/payments',
        name: 'payments',
        component: () => import('@/views/finance/Payments.vue'),
        meta: { title: '付款管理', perm: 'finance:payment' }
      },
      {
        path: 'finance/receipts',
        name: 'receipts',
        component: () => import('@/views/finance/Receipts.vue'),
        meta: { title: '收款管理', perm: 'finance:receipt' }
      },
      {
        path: 'finance/revenue',
        name: 'revenue',
        component: () => import('@/views/finance/Revenue.vue'),
        meta: { title: '计收确认', perm: 'finance:revenue' }
      },
      {
        path: 'finance/budgets',
        name: 'budgets',
        component: () => import('@/views/finance/Budgets.vue'),
        meta: { title: '预算管理', perm: 'finance:budget' }
      },
      {
        path: 'finance/periods',
        name: 'periods',
        component: () => import('@/views/finance/Periods.vue'),
        meta: { title: '财务期间', perm: 'finance:period' }
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/reports/Index.vue'),
        meta: { title: '报表中心', perm: 'report:view' }
      },
      {
        path: 'system/users',
        name: 'users',
        component: () => import('@/views/system/Users.vue'),
        meta: { title: '用户管理', perm: 'system:user' }
      },
      {
        path: 'system/roles',
        name: 'roles',
        component: () => import('@/views/system/Roles.vue'),
        meta: { title: '角色权限', perm: 'system:role' }
      },
      {
        path: 'system/depts',
        name: 'depts',
        component: () => import('@/views/system/Depts.vue'),
        meta: { title: '组织架构', perm: 'system:dept' }
      },
      {
        path: 'system/workflows',
        name: 'workflows',
        component: () => import('@/views/system/Workflows.vue'),
        meta: { title: '审批流程配置', perm: 'workflow:definition' }
      },
      {
        path: 'system/audit',
        name: 'audit',
        component: () => import('@/views/system/Audit.vue'),
        meta: { title: '审计日志', perm: 'system:audit' }
      },
      {
        path: 'system/config',
        name: 'config',
        component: () => import('@/views/system/Config.vue'),
        meta: { title: '系统参数', perm: 'system:config' }
      }
    ]
  },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/Forbidden.vue'),
    meta: { public: true, title: '无权限' }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
    meta: { public: true, title: '页面不存在' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

setUnauthorizedHandler(() => {
  if (router.currentRoute.value.path !== '/login') {
    const redirect = router.currentRoute.value.fullPath
    router.replace({ path: '/login', query: redirect && redirect !== '/login' ? { redirect } : {} })
  }
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const meta = useMetaStore()

  // 令牌在 HttpOnly Cookie 中，首次导航必须向后端确认会话，再判断权限。
  await auth.bootstrap()

  if (to.meta.public) {
    if (to.path === '/login' && auth.profile && !auth.firstLogin) return '/dashboard'
    return true
  }

  if (!auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (!auth.profile) {
    try {
      await auth.loadProfile()
    } catch {
      await auth.logout(false)
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  if (auth.firstLogin && to.path !== '/change-password') {
    return '/change-password'
  }
  if (!auth.firstLogin && to.path === '/change-password') {
    return '/dashboard'
  }

  if (to.meta.perm && !auth.can(to.meta.perm)) {
    ElMessage.warning('您没有访问该页面的权限')
    return '/403'
  }

  try {
    await meta.ensure()
  } catch {
    /* 元数据失败不阻塞页面渲染 */
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · EOMS` : 'EOMS 企业运营管理系统'
})

export default router

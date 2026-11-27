<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ collapsed }">
      <div class="sidebar-brand">
        <img class="brand-mark" src="/brand/dongyan-logo.jpg" alt="东研智联 Logo" />
        <span v-show="!collapsed">东研智联运营平台</span>
      </div>
      <div class="sidebar-menu">
        <el-menu
          :default-active="activePath"
          :collapse="collapsed"
          :collapse-transition="false"
          router
          unique-opened
          background-color="transparent"
          text-color="#a9b4c6"
          active-text-color="#ffffff"
        >
          <menu-node v-for="menu in auth.menus" :key="menu.id" :menu="menu" />
        </el-menu>
      </div>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <el-icon style="cursor: pointer; font-size: 18px" @click="toggleCollapse">
          <Fold v-if="!collapsed" />
          <Expand v-else />
        </el-icon>
        <div class="topbar-title">{{ route.meta.title || '工作台' }}</div>
        <div class="topbar-spacer" />

        <el-tooltip content="刷新当前页" placement="bottom">
          <span class="topbar-action" @click="reloadPage">
            <el-icon><Refresh /></el-icon>
          </span>
        </el-tooltip>

        <el-popover placement="bottom-end" :width="380" trigger="click" @show="loadNotifications">
          <template #reference>
            <span class="topbar-action">
              <el-badge :value="unreadCount" :hidden="!unreadCount" :max="99">
                <el-icon style="font-size: 17px"><Bell /></el-icon>
              </el-badge>
              <span>通知</span>
            </span>
          </template>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px">
            <strong>我的通知</strong>
            <el-button link type="primary" :disabled="!unreadCount" @click="markAllRead">全部已读</el-button>
          </div>
          <div class="notice-list">
            <div v-if="!notifications.length" class="empty" style="padding: 22px 0">暂无通知</div>
            <div
              v-for="item in notifications"
              :key="item.id"
              class="notice-item"
              :class="{ unread: !item.read_at }"
            >
              <div class="title">
                <span>{{ item.title }}</span>
                <el-tag size="small" :type="item.type === 'ALERT' ? 'danger' : 'warning'" effect="plain">
                  {{ item.type === 'ALERT' ? '预警' : item.type === 'APPROVAL' ? '审批' : '系统' }}
                </el-tag>
              </div>
              <div class="body">{{ item.content }}</div>
              <div class="body" style="display: flex; justify-content: space-between; align-items: center">
                <span>{{ fromNow(item.created_at) }}</span>
                <el-button link type="primary" size="small" @click="openNotice(item)">查看</el-button>
              </div>
            </div>
          </div>
        </el-popover>

        <el-dropdown trigger="click" @command="handleCommand">
          <div class="user-chip">
            <el-avatar :size="32" style="background: #2563eb">{{ initials }}</el-avatar>
            <div class="user-meta">
              <strong>{{ auth.user.real_name || auth.user.username }}</strong>
              <span>{{ roleText }}</span>
            </div>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile" :icon="User">个人信息</el-dropdown-item>
              <el-dropdown-item command="password" :icon="Lock">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>

      <main class="page-container">
        <router-view v-slot="{ Component }">
          <component :is="Component" :key="route.fullPath" />
        </router-view>
      </main>
    </div>

    <el-dialog v-model="passwordVisible" title="修改密码" width="440px" :close-on-click-modal="false">
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <div class="form-tip">密码至少 8 位，需同时包含字母与数字；修改后需要重新登录。</div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="passwordVisible = false">取消</el-button>
          <el-button type="primary" :loading="pwdLoading" @click="submitPassword">确认修改</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="profileVisible" title="个人信息" width="460px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="姓名">{{ auth.user.real_name }}</el-descriptions-item>
        <el-descriptions-item label="账号">{{ auth.user.username }}</el-descriptions-item>
        <el-descriptions-item label="公司">{{ auth.user.company_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="部门">{{ auth.user.dept_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="岗位">{{ auth.user.position || '-' }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{ roleText }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ auth.user.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="最近登录">{{ datetime(auth.user.last_login_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Lock, SwitchButton, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { notificationApi } from '@/api'
import MenuNode from '@/components/MenuNode.vue'
import { datetime, fromNow } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const collapsed = ref(localStorage.getItem('eoms_sidebar_collapsed') === '1')
const unreadCount = ref(0)
const notifications = ref([])
const passwordVisible = ref(false)
const profileVisible = ref(false)
const pwdLoading = ref(false)
const pwdFormRef = ref()
const pwdForm = ref({ old_password: '', new_password: '', confirm: '' })
let timer = null

const activePath = computed(() => {
  const path = route.path
  if (path.startsWith('/projects')) return '/projects'
  if (path.startsWith('/vendors')) return '/vendors'
  if (path.startsWith('/contracts')) return '/contracts'
  return path
})

const initials = computed(() => {
  const name = auth.user.real_name || auth.user.username || 'U'
  return name.slice(-2)
})

const roleText = computed(() => (auth.user.roles || []).map((role) => role.name).join(' / ') || '未分配角色')

const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码长度需为 8-64 位', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value && (!/[A-Za-z]/.test(value) || !/\d/.test(value))) {
          callback(new Error('密码需同时包含字母与数字'))
        } else callback()
      },
      trigger: 'blur'
    }
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== pwdForm.value.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('eoms_sidebar_collapsed', collapsed.value ? '1' : '0')
}

function reloadPage() {
  window.location.reload()
}

async function loadNotifications() {
  try {
    const [list, count] = await Promise.all([
      notificationApi.list({ page: 1, page_size: 8 }),
      notificationApi.unreadCount()
    ])
    notifications.value = list.items || []
    unreadCount.value = count.count || count.unread || 0
  } catch {
    /* 通知加载失败静默处理 */
  }
}

async function refreshUnread() {
  try {
    const count = await notificationApi.unreadCount()
    unreadCount.value = count.count || count.unread || 0
  } catch {
    /* ignore */
  }
}

async function markAllRead() {
  await notificationApi.read({ all: true })
  unreadCount.value = 0
  notifications.value = notifications.value.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() }))
}

async function openNotice(item) {
  if (!item.read_at) {
    try {
      await notificationApi.readOne(item.id)
      item.read_at = new Date().toISOString()
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch {
      /* ignore */
    }
  }
  if (item.link && item.link.startsWith('/')) router.push(item.link)
}

function handleCommand(command) {
  if (command === 'profile') profileVisible.value = true
  if (command === 'password') {
    pwdForm.value = { old_password: '', new_password: '', confirm: '' }
    passwordVisible.value = true
  }
  if (command === 'logout') {
    ElMessageBox.confirm('确认退出登录吗？', '提示', { type: 'warning' })
      .then(async () => {
        await auth.logout()
        router.replace('/login')
      })
      .catch(() => {})
  }
}

async function submitPassword() {
  await pwdFormRef.value.validate()
  pwdLoading.value = true
  try {
    await auth.changePassword({
      old_password: pwdForm.value.old_password,
      new_password: pwdForm.value.new_password
    })
    ElMessage.success('密码已修改，请重新登录')
    passwordVisible.value = false
    router.replace('/login')
  } finally {
    pwdLoading.value = false
  }
}

onMounted(() => {
  loadNotifications()
  timer = setInterval(refreshUnread, 60000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
</style>

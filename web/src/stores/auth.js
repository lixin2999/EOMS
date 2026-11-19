import { defineStore } from 'pinia'
import { authApi } from '@/api'
import { tokenStore } from '@/api/http'

const PROFILE_KEY = 'eoms_profile'

function readProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    profile: readProfile(),
    permissions: new Set(readProfile()?.permissions || []),
    loading: false,
    // 会话是否已向后端确认（Cookie 无法在前端判断有效性，必须问 /auth/me）。
    initialized: false
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.profile && state.initialized),
    user: (state) => state.profile || {},
    menus: (state) => state.profile?.menus || [],
    isSuper: (state) => Boolean(state.profile?.is_super),
    firstLogin: (state) => Boolean(state.profile?.first_login)
  },
  actions: {
    persist(profile) {
      this.profile = profile
      this.permissions = new Set(profile?.permissions || [])
      localStorage.setItem(PROFILE_KEY, JSON.stringify(profile || null))
    },
    async login(payload) {
      this.loading = true
      try {
        // 登录成功仅返回用户资料与 CSRF Token，令牌已写入 HttpOnly Cookie。
        const data = await authApi.login(payload)
        this.persist(data.user)
        this.initialized = true
        return data
      } finally {
        this.loading = false
      }
    },
    async bootstrap() {
      // 首次导航时校验会话：无 Cookie 直接置未登录，避免多余 401 请求。
      if (this.initialized) return this.profile
      if (!tokenStore.csrf) {
        this.persist(null)
        this.initialized = true
        return null
      }
      try {
        return await this.loadProfile()
      } catch {
        this.persist(null)
        this.initialized = true
        return null
      }
    },
    async loadProfile() {
      const profile = await authApi.me()
      this.persist(profile)
      this.initialized = true
      return profile
    },
    can(permission) {
      if (!permission) return true
      if (this.isSuper) return true
      if (Array.isArray(permission)) return permission.some((item) => this.permissions.has(item))
      return this.permissions.has(permission)
    },
    canAny(list) {
      if (!list?.length) return true
      return list.some((item) => this.can(item))
    },
    canAll(list) {
      if (!list?.length) return true
      return list.every((item) => this.can(item))
    },
    async logout(callApi = true) {
      if (callApi && this.initialized) {
        try {
          // 令牌与 CSRF Cookie 由后端清除，前端无需传 refresh_token。
          await authApi.logout()
        } catch {
          /* 忽略登出接口异常，本地状态必须清理 */
        }
      }
      tokenStore.clear()
      this.profile = null
      this.permissions = new Set()
      this.initialized = true
    },
    async changePassword(payload) {
      await authApi.changePassword(payload)
      tokenStore.clear()
      this.profile = null
      this.permissions = new Set()
      this.initialized = true
    }
  }
})

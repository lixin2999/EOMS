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
    loading: false
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.profile && tokenStore.access),
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
        const data = await authApi.login(payload)
        tokenStore.set(data.access_token, data.refresh_token)
        await this.loadProfile()
        return data
      } finally {
        this.loading = false
      }
    },
    async loadProfile() {
      const profile = await authApi.me()
      this.persist(profile)
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
      const refreshToken = tokenStore.refresh
      if (callApi && tokenStore.access) {
        try {
          await authApi.logout(refreshToken)
        } catch {
          /* 忽略登出接口异常，本地状态必须清理 */
        }
      }
      tokenStore.clear()
      this.profile = null
      this.permissions = new Set()
    },
    async changePassword(payload) {
      await authApi.changePassword(payload)
      tokenStore.clear()
      this.profile = null
      this.permissions = new Set()
    }
  }
})

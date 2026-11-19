import { defineStore } from 'pinia'
import { metaApi } from '@/api'

export const useMetaStore = defineStore('meta', {
  state: () => ({
    loaded: false,
    loading: null,
    labels: {},
    enums: {},
    options: {
      users: [],
      depts: [],
      projects: [],
      vendors: [],
      contracts: [],
      accounts: [],
      roles: []
    },
    dicts: []
  }),
  getters: {
    projectOptions: (state) => state.options.projects || [],
    userOptions: (state) => state.options.users || [],
    vendorOptions: (state) => state.options.vendors || [],
    contractOptions: (state) => state.options.contracts || [],
    accountOptions: (state) => state.options.accounts || [],
    deptOptions: (state) => state.options.depts || [],
    roleOptions: (state) => state.options.roles || [],
    dictMap: (state) => {
      const map = {}
      for (const item of state.dicts) {
        if (!map[item.dict_type]) map[item.dict_type] = []
        map[item.dict_type].push(item)
      }
      return map
    }
  },
  actions: {
    async ensure() {
      if (this.loaded) return
      if (this.loading) return this.loading
      this.loading = (async () => {
        const results = await Promise.allSettled([
          metaApi.me(),
          metaApi.enums(),
          metaApi.options(),
          metaApi.dicts()
        ])
        if (results[0].status === 'fulfilled') this.labels = results[0].value.labels || {}
        if (results[1].status === 'fulfilled') this.enums = results[1].value.enums || {}
        if (results[2].status === 'fulfilled') {
          this.options = { ...this.options, ...(results[2].value || {}) }
        }
        if (results[3].status === 'fulfilled') this.dicts = results[3].value || []
        this.loaded = true
      })()
      try {
        await this.loading
      } finally {
        this.loading = null
      }
    },
    async refreshOptions() {
      try {
        const data = await metaApi.options()
        this.options = { ...this.options, ...(data || {}) }
      } catch {
        /* 下拉数据刷新失败不阻塞主流程 */
      }
    },
    label(value, fallback = '') {
      return this.labels[value] || fallback || value || '-'
    }
  }
})

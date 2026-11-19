import axios from 'axios'
import { ElMessage } from 'element-plus'

const BASE = import.meta.env.VITE_API_BASE || '/api/v1'
const TOKEN_KEY = 'eoms_access_token'
const REFRESH_KEY = 'eoms_refresh_token'

export const tokenStore = {
  get access() {
    return localStorage.getItem(TOKEN_KEY) || ''
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY) || ''
  },
  set(access, refresh) {
    if (access) localStorage.setItem(TOKEN_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem('eoms_profile')
  }
}

const http = axios.create({
  baseURL: BASE,
  timeout: 60000
})

let refreshing = null
let onUnauthorized = null

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

function redirectToLogin() {
  tokenStore.clear()
  if (onUnauthorized) onUnauthorized()
}

function newIdempotencyKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

http.interceptors.request.use((config) => {
  const token = tokenStore.access
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (['post', 'put', 'delete', 'patch'].includes((config.method || '').toLowerCase())) {
    if (!config.headers['Idempotency-Key'] && !config.headers['idempotency-key']) {
      config.headers['Idempotency-Key'] = newIdempotencyKey()
    }
  }
  return config
})

function fieldMessage(data) {
  if (Array.isArray(data) && data.length) {
    return data.map((item) => `${item.field || ''} ${item.msg || ''}`.trim()).join('；')
  }
  return ''
}

http.interceptors.response.use(
  (response) => {
    if (response.config.responseType === 'blob') return response
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      const message = body.msg || '请求失败'
      ElMessage.error(fieldMessage(body.data) || message)
      return Promise.reject(Object.assign(new Error(message), { code: body.code, data: body.data }))
    }
    return body
  },
  async (error) => {
    const { response, config } = error
    if (!response) {
      ElMessage.error(error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '网络异常，请检查服务是否可用')
      return Promise.reject(error)
    }
    const body = response.data || {}
    const message = body.msg || fieldMessage(body.data) || `请求失败（${response.status}）`

    if (response.status === 401 && !config.__retried && !config.url?.includes('/auth/')) {
      config.__retried = true
      try {
        const access = await refreshAccess()
        config.headers.Authorization = `Bearer ${access}`
        return http.request(config)
      } catch (refreshError) {
        redirectToLogin()
        ElMessage.warning('登录已过期，请重新登录')
        return Promise.reject(refreshError)
      }
    }

    if (response.status === 401) {
      redirectToLogin()
    } else if (response.status === 403 && String(message).includes('初始密码')) {
      window.location.hash = '#/change-password'
    } else {
      ElMessage.error(message)
    }
    return Promise.reject(Object.assign(new Error(message), { code: body.code, data: body.data, status: response.status }))
  }
)

async function refreshAccess() {
  if (refreshing) return refreshing
  refreshing = (async () => {
    const refreshToken = tokenStore.refresh
    if (!refreshToken) throw new Error('no refresh token')
    const resp = await axios.post(`${BASE}/auth/refresh`, { refresh_token: refreshToken }, { timeout: 15000 })
    const body = resp.data
    if (!body || body.code !== 0 || !body.data?.access_token) throw new Error('refresh failed')
    tokenStore.set(body.data.access_token, body.data.refresh_token)
    return body.data.access_token
  })()
  try {
    return await refreshing
  } finally {
    refreshing = null
  }
}

export function rawGet(url, params) {
  return http.get(url, { params, responseType: 'blob' })
}

export const api = {
  get: (url, params) => http.get(url, { params }),
  post: (url, data, config) => http.post(url, data, config),
  put: (url, data) => http.put(url, data),
  del: (url, params) => http.delete(url, { params }),
  upload: (url, formData, onProgress) =>
    http.post(url, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100))
      }
    })
}

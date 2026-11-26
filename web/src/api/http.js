import axios from 'axios'
import { ElMessage } from 'element-plus'

const BASE = import.meta.env.VITE_API_BASE || '/api/v1'
const PROFILE_KEY = 'eoms_profile'
const CSRF_COOKIE = 'eoms_csrf'

function readCookie(name) {
  const target = `${name}=`
  const hit = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(target))
  return hit ? decodeURIComponent(hit.slice(target.length)) : ''
}

// 令牌不再存 localStorage：access/refresh 由后端写 HttpOnly Cookie，
// 前端只需读 CSRF Token 并在写操作时回传到 X-CSRF-Token 头。
export const tokenStore = {
  get csrf() {
    return readCookie(CSRF_COOKIE)
  },
  clear() {
    localStorage.removeItem(PROFILE_KEY)
  }
}

const http = axios.create({
  baseURL: BASE,
  timeout: 60000,
  withCredentials: true
})

let refreshing = null
let onUnauthorized = null
let redirectingToLogin = false
let authFailureNotified = false

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

function redirectToLogin() {
  tokenStore.clear()
  if (redirectingToLogin) return
  redirectingToLogin = true
  if (onUnauthorized) onUnauthorized()
}

function newIdempotencyKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

http.interceptors.request.use((config) => {
  const method = (config.method || '').toLowerCase()
  if (['post', 'put', 'delete', 'patch'].includes(method)) {
    const csrf = tokenStore.csrf
    if (csrf && !config.headers['X-CSRF-Token']) config.headers['X-CSRF-Token'] = csrf
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
    redirectingToLogin = false
    authFailureNotified = false
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
        await refreshAccess()
        return http.request(config)
      } catch (refreshError) {
        if (refreshError.response?.status === 401) {
          redirectToLogin()
          if (!authFailureNotified) {
            authFailureNotified = true
            ElMessage.warning('登录已过期，请重新登录')
          }
        } else if (!authFailureNotified) {
          // 422/5xx/网络异常不等于登录过期，保留当前会话并允许后续请求重试。
          authFailureNotified = true
          ElMessage.error('会话刷新失败，请稍后重试')
        }
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
    // refresh token 在 HttpOnly Cookie 中；发送空 JSON 对象以满足后端 DTO，写操作带 CSRF 头。
    const resp = await axios.post(`${BASE}/auth/refresh`, {}, {
      timeout: 15000,
      withCredentials: true,
      headers: { 'X-CSRF-Token': tokenStore.csrf }
    })
    const body = resp.data
    if (!body || body.code !== 0) throw new Error('refresh failed')
    return body.data
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

import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 60000,
})

// Request interceptor - add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('teamgr_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// --- Refresh token logic with concurrency lock ---
let isRefreshing = false
let refreshSubscribers = []

function onTokenRefreshed(newToken) {
  refreshSubscribers.forEach((cb) => cb(newToken))
  refreshSubscribers = []
}

function addRefreshSubscriber(cb) {
  refreshSubscribers.push(cb)
}

async function tryRefreshToken() {
  const refreshToken = localStorage.getItem('teamgr_refresh_token')

  try {
    // Always try refresh — HTTP-only cookie may exist even if localStorage
    // was cleared (Safari ITP). Use raw axios to avoid interceptor loop.
    const payload = refreshToken ? { refresh_token: refreshToken } : {}
    const res = await axios.post('/api/auth/refresh', payload)
    const { token, refresh_token: newRefresh } = res.data
    localStorage.setItem('teamgr_token', token)
    localStorage.setItem('teamgr_refresh_token', newRefresh)
    return token
  } catch (e) {
    localStorage.removeItem('teamgr_refresh_token')
    return null
  }
}

// Response interceptor - handle auth errors with auto-refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Only handle 401 and not already retried
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error)
    }

    // Don't try to refresh for auth endpoints themselves
    if (originalRequest.url?.includes('/api/auth/refresh') ||
        originalRequest.url?.includes('/api/auth/login')) {
      return Promise.reject(error)
    }

    // Always try refresh — HTTP-only cookie may exist even if localStorage was cleared
    if (isRefreshing) {
      // Another refresh is in progress — wait for it
      return new Promise((resolve) => {
        addRefreshSubscriber((newToken) => {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          originalRequest._retry = true
          resolve(api(originalRequest))
        })
      })
    }

    // Start refreshing
    isRefreshing = true
    originalRequest._retry = true

    try {
      const newToken = await tryRefreshToken()
      if (newToken) {
        onTokenRefreshed(newToken)
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return api(originalRequest)
      } else {
        // Refresh failed — go to login
        localStorage.removeItem('teamgr_token')
        refreshSubscribers = []
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    } finally {
      isRefreshing = false
    }
  }
)

export default api

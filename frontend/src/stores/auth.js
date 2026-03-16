import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

function getOrCreateDeviceId() {
  let id = localStorage.getItem('teamgr_device_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('teamgr_device_id', id)
  }
  return id
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('teamgr_token') || '')
  const authenticated = ref(false)
  const passwordConfigured = ref(true)
  const statusChecked = ref(false)

  async function checkStatus() {
    try {
      const res = await api.get('/api/auth/status')
      passwordConfigured.value = res.data.password_configured
      authenticated.value = res.data.authenticated
      statusChecked.value = true
    } catch (e) {
      statusChecked.value = true
    }
  }

  async function login(password) {
    const deviceId = getOrCreateDeviceId()
    const res = await api.post('/api/auth/login', { password, device_id: deviceId })
    token.value = res.data.token
    authenticated.value = true
    localStorage.setItem('teamgr_token', res.data.token)

    if (res.data.refresh_token) {
      localStorage.setItem('teamgr_refresh_token', res.data.refresh_token)
    }

    return res.data
  }

  async function trustDevice() {
    const deviceId = getOrCreateDeviceId()
    const res = await api.post('/api/auth/trust-device', { device_id: deviceId })
    localStorage.setItem('teamgr_refresh_token', res.data.refresh_token)
  }

  async function blacklistDevice() {
    const deviceId = getOrCreateDeviceId()
    await api.post('/api/auth/blacklist-device', { device_id: deviceId })
  }

  async function refreshToken() {
    const refreshTk = localStorage.getItem('teamgr_refresh_token')
    if (!refreshTk) return false

    try {
      const res = await api.post('/api/auth/refresh', { refresh_token: refreshTk })
      token.value = res.data.token
      authenticated.value = true
      localStorage.setItem('teamgr_token', res.data.token)
      localStorage.setItem('teamgr_refresh_token', res.data.refresh_token)
      return true
    } catch (e) {
      localStorage.removeItem('teamgr_refresh_token')
      return false
    }
  }

  function logout() {
    token.value = ''
    authenticated.value = false
    localStorage.removeItem('teamgr_token')
    localStorage.removeItem('teamgr_refresh_token')
    // Keep device_id — persists across logins
  }

  return {
    token,
    authenticated,
    passwordConfigured,
    statusChecked,
    checkStatus,
    login,
    trustDevice,
    blacklistDevice,
    refreshToken,
    logout,
  }
})

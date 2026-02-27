import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

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
    const res = await api.post('/api/auth/login', { password })
    token.value = res.data.token
    authenticated.value = true
    localStorage.setItem('teamgr_token', res.data.token)
    return res.data
  }

  function logout() {
    token.value = ''
    authenticated.value = false
    localStorage.removeItem('teamgr_token')
  }

  return {
    token,
    authenticated,
    passwordConfigured,
    statusChecked,
    checkStatus,
    login,
    logout,
  }
})

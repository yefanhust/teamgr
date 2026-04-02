<template>
  <router-view v-slot="{ Component }">
    <keep-alive include="ScholarView">
      <component :is="Component" />
    </keep-alive>
  </router-view>

  <!-- Re-login overlay: shown when token expires mid-operation -->
  <van-overlay :show="showReLogin" z-index="9999" @click="() => {}">
    <div class="relogin-center" @click.stop>
      <div class="relogin-modal">
        <div class="text-center mb-4">
          <div class="text-3xl mb-2">🔒</div>
          <h3 class="text-lg font-bold text-gray-800">登录已过期</h3>
          <p class="text-gray-500 text-sm mt-1">请重新输入密码，当前页面内容不会丢失</p>
        </div>
        <form @submit.prevent="handleReLogin">
          <van-field
            v-model="reLoginPassword"
            type="password"
            placeholder="请输入访问密码"
            :error-message="reLoginError"
            clearable
          />
          <van-button
            type="primary"
            block
            :loading="reLoginLoading"
            native-type="submit"
            class="mt-4"
          >
            重新登录
          </van-button>
        </form>
      </div>
    </div>
  </van-overlay>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { setReLoginHandler } from './api'
import { useAuthStore } from './stores/auth'

const showReLogin = ref(false)
const reLoginPassword = ref('')
const reLoginError = ref('')
const reLoginLoading = ref(false)

let reLoginResolve = null

function handleReLoginRequest() {
  return new Promise((resolve) => {
    reLoginResolve = resolve
    showReLogin.value = true
    reLoginPassword.value = ''
    reLoginError.value = ''
  })
}

async function handleReLogin() {
  if (!reLoginPassword.value.trim()) {
    reLoginError.value = '请输入密码'
    return
  }

  reLoginLoading.value = true
  reLoginError.value = ''

  try {
    const auth = useAuthStore()
    await auth.login(reLoginPassword.value)
    const newToken = localStorage.getItem('teamgr_token')
    showReLogin.value = false
    reLoginResolve?.(newToken)
    reLoginResolve = null
  } catch (e) {
    const detail = e.response?.data?.detail || '登录失败'
    if (e.response?.status === 403 || e.response?.status === 429) {
      reLoginError.value = detail
    } else {
      reLoginError.value = detail
    }
  } finally {
    reLoginLoading.value = false
  }
}

onMounted(() => {
  setReLoginHandler(handleReLoginRequest)
})
</script>

<style>
.relogin-center {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 1rem;
}
.relogin-modal {
  width: 100%;
  max-width: 360px;
  background: white;
  border-radius: 16px;
  padding: 2rem 1.5rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}
</style>

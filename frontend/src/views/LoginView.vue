<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 px-4">
    <div class="w-full max-w-sm bg-white rounded-2xl shadow-lg p-8">
      <div class="text-center mb-8">
        <div class="text-4xl mb-2">👥</div>
        <h1 class="text-2xl font-bold text-gray-800">TeaMgr</h1>
        <p class="text-gray-500 text-sm mt-1">人才卡管理系统</p>
      </div>

      <form @submit.prevent="handleLogin">
        <van-field
          v-model="password"
          type="password"
          placeholder="请输入访问密码"
          :error-message="errorMsg"
          class="mb-4"
        />

        <van-button
          type="primary"
          block
          :loading="loading"
          native-type="submit"
          class="mt-4"
        >
          登 录
        </van-button>
      </form>

      <p v-if="banMsg" class="text-red-500 text-sm text-center mt-4">
        {{ banMsg }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { showToast } from 'vant'

const router = useRouter()
const auth = useAuthStore()

const password = ref('')
const loading = ref(false)
const errorMsg = ref('')
const banMsg = ref('')

async function handleLogin() {
  if (!password.value.trim()) {
    errorMsg.value = '请输入密码'
    return
  }

  loading.value = true
  errorMsg.value = ''
  banMsg.value = ''

  try {
    await auth.login(password.value)
    showToast('登录成功')
    router.push('/')
  } catch (e) {
    const detail = e.response?.data?.detail || '登录失败'
    if (e.response?.status === 403) {
      banMsg.value = detail
    } else if (e.response?.status === 429) {
      banMsg.value = detail
    } else {
      errorMsg.value = detail
    }
  } finally {
    loading.value = false
  }
}
</script>

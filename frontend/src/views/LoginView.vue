<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 px-4">
    <div class="w-full max-w-sm bg-white rounded-2xl shadow-lg p-8">
      <div class="text-center mb-8">
        <div class="text-4xl mb-2">👥</div>
        <h1 class="text-2xl font-bold text-gray-800">TeaMgr</h1>
        <p class="text-gray-500 text-sm mt-1">人才卡管理系统</p>
      </div>

      <!-- Login form -->
      <form v-if="!showTrustPrompt" @submit.prevent="handleLogin">
        <van-field
          v-model="password"
          type="password"
          placeholder="请输入访问密码"
          :error-message="errorMsg"
          class="mb-4"
          @keypress.enter="handleLogin"
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

      <!-- Device trust prompt (unknown device after login) -->
      <div v-if="showTrustPrompt" class="text-center">
        <div class="text-green-500 text-lg font-medium mb-4">登录成功</div>
        <p class="text-gray-600 text-sm mb-6">
          是否信任此设备？信任后 30 天内无需重新输入密码。
        </p>
        <van-button
          type="primary"
          block
          :loading="actionLoading"
          @click="handleTrust"
          class="mb-3"
        >
          信任此设备
        </van-button>
        <van-button
          plain
          block
          @click="skipTrust"
          class="mb-3"
        >
          跳过
        </van-button>
        <van-button
          plain
          type="danger"
          block
          :loading="actionLoading"
          @click="handleBlacklist"
          size="small"
        >
          非可信设备（不再提示）
        </van-button>
      </div>

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
const showTrustPrompt = ref(false)
const actionLoading = ref(false)

async function handleLogin() {
  if (!password.value.trim()) {
    errorMsg.value = '请输入密码'
    return
  }

  loading.value = true
  errorMsg.value = ''
  banMsg.value = ''

  try {
    const data = await auth.login(password.value)

    if (data.device_trusted) {
      // Trusted device — got refresh_token, go straight in
      showToast('登录成功')
      router.push('/')
    } else if (data.device_blacklisted) {
      // Blacklisted device — 24h token only, no prompt
      showToast('登录成功')
      router.push('/')
    } else {
      // Unknown device — show trust/skip/blacklist prompt
      showTrustPrompt.value = true
    }
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

async function handleTrust() {
  actionLoading.value = true
  try {
    await auth.trustDevice()
    showToast('设备已信任')
    router.push('/')
  } catch (e) {
    showToast('信任失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    actionLoading.value = false
  }
}

async function handleBlacklist() {
  actionLoading.value = true
  try {
    await auth.blacklistDevice()
    showToast('登录成功')
    router.push('/')
  } catch (e) {
    showToast('操作失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    actionLoading.value = false
  }
}

function skipTrust() {
  showToast('登录成功')
  router.push('/')
}
</script>

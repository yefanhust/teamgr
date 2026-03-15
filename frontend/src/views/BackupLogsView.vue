<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
          <h1 class="text-lg font-bold text-gray-800">Backup Logs</h1>
        </div>
        <van-button
          type="primary"
          size="small"
          :loading="triggering"
          @click="triggerBackup"
          icon="replay"
        >
          立即备份
        </van-button>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 py-4">
      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <van-loading size="36px">Loading...</van-loading>
      </div>

      <template v-else>
        <!-- Health Status Card -->
        <div
          class="rounded-xl shadow-sm p-4 mb-4"
          :class="status.healthy ? 'bg-emerald-50 border border-emerald-200' : 'bg-red-50 border border-red-200'"
        >
          <div class="flex items-center gap-2 mb-2">
            <van-icon
              :name="status.healthy ? 'shield-o' : 'warning-o'"
              :size="20"
              :color="status.healthy ? '#10B981' : '#EF4444'"
            />
            <span class="font-bold" :class="status.healthy ? 'text-emerald-700' : 'text-red-700'">
              {{ status.healthy ? '备份正常' : '备份异常' }}
            </span>
          </div>
          <div class="text-sm text-gray-600 space-y-1">
            <div v-if="status.last_success_at">
              上次成功: <span class="font-mono">{{ formatTime(status.last_success_at) }}</span>
            </div>
            <div v-if="status.last_backup?.file_size">
              包大小: <span class="font-mono">{{ formatSize(status.last_backup.file_size) }}</span>
            </div>
            <div v-if="status.last_backup?.encrypted !== null">
              加密: <span class="font-mono">{{ status.last_backup.encrypted ? 'AES-256-GCM' : '未加密' }}</span>
            </div>
            <div v-if="!status.healthy && status.last_backup?.error_message" class="text-red-600 text-xs mt-1">
              {{ status.last_backup.error_message }}
            </div>
            <div v-if="status.reason === 'no_logs'" class="text-gray-500 text-xs">
              暂无备份记录
            </div>
          </div>
        </div>

        <!-- Backup Log Timeline -->
        <div v-if="logs.length">
          <h2 class="text-sm font-bold text-gray-600 mb-3 flex items-center gap-1.5">
            <span class="inline-block w-1 h-4 rounded-full bg-blue-500"></span>
            备份历史
          </h2>
          <div class="space-y-2">
            <div
              v-for="log in logs"
              :key="log.id"
              class="bg-white rounded-xl shadow-sm p-3"
            >
              <div class="flex items-center justify-between mb-1">
                <div class="flex items-center gap-2">
                  <span
                    class="inline-block w-2.5 h-2.5 rounded-full"
                    :class="log.status === 'success' ? 'bg-emerald-500' : 'bg-red-500'"
                  ></span>
                  <span class="text-sm font-medium text-gray-800">
                    {{ log.status === 'success' ? '成功' : '失败' }}
                  </span>
                </div>
                <span class="text-xs text-gray-400 font-mono">{{ formatTime(log.completed_at || log.started_at) }}</span>
              </div>
              <div class="ml-4.5 text-xs text-gray-500 space-y-0.5">
                <div v-if="log.file_size" class="flex gap-3">
                  <span>大小: {{ formatSize(log.file_size) }}</span>
                  <span v-if="log.encrypted">加密</span>
                </div>
                <div v-if="log.cos_key" class="text-gray-400 truncate">{{ log.cos_key }}</div>
                <div v-if="log.error_message" class="text-red-500">{{ log.error_message }}</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-12 text-gray-400 text-sm">
          暂无备份记录
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import { showToast } from 'vant'

const loading = ref(true)
const triggering = ref(false)
const status = ref({ healthy: true, reason: 'no_logs', last_backup: {}, last_success_at: null })
const logs = ref([])

function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function loadData() {
  try {
    const [statusRes, logsRes] = await Promise.all([
      api.get('/api/backup/status'),
      api.get('/api/backup/logs'),
    ])
    status.value = statusRes.data
    logs.value = logsRes.data
  } catch (e) {
    showToast('Failed to load backup logs')
  } finally {
    loading.value = false
  }
}

async function triggerBackup() {
  triggering.value = true
  try {
    await api.post('/api/backup/trigger')
    showToast('备份已触发，请稍后刷新查看结果')
    // Reload after a short delay
    setTimeout(() => loadData(), 5000)
  } catch (e) {
    showToast('触发失败')
  } finally {
    triggering.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

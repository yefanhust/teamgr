<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
        <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
        <h1 class="text-lg font-bold text-gray-800">LLM 调用统计</h1>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 py-4">
      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <van-loading size="36px">加载中...</van-loading>
      </div>

      <template v-else>
        <!-- Summary Cards -->
        <div v-if="summary.length > 0" class="mb-6">
          <h2 class="text-sm font-semibold text-gray-500 mb-3">模型汇总</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div v-for="s in summary" :key="s.model_name" class="bg-white rounded-xl shadow-sm p-4">
              <div class="text-sm font-bold text-gray-800 mb-2 truncate">{{ s.model_name }}</div>
              <div class="grid grid-cols-2 gap-y-2 text-xs">
                <div>
                  <span class="text-gray-400">调用次数</span>
                  <div class="text-base font-semibold text-blue-600">{{ s.call_count }}</div>
                </div>
                <div>
                  <span class="text-gray-400">平均耗时</span>
                  <div class="text-base font-semibold text-orange-500">{{ formatDuration(s.avg_duration_ms) }}</div>
                </div>
                <div>
                  <span class="text-gray-400">平均 ISL</span>
                  <div class="font-semibold text-gray-700">{{ s.avg_input_tokens }}</div>
                </div>
                <div>
                  <span class="text-gray-400">平均 OSL</span>
                  <div class="font-semibold text-gray-700">{{ s.avg_output_tokens }}</div>
                </div>
                <div>
                  <span class="text-gray-400">总输入 Token</span>
                  <div class="font-semibold text-gray-700">{{ s.total_input_tokens.toLocaleString() }}</div>
                </div>
                <div>
                  <span class="text-gray-400">总输出 Token</span>
                  <div class="font-semibold text-gray-700">{{ s.total_output_tokens.toLocaleString() }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Logs Detail -->
        <h2 class="text-sm font-semibold text-gray-500 mb-3">调用明细</h2>

        <div v-if="logs.length === 0" class="text-center py-16 text-gray-400">
          <div class="text-4xl mb-3">📊</div>
          <p>暂无调用记录</p>
        </div>

        <div v-else class="space-y-2">
          <div v-for="log in logs" :key="log.id" class="bg-white rounded-xl shadow-sm p-3">
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs text-gray-400">{{ formatTime(log.timestamp) }}</span>
              <van-tag :type="callTypeStyle(log.call_type)" size="small">{{ callTypeLabel(log.call_type) }}</van-tag>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium text-gray-700 truncate">{{ log.model_name }}</span>
              <span class="text-sm font-semibold text-orange-500 flex-shrink-0 ml-2">{{ formatDuration(log.duration_ms) }}</span>
            </div>
            <div class="flex gap-4 mt-1 text-xs text-gray-500">
              <span>ISL: <b class="text-gray-700">{{ log.input_tokens }}</b></span>
              <span>OSL: <b class="text-gray-700">{{ log.output_tokens }}</b></span>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="total > pageSize" class="flex justify-center pt-4 pb-2">
            <van-pagination
              v-model="currentPage"
              :total-items="total"
              :items-per-page="pageSize"
              :show-page-size="3"
              force-ellipses
              @change="fetchLogs"
            />
          </div>
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
const summary = ref([])
const logs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20

onMounted(async () => {
  await Promise.all([fetchSummary(), fetchLogs()])
  loading.value = false
})

async function fetchSummary() {
  try {
    const res = await api.get('/api/stats/llm-summary')
    summary.value = res.data
  } catch (e) {
    showToast('加载汇总失败')
  }
}

async function fetchLogs() {
  try {
    const res = await api.get('/api/stats/llm-logs', {
      params: { page: currentPage.value, page_size: pageSize },
    })
    logs.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    showToast('加载明细失败')
  }
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function callTypeLabel(type) {
  const map = { 'text-entry': '文本录入', 'pdf-parse': 'PDF解析', 'semantic-search': '语义搜索' }
  return map[type] || type
}

function callTypeStyle(type) {
  const map = { 'text-entry': 'primary', 'pdf-parse': 'success', 'semantic-search': 'warning' }
  return map[type] || 'default'
}
</script>

<template>
  <div class="bg-white rounded-xl shadow-sm p-4">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-700">💬 人才查询</h3>
      <div class="flex items-center gap-2">
        <div
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs cursor-pointer hover:bg-blue-100 transition"
          @click="showModelPicker = true"
        >
          <span>{{ currentModel || '模型' }}</span>
          <van-icon name="arrow-down" size="10" />
        </div>
        <van-icon
          :name="collapsed ? 'arrow-down' : 'arrow-up'"
          size="16"
          class="cursor-pointer text-gray-400"
          @click="collapsed = !collapsed"
        />
      </div>
    </div>

    <!-- Collapsible body -->
    <div v-show="!collapsed">
      <!-- Messages -->
      <div class="overflow-auto space-y-3 mb-3 chat-messages" ref="chatContainer">
        <div v-if="messages.length === 0" class="text-center text-gray-400 py-4">
          <p class="text-xs">输入关于人才库的问题，例如：谁擅长前端开发？团队中有多少人有硕士学历？</p>
        </div>

        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'"
        >
          <div
            :class="[
              'max-w-[85%] rounded-xl px-3 py-2 text-sm',
              msg.role === 'user'
                ? 'bg-blue-500 text-white'
                : msg.type === 'processing'
                  ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                  : msg.type === 'step'
                    ? 'bg-purple-50 text-purple-700 border border-purple-200'
                    : msg.type === 'failed'
                      ? 'bg-red-50 text-red-600'
                      : msg.type === 'debug'
                        ? 'bg-amber-50 text-amber-800 border border-amber-200'
                        : 'bg-gray-100 text-gray-700'
            ]"
          >
            <div v-if="msg.type === 'processing'" class="flex items-center gap-2">
              <van-loading size="14px" />
              <span>{{ msg.content }}</span>
            </div>
            <div v-else-if="msg.type === 'debug'">
              <div
                class="flex items-center gap-1 cursor-pointer select-none"
                @click="msg.expanded = !msg.expanded"
              >
                <van-icon :name="msg.expanded ? 'arrow-down' : 'arrow'" size="12" />
                <span class="text-xs font-medium">{{ msg.title }}</span>
              </div>
              <pre v-show="msg.expanded" class="mt-1 text-xs whitespace-pre-wrap break-all max-h-48 overflow-auto">{{ msg.content }}</pre>
            </div>
            <p v-else class="whitespace-pre-line">{{ msg.content }}</p>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="flex gap-2 items-end">
        <van-field
          v-model="inputText"
          type="textarea"
          :autosize="{ minHeight: 40, maxHeight: 120 }"
          placeholder="问一个关于人才的问题..."
          class="flex-1 chat-input"
          @keypress.enter.exact.prevent="submitQuery"
        />
        <van-button
          type="primary"
          icon="guide-o"
          size="small"
          :disabled="!inputText.trim() || loading"
          :loading="loading"
          @click="submitQuery"
          class="query-btn"
        >
          提问
        </van-button>
      </div>
    </div>

    <!-- Model Picker -->
    <van-action-sheet
      v-model:show="showModelPicker"
      :actions="modelActions"
      cancel-text="取消"
      close-on-click-action
      @select="onModelSelect"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { showToast } from 'vant'
import api from '../api'

const collapsed = ref(false)
const inputText = ref('')
const messages = ref([])
const loading = ref(false)
const chatContainer = ref(null)
const showModelPicker = ref(false)
const currentModel = ref('')
const availableModels = ref([])

const modelActions = computed(() => {
  return availableModels.value.map(m => ({
    name: m,
    color: m === currentModel.value ? '#1989fa' : undefined,
    className: m === currentModel.value ? 'font-bold' : '',
  }))
})

onMounted(() => {
  fetchModelSettings()
})

async function fetchModelSettings() {
  try {
    const res = await api.get('/api/settings/model')
    currentModel.value = res.data.current_model
    availableModels.value = res.data.available_models
  } catch (e) {
    // ignore
  }
}

async function onModelSelect(action) {
  const model = action.name
  if (model === currentModel.value) return
  try {
    await api.put('/api/settings/model', { model })
    currentModel.value = model
    showToast(`已切换到 ${model}`)
  } catch (e) {
    showToast('切换失败')
  }
}

async function submitQuery() {
  if (!inputText.value.trim() || loading.value) return

  const query = inputText.value.trim()
  inputText.value = ''
  loading.value = true

  // User message
  messages.value.push({ role: 'user', content: query })

  // Step 1: Analyzing
  const analyzeIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    type: 'processing',
    content: '正在分析问题，识别相关维度...',
  })
  await nextTick()
  scrollToBottom()

  try {
    const analyzeRes = await api.post('/api/chat/analyze', { query })
    const { relevant_dimensions, reasoning } = analyzeRes.data

    // Show analysis result
    const dimLabels = relevant_dimensions.map(d => d.label).join('、')
    messages.value[analyzeIdx] = {
      role: 'assistant',
      type: 'step',
      content: `📋 ${reasoning}\n📌 相关维度：${dimLabels || '无'}`,
    }
    await nextTick()
    scrollToBottom()

    if (!relevant_dimensions || relevant_dimensions.length === 0) {
      messages.value.push({
        role: 'assistant',
        content: '未找到相关维度，无法回答该问题。请尝试换一种方式提问。',
      })
      loading.value = false
      return
    }

    // Step 2: Answering (with name privacy protection)
    const answerIdx = messages.value.length
    messages.value.push({
      role: 'assistant',
      type: 'processing',
      content: `正在从${relevant_dimensions.length}个维度提取人才数据并生成回答...`,
    })
    await nextTick()
    scrollToBottom()

    const dimension_keys = relevant_dimensions.map(d => d.key)
    const answerRes = await api.post('/api/chat/answer', { query, dimension_keys })
    const { raw_answer, final_answer, name_mapping } = answerRes.data

    // Replace processing message with name mapping debug info
    const mappingEntries = Object.entries(name_mapping || {})
    const mappingText = mappingEntries.map(([real, pseudo]) => `${real} → ${pseudo}`).join('\n')
    messages.value[answerIdx] = {
      role: 'assistant',
      type: 'debug',
      title: `🔒 姓名隐私保护：已将 ${mappingEntries.length} 个姓名替换为化名`,
      content: mappingText || '（无姓名需要替换）',
      expanded: false,
    }

    // Show raw LLM answer (with pseudonyms) for debugging
    messages.value.push({
      role: 'assistant',
      type: 'debug',
      title: '🤖 模型原始回答（含化名）',
      content: raw_answer,
      expanded: false,
    })

    // Show final answer with real names restored
    messages.value.push({
      role: 'assistant',
      content: final_answer,
    })
  } catch (e) {
    // Replace last processing message with error
    const lastIdx = messages.value.length - 1
    if (messages.value[lastIdx]?.type === 'processing') {
      messages.value[lastIdx] = {
        role: 'assistant',
        type: 'failed',
        content: '查询失败: ' + (e.response?.data?.detail || '未知错误'),
      }
    } else {
      messages.value.push({
        role: 'assistant',
        type: 'failed',
        content: '查询失败: ' + (e.response?.data?.detail || '未知错误'),
      })
    }
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-messages {
  max-height: 400px;
}
.chat-input {
  border: 1px solid #d1d5db !important;
  border-radius: 10px !important;
  padding: 8px 12px !important;
  overflow: hidden;
}
.chat-input::after {
  display: none !important;
}
.chat-input:focus-within {
  border-color: #3b82f6 !important;
}
.chat-input :deep(.van-field__control) {
  font-size: 14px !important;
  line-height: 1.5 !important;
}
.query-btn {
  height: auto !important;
  min-height: 36px;
  padding: 8px 14px;
}
</style>

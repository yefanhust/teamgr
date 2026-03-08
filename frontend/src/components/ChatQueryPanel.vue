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
        <div v-if="messages.length === 0" class="text-center text-gray-400 py-3">
          <p class="text-xs">点击下方预设问题或自行输入</p>
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

      <!-- Preset questions (dynamic) -->
      <div class="flex flex-wrap gap-1.5 mb-2 items-center">
        <template v-for="preset in presetQuestions" :key="preset.id">
          <!-- Editing mode -->
          <input
            v-if="editingPresetId === preset.id"
            v-model="editingPresetText"
            class="preset-edit-input"
            ref="presetEditInput"
            @blur="finishEditPreset(preset)"
            @keypress.enter="finishEditPreset(preset)"
            @keydown.escape="cancelEditPreset"
          />
          <!-- Normal mode -->
          <span
            v-else
            class="preset-chip group relative px-2 py-1 text-xs rounded-full cursor-pointer transition select-none"
            :class="preset.is_scheduled ? 'bg-blue-50 text-blue-600 border border-blue-200' : 'bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-600'"
            @click="handlePresetClick(preset)"
            @dblclick.stop="handlePresetDblClick(preset)"
          >
            {{ preset.question }}
            <!-- Hover actions -->
            <span
              class="preset-actions absolute -top-3 -right-1 hidden group-hover:flex items-center gap-0.5 bg-white shadow-md rounded-full px-1 py-0.5"
              @click.stop
            >
              <van-icon
                name="clock-o"
                size="14"
                :color="preset.is_scheduled ? '#1989fa' : '#999'"
                class="cursor-pointer"
                @click="toggleSchedule(preset)"
              />
              <van-icon
                name="cross"
                size="14"
                color="#ee0a24"
                class="cursor-pointer"
                @click="deletePreset(preset)"
              />
            </span>
          </span>
        </template>
        <!-- Add button -->
        <span
          class="px-2 py-1 text-xs rounded-full bg-gray-50 text-gray-400 cursor-pointer hover:bg-green-50 hover:text-green-600 transition select-none border border-dashed border-gray-300"
          @click="addPreset"
        >+</span>
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
        <VoiceInputButton v-model="inputText" />
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
import VoiceInputButton from './VoiceInputButton.vue'

const presetQuestions = ref([])
const editingPresetId = ref(null)
const editingPresetText = ref('')
const presetEditInput = ref(null)
let presetClickTimer = null

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
    name: m.name,
    subname: m.location === 'local' ? '本地' : '网络',
    color: m.name === currentModel.value ? '#1989fa' : undefined,
    className: m.name === currentModel.value ? 'font-bold' : '',
  }))
})

onMounted(() => {
  fetchModelSettings()
  fetchPresets()
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

function handlePresetClick(preset) {
  clearTimeout(presetClickTimer)
  presetClickTimer = setTimeout(() => {
    inputText.value = preset.question
  }, 300)
}

function handlePresetDblClick(preset) {
  clearTimeout(presetClickTimer)
  startEditPreset(preset)
}

async function fetchPresets() {
  try {
    const res = await api.get('/api/chat/presets')
    presetQuestions.value = res.data
  } catch (e) {
    // ignore
  }
}

async function addPreset() {
  try {
    const res = await api.post('/api/chat/presets', { question: '新问题' })
    presetQuestions.value.push(res.data)
    startEditPreset(res.data)
  } catch (e) {
    showToast('添加失败')
  }
}

async function startEditPreset(preset) {
  editingPresetId.value = preset.id
  editingPresetText.value = preset.question
  await nextTick()
  const inputs = presetEditInput.value
  if (inputs) {
    const el = Array.isArray(inputs) ? inputs[0] : inputs
    el?.focus()
    el?.select()
  }
}

async function finishEditPreset(preset) {
  const newText = editingPresetText.value.trim()
  editingPresetId.value = null
  if (!newText || newText === preset.question) return
  try {
    const res = await api.put(`/api/chat/presets/${preset.id}`, { question: newText })
    const idx = presetQuestions.value.findIndex(p => p.id === preset.id)
    if (idx !== -1) presetQuestions.value[idx] = res.data
  } catch (e) {
    showToast('更新失败')
  }
}

function cancelEditPreset() {
  editingPresetId.value = null
}

async function deletePreset(preset) {
  try {
    await api.delete(`/api/chat/presets/${preset.id}`)
    presetQuestions.value = presetQuestions.value.filter(p => p.id !== preset.id)
  } catch (e) {
    showToast('删除失败')
  }
}

async function toggleSchedule(preset) {
  try {
    const res = await api.put(`/api/chat/presets/${preset.id}`, {
      is_scheduled: !preset.is_scheduled,
    })
    const idx = presetQuestions.value.findIndex(p => p.id === preset.id)
    if (idx !== -1) presetQuestions.value[idx] = res.data
    showToast(res.data.is_scheduled ? '已启用每日定时查询' : '已关闭定时查询')
  } catch (e) {
    showToast('操作失败')
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
.preset-chip {
  position: relative;
}
.preset-actions {
  z-index: 5;
}
.preset-edit-input {
  border: 1.5px solid #3b82f6;
  border-radius: 12px;
  padding: 2px 8px;
  font-size: 12px;
  width: 180px;
  outline: none;
  background: #fff;
}
</style>

<template>
  <div class="min-h-screen bg-gray-100 flex flex-col">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
        <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
        <h1 class="text-lg font-bold text-gray-800">信息录入</h1>
        <div class="w-5"></div>
      </div>
    </div>

    <div class="max-w-3xl mx-auto w-full flex-1 flex flex-col px-4 py-4">
      <!-- Candidate Selector -->
      <div class="bg-white rounded-xl shadow-sm p-4 mb-4">
        <label class="text-sm font-medium text-gray-600 mb-2 block">选择候选人</label>
        <div class="flex gap-2">
          <div class="flex-1 relative">
            <van-field
              v-model="candidateSearch"
              placeholder="输入姓名/拼音搜索..."
              clearable
              @update:model-value="searchCandidates"
              @focus="onSearchFocus"
            />
            <!-- Dropdown -->
            <div
              v-if="showDropdown && filteredCandidates.length > 0"
              class="absolute top-full left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-lg z-20 max-h-48 overflow-auto"
            >
              <div
                v-for="c in filteredCandidates"
                :key="c.id"
                class="px-3 py-2 hover:bg-blue-50 cursor-pointer text-sm flex items-center justify-between"
                @mousedown.prevent="selectCandidate(c)"
              >
                <span>{{ c.name }}</span>
                <span class="text-xs text-gray-400">{{ c.current_role || c.department || '' }}</span>
              </div>
            </div>
          </div>
          <van-button size="small" type="primary" plain @click="showNewTalent = true">
            + 新建
          </van-button>
        </div>

        <div v-if="selectedTalent" class="mt-2 flex items-center gap-2">
          <van-tag type="primary" size="medium" closeable @close="clearSelection">
            {{ selectedTalent.name }}
          </van-tag>
          <span class="text-xs text-gray-400">
            {{ selectedTalent.current_role || '' }}
          </span>
        </div>
      </div>

      <!-- Chat Dialog Area -->
      <div class="flex-1 bg-white rounded-xl shadow-sm p-4 mb-4 flex flex-col min-h-[300px]">
        <div class="flex-1 overflow-auto space-y-3 mb-4" ref="chatContainer">
          <div v-if="messages.length === 0" class="text-center text-gray-400 py-4">
            <p class="text-sm">选择一个候选人后，输入关于TA的信息</p>
            <p class="text-xs mt-1">例如：技术能力强，擅长前端开发，沟通能力好...</p>
          </div>

          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'"
          >
            <div
              :class="[
                'max-w-[80%] rounded-xl px-3 py-2 text-sm',
                msg.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : msg.status === 'processing'
                    ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                    : msg.status === 'failed'
                      ? 'bg-red-50 text-red-600'
                      : 'bg-gray-100 text-gray-700'
              ]"
            >
              <div v-if="msg.status === 'processing'" class="flex items-center gap-2">
                <van-loading size="14px" />
                <span>{{ msg.content }}</span>
              </div>
              <p v-else class="whitespace-pre-line">{{ msg.content }}</p>
            </div>
          </div>
        </div>

        <!-- Model Selector + Input Area -->
        <div class="flex items-center gap-2 mb-1">
          <span class="text-xs text-gray-400">模型:</span>
          <div
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs cursor-pointer hover:bg-blue-100 transition"
            @click="showModelPicker = true"
          >
            <span>{{ currentModel || '选择模型' }}</span>
            <van-icon name="arrow-down" size="10" />
          </div>
        </div>

        <div class="flex gap-2 items-end">
          <van-field
            v-model="inputText"
            type="textarea"
            :autosize="{ minHeight: 100 }"
            placeholder="输入候选人的信息..."
            class="flex-1 entry-input"
            @keypress.enter.exact.prevent="submitEntry"
          />
          <van-button
            type="primary"
            icon="guide-o"
            :disabled="!canSubmit"
            @click="submitEntry"
            class="send-btn"
          >
            发送
          </van-button>
        </div>
      </div>

      <!-- PDF Upload -->
      <div class="bg-white rounded-xl shadow-sm p-4 mb-4">
        <label class="text-sm font-medium text-gray-600 mb-2 block">上传简历PDF</label>
        <van-uploader
          :after-read="handlePdfUpload"
          accept="application/pdf"
          :max-count="1"
          :disabled="!selectedTalent || uploading"
        >
          <van-button
            icon="description"
            type="primary"
            plain
            size="small"
            :loading="uploading"
            :disabled="!selectedTalent"
          >
            {{ selectedTalent ? '选择PDF文件' : '请先选择候选人' }}
          </van-button>
        </van-uploader>
      </div>
    </div>

    <!-- Model Picker -->
    <van-action-sheet
      v-model:show="showModelPicker"
      :actions="modelActions"
      cancel-text="取消"
      @select="onModelSelect"
    />

    <!-- Create New Talent Dialog -->
    <van-dialog
      v-model:show="showNewTalent"
      title="新建人才"
      show-cancel-button
      @confirm="createAndSelect"
    >
      <div class="px-4 py-2">
        <van-field v-model="newTalentName" label="姓名" placeholder="必填" required />
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useTalentStore } from '../stores/talent'
import { showToast } from 'vant'
import api from '../api'

const route = useRoute()
const store = useTalentStore()

const candidateSearch = ref('')
const showDropdown = ref(false)
const filteredCandidates = ref([])
const selectedTalent = ref(null)
const inputText = ref('')
const messages = ref([])
const uploading = ref(false)
const chatContainer = ref(null)
const showNewTalent = ref(false)
const newTalentName = ref('')
const showModelPicker = ref(false)
const currentModel = ref('')
const availableModels = ref([])

// Track pending entry IDs for polling
const pendingEntries = ref(new Map()) // entryId -> msgIndex
let pollTimer = null

const canSubmit = computed(() => {
  return selectedTalent.value && inputText.value.trim()
})

const modelActions = computed(() => {
  return availableModels.value.map(m => ({
    name: m,
    color: m === currentModel.value ? '#1989fa' : undefined,
    className: m === currentModel.value ? 'font-bold' : '',
  }))
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

onMounted(async () => {
  fetchModelSettings()
  await store.fetchTalents({ page_size: 200 })

  const tid = route.query.talent_id
  if (tid) {
    try {
      selectedTalent.value = await store.getTalent(tid)
      candidateSearch.value = selectedTalent.value.name
    } catch (e) {
      // ignore
    }
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

if (typeof document !== 'undefined') {
  document.addEventListener('click', () => {
    showDropdown.value = false
  })
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollPendingEntries, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollPendingEntries() {
  if (pendingEntries.value.size === 0) {
    stopPolling()
    return
  }

  for (const [entryId, msgIndex] of pendingEntries.value.entries()) {
    try {
      const res = await api.get(`/api/entry/status/${entryId}`)
      const status = res.data.status

      if (status === 'done') {
        messages.value[msgIndex] = {
          role: 'assistant',
          status: 'done',
          content: '信息已整理到人才卡',
        }
        pendingEntries.value.delete(entryId)
      } else if (status === 'failed') {
        messages.value[msgIndex] = {
          role: 'assistant',
          status: 'failed',
          content: '整理失败，请重新输入',
        }
        pendingEntries.value.delete(entryId)
      }
    } catch (e) {
      // ignore poll errors
    }
  }

  if (pendingEntries.value.size === 0) {
    stopPolling()
  }

  await nextTick()
  scrollToBottom()
}

async function onSearchFocus() {
  // Show all candidates on focus if input is empty
  if (!candidateSearch.value.trim()) {
    filteredCandidates.value = store.talents.slice(0, 20)
  }
  showDropdown.value = true
}

async function searchCandidates(val) {
  if (!val || !val.trim()) {
    filteredCandidates.value = store.talents.slice(0, 20)
    showDropdown.value = true
    return
  }
  try {
    filteredCandidates.value = await store.searchTalents(val)
    showDropdown.value = true
  } catch (e) {
    filteredCandidates.value = []
  }
}

function selectCandidate(c) {
  selectedTalent.value = c
  candidateSearch.value = c.name
  showDropdown.value = false
}

function clearSelection() {
  selectedTalent.value = null
  candidateSearch.value = ''
  messages.value = []
  pendingEntries.value.clear()
  stopPolling()
}

async function submitEntry() {
  if (!canSubmit.value) return

  const content = inputText.value.trim()
  inputText.value = ''

  // Add user message
  messages.value.push({ role: 'user', content })

  // Add processing placeholder
  const processingIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    status: 'processing',
    content: '后台整理中...',
  })

  await nextTick()
  scrollToBottom()

  try {
    const result = await store.submitTextEntry(selectedTalent.value.id, content)
    // Track this entry for polling
    pendingEntries.value.set(result.entry_id, processingIdx)
    startPolling()
  } catch (e) {
    messages.value[processingIdx] = {
      role: 'assistant',
      status: 'failed',
      content: '提交失败: ' + (e.response?.data?.detail || '未知错误'),
    }
  }
}

async function handlePdfUpload(file) {
  if (!selectedTalent.value) return

  uploading.value = true
  messages.value.push({ role: 'user', content: `[上传简历] ${file.file.name}` })

  const processingIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    status: 'processing',
    content: '简历解析中...',
  })

  await nextTick()
  scrollToBottom()

  try {
    const result = await store.uploadPdf(selectedTalent.value.id, file.file)
    pendingEntries.value.set(result.entry_id, processingIdx)
    startPolling()
  } catch (e) {
    messages.value[processingIdx] = {
      role: 'assistant',
      status: 'failed',
      content: 'PDF上传失败: ' + (e.response?.data?.detail || '未知错误'),
    }
  } finally {
    uploading.value = false
  }
}

async function createAndSelect() {
  if (!newTalentName.value.trim()) {
    showToast('请输入姓名')
    return
  }
  try {
    const created = await store.createTalent({ name: newTalentName.value.trim() })
    selectedTalent.value = created
    candidateSearch.value = created.name
    newTalentName.value = ''
    showToast('已创建')
    await store.fetchTalents({ page_size: 200 })
  } catch (e) {
    showToast('创建失败')
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}
</script>

<style scoped>
/* entry-input IS the .van-cell root — target it directly, not as descendant */
.entry-input {
  border: 1px solid #6b7280 !important;
  border-radius: 10px !important;
  padding: 10px 12px !important;
  overflow: hidden;
}
.entry-input::after {
  display: none !important;
}
.entry-input:focus-within {
  border-color: #3b82f6 !important;
}
.entry-input :deep(.van-field__control) {
  font-size: 15px !important;
  line-height: 1.6 !important;
  min-height: 100px !important;
}
.send-btn {
  height: auto !important;
  min-height: 50px;
  padding: 10px 18px;
  font-size: 15px;
}
</style>

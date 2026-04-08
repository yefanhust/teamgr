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
      <!-- Draft restored banner -->
      <div
        v-if="draftRestored"
        class="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 mb-4 flex items-center justify-between"
      >
        <div class="flex items-center gap-2 text-sm text-amber-700">
          <van-icon name="edit" size="16" />
          <span>已恢复未提交的草稿<template v-if="draftTimeLabel">（保存于 {{ draftTimeLabel }}）</template></span>
        </div>
        <van-icon name="cross" size="16" class="text-amber-400 cursor-pointer" @click="dismissDraftBanner" />
      </div>

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
      <div
        class="flex-1 bg-white rounded-xl shadow-sm p-4 mb-4 flex flex-col min-h-[300px] relative"
        @dragover.prevent="onDragOver"
        @dragenter.prevent="onDragEnter"
        @dragleave.prevent="onDragLeave"
        @drop.prevent="handleDrop"
      >
        <!-- Drop overlay -->
        <div
          v-if="isDragging"
          class="absolute inset-0 z-30 rounded-xl bg-blue-500/10 border-2 border-dashed border-blue-400 flex items-center justify-center pointer-events-none"
        >
          <span class="text-blue-500 text-sm font-medium">松开以上传图片</span>
        </div>
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
                  : msg.status === 'uploaded'
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : msg.status === 'processing'
                      ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                      : msg.status === 'failed'
                        ? 'bg-red-50 text-red-600'
                        : 'bg-gray-100 text-gray-700'
              ]"
            >
              <div v-if="msg.images && msg.images.length" class="flex flex-wrap gap-1.5 mb-1">
                <img
                  v-for="(src, imgIdx) in msg.images"
                  :key="imgIdx"
                  :src="src"
                  class="w-20 h-20 object-cover rounded-lg cursor-pointer"
                  @click="previewImage(src)"
                />
              </div>
              <div v-if="msg.status === 'uploaded'" class="flex items-center gap-2">
                <van-icon name="passed" size="14" color="#16a34a" />
                <span>{{ msg.content }}</span>
              </div>
              <div v-else-if="msg.status === 'processing'" class="flex items-center gap-2">
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
          <div class="flex-1" ref="inputWrapper">
            <van-field
              v-model="inputText"
              type="textarea"
              :autosize="{ minHeight: 100 }"
              placeholder="输入候选人的信息...（⌘/Ctrl+Enter发送）"
              class="entry-input"
              @paste="handlePaste"
            />
          </div>
          <div class="flex flex-col gap-1 items-center">
            <VoiceInputButton v-model="inputText" />
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
      </div>

      <!-- File Upload -->
      <div class="bg-white rounded-xl shadow-sm p-4 mb-4">
        <div class="flex items-center justify-between mb-2">
          <label class="text-sm font-medium text-gray-600">上传文件</label>
          <van-icon
            name="setting-o"
            size="16"
            class="text-gray-400 cursor-pointer hover:text-blue-500"
            @click="openParsePromptEditor"
          />
        </div>
        <div class="flex gap-3">
          <van-uploader
            :after-read="handlePdfUpload"
            accept="application/pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
              简历（PDF/Word）
            </van-button>
          </van-uploader>
          <van-uploader
            :after-read="handleImageUpload"
            accept="image/*"
            :max-count="10"
            multiple
            :disabled="!selectedTalent || uploadingImage"
          >
            <van-button
              icon="photo-o"
              type="primary"
              plain
              size="small"
              :loading="uploadingImage"
              :disabled="!selectedTalent"
            >
              图片（名片等）
            </van-button>
          </van-uploader>
        </div>
        <p v-if="!selectedTalent" class="text-xs text-gray-400 mt-1">请先选择候选人</p>
        <p v-else class="text-xs text-gray-400 mt-1">支持 PDF、Word(.docx) 格式简历和图片</p>
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

    <!-- Create New Talent Dialog -->
    <van-dialog
      v-model:show="showNewTalent"
      title="新建人才"
      show-cancel-button
      @confirm="createAndSelect"
    >
      <form class="px-4 py-2" @submit.prevent="createAndSelect">
        <div class="van-cell van-field">
          <div class="van-cell__title van-field__label">
            <label><span class="text-red-500 mr-1">*</span>姓名</label>
          </div>
          <div class="van-cell__value van-field__value">
            <div class="van-field__body">
              <input v-model="newTalentName" type="text" placeholder="必填" class="van-field__control" />
            </div>
          </div>
        </div>
        <button type="submit" style="display:none" />
      </form>
    </van-dialog>

    <!-- Parse Prompt Editor -->
    <van-popup
      v-model:show="showPromptEditor"
      position="bottom"
      :style="{ height: '80vh' }"
      round
      closeable
    >
      <div class="flex flex-col h-full p-4">
        <h3 class="text-base font-bold text-gray-700 mb-2">编辑解析提示词</h3>
        <van-tabs v-model:active="promptTab" shrink>
          <van-tab title="PDF简历解析" name="pdf-parse" />
          <van-tab title="图片解析" name="image-parse" />
        </van-tabs>
        <textarea
          v-model="promptEditorText"
          class="flex-1 w-full border border-gray-300 rounded-lg p-3 mt-2 text-sm resize-none focus:outline-none focus:border-blue-400"
          placeholder="输入提示词..."
        />
        <div class="flex gap-2 mt-3">
          <van-button size="small" plain @click="resetParsePrompt">恢复默认</van-button>
          <van-button size="small" type="primary" class="flex-1" @click="saveParsePrompt">保存</van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useTalentStore } from '../stores/talent'
import { showToast, showImagePreview } from 'vant'
import api from '../api'
import VoiceInputButton from '../components/VoiceInputButton.vue'

const route = useRoute()
const store = useTalentStore()

const candidateSearch = ref('')
const showDropdown = ref(false)
const filteredCandidates = ref([])
const selectedTalent = ref(null)
const inputText = ref('')
const messages = ref([])
const uploading = ref(false)
const uploadingImage = ref(false)
const chatContainer = ref(null)
const inputWrapper = ref(null)
const showNewTalent = ref(false)
const newTalentName = ref('')
const showModelPicker = ref(false)
const currentModel = ref('')
const availableModels = ref([])

// Drag-and-drop state
const isDragging = ref(false)
let dragCounter = 0

// Track pending entry IDs for polling
const pendingEntries = ref(new Map()) // entryId -> msgIndex
let pollTimer = null

// Prompt editor state
const showPromptEditor = ref(false)
const promptTab = ref('pdf-parse')
const promptEditorText = ref('')
const promptCache = ref({}) // { 'pdf-parse': { instructions, default }, 'image-parse': ... }

// --- Draft auto-save ---
const DRAFT_KEY = 'teamgr_entry_draft'
let draftTimer = null
const draftRestored = ref(false)
const draftSavedAt = ref(null)

function saveDraft() {
  if (draftTimer) clearTimeout(draftTimer)
  draftTimer = setTimeout(() => {
    const text = inputText.value
    if (text.trim()) {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        talentId: selectedTalent.value?.id || null,
        talentName: selectedTalent.value?.name || '',
        text,
        savedAt: Date.now(),
      }))
    } else {
      localStorage.removeItem(DRAFT_KEY)
    }
  }, 500)
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return
    const draft = JSON.parse(raw)
    if (!draft.text?.trim()) return

    // Restore draft text
    inputText.value = draft.text

    // Try to restore talent selection if not already set
    if (draft.talentId && !selectedTalent.value) {
      const talent = store.talents.find(t => t.id === draft.talentId)
      if (talent) {
        selectedTalent.value = talent
        candidateSearch.value = talent.name
      }
    }

    draftRestored.value = true
    draftSavedAt.value = draft.savedAt ? new Date(draft.savedAt) : null
    showToast('已恢复上次未提交的草稿')
  } catch (e) {
    // ignore
  }
}

function clearDraft() {
  if (draftTimer) clearTimeout(draftTimer)
  localStorage.removeItem(DRAFT_KEY)
  draftRestored.value = false
  draftSavedAt.value = null
}

const draftTimeLabel = computed(() => {
  if (!draftSavedAt.value) return ''
  const d = draftSavedAt.value
  const pad = n => String(n).padStart(2, '0')
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (isToday) return `今天 ${time}`
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${time}`
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${time}`
})

function dismissDraftBanner() {
  draftRestored.value = false
}

const canSubmit = computed(() => {
  return selectedTalent.value && inputText.value.trim()
})


const modelActions = computed(() => {
  return availableModels.value.map(m => ({
    name: m.name,
    subname: m.location === 'local' ? '本地' : '网络',
    color: m.name === currentModel.value ? '#1989fa' : undefined,
    className: m.name === currentModel.value ? 'font-bold' : '',
  }))
})

async function fetchModelSettings() {
  try {
    const [modelRes, defaultsRes] = await Promise.all([
      api.get('/api/settings/model'),
      api.get('/api/settings/model-defaults'),
    ])
    const textEntryModel = defaultsRes.data.defaults?.['text-entry']
    currentModel.value = textEntryModel || modelRes.data.current_model
    availableModels.value = modelRes.data.available_models
  } catch (e) {
    // ignore
  }
}

async function onModelSelect(action) {
  const model = action.name
  if (model === currentModel.value) return
  try {
    const defaultsRes = await api.get('/api/settings/model-defaults')
    const defaults = defaultsRes.data.defaults || {}
    defaults['text-entry'] = model
    await api.put('/api/settings/model-defaults', { defaults })
    currentModel.value = model
    showToast(`已切换到 ${model}`)
  } catch (e) {
    showToast('切换失败')
  }
}

// Prevent browser default: opening dropped files as a new page
function preventDragDefault(e) { e.preventDefault() }

// Auto-save draft on input change
watch(inputText, saveDraft)

onMounted(async () => {
  document.addEventListener('dragover', preventDragDefault)
  document.addEventListener('drop', preventDragDefault)
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

  // Restore draft if available (after talents are loaded)
  loadDraft()

  // Attach keydown listener directly on the native <textarea> DOM element
  // This bypasses all Vue/Vant component layers
  await nextTick()
  const textarea = inputWrapper.value?.querySelector('textarea')
  if (textarea) {
    textarea.addEventListener('keydown', handleTextareaKeydown)
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (draftTimer) clearTimeout(draftTimer)
  document.removeEventListener('dragover', preventDragDefault)
  document.removeEventListener('drop', preventDragDefault)
  const textarea = inputWrapper.value?.querySelector('textarea')
  if (textarea) {
    textarea.removeEventListener('keydown', handleTextareaKeydown)
  }
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
      } else if (status === 'processing') {
        // Transition from uploaded → processing: update message
        if (messages.value[msgIndex]?.status === 'uploaded') {
          messages.value[msgIndex] = {
            role: 'assistant',
            status: 'processing',
            content: '后台解析中...',
          }
        }
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
  clearDraft()
}

// Attached directly to native <textarea> element via addEventListener in onMounted
function handleTextareaKeydown(event) {
  if (event.key !== 'Enter') return

  if (event.ctrlKey || event.metaKey) {
    // Cmd+Enter (macOS) or Ctrl+Enter: submit
    event.preventDefault()
    event.stopPropagation()
    submitEntry()
    return
  }
  // All other Enter combinations (plain, Shift, Alt): default newline behavior
}

async function submitEntry() {
  if (!canSubmit.value) return

  const content = inputText.value.trim()
  inputText.value = ''
  clearDraft()

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
    content: '正在上传...',
  })

  await nextTick()
  scrollToBottom()

  try {
    const result = await store.uploadPdf(selectedTalent.value.id, file.file)
    // Phase 1 complete: file saved on server
    messages.value[processingIdx] = {
      role: 'assistant',
      status: 'uploaded',
      content: '✓ 文档已上传成功，正在排队等待后台解析（可安全关闭页面）',
    }
    pendingEntries.value.set(result.entry_id, processingIdx)
    startPolling()
  } catch (e) {
    messages.value[processingIdx] = {
      role: 'assistant',
      status: 'failed',
      content: '文档上传失败: ' + (e.response?.data?.detail || '未知错误'),
    }
  } finally {
    uploading.value = false
  }
}

function handlePaste(event) {
  if (!selectedTalent.value) return

  const items = event.clipboardData?.items
  if (!items) return

  const imageFiles = []
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const blob = item.getAsFile()
      if (blob) imageFiles.push(blob)
    }
  }

  if (imageFiles.length === 0) return

  // Prevent the default paste (don't insert binary data into textarea)
  event.preventDefault()

  // Trigger the same upload flow
  uploadingImage.value = true
  const imageUrls = imageFiles.map(f => URL.createObjectURL(f))
  messages.value.push({
    role: 'user',
    content: `粘贴了 ${imageFiles.length} 张图片`,
    images: imageUrls,
  })

  const processingIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    status: 'processing',
    content: '图片解析中...',
  })

  nextTick().then(() => scrollToBottom())

  store.uploadImage(selectedTalent.value.id, imageFiles)
    .then(result => {
      pendingEntries.value.set(result.entry_id, processingIdx)
      startPolling()
    })
    .catch(e => {
      messages.value[processingIdx] = {
        role: 'assistant',
        status: 'failed',
        content: '图片上传失败: ' + (e.response?.data?.detail || '未知错误'),
      }
    })
    .finally(() => {
      uploadingImage.value = false
    })
}

function onDragOver(event) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function onDragEnter() {
  dragCounter++
  isDragging.value = true
}

function onDragLeave() {
  dragCounter--
  if (dragCounter <= 0) {
    dragCounter = 0
    isDragging.value = false
  }
}

function isImageFile(file) {
  if (file.type && file.type.startsWith('image/')) return true
  // Some external apps don't set MIME type — check extension
  if (/\.(jpe?g|png|gif|webp|bmp|tiff?)$/i.test(file.name)) return true
  return false
}

function handleDrop(event) {
  dragCounter = 0
  isDragging.value = false

  if (!selectedTalent.value) {
    showToast('请先选择候选人')
    return
  }

  let imageFiles = []

  // Strategy 1: dataTransfer.files
  if (event.dataTransfer?.files?.length) {
    for (const f of event.dataTransfer.files) {
      if (isImageFile(f)) imageFiles.push(f)
    }
  }

  // Strategy 2: dataTransfer.items (some apps/browsers only populate items)
  if (imageFiles.length === 0 && event.dataTransfer?.items) {
    for (const item of event.dataTransfer.items) {
      if (item.kind === 'file') {
        const file = item.getAsFile()
        if (file && (isImageFile(file) || !file.type)) imageFiles.push(file)
      }
    }
  }

  if (imageFiles.length === 0) return

  uploadingImage.value = true
  const imageUrls = imageFiles.map(f => URL.createObjectURL(f))
  messages.value.push({
    role: 'user',
    content: `拖入了 ${imageFiles.length} 张图片`,
    images: imageUrls,
  })

  const processingIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    status: 'processing',
    content: '图片解析中...',
  })

  nextTick().then(() => scrollToBottom())

  store.uploadImage(selectedTalent.value.id, imageFiles)
    .then(result => {
      pendingEntries.value.set(result.entry_id, processingIdx)
      startPolling()
    })
    .catch(e => {
      messages.value[processingIdx] = {
        role: 'assistant',
        status: 'failed',
        content: '图片上传失败: ' + (e.response?.data?.detail || '未知错误'),
      }
    })
    .finally(() => {
      uploadingImage.value = false
    })
}

async function handleImageUpload(fileOrFiles) {
  if (!selectedTalent.value) return

  const fileList = Array.isArray(fileOrFiles) ? fileOrFiles : [fileOrFiles]

  uploadingImage.value = true
  const imageUrls = fileList.map(f => f.content)
  const names = fileList.map(f => f.file.name).join(', ')
  messages.value.push({
    role: 'user',
    content: names,
    images: imageUrls,
  })

  const processingIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    status: 'processing',
    content: '图片解析中...',
  })

  await nextTick()
  scrollToBottom()

  try {
    const result = await store.uploadImage(
      selectedTalent.value.id,
      fileList.map(f => f.file)
    )
    pendingEntries.value.set(result.entry_id, processingIdx)
    startPolling()
  } catch (e) {
    messages.value[processingIdx] = {
      role: 'assistant',
      status: 'failed',
      content: '图片上传失败: ' + (e.response?.data?.detail || '未知错误'),
    }
  } finally {
    uploadingImage.value = false
  }
}

async function createAndSelect() {
  if (!newTalentName.value.trim()) {
    showToast('请输入姓名')
    return
  }
  try {
    const created = await store.createTalent({ name: newTalentName.value.trim() })
    showNewTalent.value = false
    messages.value = []
    inputText.value = ''
    clearDraft()
    pendingEntries.value.clear()
    stopPolling()
    selectedTalent.value = created
    candidateSearch.value = created.name
    newTalentName.value = ''
    showToast('已创建')
    await store.fetchTalents({ page_size: 200 })
  } catch (e) {
    showToast(e.response?.data?.detail || '创建失败')
  }
}

function previewImage(src) {
  showImagePreview({ images: [src], closeable: true })
}

async function openParsePromptEditor() {
  showPromptEditor.value = true
  await loadPromptForTab(promptTab.value)
}

async function loadPromptForTab(type) {
  try {
    const res = await api.get(`/api/entry/prompts/${type}`)
    promptCache.value[type] = res.data
    promptEditorText.value = res.data.instructions || ''
  } catch (e) {
    showToast('加载失败')
  }
}

// Watch tab switch
watch(promptTab, (val) => {
  if (showPromptEditor.value) loadPromptForTab(val)
})

async function saveParsePrompt() {
  try {
    await api.put(`/api/entry/prompts/${promptTab.value}`, {
      instructions: promptEditorText.value,
    })
    showToast('已保存')
    showPromptEditor.value = false
  } catch (e) {
    showToast('保存失败')
  }
}

async function resetParsePrompt() {
  const cached = promptCache.value[promptTab.value]
  if (cached?.default) {
    promptEditorText.value = cached.default
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

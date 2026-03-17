<template>
  <div class="scholar-chat flex flex-col" :style="{ height: chatHeight }">
    <!-- Header -->
    <div class="scholar-header flex items-center px-4 py-3 border-b bg-white flex-shrink-0">
      <div class="flex items-center gap-3 flex-shrink-0">
        <!-- left placeholder for balance -->
      </div>
      <div class="flex-1 flex items-center justify-center gap-2.5">
        <div class="scholar-avatar">
          <span>📜</span>
        </div>
        <div class="text-center">
          <div class="text-base font-bold text-gray-800">龙图阁大学士</div>
          <div class="text-xs text-gray-400" v-if="!streaming">博学多才 · 有问必答</div>
          <div class="text-xs text-blue-500 flex items-center justify-center gap-1" v-else>
            <van-loading size="10" />
            <span>思考中...</span>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3 flex-shrink-0">
        <div class="header-btn" title="定时报告" @click="showScheduled = true">
          <van-icon name="notes-o" size="18" />
        </div>
        <div class="header-btn" title="历史对话" @click="openHistory">
          <van-icon name="clock-o" size="18" />
        </div>
        <div class="header-btn" title="新建对话" @click="newConversation">
          <van-icon name="add-o" size="18" />
        </div>
      </div>
    </div>

    <!-- History overlay -->
    <transition name="slide-down">
      <div v-if="showHistory" class="history-overlay absolute inset-0 z-20 bg-white flex flex-col" :style="{ top: '57px' }">
        <div class="flex items-center justify-between px-4 py-2.5 border-b bg-gray-50">
          <span class="text-sm font-medium text-gray-600">历史对话</span>
          <van-icon name="cross" size="18" class="text-gray-400 cursor-pointer hover:text-gray-600" @click="showHistory = false" />
        </div>
        <div class="flex-1 overflow-y-auto px-4 py-3">
          <div v-if="historyLoading" class="flex items-center justify-center py-16">
            <van-loading size="24" />
            <span class="ml-2 text-sm text-gray-400">正在分类...</span>
          </div>
          <div v-else-if="categories.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-300">
            <van-icon name="records-o" size="40" />
            <p class="mt-3 text-sm">暂无历史对话</p>
          </div>
          <div v-else class="max-w-3xl mx-auto space-y-4">
            <div
              v-for="(cat, ci) in categories"
              :key="cat.category"
              class="category-card rounded-xl overflow-hidden border"
              :style="{ borderColor: categoryColors[ci % categoryColors.length] + '30' }"
            >
              <div
                class="px-3 py-2 flex items-center gap-2"
                :style="{ background: categoryColors[ci % categoryColors.length] + '12' }"
              >
                <span
                  class="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                  :style="{ background: categoryColors[ci % categoryColors.length] }"
                ></span>
                <span class="text-sm font-semibold" :style="{ color: categoryColors[ci % categoryColors.length] }">
                  {{ cat.category }}
                </span>
                <span class="text-xs text-gray-400 ml-1">{{ cat.conversations.length }}个对话</span>
              </div>
              <div class="divide-y divide-gray-50">
                <div
                  v-for="conv in cat.conversations"
                  :key="conv.conversation_id"
                  class="px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors flex items-center justify-between"
                  @click="loadConversation(conv.conversation_id); showHistory = false"
                >
                  <div class="flex-1 min-w-0">
                    <div class="text-sm text-gray-700 truncate">{{ conv.title }}</div>
                    <div class="text-xs text-gray-400 mt-0.5">{{ formatTime(conv.updated_at) }} · {{ conv.message_count }}条</div>
                  </div>
                  <van-icon
                    name="delete-o"
                    size="16"
                    class="text-gray-300 hover:text-red-400 flex-shrink-0 ml-2 transition-colors"
                    @click.stop="deleteConversation(conv.conversation_id)"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Scheduled overlay -->
    <transition name="slide-down">
      <ScholarScheduled v-if="showScheduled" @close="showScheduled = false" />
    </transition>

    <!-- Messages -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-gray-50 scholar-messages" @click="pdfMenuIdx = null">
      <div class="max-w-2xl mx-auto">
        <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-8 text-gray-300">
          <div class="text-6xl mb-4">📜</div>
          <p class="text-base font-medium text-gray-400">向大学士提问</p>
          <p class="text-xs mt-2 text-gray-300">支持上传 PDF 文档 · 联网搜索实时信息</p>
        </div>

        <template v-for="(msg, idx) in messages" :key="idx">
          <!-- User message -->
          <div v-if="msg.role === 'user'" class="flex justify-end mb-3">
            <div class="max-w-[80%]">
              <div v-if="msg.files && msg.files.length" class="flex flex-wrap gap-1 mb-1.5 justify-end">
                <van-tag v-for="f in msg.files" :key="f.file_id" plain type="primary" size="medium" round>
                  📎 {{ f.filename }}
                </van-tag>
              </div>
              <div class="bg-blue-500 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm">{{ msg.content }}</div>
            </div>
          </div>

          <!-- Thinking block -->
          <div v-else-if="msg.role === 'thinking'" class="mb-2">
            <div class="max-w-[90%] bg-amber-50/70 border border-amber-100 rounded-xl px-3 py-2">
              <div class="flex items-center gap-1.5 cursor-pointer select-none" @click="msg.collapsed = !msg.collapsed">
                <van-icon :name="msg.collapsed ? 'arrow' : 'arrow-down'" size="12" class="text-amber-400" />
                <span class="text-xs text-amber-500 font-medium">思考过程</span>
                <van-loading v-if="msg.streaming" size="12" class="ml-1" />
              </div>
              <div v-show="!msg.collapsed" class="mt-2 text-xs text-amber-700/80 italic whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed">{{ msg.content }}</div>
            </div>
          </div>

          <!-- Tool use (search) -->
          <div v-else-if="msg.role === 'tool_use'" class="mb-2">
            <div class="inline-flex items-center gap-1.5 bg-gray-100 rounded-full px-3 py-1 text-xs text-gray-500">
              <van-icon v-if="msg.tool === 'WebSearch'" name="search" size="13" class="text-blue-400" />
              <van-icon v-else name="link-o" size="13" class="text-green-400" />
              <span v-if="msg.tool === 'WebSearch'">搜索: {{ msg.query }}</span>
              <span v-else>获取: {{ truncUrl(msg.url) }}</span>
            </div>
          </div>

          <!-- Assistant text -->
          <div v-else-if="msg.role === 'assistant'" class="mb-3">
            <div class="relative bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
              <div v-if="!msg.streaming" class="absolute top-2.5 right-2.5 z-10">
                <div
                  class="cursor-pointer text-gray-300 active:text-blue-600 transition-colors p-1"
                  title="导出PDF"
                  @click.stop="pdfMenuIdx = pdfMenuIdx === idx ? null : idx"
                >
                  <van-icon name="description" size="16" />
                </div>
                <div v-if="pdfMenuIdx === idx" class="absolute right-0 top-8 bg-white border border-gray-200 rounded-xl shadow-lg p-3 w-48" @click.stop>
                  <label class="flex items-center gap-2 text-xs text-gray-600 cursor-pointer select-none mb-3">
                    <input type="checkbox" v-model="pdfIncludeQuestion" class="rounded" />
                    <span>包含提问内容</span>
                  </label>
                  <van-button size="small" type="primary" block @click="downloadAnswerPDF(idx); pdfMenuIdx = null">导出 PDF</van-button>
                </div>
              </div>
              <div class="text-base text-gray-700 leading-relaxed scholar-md" :class="{ 'pr-7': !msg.streaming }" v-html="renderMarkdown(msg.content)"></div>
              <van-loading v-if="msg.streaming" size="16" class="mt-2" />
            </div>
          </div>

          <!-- Error -->
          <div v-else-if="msg.role === 'error'" class="mb-3">
            <div class="bg-red-50 border border-red-100 rounded-xl px-4 py-2.5 text-sm text-red-600">{{ msg.content }}</div>
          </div>
        </template>
      </div>
    </div>

    <!-- File attachments preview -->
    <div v-if="attachedFiles.length > 0" class="px-4 py-2 border-t bg-white flex-shrink-0">
      <div class="max-w-2xl mx-auto flex flex-wrap gap-1.5">
        <van-tag
          v-for="f in attachedFiles"
          :key="f.file_id"
          closeable
          type="primary"
          size="medium"
          round
          @close="removeFile(f.file_id)"
        >
          📎 {{ f.filename }}
          <span v-if="f.page_count" class="ml-0.5 opacity-70">{{ f.page_count }}页</span>
        </van-tag>
      </div>
    </div>

    <!-- Input area -->
    <div
      class="border-t bg-white px-4 py-3 flex-shrink-0"
      :class="{ 'ring-2 ring-blue-300 ring-inset bg-blue-50': isDragging }"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="handleDrop"
    >
      <div class="max-w-2xl mx-auto">
        <div v-if="isDragging" class="text-center py-6 text-blue-400 text-sm font-medium">
          📄 松开以上传文件
        </div>
        <div v-else class="flex items-end gap-3">
          <div class="flex-1 relative">
            <textarea
              ref="inputEl"
              v-model="inputText"
              class="scholar-input w-full border border-gray-200 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100 bg-gray-50 focus:bg-white transition-colors"
              :rows="inputRows"
              placeholder="向大学士提问... (支持拖拽PDF到此处)"
              @keydown.enter.exact="handleEnter"
              @input="autoResize"
            />
          </div>
          <div class="flex items-center gap-2 pb-1.5">
            <label class="cursor-pointer text-gray-400 hover:text-blue-500 transition-colors" title="上传文件">
              <van-icon name="paperclip" size="22" />
              <input type="file" class="hidden" accept=".pdf,.txt,.md,.csv,.json,.yaml,.yml" multiple @change="handleFileSelect" />
            </label>
            <VoiceInputButton v-model="inputText" :size="20" />
            <van-button
              :type="streaming ? 'default' : 'primary'"
              size="normal"
              round
              :icon="streaming ? 'pause-circle-o' : 'guide-o'"
              :loading="uploading"
              :disabled="!canSend"
              class="send-btn"
              @click="sendMessage"
            >
              {{ streaming ? '停止' : '发送' }}
            </van-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { showToast } from 'vant'
import api from '../api'
import VoiceInputButton from './VoiceInputButton.vue'
import ScholarScheduled from './ScholarScheduled.vue'

// ──────────────── State ────────────────

const messages = ref([])
const inputText = ref('')
const attachedFiles = ref([])
const streaming = ref(false)
const uploading = ref(false)
const isDragging = ref(false)
const showHistory = ref(false)
const showScheduled = ref(false)
const historyLoading = ref(false)
const conversations = ref([])
const categories = ref([])
const categoryColors = ['#3B82F6', '#F59E0B', '#10B981', '#8B5CF6', '#EF4444', '#06B6D4']

const conversationId = ref('')
const messagesEl = ref(null)
const inputEl = ref(null)
const pdfMenuIdx = ref(null)
const pdfIncludeQuestion = ref(false)

const inputRows = computed(() => {
  const lines = (inputText.value.match(/\n/g) || []).length + 1
  return Math.min(Math.max(lines, 2), 6)
})

const canSend = computed(() => {
  if (streaming.value) return true // can stop
  return inputText.value.trim().length > 0
})

const chatHeight = computed(() => {
  return 'calc(100dvh - 96px)'
})

// ──────────────── Markdown ────────────────

function inlineMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono">$1</code>')
}

function renderMarkdownTable(block) {
  // Parse a pipe-table block (lines array) into HTML <table>
  const rows = block.map(line =>
    line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
  )
  if (rows.length < 2) return block.join('\n')
  // Row 1 = header, Row 2 = separator (---|---), rest = body
  const header = rows[0]
  const body = rows.slice(2)
  let t = '<div class="overflow-x-auto my-2"><table class="scholar-table"><thead><tr>'
  for (const h of header) t += `<th>${inlineMarkdown(h)}</th>`
  t += '</tr></thead><tbody>'
  for (const row of body) {
    t += '<tr>'
    for (let i = 0; i < header.length; i++) t += `<td>${inlineMarkdown(row[i] || '')}</td>`
    t += '</tr>'
  }
  t += '</tbody></table></div>'
  return t
}

function renderMarkdown(text) {
  if (!text) return ''

  // Extract pipe tables before general processing
  // Split by lines, find table blocks, process them separately
  const lines = text.split('\n')
  const segments = []  // { type: 'text' | 'table', content }
  let i = 0
  while (i < lines.length) {
    // Detect table: line with pipes, followed by separator line (|---|---|)
    if (
      lines[i].includes('|') &&
      i + 1 < lines.length &&
      /^\|?\s*[-:]+[-| :]*$/.test(lines[i + 1])
    ) {
      const tableLines = [lines[i], lines[i + 1]]
      i += 2
      while (i < lines.length && lines[i].includes('|') && !/^\s*$/.test(lines[i])) {
        tableLines.push(lines[i])
        i++
      }
      segments.push({ type: 'table', content: tableLines })
    } else {
      // Accumulate text lines
      if (segments.length > 0 && segments[segments.length - 1].type === 'text') {
        segments[segments.length - 1].content += '\n' + lines[i]
      } else {
        segments.push({ type: 'text', content: lines[i] })
      }
      i++
    }
  }

  // Process each segment
  const parts = segments.map(seg => {
    if (seg.type === 'table') {
      // Escape HTML in table cells first, then build table
      const escaped = seg.content.map(line =>
        line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      )
      return renderMarkdownTable(escaped)
    }
    // Regular text — full markdown processing
    let html = seg.content
      // Escape HTML first
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Code blocks (before inline processing)
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-50 border rounded-lg p-3 my-2 text-xs overflow-x-auto font-mono"><code>$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono">$1</code>')
      // Bold & italic
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Headings
      .replace(/^### (.+)$/gm, '<h4 class="font-semibold text-gray-800 mt-3 mb-1 text-sm">$1</h4>')
      .replace(/^## (.+)$/gm, '<h3 class="font-semibold text-gray-800 mt-3 mb-1">$1</h3>')
      .replace(/^# (.+)$/gm, '<h3 class="font-bold text-gray-800 mt-3 mb-1">$1</h3>')
      // Lists
      .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc my-0.5">$1</li>')
      .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal my-0.5">$2</li>')
      // Line breaks
      .replace(/\n{2,}/g, '<br><br>')
      .replace(/\n/g, '<br>')

    // Markdown links: [text](url) — process AFTER HTML escaping
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-600 underline underline-offset-2">$1</a>')

    // Auto-link bare URLs (http/https) not already inside href=""
    html = html.replace(/(?<!href="|">)(https?:\/\/[^\s<"]+)/g, '<a href="$1" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-600 underline underline-offset-2 break-all">$1</a>')

    return html
  })

  return parts.join('')
}

function truncUrl(url) {
  if (!url) return ''
  try {
    const u = new URL(url)
    return u.hostname + (u.pathname.length > 30 ? u.pathname.slice(0, 30) + '...' : u.pathname)
  } catch {
    return url.slice(0, 50)
  }
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    const now = new Date()
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

// ──────────────── Scrolling ────────────────

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

// Auto-scroll when streaming new content
watch(
  () => messages.value.length > 0 && messages.value[messages.value.length - 1]?.content,
  () => {
    if (streaming.value) scrollToBottom()
  }
)

// ──────────────── File upload ────────────────

async function uploadFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  uploading.value = true
  try {
    const res = await api.post('/api/scholar/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    attachedFiles.value.push(res.data)
    showToast({ message: `${file.name} 已上传`, type: 'success' })
  } catch (e) {
    showToast({ message: `上传失败: ${e.response?.data?.detail || e.message}`, type: 'fail' })
  } finally {
    uploading.value = false
  }
}

function removeFile(fileId) {
  attachedFiles.value = attachedFiles.value.filter(f => f.file_id !== fileId)
}

async function handleDrop(e) {
  isDragging.value = false
  const files = Array.from(e.dataTransfer.files)
  for (const file of files) {
    await uploadFile(file)
  }
}

async function handleFileSelect(e) {
  const files = Array.from(e.target.files)
  for (const file of files) {
    await uploadFile(file)
  }
  e.target.value = ''
}

// ──────────────── Send message ────────────────

function handleEnter(e) {
  if (e.isComposing) return // IME composing
  e.preventDefault()
  sendMessage()
}

function autoResize() {
  // handled by computed inputRows
}

let abortController = null

async function sendMessage() {
  if (streaming.value) {
    // Stop streaming
    if (abortController) abortController.abort()
    streaming.value = false
    return
  }

  const question = inputText.value.trim()
  if (!question) return

  // Add user message to display
  messages.value.push({
    role: 'user',
    content: question,
    files: [...attachedFiles.value],
  })
  scrollToBottom()

  const fileIds = attachedFiles.value.map(f => f.file_id)

  // Clear input (keep attached files for follow-up questions)
  inputText.value = ''

  // Submit question
  streaming.value = true
  abortController = new AbortController()

  try {
    const askRes = await api.post('/api/scholar/ask', {
      question,
      conversation_id: conversationId.value || undefined,
      file_ids: fileIds,
    })

    const { query_id, conversation_id: convId } = askRes.data
    conversationId.value = convId

    // Subscribe to SSE stream
    await consumeStream(query_id)
  } catch (e) {
    if (e.name !== 'AbortError') {
      messages.value.push({ role: 'error', content: `请求失败: ${e.response?.data?.detail || e.message}` })
    }
  } finally {
    streaming.value = false
    abortController = null
    scrollToBottom()
  }
}

async function consumeStream(queryId) {
  const token = localStorage.getItem('teamgr_token')
  const res = await fetch(`/api/scholar/stream/${queryId}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: abortController?.signal,
  })

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  // State for accumulating into message objects
  let thinkingMsg = null
  let textMsg = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        handleStreamEvent(data)
      } catch {
        // skip malformed
      }
    }
  }
  if (buffer.trim() && buffer.startsWith('data: ')) {
    try {
      handleStreamEvent(JSON.parse(buffer.slice(6)))
    } catch {}
  }

  function handleStreamEvent(data) {
    switch (data.type) {
      case 'thinking':
        if (!thinkingMsg) {
          thinkingMsg = { role: 'thinking', content: '', collapsed: true, streaming: true }
          messages.value.push(thinkingMsg)
        }
        thinkingMsg.content += data.content
        break

      case 'tool_use': {
        // Finalize thinking if still streaming
        if (thinkingMsg && thinkingMsg.streaming) {
          thinkingMsg.streaming = false
        }
        const toolMsg = { role: 'tool_use', tool: data.tool, query: '', url: '' }
        if (data.tool === 'WebSearch') {
          toolMsg.query = data.input?.query || JSON.stringify(data.input)
        } else if (data.tool === 'WebFetch') {
          toolMsg.url = data.input?.url || JSON.stringify(data.input)
        } else {
          toolMsg.query = data.tool + ': ' + JSON.stringify(data.input).slice(0, 80)
        }
        messages.value.push(toolMsg)
        break
      }

      case 'text':
        if (thinkingMsg && thinkingMsg.streaming) {
          thinkingMsg.streaming = false
        }
        if (!textMsg) {
          textMsg = { role: 'assistant', content: '', streaming: true }
          messages.value.push(textMsg)
        }
        textMsg.content += data.content
        scrollToBottom()
        break

      case 'done':
        if (thinkingMsg) thinkingMsg.streaming = false
        if (textMsg) {
          textMsg.streaming = false
          if (!textMsg.content && data.result) {
            textMsg.content = data.result
          }
        } else if (data.result) {
          messages.value.push({ role: 'assistant', content: data.result, streaming: false })
        }
        streaming.value = false
        break

      case 'error':
        messages.value.push({ role: 'error', content: data.content || '未知错误' })
        streaming.value = false
        break
    }
    scrollToBottom()
  }
}

// ──────────────── Conversation management ────────────────

function newConversation() {
  conversationId.value = ''
  messages.value = []
  attachedFiles.value = []
  showHistory.value = false
}

async function downloadAnswerPDF(msgIdx) {
  // Find the corresponding question (previous user message)
  const msg = messages.value[msgIdx]
  if (!msg || msg.role !== 'assistant') return

  let question = ''
  for (let i = msgIdx - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      question = messages.value[i].content
      break
    }
  }

  const includeQ = pdfIncludeQuestion.value

  // Determine title: when not including question, extract from answer content
  let titleText = '龙图阁大学士'
  let answerForPdf = msg.content || ''
  if (includeQ && question) {
    titleText = question.substring(0, 50)
  } else {
    // Try markdown heading (# / ## / ###), then bold line, then first non-empty line
    const headingMatch = answerForPdf.match(/^#{1,4}\s+(.+)/m)
    const boldMatch = answerForPdf.match(/^\*\*(.+?)\*\*/m)
    if (headingMatch) {
      titleText = headingMatch[1].replace(/\*\*/g, '').trim().substring(0, 50)
      // Remove the heading line from answer to avoid title/subtitle duplication
      answerForPdf = answerForPdf.replace(headingMatch[0], '').replace(/^\s*\n/, '')
    } else if (boldMatch) {
      titleText = boldMatch[1].trim().substring(0, 50)
      answerForPdf = answerForPdf.replace(boldMatch[0], '').replace(/^\s*\n/, '')
    } else {
      const firstLine = answerForPdf.trim().split('\n')[0]?.trim()
      if (firstLine) titleText = firstLine.substring(0, 50)
    }
  }

  try {
    const res = await api.post('/api/scholar/answer/pdf', {
      question: includeQ ? question : '',
      answer: answerForPdf,
      title: titleText,
    }, { responseType: 'blob' })

    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = titleText.substring(0, 30) + '.pdf'
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    showToast('导出失败')
  }
}

async function fetchConversations() {
  try {
    const res = await api.get('/api/scholar/conversations')
    conversations.value = res.data
  } catch {
    // silent
  }
}

async function fetchCategorized() {
  historyLoading.value = true
  try {
    const res = await api.get('/api/scholar/conversations/categorized')
    categories.value = res.data
  } catch {
    // Fallback to flat list
    await fetchConversations()
    categories.value = conversations.value.length
      ? [{ category: '全部', conversations: conversations.value }]
      : []
  } finally {
    historyLoading.value = false
  }
}

function openHistory() {
  showHistory.value = true
  fetchCategorized()
}

async function loadConversation(convId) {
  showHistory.value = false
  try {
    const res = await api.get(`/api/scholar/conversations/${convId}`)
    const conv = res.data
    conversationId.value = conv.conversation_id
    messages.value = []
    for (const msg of conv.messages || []) {
      messages.value.push({
        role: 'user',
        content: msg.question,
        files: (msg.file_ids || []).map(fid => ({ file_id: fid, filename: fid })),
      })
      if (msg.answer) {
        messages.value.push({
          role: 'assistant',
          content: msg.answer,
          streaming: false,
        })
      }
    }
    scrollToBottom()
  } catch {
    showToast({ message: '加载对话失败', type: 'fail' })
  }
}

async function deleteConversation(convId) {
  try {
    await api.delete(`/api/scholar/conversations/${convId}`)
    conversations.value = conversations.value.filter(c => c.conversation_id !== convId)
    // Remove from categories
    for (const cat of categories.value) {
      cat.conversations = cat.conversations.filter(c => c.conversation_id !== convId)
    }
    categories.value = categories.value.filter(c => c.conversations.length > 0)
    if (conversationId.value === convId) {
      newConversation()
    }
    showToast({ message: '已删除', type: 'success' })
  } catch {
    showToast({ message: '删除失败', type: 'fail' })
  }
}

// ──────────────── Lifecycle ────────────────

onMounted(() => {
  fetchConversations()
})

</script>

<style scoped>
.scholar-chat {
  position: relative;
  max-height: calc(100vh - 96px);
  max-height: calc(100dvh - 96px);
}

/* ── Header ── */
.scholar-avatar {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.header-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.15s;
}

.header-btn:hover {
  background: #f3f4f6;
  color: #6b7280;
}

/* ── History overlay ── */
.history-overlay {
  bottom: 0;
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

/* ── Messages area ── */
.scholar-messages {
  scroll-behavior: smooth;
}

/* ── Input ── */
.scholar-input {
  font-family: inherit;
  line-height: 1.6;
  min-height: 44px;
}

.send-btn {
  min-width: 70px;
}

/* ── Markdown content ── */
.scholar-md :deep(h3),
.scholar-md :deep(h4) {
  margin-top: 0.75rem;
  margin-bottom: 0.25rem;
}

.scholar-md :deep(h3):first-child,
.scholar-md :deep(h4):first-child {
  margin-top: 0;
}

.scholar-md :deep(li) {
  margin-left: 1.25rem;
  margin-top: 0.125rem;
  margin-bottom: 0.125rem;
}

.scholar-md :deep(pre) {
  margin: 0.5rem 0;
}

.scholar-md :deep(code) {
  font-size: 0.75rem;
}

.scholar-md :deep(a) {
  word-break: break-all;
}

.scholar-md :deep(strong) {
  color: #1f2937;
}

/* ── Tables ── */
.scholar-md :deep(.scholar-table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  line-height: 1.5;
}

.scholar-md :deep(.scholar-table th),
.scholar-md :deep(.scholar-table td) {
  border: 1px solid #e5e7eb;
  padding: 0.5rem 0.75rem;
  text-align: left;
}

.scholar-md :deep(.scholar-table th) {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
  white-space: nowrap;
}

.scholar-md :deep(.scholar-table tr:hover) {
  background: #f9fafb;
}

.scholar-md :deep(.scholar-table td) {
  color: #4b5563;
}
</style>

<template>
  <div class="scholar-scheduled flex flex-col h-full bg-white">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b bg-white flex-shrink-0">
      <div class="flex items-center gap-2">
        <van-icon name="arrow-left" size="18" class="text-gray-400 cursor-pointer" @click="$emit('close')" />
        <span class="text-base font-bold text-gray-800">定时报告</span>
      </div>
      <van-icon name="plus" size="20" class="text-blue-500 cursor-pointer" @click="showCreateDialog = true" />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <van-loading size="24" />
    </div>

    <!-- Empty state -->
    <div v-else-if="questions.length === 0" class="flex-1 flex flex-col items-center justify-center py-16 text-gray-300">
      <div class="text-5xl mb-4">📅</div>
      <p class="text-sm text-gray-400">暂无定时问题</p>
      <p class="text-xs text-gray-300 mt-1">点击右上角 + 创建</p>
    </div>

    <!-- Question list / Result view -->
    <div v-else class="flex-1 overflow-y-auto">
      <!-- Result detail view -->
      <div v-if="viewingResult" class="px-4 py-3">
        <div class="flex items-center gap-2 mb-3">
          <van-icon name="arrow-left" size="16" class="text-gray-400 cursor-pointer" @click="viewingResult = null; stopPolling(); runningQuestionId = null; stopTTS()" />
          <span class="text-sm font-medium text-gray-700">{{ viewingResult.question_title || viewingResult.title }}</span>
          <van-tag size="small" :type="typeTagColor(viewingResult.schedule_type)">{{ typeLabel(viewingResult.schedule_type) }}</van-tag>
        </div>
        <!-- Running progress panel -->
        <div v-if="runningQuestionId === viewingResult.id" class="mb-3 px-3 py-3 bg-blue-50 border border-blue-100 rounded-xl">
          <div class="flex items-center gap-2 mb-2">
            <van-loading size="14" color="#3B82F6" />
            <span class="text-sm font-medium text-blue-600">{{ progressStage || '正在执行中...' }}</span>
          </div>
          <div v-if="progressEvents.length > 0" class="space-y-1 ml-5">
            <div v-for="(evt, i) in progressEvents" :key="i" class="flex items-center gap-1.5 text-xs text-blue-500/70">
              <van-icon v-if="evt.type === 'search'" name="search" size="12" />
              <van-icon v-else name="link-o" size="12" />
              <span class="truncate">{{ evt.type === 'search' ? evt.query : evt.url }}</span>
            </div>
          </div>
        </div>
        <!-- Info bar: results are persisted -->
        <div v-if="results.length > 0 && runningQuestionId !== viewingResult.id" class="mb-3 px-3 py-2 bg-gray-50 border border-gray-100 rounded-xl flex items-center justify-between">
          <span class="text-xs text-gray-400">共 {{ results.length }} 条历史结果 · 定时任务会自动获取最新内容</span>
          <van-button size="mini" plain type="primary" @click="forceRunNow(viewingResult)" :loading="runningQuestionId === viewingResult.id">重新执行</van-button>
        </div>
        <!-- Results timeline -->
        <div v-if="resultLoading" class="flex items-center justify-center py-8">
          <van-loading size="20" />
        </div>
        <div v-else-if="results.length === 0 && !runningQuestionId" class="text-center py-8 text-gray-300 text-sm">
          暂无执行结果
          <div class="mt-3">
            <van-button size="small" type="primary" @click="forceRunNow(viewingResult)">立即执行</van-button>
          </div>
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="r in results"
            :key="r.id"
            class="border rounded-xl overflow-hidden"
            :class="expandedResult === r.id ? 'border-blue-200' : 'border-gray-100'"
          >
            <div
              class="px-3 py-2.5 flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors"
              @click="expandedResult = expandedResult === r.id ? null : r.id"
            >
              <div class="flex items-center gap-2">
                <van-icon :name="r.status === 'success' ? 'checked' : 'warning-o'" :class="r.status === 'success' ? 'text-green-500' : 'text-red-400'" size="16" />
                <span class="text-sm font-medium text-gray-700">{{ r.period_label }}</span>
                <span class="text-xs text-gray-400">{{ formatExactTime(r.generated_at) }}</span>
              </div>
              <div class="flex items-center gap-2 text-xs text-gray-400">
                <span v-if="r.duration_seconds">{{ r.duration_seconds.toFixed(0) }}s</span>
                <span>{{ formatRelativeTime(r.generated_at) }}</span>
                <van-icon :name="expandedResult === r.id ? 'arrow-up' : 'arrow-down'" size="12" />
              </div>
            </div>
            <div v-if="expandedResult === r.id" class="border-t border-gray-50 bg-gray-50/50">
              <!-- TTS control bar -->
              <div v-if="r.status === 'success'" class="px-3 py-2 flex items-center gap-2 border-b border-gray-100 bg-white/60">
                <div
                  class="flex items-center gap-1.5 cursor-pointer select-none rounded-full px-2.5 py-1 text-xs transition-colors"
                  :class="ttsResultId === r.id && (tts.isSpeaking.value || tts.isLoading.value) ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'"
                  @click.stop="toggleTTS(r)"
                >
                  <van-loading v-if="ttsResultId === r.id && tts.isLoading.value" size="12" color="#3B82F6" />
                  <van-icon v-else-if="ttsResultId === r.id && tts.isSpeaking.value && !tts.isPaused.value" name="pause-circle-o" size="14" />
                  <van-icon v-else name="play-circle-o" size="14" />
                  <span v-if="ttsResultId === r.id && tts.isLoading.value">生成语音中...</span>
                  <span v-else-if="ttsResultId === r.id && tts.isSpeaking.value && !tts.isPaused.value">暂停朗读</span>
                  <span v-else-if="ttsResultId === r.id && tts.isPaused.value">继续朗读</span>
                  <span v-else>语音朗读</span>
                </div>
                <div v-if="ttsResultId === r.id && (tts.isSpeaking.value || tts.isLoading.value)" class="flex items-center gap-2 flex-1 min-w-0">
                  <div
                    class="flex-shrink-0 cursor-pointer select-none rounded-full px-1.5 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 hover:bg-gray-200 transition-colors"
                    @click.stop="tts.cycleRate()"
                    title="切换播放速度"
                  >{{ tts.playbackRate.value === 1.0 ? '1x' : tts.playbackRate.value + 'x' }}</div>
                  <div
                    class="flex-1 h-8 flex items-center cursor-pointer group"
                    @touchstart.stop.prevent="startSeekDrag($event)"
                    @mousedown.stop.prevent="startSeekDrag($event)"
                  >
                    <div class="w-full h-1 bg-gray-200 rounded-full overflow-hidden relative group-hover:h-1.5 transition-all">
                      <div class="h-full bg-blue-400 rounded-full" :style="{ width: tts.progress.value + '%' }"></div>
                    </div>
                  </div>
                  <van-icon name="close" size="14" class="text-gray-400 cursor-pointer hover:text-gray-600 flex-shrink-0" @click.stop="stopTTS" />
                </div>
              </div>
              <div class="px-3 py-3">
                <div class="text-base text-gray-700 leading-relaxed scholar-md" v-html="renderMarkdown(r.answer)"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Question list view -->
      <div v-else class="px-4 py-3 space-y-2">
        <div v-for="type in ['daily', 'weekly', 'monthly']" :key="type">
          <div v-if="questionsByType(type).length > 0" class="mb-3">
            <div class="text-xs font-medium text-gray-400 uppercase mb-2 flex items-center gap-1.5">
              <span class="inline-block w-2 h-2 rounded-full" :class="typeDotClass(type)"></span>
              {{ typeLabel(type) }}
            </div>
            <div class="space-y-2">
              <div
                v-for="q in questionsByType(type)"
                :key="q.id"
                class="border rounded-xl px-3 py-3 transition-colors"
                :class="q.enabled ? 'border-gray-100 bg-white' : 'border-gray-50 bg-gray-50/50 opacity-60'"
              >
                <div class="flex items-center justify-between mb-1">
                  <div class="flex items-center gap-2 flex-1 min-w-0 cursor-pointer" @click="viewResults(q)">
                    <span class="text-sm font-medium text-gray-800 truncate">{{ q.title }}</span>
                    <van-tag v-if="q.depends_on_id" size="small" plain type="primary">聚合</van-tag>
                  </div>
                  <van-switch v-model="q.enabled" size="18" @change="toggleEnabled(q)" />
                </div>
                <div class="text-xs text-gray-400 mb-2 truncate">{{ q.prompt.substring(0, 60) }}...</div>
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-3 text-xs text-gray-400">
                    <span>{{ scheduleDesc(q) }}</span>
                    <span v-if="q.latest_result" class="flex items-center gap-1">
                      <van-icon :name="q.latest_result.status === 'success' ? 'checked' : 'warning-o'" size="12" :class="q.latest_result.status === 'success' ? 'text-green-500' : 'text-red-400'" />
                      {{ q.latest_result.period_label }}
                    </span>
                    <span v-if="q.result_count" class="text-gray-300">{{ q.result_count }}次</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <van-loading v-if="runningQuestionId === q.id" size="16" color="#3B82F6" />
                    <van-icon v-else name="play-circle-o" size="18" class="text-blue-400 cursor-pointer" title="立即执行" @click.stop="runNow(q)" />
                    <van-icon name="edit" size="16" class="text-gray-400 cursor-pointer" title="编辑" @click.stop="editQuestion(q)" />
                    <van-icon name="delete-o" size="16" class="text-gray-300 cursor-pointer hover:text-red-400" title="删除" @click.stop="deleteQuestion(q)" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit dialog -->
    <van-popup v-model:show="showCreateDialog" position="bottom" round :style="{ maxHeight: '85vh' }">
      <div class="px-4 py-4">
        <div class="text-base font-bold text-gray-800 mb-4">{{ editingId ? '编辑' : '新建' }}定时问题</div>

        <div class="space-y-3">
          <div>
            <label class="text-xs text-gray-500 mb-1 block">标题</label>
            <input v-model="form.title" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400" placeholder="如：每日财经要闻" />
          </div>

          <div>
            <label class="text-xs text-gray-500 mb-1 block">提问内容（支持变量 {date} {week_label} {month_label}）</label>
            <textarea v-model="form.prompt" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-blue-400" rows="4" placeholder="请搜索并整理今天（{date}）最重要的10个财经新闻..." />
          </div>

          <div class="flex gap-3">
            <div class="flex-1">
              <label class="text-xs text-gray-500 mb-1 block">频率</label>
              <select v-model="form.schedule_type" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400">
                <option value="daily">每日</option>
                <option value="weekly">每周</option>
                <option value="monthly">每月</option>
              </select>
            </div>
            <div class="w-20">
              <label class="text-xs text-gray-500 mb-1 block">时</label>
              <input v-model.number="form.cron_hour" type="number" min="0" max="23" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400" />
            </div>
            <div class="w-20">
              <label class="text-xs text-gray-500 mb-1 block">分</label>
              <input v-model.number="form.cron_minute" type="number" min="0" max="59" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400" />
            </div>
          </div>

          <div v-if="form.schedule_type === 'weekly'" class="flex gap-3">
            <div class="flex-1">
              <label class="text-xs text-gray-500 mb-1 block">星期几</label>
              <select v-model="form.day_of_week" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400">
                <option value="mon">周一</option>
                <option value="tue">周二</option>
                <option value="wed">周三</option>
                <option value="thu">周四</option>
                <option value="fri">周五</option>
                <option value="sat">周六</option>
                <option value="sun">周日</option>
              </select>
            </div>
          </div>

          <div v-if="form.schedule_type === 'monthly'" class="flex gap-3">
            <div class="flex-1">
              <label class="text-xs text-gray-500 mb-1 block">每月几号</label>
              <input v-model.number="form.day_of_month" type="number" min="1" max="28" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400" />
            </div>
          </div>

          <div>
            <label class="text-xs text-gray-500 mb-1 block">依赖问题（用于周/月聚合，引用另一个问题的结果作为上下文）</label>
            <select v-model="form.depends_on_id" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400">
              <option :value="null">无依赖</option>
              <option v-for="dq in dependableQuestions" :key="dq.id" :value="dq.id">{{ dq.title }} ({{ typeLabel(dq.schedule_type) }})</option>
            </select>
          </div>

          <div v-if="form.depends_on_id">
            <label class="text-xs text-gray-500 mb-1 block">取最近几天的结果</label>
            <input v-model.number="form.context_days" type="number" min="1" max="90" class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400" />
          </div>
        </div>

        <div class="flex gap-3 mt-5">
          <van-button block plain @click="showCreateDialog = false">取消</van-button>
          <van-button block type="primary" :loading="saving" @click="saveQuestion">{{ editingId ? '保存' : '创建' }}</van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api from '../api'
import { useTTS } from '../composables/useTTS'

const emit = defineEmits(['close'])

// State
const loading = ref(false)
const saving = ref(false)
const questions = ref([])
const showCreateDialog = ref(false)
const editingId = ref(null)
const viewingResult = ref(null)
const resultLoading = ref(false)
const results = ref([])
const expandedResult = ref(null)
const runningQuestionId = ref(null)  // which question is currently executing
const progressStage = ref('')
const progressEvents = ref([])
let pollTimer = null
let progressTimer = null
const tts = useTTS()
const ttsResultId = ref(null)  // which result is currently being read aloud

const defaultForm = {
  title: '',
  prompt: '',
  schedule_type: 'daily',
  cron_hour: 6,
  cron_minute: 0,
  day_of_week: 'mon',
  day_of_month: 1,
  depends_on_id: null,
  context_days: 7,
}
const form = ref({ ...defaultForm })

const dependableQuestions = computed(() =>
  questions.value.filter(q => !editingId.value || q.id !== editingId.value)
)

function questionsByType(type) {
  return questions.value.filter(q => q.schedule_type === type)
}

function typeLabel(type) {
  return { daily: '每日', weekly: '每周', monthly: '每月' }[type] || type
}

function typeTagColor(type) {
  return { daily: 'primary', weekly: 'success', monthly: 'warning' }[type] || 'default'
}

function typeDotClass(type) {
  return { daily: 'bg-blue-500', weekly: 'bg-green-500', monthly: 'bg-amber-500' }[type] || 'bg-gray-400'
}

function scheduleDesc(q) {
  const time = `${String(q.cron_hour).padStart(2, '0')}:${String(q.cron_minute).padStart(2, '0')}`
  if (q.schedule_type === 'daily') return `每天 ${time}`
  if (q.schedule_type === 'weekly') {
    const days = { mon: '一', tue: '二', wed: '三', thu: '四', fri: '五', sat: '六', sun: '日' }
    return `每周${days[q.day_of_week] || q.day_of_week} ${time}`
  }
  if (q.schedule_type === 'monthly') return `每月${q.day_of_month}号 ${time}`
  return time
}

function _parseUTC(iso) {
  if (!iso) return null
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  return isNaN(d.getTime()) ? null : d
}

function formatExactTime(iso) {
  const d = _parseUTC(iso)
  if (!d) return ''
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatRelativeTime(iso) {
  const d = _parseUTC(iso)
  if (!d) return ''
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// Markdown renderer (with pipe table support)
function colorizeCell(text) {
  // Color percentage changes: green for up, red for down
  // Matches: +2.3%, -1.5%, ▲2.3%, ▼1.5%, 涨2.3%, 跌1.5%
  return text
    .replace(/([+▲涨]\s*[\d.]+%)/g, '<span style="color:#16a34a;font-weight:600">$1</span>')
    .replace(/([-▼跌]\s*[\d.]+%)/g, '<span style="color:#dc2626;font-weight:600">$1</span>')
}

function renderMarkdownTable(block) {
  const rows = block.map(line =>
    line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
  )
  if (rows.length < 2) return block.join('\n')
  const header = rows[0]
  const body = rows.slice(2)
  let t = '<div class="overflow-x-auto my-2"><table class="scholar-table"><thead><tr>'
  for (const h of header) t += `<th>${h}</th>`
  t += '</tr></thead><tbody>'
  for (const row of body) {
    t += '<tr>'
    for (let i = 0; i < header.length; i++) t += `<td>${colorizeCell(row[i] || '')}</td>`
    t += '</tr>'
  }
  t += '</tbody></table></div>'
  return t
}

function renderMarkdown(text) {
  if (!text) return ''

  const lines = text.split('\n')
  const segments = []
  let i = 0
  while (i < lines.length) {
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
      if (segments.length > 0 && segments[segments.length - 1].type === 'text') {
        segments[segments.length - 1].content += '\n' + lines[i]
      } else {
        segments.push({ type: 'text', content: lines[i] })
      }
      i++
    }
  }

  return segments.map(seg => {
    if (seg.type === 'table') {
      const escaped = seg.content.map(line =>
        line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      )
      return renderMarkdownTable(escaped)
    }
    let html = seg.content
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-100 rounded-lg p-3 text-xs overflow-x-auto my-2"><code>$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono">$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/^### (.+)$/gm, '<h4 class="font-semibold text-gray-800 mt-4 mb-1.5 text-base">$1</h4>')
      .replace(/^## (.+)$/gm, '<h3 class="font-semibold text-gray-800 mt-4 mb-1.5 text-lg">$1</h3>')
      .replace(/^# (.+)$/gm, '<h3 class="font-bold text-gray-800 mt-4 mb-1.5 text-lg">$1</h3>')
      .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc my-0.5">$1</li>')
      .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal my-0.5">$2</li>')
      .replace(/^---$/gm, '<hr class="my-3 border-gray-200" />')
      .replace(/\n{2,}/g, '<br><br>')
      .replace(/\n/g, '<br>')
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-600 underline underline-offset-2">$1</a>')
    return html
  }).join('')
}

// API calls
async function loadQuestions() {
  loading.value = true
  try {
    const { data } = await api.get('/api/scholar/scheduled')
    questions.value = data
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
}

async function saveQuestion() {
  if (!form.value.title.trim() || !form.value.prompt.trim()) {
    showToast('标题和内容不能为空')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/scholar/scheduled/${editingId.value}`, form.value)
    } else {
      await api.post('/api/scholar/scheduled', form.value)
    }
    showCreateDialog.value = false
    editingId.value = null
    form.value = { ...defaultForm }
    await loadQuestions()
    showToast(editingId.value ? '已保存' : '已创建')
  } catch (e) {
    showToast('操作失败')
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(q) {
  try {
    await api.put(`/api/scholar/scheduled/${q.id}`, { enabled: q.enabled })
  } catch (e) {
    q.enabled = !q.enabled
    showToast('操作失败')
  }
}

function editQuestion(q) {
  editingId.value = q.id
  form.value = {
    title: q.title,
    prompt: q.prompt,
    schedule_type: q.schedule_type,
    cron_hour: q.cron_hour,
    cron_minute: q.cron_minute,
    day_of_week: q.day_of_week || 'mon',
    day_of_month: q.day_of_month || 1,
    depends_on_id: q.depends_on_id,
    context_days: q.context_days || 7,
  }
  showCreateDialog.value = true
}

async function deleteQuestion(q) {
  try {
    await showConfirmDialog({ title: '确认删除', message: `删除「${q.title}」及所有结果？` })
    await api.delete(`/api/scholar/scheduled/${q.id}`)
    await loadQuestions()
    showToast('已删除')
  } catch {
    // cancelled
  }
}

async function runNow(q, force = false) {
  let resp
  try {
    resp = (await api.post(`/api/scholar/scheduled/${q.id}/run`, { force })).data
  } catch (e) {
    showToast('执行失败')
    return
  }

  // Navigate to results view
  viewingResult.value = { ...q, question_title: q.title }
  expandedResult.value = null
  results.value = []
  resultLoading.value = false

  // If skipped (already has result for this period), just show existing results
  if (resp.skipped) {
    showToast({ message: `${resp.period_label} 已有结果`, duration: 2000 })
    await viewResults(q)
    return
  }

  // Start polling for new result
  const prevCount = q.result_count || 0
  runningQuestionId.value = q.id
  progressStage.value = '等待处理...'
  progressEvents.value = []

  // Load existing results first
  try {
    const { data } = await api.get(`/api/scholar/scheduled/${q.id}/results?limit=30`)
    results.value = data.results
  } catch { /* ignore */ }

  // Poll for progress + result
  stopPolling()
  let elapsed = 0
  const pollInterval = 2000
  const maxWait = 1260000  // 21 minutes
  pollTimer = setInterval(async () => {
    elapsed += pollInterval
    if (elapsed > maxWait) {
      stopPolling()
      runningQuestionId.value = null
      showToast('执行超时，请稍后手动刷新')
      return
    }
    try {
      // Poll progress
      const { data: prog } = await api.get(`/api/scholar/scheduled/${q.id}/progress`)
      if (prog.stage) progressStage.value = prog.stage
      if (prog.events) progressEvents.value = prog.events

      // Check if done
      if (prog.done) {
        const { data } = await api.get(`/api/scholar/scheduled/${q.id}/results?limit=30`)
        results.value = data.results
        if (data.results.length > 0) {
          expandedResult.value = data.results[0].id
        }
        stopPolling()
        runningQuestionId.value = null
        await loadQuestions()
        return
      }
    } catch { /* ignore poll errors */ }
  }, pollInterval)
}

async function forceRunNow(q) {
  await runNow(q, true)
}

function toggleTTS(r) {
  if (ttsResultId.value === r.id && (tts.isSpeaking.value || tts.isLoading.value)) {
    tts.toggle(r.id)
  } else {
    ttsResultId.value = r.id
    tts.speak(r.id)
  }
}

function stopTTS() {
  tts.stop()
  ttsResultId.value = null
}

function seekToPosition(el, clientX) {
  const rect = el.getBoundingClientRect()
  const percent = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
  tts.seek(percent)
}

function startSeekDrag(e) {
  const el = e.currentTarget
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  seekToPosition(el, clientX)

  const onMove = (ev) => {
    ev.preventDefault()
    const x = ev.touches ? ev.touches[0].clientX : ev.clientX
    seekToPosition(el, x)
  }
  const onEnd = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onEnd)
    document.removeEventListener('touchmove', onMove)
    document.removeEventListener('touchend', onEnd)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onEnd)
  document.addEventListener('touchmove', onMove, { passive: false })
  document.addEventListener('touchend', onEnd)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  progressStage.value = ''
  progressEvents.value = []
}

async function viewResults(q) {
  viewingResult.value = { ...q, question_title: q.title }
  expandedResult.value = null
  resultLoading.value = true
  try {
    const { data } = await api.get(`/api/scholar/scheduled/${q.id}/results?limit=30`)
    results.value = data.results
    // Auto-expand the first result
    if (results.value.length > 0) {
      expandedResult.value = results.value[0].id
    }
  } catch (e) {
    showToast('加载结果失败')
    results.value = []
  } finally {
    resultLoading.value = false
  }
}

onMounted(() => {
  loadQuestions()
})

onUnmounted(() => {
  stopPolling()
})

defineExpose({ refresh: loadQuestions })
</script>

<style scoped>
.scholar-scheduled {
  position: absolute;
  inset: 0;
  z-index: 20;
}
.scholar-md h2, .scholar-md h3, .scholar-md h4 {
  color: #1f2937;
}
.scholar-md li {
  margin-bottom: 2px;
}
.scholar-md hr {
  margin: 8px 0;
}
.scholar-md :deep(.scholar-table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  line-height: 1.5;
}
.scholar-md :deep(.scholar-table th),
.scholar-md :deep(.scholar-table td) {
  border: 1px solid #e5e7eb;
  padding: 6px 10px;
  text-align: left;
}
.scholar-md :deep(.scholar-table th) {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
}
.scholar-md :deep(.scholar-table tr:nth-child(even)) {
  background: #f9fafb;
}
</style>

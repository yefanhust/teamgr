<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.push('/')" />
          <h1 class="text-lg font-bold text-gray-800">灵感空间</h1>
        </div>
        <div class="flex gap-2">
          <van-button
            size="mini"
            icon="fire-o"
            :loading="generatingInsights"
            @click="generateInsights"
          >
            生成洞见
          </van-button>
        </div>
      </div>
    </div>

    <van-tabs v-model:active="activeTab" shrink sticky offset-top="49" class="ideas-tabs" @change="onTabChange">
      <van-tab title="灵感洞见">
    <div class="max-w-3xl mx-auto px-4 py-4 space-y-6">

      <!-- ========== TAGS SECTION ========== -->
      <section v-if="allTags.length > 0">
        <!-- Organize progress -->
        <div v-if="organizing || organizeStatus" class="mb-3 bg-gray-50 rounded-lg p-3 text-sm">
          <div class="flex items-center gap-2 mb-1">
            <van-icon v-if="organizeStatus === 'done'" name="checked" color="#10B981" size="14" />
            <van-icon v-else-if="organizeStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
            <van-loading v-else size="14" />
            <span class="text-gray-600">{{ organizeStatusText }}</span>
          </div>
          <pre v-if="orgThinkingStream" ref="orgThinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed italic">{{ orgThinkingStream }}</pre>
          <pre v-if="organizeStream" ref="orgOutputPre" class="text-xs text-gray-500 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono leading-relaxed">{{ organizeStream }}</pre>
        </div>

        <div class="flex items-center gap-2 mb-2">
          <van-checkbox
            :model-value="allTagsSelected"
            shape="square"
            icon-size="16px"
            class="flex-shrink-0"
            @update:model-value="selectAllTags"
          >
            全选
          </van-checkbox>
          <van-button
            size="mini"
            icon="sort"
            :loading="organizing"
            @click="organizeTags"
          >
            一键整理
          </van-button>
          <span class="text-xs text-gray-400">{{ displayedFragments.length }}/{{ fragments.length }} 条碎片</span>
        </div>

        <!-- Tag categories display -->
        <template v-if="tagCategories.length > 0">
          <div v-for="cat in tagCategories" :key="cat.name" class="mb-3">
            <div class="text-xs text-gray-400 mb-1">{{ cat.name }}</div>
            <div class="flex flex-wrap gap-1">
              <van-tag
                v-for="tag in cat.children" :key="tag"
                :type="selectedTags.has(tag) ? 'primary' : 'default'"
                size="medium"
                class="cursor-pointer"
                @click="toggleTag(tag)"
              >
                {{ tag }}
              </van-tag>
            </div>
          </div>
        </template>

        <!-- Flat tags display (when no categories) -->
        <div v-else class="flex flex-wrap gap-1 mb-2">
          <van-tag
            v-for="tag in allTags" :key="tag"
            :type="selectedTags.has(tag) ? 'primary' : 'default'"
            size="medium"
            class="cursor-pointer"
            @click="toggleTag(tag)"
          >
            {{ tag }}
          </van-tag>
        </div>
      </section>

      <!-- ========== DAILY INSIGHTS SECTION ========== -->
      <section v-if="insights.length > 0">
        <h2 class="text-sm font-semibold text-gray-500 mb-3 flex items-center gap-2">
          <span class="w-1 h-4 bg-orange-400 rounded-full inline-block"></span>
          每日洞见
        </h2>
        <div v-for="(group, date) in groupedInsights" :key="date" class="mb-4">
          <div class="text-xs text-gray-400 mb-2">{{ date }}</div>
          <div class="space-y-3">
            <div
              v-for="ins in group"
              :key="ins.id"
              class="bg-white rounded-xl shadow-sm p-4"
            >
              <p class="text-sm text-gray-800 whitespace-pre-line mb-3 leading-relaxed">{{ ins.content }}</p>
              <div
                v-if="ins.reasoning"
                class="text-xs text-gray-400 bg-gray-50 rounded-lg p-2 mb-3 italic leading-relaxed"
              >
                {{ ins.reasoning }}
              </div>
              <div class="flex items-center justify-between">
                <div class="text-xs text-gray-400">
                  <span v-if="ins.model_name" class="mr-2">{{ ins.model_name }}</span>
                  <span>{{ ins.liked ? '已收藏' : '未收藏的洞见次日会被丢弃' }}</span>
                </div>
                <van-button
                  :icon="ins.liked ? 'like' : 'like-o'"
                  :type="ins.liked ? 'primary' : 'default'"
                  size="small"
                  round
                  @click="toggleLike(ins)"
                >
                  {{ ins.liked ? '已赞' : '点赞保留' }}
                </van-button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ========== FRAGMENTS SECTION ========== -->
      <section>
        <h2 class="text-sm font-semibold text-gray-500 mb-3 flex items-center gap-2">
          <span class="w-1 h-4 bg-blue-500 rounded-full inline-block"></span>
          灵感碎片
          <span v-if="fragments.length" class="text-xs text-gray-400 font-normal">({{ displayedFragments.length }})</span>
        </h2>

        <div v-if="loading" class="flex justify-center py-8">
          <van-loading size="28px">加载中...</van-loading>
        </div>

        <div v-else-if="fragments.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
          <p class="text-sm">还没有灵感碎片，写下你的第一个想法吧</p>
        </div>

        <template v-else>
          <div v-for="(group, category) in groupedDisplayedFragments" :key="category" class="mb-4">
            <h3 class="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1">
              {{ category }}
              <span class="text-gray-300">({{ group.length }})</span>
            </h3>
            <div class="space-y-2">
              <van-swipe-cell v-for="frag in group" :key="frag.id">
                <div class="bg-white rounded-xl shadow-sm p-3">
                  <div class="flex items-start justify-between mb-1">
                    <h4 class="text-sm font-medium text-gray-800">{{ frag.title }}</h4>
                    <span class="text-xs text-gray-400 flex-shrink-0 ml-2">{{ formatDate(frag.updated_at) }}</span>
                  </div>
                  <div class="flex items-center flex-wrap gap-1">
                    <van-tag
                      v-for="tag in (frag.tags || [])"
                      :key="tag"
                      :type="selectedTags.has(tag) ? 'primary' : 'default'"
                      plain
                      size="small"
                      class="cursor-pointer"
                      @click="toggleTag(tag)"
                    >
                      {{ tag }}
                    </van-tag>
                    <span
                      v-if="frag.content"
                      class="text-xs text-blue-500 cursor-pointer ml-1"
                      @click="toggleExpand(frag.id)"
                    >
                      {{ expandedIds.has(frag.id) ? '收起' : '展开' }}
                    </span>
                  </div>
                  <p v-if="expandedIds.has(frag.id)" class="text-sm text-gray-600 whitespace-pre-line mt-2">{{ frag.content }}</p>
                </div>
                <template #right>
                  <van-button
                    square
                    type="danger"
                    text="删除"
                    class="h-full"
                    @click="handleDeleteFragment(frag.id)"
                  />
                </template>
              </van-swipe-cell>
            </div>
          </div>
        </template>
      </section>

      <!-- ========== INPUT SECTION ========== -->
      <section>
        <div class="bg-white rounded-xl shadow-sm p-4">
          <van-field
            v-model="inputText"
            type="textarea"
            :autosize="{ minHeight: 100 }"
            placeholder="写下你此刻的灵感、想法、碎片思考..."
            class="idea-input"
          />
          <div class="flex justify-end mt-3">
            <van-button
              type="primary"
              icon="guide-o"
              :disabled="!inputText.trim() || submitting"
              :loading="submitting"
              @click="submitIdea"
            >
              记录灵感
            </van-button>
          </div>
        </div>

        <!-- Streaming output area -->
        <div v-if="streamState" class="mt-3 bg-white rounded-xl shadow-sm p-4">
          <div class="flex items-center gap-2 mb-2">
            <van-loading v-if="streamState === 'streaming'" size="16px" />
            <van-icon v-else-if="streamState === 'done'" name="checked" color="#10B981" size="18" />
            <van-icon v-else-if="streamState === 'error'" name="warning-o" color="#EF4444" size="18" />
            <span class="text-sm font-medium text-gray-600">
              {{ streamState === 'streaming' ? 'LLM 整理中...' : streamState === 'done' ? '整理完成' : '处理失败' }}
            </span>
          </div>

          <!-- Thinking stream -->
          <pre
            v-if="thinkingStream"
            ref="thinkingPre"
            class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed italic bg-gray-50 rounded-lg p-2 mb-2"
          >{{ thinkingStream }}</pre>

          <!-- Output stream -->
          <pre
            v-if="outputStream"
            ref="outputPre"
            class="text-xs text-gray-600 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono leading-relaxed bg-blue-50 rounded-lg p-2"
          >{{ outputStream }}</pre>

          <!-- Result summary -->
          <div v-if="streamState === 'done' && streamResult.length > 0" class="mt-3 space-y-2">
            <div v-for="(frag, idx) in streamResult" :key="idx" class="flex items-center gap-2 text-sm">
              <van-tag :type="frag.action === 'merge' ? 'warning' : 'success'" size="small">
                {{ frag.action === 'merge' ? '合并' : '新建' }}
              </van-tag>
              <span class="text-gray-700">{{ frag.title }}</span>
              <span class="text-xs text-gray-400">[{{ frag.category }}]</span>
            </div>
          </div>
        </div>
      </section>

    </div>
      </van-tab>

      <van-tab title="输入历史">
    <div class="max-w-3xl mx-auto px-4 py-4">
      <div v-if="loadingHistory" class="flex justify-center py-8">
        <van-loading size="28px">加载中...</van-loading>
      </div>

      <div v-else-if="history.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400 text-sm">
        暂无输入历史
      </div>

      <template v-else>
        <div class="space-y-2">
          <div v-for="log in history" :key="log.id" class="bg-white rounded-xl shadow-sm p-3">
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs text-gray-400">{{ formatDateTime(log.created_at) }}</span>
              <van-tag
                :type="log.status === 'done' ? 'success' : log.status === 'processing' ? 'warning' : 'danger'"
                size="small"
              >
                {{ log.status === 'done' ? '已处理' : log.status === 'processing' ? '处理中' : '失败' }}
              </van-tag>
            </div>
            <p class="text-sm text-gray-700 whitespace-pre-line">{{ log.raw_text }}</p>
          </div>
        </div>

        <div v-if="historyTotal > 20" class="flex justify-center pt-4 pb-2">
          <van-pagination
            v-model="historyPage"
            :total-items="historyTotal"
            :items-per-page="20"
            :show-page-size="3"
            force-ellipses
            @change="loadHistory"
          />
        </div>
      </template>
    </div>
      </van-tab>
    </van-tabs>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useIdeasStore } from '../stores/ideas'
import { showToast, showConfirmDialog } from 'vant'

const store = useIdeasStore()

const activeTab = ref(0)
const inputText = ref('')
const submitting = ref(false)
const loading = ref(false)
const loadingHistory = ref(false)
const generatingInsights = ref(false)
const historyPage = ref(1)

// Streaming state
const streamState = ref(null) // null | 'streaming' | 'done' | 'error'
const thinkingStream = ref('')
const outputStream = ref('')
const streamResult = ref([])
const thinkingPre = ref(null)
const outputPre = ref(null)

// Fragment expand state
const expandedIds = ref(new Set())

// Tag filter state
const selectedTags = ref(new Set())
const tagCategories = ref([]) // [{name, children: [tag_name, ...]}]

// Organize state
const organizing = ref(false)
const organizeStream = ref('')
const orgThinkingStream = ref('')
const orgThinkingPre = ref(null)
const orgOutputPre = ref(null)
const organizeStatus = ref('')
const organizeStatusText = ref('')

const fragments = computed(() => store.fragments)
const insights = computed(() => store.insights)
const history = computed(() => store.history)
const historyTotal = computed(() => store.historyTotal)

// Collect all unique tags from fragments
const allTags = computed(() => {
  const tags = new Set()
  for (const f of fragments.value) {
    for (const t of (f.tags || [])) {
      tags.add(t)
    }
  }
  return [...tags].sort()
})

const allTagsSelected = computed(() => {
  if (allTags.value.length === 0) return true
  return allTags.value.every(t => selectedTags.value.has(t))
})

// Filter fragments by selected tags
const displayedFragments = computed(() => {
  if (selectedTags.value.size === 0 || allTagsSelected.value) {
    return fragments.value
  }
  return fragments.value.filter(f =>
    (f.tags || []).some(t => selectedTags.value.has(t))
  )
})

const groupedDisplayedFragments = computed(() => {
  const groups = {}
  for (const f of displayedFragments.value) {
    const cat = f.category || '未分类'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(f)
  }
  return groups
})

const groupedInsights = computed(() => {
  const groups = {}
  for (const i of insights.value) {
    const date = i.generated_date || '未知日期'
    if (!groups[date]) groups[date] = []
    groups[date].push(i)
  }
  return groups
})

// Auto-select all tags when fragments change
watch(allTags, (tags) => {
  selectedTags.value = new Set(tags)
}, { immediate: true })

function autoScroll(el) {
  if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight })
}
watch(orgThinkingStream, () => autoScroll(orgThinkingPre.value), { flush: 'post' })
watch(organizeStream, () => autoScroll(orgOutputPre.value), { flush: 'post' })

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([store.fetchFragments(), store.fetchInsights()])
  } finally {
    loading.value = false
  }
})

function toggleExpand(id) {
  const s = new Set(expandedIds.value)
  if (s.has(id)) {
    s.delete(id)
  } else {
    s.add(id)
  }
  expandedIds.value = s
}

function toggleTag(tag) {
  const s = new Set(selectedTags.value)
  if (s.has(tag)) {
    s.delete(tag)
  } else {
    s.add(tag)
  }
  selectedTags.value = s
}

function selectAllTags() {
  if (allTagsSelected.value) {
    selectedTags.value = new Set()
  } else {
    selectedTags.value = new Set(allTags.value)
  }
}

async function submitIdea() {
  if (!inputText.value.trim() || submitting.value) return
  submitting.value = true
  const text = inputText.value.trim()

  // Reset streaming state
  streamState.value = 'streaming'
  thinkingStream.value = ''
  outputStream.value = ''
  streamResult.value = []

  try {
    const token = localStorage.getItem('teamgr_token')
    const response = await fetch('/api/ideas/input/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content: text }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    inputText.value = ''

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const dataStr = line.slice(6).trim()
        if (!dataStr) continue

        try {
          const data = JSON.parse(dataStr)

          if (data.type === 'thinking_chunk') {
            thinkingStream.value += data.content
            await nextTick()
            if (thinkingPre.value) {
              thinkingPre.value.scrollTop = thinkingPre.value.scrollHeight
            }
          } else if (data.type === 'thinking_done') {
            // thinking done, output starts
          } else if (data.type === 'thinking') {
            // heartbeat during thinking, no-op
          } else if (data.type === 'chunk') {
            outputStream.value += data.content
            await nextTick()
            if (outputPre.value) {
              outputPre.value.scrollTop = outputPre.value.scrollHeight
            }
          } else if (data.type === 'done') {
            streamState.value = 'done'
            streamResult.value = data.fragments || []
            store.fetchFragments()
          } else if (data.type === 'error') {
            streamState.value = 'error'
            showToast('处理失败: ' + (data.content || '未知错误'))
          }
        } catch (e) {
          // ignore parse errors
        }
      }
    }

    // If stream ended without explicit done/error
    if (streamState.value === 'streaming') {
      streamState.value = 'done'
      store.fetchFragments()
    }

  } catch (e) {
    streamState.value = 'error'
    showToast('提交失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

async function handleDeleteFragment(id) {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后不可恢复' })
    await store.deleteFragment(id)
    showToast('已删除')
  } catch (e) {
    // cancelled or error
  }
}

async function toggleLike(insight) {
  try {
    if (insight.liked) {
      await store.unlikeInsight(insight.id)
    } else {
      await store.likeInsight(insight.id)
    }
  } catch (e) {
    showToast('操作失败')
  }
}

async function generateInsights() {
  generatingInsights.value = true
  try {
    await store.triggerInsightGeneration()
    await store.fetchInsights()
    showToast('洞见已生成')
  } catch (e) {
    showToast('生成失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    generatingInsights.value = false
  }
}

function handleOrganizeSSELine(line) {
  if (!line.startsWith('data: ')) return
  try {
    const data = JSON.parse(line.slice(6))
    if (data.type === 'thinking') {
      organizeStatusText.value = `模型正在思考中... (${data.elapsed}s)`
    } else if (data.type === 'thinking_chunk') {
      organizeStatusText.value = '模型正在思考中...'
      orgThinkingStream.value += data.content
    } else if (data.type === 'thinking_done') {
      organizeStatusText.value = `思考完成 (${data.elapsed}s)，正在生成整理结果...`
    } else if (data.type === 'chunk') {
      organizeStream.value += data.content
    } else if (data.type === 'merge') {
      const count = data.merges.length
      organizeStream.value += `\n--- 合并了 ${count} 组相似标签 ---\n` + data.merges.map(m => `  ${m}`).join('\n') + '\n'
    } else if (data.type === 'done') {
      tagCategories.value = data.categories || []
      store.fetchFragments()
      selectedTags.value = new Set(data.all_tags || [])
      organizeStatus.value = 'done'
      organizeStatusText.value = `整理完成：${(data.categories || []).length} 个分类，${(data.all_tags || []).length} 个标签`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 3000)
    } else if (data.type === 'error') {
      organizeStatus.value = 'error'
      organizeStatusText.value = `整理失败：${data.content}`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 5000)
    }
  } catch (e) {
    console.error('SSE parse error:', e)
  }
}

async function organizeTags() {
  organizing.value = true
  organizeStream.value = ''
  orgThinkingStream.value = ''
  organizeStatus.value = 'running'
  organizeStatusText.value = `正在分析 ${allTags.value.length} 个标签...`

  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/ideas/tags/organize', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        handleOrganizeSSELine(line)
      }
    }
    if (buffer.trim()) handleOrganizeSSELine(buffer)

    if (organizeStatus.value === 'running') {
      await store.fetchFragments()
      selectedTags.value = new Set(allTags.value)
      organizeStatus.value = 'done'
      organizeStatusText.value = '整理完成'
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 3000)
    }
  } catch (e) {
    organizeStatus.value = 'error'
    organizeStatusText.value = `整理失败：${e.message}`
    setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 5000)
  } finally {
    organizing.value = false
  }
}

function onTabChange(index) {
  if (index === 1) {
    historyPage.value = 1
    loadHistory()
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    await store.fetchHistory(historyPage.value)
  } finally {
    loadingHistory.value = false
  }
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatDateTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.idea-input {
  border: 1px solid #d1d5db !important;
  border-radius: 12px !important;
  padding: 12px !important;
  overflow: hidden;
}
.idea-input::after {
  display: none !important;
}
.idea-input:focus-within {
  border-color: #3b82f6 !important;
}
.idea-input :deep(.van-field__control) {
  font-size: 15px !important;
  line-height: 1.7 !important;
}
.ideas-tabs :deep(.van-tabs__wrap) {
  max-width: 48rem; /* max-w-3xl */
  margin: 0 auto;
  padding: 0 1rem; /* px-4 */
}
</style>

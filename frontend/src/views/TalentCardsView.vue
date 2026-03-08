<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Top Navigation -->
    <TopNavBar />
    <div class="max-w-6xl mx-auto px-4 py-1 flex items-center justify-between">
      <h1 class="text-sm font-bold text-gray-500">👥 人才卡</h1>
      <div class="flex gap-2">
        <van-button size="small" icon="search" @click="$router.push('/search')">搜索</van-button>
        <van-button size="small" icon="edit" type="primary" @click="$router.push('/entry')">录入</van-button>
      </div>
    </div>

    <!-- Quick Search (Mobile) -->
    <div class="px-4 pt-3 md:hidden">
      <div class="flex items-center gap-1">
        <van-search
          v-model="quickSearchQuery"
          placeholder="搜索姓名/拼音..."
          shape="round"
          class="flex-1"
          @update:model-value="handleQuickSearch"
        />
        <VoiceInputButton v-model="quickSearchQuery" mode="replace" />
      </div>
    </div>

    <!-- Tag Filter -->
    <div class="px-4 pt-3 pb-1">
      <div class="flex items-center gap-2 mb-2">
        <van-checkbox
          :model-value="allSelected"
          shape="square"
          icon-size="16px"
          class="flex-shrink-0 select-all-checkbox"
          @update:model-value="selectAll"
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
      </div>
      <!-- Organize progress -->
      <div v-if="organizing || organizeStatus" class="mb-3 bg-gray-50 rounded-lg p-3 text-sm">
        <div v-if="organizeStatus" class="flex items-center gap-2 mb-1">
          <van-icon v-if="organizeStatus === 'done'" name="checked" color="#10B981" size="14" />
          <van-icon v-else-if="organizeStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
          <van-loading v-else size="14" />
          <span class="text-gray-600">{{ organizeStatusText }}</span>
        </div>
        <pre v-if="thinkingStream" ref="thinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed italic">💭 {{ thinkingStream }}</pre>
        <pre v-if="organizeStream" ref="organizePre" class="text-xs text-gray-500 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono leading-relaxed">{{ organizeStream }}</pre>
      </div>
      <!-- Hierarchical tags display -->
      <template v-if="tagTree.length > 0">
        <div v-for="group in tagTree" :key="group.id" class="mb-2">
          <div class="flex gap-2 flex-wrap items-center">
            <span class="text-xs text-gray-500 font-medium flex-shrink-0" :style="{ color: group.color }">{{ group.name }}</span>
            <template v-for="tag in group.children" :key="tag.id">
              <input
                v-if="editingTagId === tag.id"
                v-model="editingTagName"
                class="edit-tag-input"
                @blur="finishEditTag(tag)"
                @keypress.enter="finishEditTag(tag)"
                @keydown.escape="cancelEditTag"
                ref="tagEditInput"
              />
              <van-tag
                v-else
                :type="selectedTagIds.has(tag.id) ? 'primary' : 'default'"
                :color="selectedTagIds.has(tag.id) ? tag.color : undefined"
                size="medium"
                class="cursor-pointer tag-closeable"
                closeable
                @click="toggleTag(tag.id)"
                @dblclick.stop="startEditTag(tag)"
                @close.stop="confirmDeleteTag(tag)"
              >
                {{ tag.name }}
              </van-tag>
            </template>
          </div>
        </div>
      </template>
      <!-- Flat tags (no hierarchy yet) -->
      <div v-if="orphanTags.length > 0" class="flex gap-2 flex-wrap items-center">
        <template v-for="tag in orphanTags" :key="tag.id">
          <input
            v-if="editingTagId === tag.id"
            v-model="editingTagName"
            class="edit-tag-input"
            @blur="finishEditTag(tag)"
            @keypress.enter="finishEditTag(tag)"
            @keydown.escape="cancelEditTag"
            ref="tagEditInput"
          />
          <van-tag
            v-else
            :type="selectedTagIds.has(tag.id) ? 'primary' : 'default'"
            :color="selectedTagIds.has(tag.id) ? tag.color : undefined"
            size="medium"
            class="cursor-pointer tag-closeable"
            closeable
            @click="toggleTag(tag.id)"
            @dblclick.stop="startEditTag(tag)"
            @close.stop="confirmDeleteTag(tag)"
          >
            {{ tag.name }}
          </van-tag>
        </template>
      </div>
    </div>

    <!-- Talent Cards Grid -->
    <div class="max-w-6xl mx-auto px-4 py-4">
      <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
        <div v-if="displayedTalents.length === 0 && !store.loading" class="text-center py-16 text-gray-400">
          <div class="text-4xl mb-3">📋</div>
          <p>暂无人才卡</p>
          <van-button type="primary" size="small" class="mt-4" @click="showCreateDialog = true">
            添加第一个人才
          </van-button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="talent in displayedTalents"
            :key="talent.id"
            class="bg-white rounded-xl shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow active:bg-gray-50"
            @click="$router.push(`/talent/${talent.id}`)"
          >
            <div class="flex items-start justify-between mb-2">
              <div class="flex-1 min-w-0">
                <h3 class="text-base font-semibold text-gray-800">{{ talent.name }}</h3>
                <p class="text-xs text-gray-500">{{ talent.current_role || talent.department || '' }}</p>
              </div>
              <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                <van-tag
                  v-for="tag in talent.tags.slice(0, 3)"
                  :key="tag.id"
                  :color="tag.color"
                  size="small"
                  plain
                >
                  {{ tag.name }}
                </van-tag>
                <van-icon
                  name="delete-o"
                  size="16"
                  color="#999"
                  class="ml-1 p-1 rounded-full hover:bg-gray-100"
                  @click.stop="confirmDelete(talent)"
                />
              </div>
            </div>
            <p class="text-sm text-gray-600 line-clamp-2">
              {{ talent.summary || '暂无摘要' }}
            </p>
          </div>
        </div>
      </van-pull-refresh>

      <!-- Scheduled Query Results -->
      <div v-if="scheduledResults.length > 0" class="mt-4 space-y-3">
        <h3 class="text-sm font-semibold text-gray-600 flex items-center gap-1">
          <van-icon name="clock-o" size="14" />
          定时查询结果
        </h3>
        <div
          v-for="result in scheduledResults"
          :key="result.id"
          class="bg-blue-50 rounded-xl p-3 border border-blue-100"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-blue-700">{{ result.question_snapshot }}</span>
            <span class="text-xs text-gray-400">{{ formatTime(result.generated_at) }} · {{ result.model_name }}</span>
          </div>
          <p class="text-sm text-gray-700 whitespace-pre-line">{{ result.answer }}</p>
        </div>
      </div>

      <!-- Chat Query Panel -->
      <div class="mt-6">
        <ChatQueryPanel />
      </div>
    </div>

    <!-- FAB: Add Talent -->
    <div class="fixed bottom-6 right-6 z-20">
      <van-button
        type="primary"
        round
        icon="plus"
        class="shadow-lg"
        @click="showCreateDialog = true"
      />
    </div>

    <!-- Create Talent Dialog -->
    <van-dialog
      v-model:show="showCreateDialog"
      title="添加人才"
      show-cancel-button
      @confirm="createNewTalent"
    >
      <div class="px-4 py-2">
        <van-field v-model="newTalent.name" label="姓名" placeholder="必填" required />
        <van-field v-model="newTalent.email" label="邮箱" placeholder="选填" />
        <van-field v-model="newTalent.phone" label="电话" placeholder="选填" />
        <van-field v-model="newTalent.current_role" label="职位" placeholder="选填" />
        <van-field v-model="newTalent.department" label="部门" placeholder="选填" />
      </div>
    </van-dialog>

    <!-- Delete Talent Confirm -->
    <van-dialog
      v-model:show="showDeleteConfirm"
      title="确认删除"
      :message="`删除「${deletingTalent?.name}」后不可恢复，确定？`"
      show-cancel-button
      @confirm="handleDelete"
    />

    <!-- Delete Tag Confirm -->
    <van-dialog
      v-model:show="showDeleteTagConfirm"
      title="删除标签"
      :message="`删除标签「${deletingTag?.name}」后，所有人才卡上的该标签也会移除，确定？`"
      show-cancel-button
      @confirm="handleDeleteTag"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useTalentStore } from '../stores/talent'
import { showToast } from 'vant'
import ChatQueryPanel from '../components/ChatQueryPanel.vue'
import VoiceInputButton from '../components/VoiceInputButton.vue'
import TopNavBar from '../components/TopNavBar.vue'
import api from '../api'

const store = useTalentStore()

const selectedTagIds = ref(new Set())
const quickSearchQuery = ref('')
const quickSearchResults = ref(null)
const refreshing = ref(false)
const showCreateDialog = ref(false)
const showDeleteConfirm = ref(false)
const deletingTalent = ref(null)
const editingTagId = ref(null)
const editingTagName = ref('')
const tagEditInput = ref(null)
const showDeleteTagConfirm = ref(false)
const deletingTag = ref(null)
const scheduledResults = ref([])
const organizing = ref(false)
const organizeStream = ref('')
const thinkingStream = ref('')
const thinkingPre = ref(null)
const organizePre = ref(null)
const organizeStatus = ref('')
const organizeStatusText = ref('')
const newTalent = ref({
  name: '', email: '', phone: '', current_role: '', department: '',
})

// Auto-scroll streaming outputs to bottom
function autoScroll(el) {
  if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight })
}
watch(thinkingStream, () => autoScroll(thinkingPre.value), { flush: 'post' })
watch(organizeStream, () => autoScroll(organizePre.value), { flush: 'post' })

// Build tag tree from flat tags with parent_id
const parentTags = computed(() => store.tags.filter(t => !t.parent_id && store.tags.some(c => c.parent_id === t.id)))
const childTags = computed(() => store.tags.filter(t => t.parent_id))
const orphanTags = computed(() => store.tags.filter(t => !t.parent_id && !store.tags.some(c => c.parent_id === t.id)))
const tagTree = computed(() => {
  return parentTags.value.map(p => ({
    ...p,
    children: childTags.value.filter(c => c.parent_id === p.id),
  }))
})

const allSelected = computed(() => {
  const leafTags = [...childTags.value, ...orphanTags.value]
  if (leafTags.length === 0) return true
  return leafTags.every(t => selectedTagIds.value.has(t.id))
})

const displayedTalents = computed(() => {
  if (quickSearchResults.value !== null) {
    return quickSearchResults.value
  }
  if (allSelected.value || selectedTagIds.value.size === 0) {
    return store.talents
  }
  return store.talents.filter(t =>
    t.tags.some(tag => selectedTagIds.value.has(tag.id))
  )
})

onMounted(async () => {
  await Promise.all([
    store.fetchTalents(),
    store.fetchTags(),
    fetchScheduledResults(),
  ])
  // Select only leaf tags (children + orphans), not parent tags
  const leafs = store.tags.filter(t => t.parent_id || !store.tags.some(c => c.parent_id === t.id))
  selectedTagIds.value = new Set(leafs.map(t => t.id))
})

async function fetchScheduledResults() {
  try {
    const res = await api.get('/api/chat/scheduled-results', { params: { limit: 10 } })
    scheduledResults.value = res.data
  } catch (e) {
    // ignore
  }
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr + 'Z')
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function selectAll() {
  const leafs = [...childTags.value, ...orphanTags.value]
  if (allSelected.value) {
    selectedTagIds.value = new Set()
  } else {
    selectedTagIds.value = new Set(leafs.map(t => t.id))
  }
  quickSearchResults.value = null
  quickSearchQuery.value = ''
}

function toggleTag(tagId) {
  const s = new Set(selectedTagIds.value)
  if (s.has(tagId)) {
    s.delete(tagId)
  } else {
    s.add(tagId)
  }
  selectedTagIds.value = s
  quickSearchResults.value = null
  quickSearchQuery.value = ''
}

async function handleQuickSearch(val) {
  if (!val.trim()) {
    quickSearchResults.value = null
    return
  }
  try {
    quickSearchResults.value = await store.searchTalents(val)
  } catch (e) {
    // ignore
  }
}

async function onRefresh() {
  await Promise.all([
    store.fetchTalents(),
    store.fetchTags(),
    fetchScheduledResults(),
  ])
  refreshing.value = false
}

function confirmDelete(talent) {
  deletingTalent.value = talent
  showDeleteConfirm.value = true
}

async function handleDelete() {
  try {
    await store.deleteTalent(deletingTalent.value.id)
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

function confirmDeleteTag(tag) {
  deletingTag.value = tag
  showDeleteTagConfirm.value = true
}

async function handleDeleteTag() {
  try {
    await store.deleteTag(deletingTag.value.id)
    showToast('标签已删除')
    const s = new Set(selectedTagIds.value)
    s.delete(deletingTag.value.id)
    selectedTagIds.value = s
  } catch (e) {
    showToast('删除失败')
  }
}

async function createNewTalent() {
  if (!newTalent.value.name.trim()) {
    showToast('请输入姓名')
    return
  }
  try {
    await store.createTalent(newTalent.value)
    showToast('添加成功')
    newTalent.value = { name: '', email: '', phone: '', current_role: '', department: '' }
    await store.fetchTalents()
  } catch (e) {
    showToast('添加失败')
  }
}

async function startEditTag(tag) {
  editingTagId.value = tag.id
  editingTagName.value = tag.name
  await nextTick()
  const inputs = tagEditInput.value
  if (inputs) {
    const el = Array.isArray(inputs) ? inputs[0] : inputs
    el?.focus()
    el?.select()
  }
}

function cancelEditTag() {
  editingTagId.value = null
  editingTagName.value = ''
}

function handleSSELine(line) {
  if (!line.startsWith('data: ')) return
  try {
    const data = JSON.parse(line.slice(6))
    if (data.type === 'thinking') {
      organizeStatusText.value = `模型正在思考中... (${data.elapsed}s)`
    } else if (data.type === 'thinking_chunk') {
      organizeStatusText.value = '模型正在思考中...'
      thinkingStream.value += data.content
    } else if (data.type === 'thinking_done') {
      organizeStatusText.value = `思考完成 (${data.elapsed}s)，正在生成分类结果...`
    } else if (data.type === 'chunk') {
      organizeStream.value += data.content
    } else if (data.type === 'merge') {
      const count = data.merges.length
      organizeStream.value += `\n--- 合并了 ${count} 组相似标签 ---\n` + data.merges.map(m => `  ${m}`).join('\n') + '\n'
    } else if (data.type === 'done') {
      store.tags = data.tags
      const leafs = data.tags.filter(t => t.parent_id || !data.tags.some(c => c.parent_id === t.id))
      selectedTagIds.value = new Set(leafs.map(t => t.id))
      const parentCount = data.tags.filter(t => !t.parent_id && data.tags.some(c => c.parent_id === t.id)).length
      organizeStatus.value = 'done'
      organizeStatusText.value = `整理完成：${parentCount} 个分类，${leafs.length} 个标签`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 3000)
    } else if (data.type === 'error') {
      organizeStatus.value = 'error'
      organizeStatusText.value = `整理失败：${data.content}`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 5000)
    }
  } catch (e) {
    console.error('SSE parse error:', e, 'line:', line)
  }
}

async function organizeTags() {
  organizing.value = true
  organizeStream.value = ''
  thinkingStream.value = ''
  organizeStatus.value = 'running'
  organizeStatusText.value = `正在分析 ${store.tags.length} 个标签...`

  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/talents/tags/organize', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    // Read stream incrementally
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // keep incomplete last line
      for (const line of lines) {
        handleSSELine(line)
      }
    }
    // Process any remaining buffer
    if (buffer.trim()) handleSSELine(buffer)

    // If no done/error event was received, refresh tags
    if (organizeStatus.value === 'running') {
      await store.fetchTags()
      const leafs = store.tags.filter(t => t.parent_id || !store.tags.some(c => c.parent_id === t.id))
      selectedTagIds.value = new Set(leafs.map(t => t.id))
      organizeStatus.value = 'done'
      organizeStatusText.value = '整理完成'
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 3000)
    }
  } catch (e) {
    organizeStatus.value = 'error'
    organizeStatusText.value = `整理失败：${e.message}`
    setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 5000)
  } finally {
    organizing.value = false
  }
}

async function finishEditTag(tag) {
  const newName = editingTagName.value.trim()
  editingTagId.value = null
  if (!newName || newName === tag.name) return
  try {
    await store.updateTag(tag.id, newName, tag.color)
    await store.fetchTalents()
    showToast('标签已更新')
  } catch (e) {
    showToast(e.response?.data?.detail || '更新失败')
  }
}
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tag-closeable :deep(.van-tag__close) {
  opacity: 0;
  width: 0;
  margin-left: 0;
  transition: all 0.2s;
}
.tag-closeable:hover :deep(.van-tag__close) {
  opacity: 1;
  width: 12px;
  margin-left: 2px;
}
.edit-tag-input {
  border: 1.5px solid #3b82f6;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 13px;
  width: 80px;
  outline: none;
  background: #fff;
}
</style>

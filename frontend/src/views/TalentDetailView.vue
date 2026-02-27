<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
        <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
        <h1 class="text-lg font-bold text-gray-800">{{ talent?.name || '人才详情' }}</h1>
        <van-popover v-model:show="showActions" :actions="actions" @select="onAction" placement="bottom-end">
          <template #reference>
            <van-icon name="ellipsis" size="20" class="cursor-pointer" />
          </template>
        </van-popover>
      </div>
    </div>

    <!-- Processing Banner -->
    <div
      v-if="hasProcessing"
      class="max-w-3xl mx-auto px-4 pt-3"
    >
      <div class="bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-2 text-sm text-yellow-700">
          <van-loading size="14px" color="#d97706" />
          <span>后台正在整理信息...</span>
        </div>
      </div>
    </div>

    <!-- Update Available Banner -->
    <div
      v-if="updateAvailable && !hasProcessing"
      class="max-w-3xl mx-auto px-4 pt-3"
    >
      <div class="bg-green-50 border border-green-200 rounded-xl px-4 py-3 flex items-center justify-between">
        <span class="text-sm text-green-700">信息已更新</span>
        <van-button size="small" type="success" plain round @click="refreshData">
          刷新查看
        </van-button>
      </div>
    </div>

    <div v-if="talent" class="max-w-3xl mx-auto px-4 py-4 space-y-4">
      <!-- Basic Info Card -->
      <div class="bg-white rounded-xl shadow-sm p-5">
        <h2 class="text-xl font-bold text-gray-800">{{ talent.name }}</h2>
        <div v-if="talent.tags.length" class="flex gap-1 flex-wrap mt-2">
          <van-tag
            v-for="tag in talent.tags"
            :key="tag.id"
            :color="tag.color"
            size="medium"
          >
            {{ tag.name }}
          </van-tag>
        </div>
        <p v-if="talent.summary" class="text-sm text-blue-600 mt-2 italic">
          "{{ talent.summary }}"
        </p>

        <div class="grid grid-cols-2 gap-2 text-sm">
          <div v-if="talent.current_role">
            <span class="text-gray-500">职位：</span>{{ talent.current_role }}
          </div>
          <div v-if="talent.department">
            <span class="text-gray-500">部门：</span>{{ talent.department }}
          </div>
          <div v-if="talent.email">
            <span class="text-gray-500">邮箱：</span>{{ talent.email }}
          </div>
          <div v-if="talent.phone">
            <span class="text-gray-500">电话：</span>{{ talent.phone }}
          </div>
        </div>
      </div>

      <!-- Dimension Cards -->
      <div
        v-for="dim in dimensions"
        :key="dim.key"
        class="bg-white rounded-xl shadow-sm p-5"
      >
        <h3 class="text-base font-semibold text-gray-700 mb-3 flex items-center">
          <span class="w-1 h-4 bg-blue-500 rounded-full mr-2 inline-block"></span>
          {{ dim.label }}
        </h3>

        <div v-if="getCardValue(dim.key)" class="text-sm text-gray-600">
          <!-- Array of objects (e.g. career_history, interview_feedback, children) -->
          <template v-if="Array.isArray(getCardValue(dim.key))">
            <div v-if="getCardValue(dim.key).length === 0" class="text-gray-400">暂无数据</div>
            <template v-else-if="typeof getCardValue(dim.key)[0] === 'object'">
              <div
                v-for="(item, idx) in getCardValue(dim.key)"
                :key="idx"
                class="border-l-2 border-blue-200 pl-3 py-1 mb-2"
              >
                <div v-for="(v, k) in item" :key="k">
                  <template v-if="v && v !== ''">
                    <span class="text-gray-500">{{ k }}：</span>
                    <input v-if="isEditing(dim.key, idx, k)" v-model="editValue" class="edit-value-input" ref="editInput"
                      @blur="finishEdit" @keypress.enter="finishEdit" @keydown.escape="cancelEdit" />
                    <span v-else-if="Array.isArray(v)" class="editable-value" @dblclick.stop="startEdit(dim.key, [idx, k], v, true)">{{ v.join('、') }}</span>
                    <span v-else class="editable-value" @dblclick.stop="startEdit(dim.key, [idx, k], v)">{{ v }}</span>
                  </template>
                </div>
              </div>
            </template>
            <!-- Array of strings -->
            <ul v-else class="list-disc list-inside space-y-1">
              <li v-for="(item, idx) in getCardValue(dim.key)" :key="idx">
                <input v-if="isEditing(dim.key, idx)" v-model="editValue" class="edit-value-input" ref="editInput"
                  @blur="finishEdit" @keypress.enter="finishEdit" @keydown.escape="cancelEdit" />
                <span v-else class="editable-value" @dblclick.stop="startEdit(dim.key, [idx], item)">{{ item }}</span>
              </li>
            </ul>
          </template>

          <!-- Object type -->
          <template v-else-if="typeof getCardValue(dim.key) === 'object'">
            <div class="space-y-2">
              <div v-for="(val, key) in getCardValue(dim.key)" :key="key">
                <template v-if="val && val !== '' && !(Array.isArray(val) && val.length === 0)">
                  <span class="text-gray-500">{{ key }}：</span>
                  <!-- Array of objects inside an object field -->
                  <template v-if="Array.isArray(val) && val.length > 0 && typeof val[0] === 'object'">
                    <div
                      v-for="(subItem, si) in val"
                      :key="si"
                      class="border-l-2 border-blue-200 pl-3 py-1 ml-2 mt-1 mb-2"
                    >
                      <div v-for="(sv, sk) in subItem" :key="sk">
                        <template v-if="sv && sv !== ''">
                          <span class="text-gray-500">{{ sk }}：</span>
                          <input v-if="isEditing(dim.key, key, si, sk)" v-model="editValue" class="edit-value-input" ref="editInput"
                            @blur="finishEdit" @keypress.enter="finishEdit" @keydown.escape="cancelEdit" />
                          <span v-else class="editable-value" @dblclick.stop="startEdit(dim.key, [key, si, sk], sv, Array.isArray(sv))">{{ Array.isArray(sv) ? sv.join('、') : sv }}</span>
                        </template>
                      </div>
                    </div>
                  </template>
                  <template v-else>
                    <input v-if="isEditing(dim.key, key)" v-model="editValue" class="edit-value-input" ref="editInput"
                      @blur="finishEdit" @keypress.enter="finishEdit" @keydown.escape="cancelEdit" />
                    <span v-else-if="Array.isArray(val)" class="editable-value" @dblclick.stop="startEdit(dim.key, [key], val, true)">{{ val.join('、') }}</span>
                    <span v-else-if="typeof val === 'object' && val !== null" class="editable-value" @dblclick.stop="startEdit(dim.key, [key], Object.entries(val).filter(([,v]) => v).map(([k,v]) => `${k}: ${v}`).join(', '))">{{ Object.entries(val).filter(([,v]) => v).map(([k,v]) => `${k}: ${v}`).join(', ') || '' }}</span>
                    <span v-else class="editable-value" @dblclick.stop="startEdit(dim.key, [key], val)">{{ val }}</span>
                  </template>
                </template>
              </div>
            </div>
          </template>

          <!-- String type -->
          <template v-else>
            <input v-if="isEditing(dim.key)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
              @blur="finishEdit" @keypress.enter="finishEdit" @keydown.escape="cancelEdit" />
            <p v-else-if="getCardValue(dim.key)" class="editable-value" @dblclick.stop="startEdit(dim.key, [], getCardValue(dim.key))">{{ getCardValue(dim.key) }}</p>
            <p v-else class="text-gray-400">暂无数据</p>
          </template>
        </div>
        <div v-else class="text-sm text-gray-400">暂无数据</div>
      </div>

      <!-- Entry History -->
      <div class="bg-white rounded-xl shadow-sm p-5">
        <h3 class="text-base font-semibold text-gray-700 mb-3 flex items-center">
          <span class="w-1 h-4 bg-green-500 rounded-full mr-2 inline-block"></span>
          信息录入历史
        </h3>

        <div v-if="entryLogs.length === 0" class="text-sm text-gray-400">
          暂无录入记录
        </div>
        <div v-else class="space-y-3">
          <div v-for="log in entryLogs" :key="log.id" class="border-l-2 border-gray-200 pl-3 py-1">
            <div class="flex items-center justify-between mb-1">
              <div class="flex items-center gap-2 text-xs text-gray-400">
                <van-tag size="small" :type="log.source === 'pdf' ? 'warning' : 'primary'">
                  {{ log.source === 'pdf' ? 'PDF' : '手动' }}
                </van-tag>
                <van-tag v-if="log.status === 'processing'" size="small" type="warning" plain>整理中</van-tag>
                <van-tag v-if="log.status === 'failed'" size="small" type="danger" plain>失败</van-tag>
                {{ formatDate(log.created_at) }}
              </div>
              <van-icon
                name="delete-o"
                size="16"
                color="#ee0a24"
                class="cursor-pointer"
                @click="confirmDeleteLog(log.id)"
              />
            </div>
            <p class="text-sm text-gray-600 whitespace-pre-line">{{ expandedLogs.has(log.id) ? log.content : log.content.slice(0, 200) }}<span
              v-if="log.content.length > 200"
              class="text-blue-500 cursor-pointer ml-1"
              @click="toggleLogExpand(log.id)"
            >{{ expandedLogs.has(log.id) ? '收起' : '...展开' }}</span></p>
          </div>
        </div>
      </div>

      <!-- Quick Entry Button -->
      <div class="pb-8">
        <van-button
          type="primary"
          block
          round
          @click="$router.push(`/entry?talent_id=${talent.id}`)"
        >
          为此人才录入信息
        </van-button>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-64">
      <van-loading size="36px">加载中...</van-loading>
    </div>

    <!-- Delete Talent Confirm -->
    <van-dialog
      v-model:show="showDeleteConfirm"
      title="确认删除"
      message="删除后不可恢复，确定删除该人才卡？"
      show-cancel-button
      @confirm="handleDelete"
    />

    <!-- Delete Entry Log Confirm -->
    <van-dialog
      v-model:show="showDeleteLogConfirm"
      title="删除记录"
      message="确定删除这条录入记录？"
      show-cancel-button
      @confirm="handleDeleteLog"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTalentStore } from '../stores/talent'
import { showToast } from 'vant'
import api from '../api'

const route = useRoute()
const router = useRouter()
const store = useTalentStore()

const talent = ref(null)
const dimensions = ref([])
const expandedLogs = ref(new Set())
const entryLogs = ref([])
const showActions = ref(false)
const showDeleteConfirm = ref(false)
const showDeleteLogConfirm = ref(false)
const deleteLogId = ref(null)
const updateAvailable = ref(false)
const editing = ref(null) // { dimKey, path: [], isArray: false }
const editValue = ref('')
const editInput = ref(null)
let pollTimer = null

const actions = [
  { text: '录入信息', icon: 'edit' },
  { text: '导出PDF', icon: 'down' },
  { text: '删除', icon: 'delete', color: '#ee0a24' },
]

const hasProcessing = computed(() => {
  return entryLogs.value.some(l => l.status === 'processing')
})

function isEmptyValue(v) {
  if (v === null || v === undefined || v === '') return true
  if (Array.isArray(v)) return v.length === 0
  if (typeof v === 'object') return Object.values(v).every(isEmptyValue)
  return false
}

function getCardValue(key) {
  const val = talent.value?.card_data?.[key]
  if (!val) return null
  // Filter out JSON Schema definitions mistakenly stored as data
  if (typeof val === 'object' && !Array.isArray(val)) {
    if ('type' in val && ('properties' in val || 'items' in val)) return null
  }
  // Recursively check if all values are empty
  if (isEmptyValue(val)) return null
  return val
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN')
}

async function onAction(action) {
  if (action.text === '录入信息') {
    router.push(`/entry?talent_id=${talent.value.id}`)
  } else if (action.text === '导出PDF') {
    try {
      const res = await api.get(`/api/talents/${talent.value.id}/export-pdf`, {
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${talent.value.name}_人才卡.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast('导出失败')
    }
  } else if (action.text === '删除') {
    showDeleteConfirm.value = true
  }
}

async function handleDelete() {
  try {
    await store.deleteTalent(talent.value.id)
    showToast('已删除')
    router.push('/')
  } catch (e) {
    showToast('删除失败')
  }
}

function toggleLogExpand(logId) {
  const s = new Set(expandedLogs.value)
  if (s.has(logId)) s.delete(logId)
  else s.add(logId)
  expandedLogs.value = s
}

function confirmDeleteLog(logId) {
  deleteLogId.value = logId
  showDeleteLogConfirm.value = true
}

async function handleDeleteLog() {
  try {
    await store.deleteEntryLog(deleteLogId.value)
    entryLogs.value = entryLogs.value.filter(l => l.id !== deleteLogId.value)
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

async function refreshData() {
  const id = route.params.id
  try {
    const [talentData, logs] = await Promise.all([
      store.getTalent(id),
      store.getEntryLogs(id),
    ])
    talent.value = talentData
    entryLogs.value = logs
    updateAvailable.value = false
  } catch (e) {
    showToast('刷新失败')
  }
}

async function pollProcessingEntries() {
  if (!hasProcessing.value) {
    stopPolling()
    return
  }

  const processingLogs = entryLogs.value.filter(l => l.status === 'processing')
  let anyDone = false

  for (const log of processingLogs) {
    try {
      const res = await api.get(`/api/entry/status/${log.id}`)
      if (res.data.status === 'done') {
        log.status = 'done'
        anyDone = true
      } else if (res.data.status === 'failed') {
        log.status = 'failed'
      }
    } catch (e) {
      // ignore
    }
  }

  if (anyDone) {
    updateAvailable.value = true
  }

  if (!hasProcessing.value) {
    stopPolling()
  }
}

function isEditing(dimKey, ...path) {
  if (!editing.value || editing.value.dimKey !== dimKey) return false
  const ep = editing.value.path
  if (ep.length !== path.length) return false
  return ep.every((p, i) => String(p) === String(path[i]))
}

function startEdit(dimKey, path, value, isArray = false) {
  editing.value = { dimKey, path, isArray }
  editValue.value = isArray && Array.isArray(value) ? value.join('、') : String(value ?? '')
  nextTick(() => {
    const el = editInput.value
    const input = Array.isArray(el) ? el[0] : el
    input?.focus()
    input?.select()
  })
}

function cancelEdit() {
  editing.value = null
  editValue.value = ''
}

async function finishEdit() {
  if (!editing.value) return
  const { dimKey, path, isArray } = editing.value
  const newVal = isArray
    ? editValue.value.split(/[、,，]/).map(s => s.trim()).filter(Boolean)
    : editValue.value
  editing.value = null

  const cardData = talent.value.card_data || {}
  let dimVal = path.length === 0
    ? newVal
    : JSON.parse(JSON.stringify(cardData[dimKey] ?? {}))

  if (path.length === 1) {
    dimVal[path[0]] = newVal
  } else if (path.length === 2) {
    dimVal[path[0]][path[1]] = newVal
  } else if (path.length === 3) {
    dimVal[path[0]][path[1]][path[2]] = newVal
  }

  try {
    const updated = await store.updateTalent(talent.value.id, { card_data: { [dimKey]: dimVal } })
    talent.value = updated
    showToast('已保存')
  } catch (e) {
    showToast('保存失败')
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollProcessingEntries, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  const id = route.params.id
  try {
    const [talentData, , logs] = await Promise.all([
      store.getTalent(id),
      store.fetchDimensions(),
      store.getEntryLogs(id),
    ])
    talent.value = talentData
    dimensions.value = store.dimensions
    entryLogs.value = logs

    if (hasProcessing.value) {
      startPolling()
    }
  } catch (e) {
    showToast('加载失败')
    router.push('/')
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.editable-value {
  cursor: pointer;
  border-radius: 3px;
  transition: background-color 0.15s;
}
.editable-value:hover {
  background-color: #f0f5ff;
}
.edit-value-input {
  border: 1.5px solid #3b82f6;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 13px;
  outline: none;
  background: #fff;
  min-width: 80px;
}
.edit-value-input-wide {
  width: 100%;
}
</style>

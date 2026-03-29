<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
        <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
        <h1 class="text-lg font-bold text-gray-800">Settings</h1>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 py-4">
      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <van-loading size="36px">Loading...</van-loading>
      </div>

      <template v-else>
        <!-- Scheduler Config -->
        <div class="mb-6" v-if="Object.keys(schedulerTypes).length">
          <h2 class="text-base font-bold text-gray-600 mb-2 flex items-center gap-1.5">
            <span class="inline-block w-1.5 h-5 rounded-full bg-emerald-500"></span>
            定时任务
          </h2>
          <div class="pl-5">
          <p class="text-xs text-gray-400 mb-3">配置各定时任务的执行时间，修改后即时生效</p>

          <div v-for="group in schedulerGroups" :key="group.page" class="mb-5">
            <h3 class="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-1.5">
              <span class="inline-block w-1 h-4 rounded-full" :style="{ backgroundColor: group.color }"></span>
              {{ group.page }}
            </h3>

            <!-- Parent group with children -->
            <div v-if="group.children" class="pl-4">
              <div v-for="child in group.children" :key="child.page" class="mb-4">
                <h4 class="text-xs font-semibold text-gray-500 mb-2 flex items-center gap-1.5">
                  <span class="inline-block w-1 h-3 rounded-full" :style="{ backgroundColor: child.color }"></span>
                  {{ child.page }}
                </h4>
                <div class="space-y-2 pl-4">
                  <div
                    v-for="key in child.types"
                    :key="key"
                    class="bg-white rounded-xl shadow-sm overflow-hidden"
                  >
                    <div class="p-3 flex items-center justify-between gap-3">
                      <div class="flex-1 min-w-0">
                        <div class="text-sm font-medium text-gray-800 flex items-center gap-1.5">
                          {{ schedulerTypes[key] }}
                          <van-icon
                            v-if="schedulerInstructions[key]"
                            name="edit"
                            size="14"
                            class="text-gray-400 cursor-pointer hover:text-blue-500"
                            @click="togglePromptExpand(key)"
                          />
                        </div>
                        <div class="text-xs text-gray-400">{{ schedulerDescriptions[key] || key }}</div>
                      </div>
                      <template v-if="schedulers[key]?.interval_hours !== undefined">
                        <div class="flex items-center gap-1">
                          <span class="text-xs text-gray-500">每</span>
                          <input type="number" :value="schedulers[key].interval_hours" @change="schedulers[key].interval_hours = Math.max(1, Number($event.target.value) || 1)" class="w-14 text-sm text-center border border-gray-200 rounded-lg px-1 py-1.5 bg-gray-50" min="1" max="24" />
                          <span class="text-xs text-gray-500">小时</span>
                        </div>
                      </template>
                      <template v-else>
                        <span class="text-sm text-blue-500 cursor-pointer hover:text-blue-700 font-mono bg-blue-50 px-2 py-1 rounded" @click="openSchedulerTimePicker(key)">{{ formatTime(schedulers[key]?.cron_hour, schedulers[key]?.cron_minute) }}</span>
                      </template>
                    </div>
                    <div v-if="schedulerInstructions[key] && expandedPrompts[key]" class="border-t border-gray-100 px-3 pb-3 pt-2">
                      <div class="flex items-center justify-between mb-1.5">
                        <span class="text-xs text-gray-500">提示词模板</span>
                        <span v-if="schedulerInstructions[key]?.prompt !== schedulerInstructions[key]?.default" class="text-xs text-orange-500 cursor-pointer hover:text-orange-600" @click="resetPrompt(key)">恢复默认</span>
                      </div>
                      <textarea v-model="schedulerInstructions[key].prompt" class="w-full text-xs text-gray-700 border border-gray-200 rounded-lg p-2 bg-gray-50 resize-y leading-relaxed" rows="8" placeholder="输入提示词模板..."></textarea>
                      <p class="text-xs text-gray-400 mt-1">可用占位符：{{ key === 'daily_todo_analysis' ? '{tasks_text}' : '{projects_text}' }}（运行时自动替换为实际数据）</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Leaf group with types directly -->
            <div v-else class="space-y-2 pl-4">
              <div
                v-for="key in group.types"
                :key="key"
                class="bg-white rounded-xl shadow-sm overflow-hidden"
              >
                <div class="p-3 flex items-center justify-between gap-3">
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-800 flex items-center gap-1.5">
                      {{ schedulerTypes[key] }}
                      <van-icon
                        v-if="schedulerInstructions[key]"
                        name="edit"
                        size="14"
                        class="text-gray-400 cursor-pointer hover:text-blue-500"
                        @click="togglePromptExpand(key)"
                      />
                    </div>
                    <div class="text-xs text-gray-400">{{ schedulerDescriptions[key] || key }}</div>
                  </div>
                  <template v-if="schedulers[key]?.interval_hours !== undefined">
                    <div class="flex items-center gap-1">
                      <span class="text-xs text-gray-500">每</span>
                      <input type="number" :value="schedulers[key].interval_hours" @change="schedulers[key].interval_hours = Math.max(1, Number($event.target.value) || 1)" class="w-14 text-sm text-center border border-gray-200 rounded-lg px-1 py-1.5 bg-gray-50" min="1" max="24" />
                      <span class="text-xs text-gray-500">小时</span>
                    </div>
                  </template>
                  <template v-else>
                    <span class="text-sm text-blue-500 cursor-pointer hover:text-blue-700 font-mono bg-blue-50 px-2 py-1 rounded" @click="openSchedulerTimePicker(key)">{{ formatTime(schedulers[key]?.cron_hour, schedulers[key]?.cron_minute) }}</span>
                  </template>
                </div>
                <div v-if="schedulerInstructions[key] && expandedPrompts[key]" class="border-t border-gray-100 px-3 pb-3 pt-2">
                  <div class="flex items-center justify-between mb-1.5">
                    <span class="text-xs text-gray-500">提示词模板</span>
                    <span v-if="schedulerInstructions[key]?.prompt !== schedulerInstructions[key]?.default" class="text-xs text-orange-500 cursor-pointer hover:text-orange-600" @click="resetPrompt(key)">恢复默认</span>
                  </div>
                  <textarea v-model="schedulerInstructions[key].prompt" class="w-full text-xs text-gray-700 border border-gray-200 rounded-lg p-2 bg-gray-50 resize-y leading-relaxed" rows="8" placeholder="输入提示词模板..."></textarea>
                  <p class="text-xs text-gray-400 mt-1">可用占位符：{{ key === 'daily_todo_analysis' ? '{tasks_text}' : '{projects_text}' }}（运行时自动替换为实际数据）</p>
                </div>
              </div>
            </div>
          </div>

          <div class="mt-4 flex justify-end">
            <van-button type="primary" size="small" :loading="savingSchedulers" @click="saveSchedulers">Save</van-button>
          </div>
          </div>
        </div>

        <!-- 企微推送设置 -->
        <div class="mb-6">
          <h2 class="text-base font-bold text-gray-600 mb-2 flex items-center gap-1.5">
            <span class="inline-block w-1.5 h-5 rounded-full bg-amber-500"></span>
            企微推送
          </h2>
          <div class="pl-5">
          <p class="text-xs text-gray-400 mb-3">管理推送机器人及订阅功能</p>
          <MessageHubTab />
          </div>
        </div>

        <!-- Model Defaults -->
        <div class="mb-4">
          <h2 class="text-base font-bold text-gray-600 mb-2 flex items-center gap-1.5">
            <span class="inline-block w-1.5 h-5 rounded-full bg-violet-500"></span>
            模型配置
          </h2>
          <div class="pl-5">
          <p class="text-xs text-gray-400 mb-3">Choose a model for each task. Blank means use the global default ({{ globalModel }}).</p>

          <div v-for="group in pageGroups" :key="group.page" class="mb-5">
            <h3 class="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-1.5">
              <span class="inline-block w-1 h-4 rounded-full" :style="{ backgroundColor: group.color }"></span>
              {{ group.page }}
            </h3>

            <!-- Parent group with children (e.g. Studio → TODO / 项目管理) -->
            <div v-if="group.children" class="pl-4">
              <div v-for="child in group.children" :key="child.page" class="mb-4">
                <h4 class="text-xs font-semibold text-gray-500 mb-2 flex items-center gap-1.5">
                  <span class="inline-block w-1 h-3 rounded-full" :style="{ backgroundColor: child.color }"></span>
                  {{ child.page }}
                </h4>
                <div class="space-y-2 pl-4">
                  <div
                    v-for="callType in child.types"
                    :key="callType"
                    class="bg-white rounded-xl shadow-sm p-3 flex items-center justify-between gap-3"
                  >
                    <div class="flex-1 min-w-0">
                      <div class="text-sm font-medium text-gray-800">{{ callTypes[callType] }}</div>
                      <div class="text-xs text-gray-400">{{ callType }}</div>
                    </div>
                    <select
                      :value="defaults[callType] || ''"
                      @change="onModelChange(callType, $event.target.value)"
                      class="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-gray-50 text-gray-700 min-w-[140px] max-w-[200px]"
                    >
                      <option value="">Global Default</option>
                      <optgroup v-if="networkModels.length" label="Cloud">
                        <option v-for="m in networkModels" :key="m.name" :value="m.name">{{ m.name }}</option>
                      </optgroup>
                      <optgroup v-if="localModels.length" label="Local">
                        <option v-for="m in localModels" :key="m.name" :value="m.name">{{ m.name }}</option>
                      </optgroup>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            <!-- Leaf group with types directly -->
            <div v-else class="space-y-2 pl-4">
              <div
                v-for="callType in group.types"
                :key="callType"
                class="bg-white rounded-xl shadow-sm overflow-hidden"
              >
                <div class="p-3 flex items-center justify-between gap-3">
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-800 flex items-center gap-1.5">
                      {{ callTypes[callType] }}
                      <van-icon
                        v-if="callTypePrompts[callType]"
                        name="edit"
                        size="14"
                        class="text-gray-400 cursor-pointer hover:text-blue-500"
                        @click="toggleCallTypePrompt(callType)"
                      />
                    </div>
                    <div class="text-xs text-gray-400">{{ callType }}</div>
                  </div>
                  <select
                    :value="defaults[callType] || ''"
                    @change="onModelChange(callType, $event.target.value)"
                    class="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-gray-50 text-gray-700 min-w-[140px] max-w-[200px]"
                  >
                    <option value="">Global Default</option>
                    <optgroup v-if="networkModels.length" label="Cloud">
                      <option v-for="m in networkModels" :key="m.name" :value="m.name">{{ m.name }}</option>
                    </optgroup>
                    <optgroup v-if="localModels.length" label="Local">
                      <option v-for="m in localModels" :key="m.name" :value="m.name">{{ m.name }}</option>
                    </optgroup>
                  </select>
                </div>
                <!-- Expandable prompt editor for call types that support it -->
                <div v-if="callTypePrompts[callType] && expandedCallTypePrompts[callType]" class="border-t border-gray-100 px-3 pb-3 pt-2">
                  <div class="flex items-center justify-between mb-1.5">
                    <span class="text-xs text-gray-500">提示词模板</span>
                    <span
                      v-if="callTypePrompts[callType].prompt !== callTypePrompts[callType].default"
                      class="text-xs text-orange-500 cursor-pointer hover:text-orange-600"
                      @click="callTypePrompts[callType].prompt = callTypePrompts[callType].default"
                    >恢复默认</span>
                  </div>
                  <textarea
                    v-model="callTypePrompts[callType].prompt"
                    class="w-full text-xs text-gray-700 border border-gray-200 rounded-lg p-2 bg-gray-50 resize-y leading-relaxed"
                    rows="8"
                    placeholder="输入提示词模板..."
                  ></textarea>
                  <p class="text-xs text-gray-400 mt-1">{{ callTypePromptHints[callType] || '' }}</p>
                  <div class="mt-2 flex justify-end">
                    <van-button type="primary" size="small" :loading="savingCallTypePrompt === callType" @click="saveCallTypePrompt(callType)">Save</van-button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="mt-4 flex justify-end">
            <van-button type="primary" size="small" :loading="saving" @click="saveDefaults">Save</van-button>
          </div>
          </div>
        </div>


      </template>
    </div>

    <!-- Time Picker Popup (bottom for mobile thumb reach) -->
    <van-popup v-model:show="showTimePicker" position="bottom" round>
      <DrumTimePicker
        v-model:model-hour="timePickerHour"
        v-model:model-minute="timePickerMinute"
        title="选择执行时间"
        @confirm="onTimeConfirm(); showTimePicker = false"
        @cancel="showTimePicker = false"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { showToast } from 'vant'
import DrumTimePicker from '../components/DrumTimePicker.vue'
import MessageHubTab from '../components/MessageHubTab.vue'

// Group scheduler types by first-level page
const SCHEDULER_GROUPS = [
  {
    page: 'Studio',
    color: '#8B5CF6',
    children: [
      { page: 'TODO', color: '#8B5CF6', types: ['daily_todo_analysis', 'daily_duration_stats', 'repeat_todo_check', 'daily_todo_tag_organize'] },
      { page: '项目管理', color: '#10B981', types: ['daily_project_analysis'] },
    ],
  },
  {
    page: '灵感',
    color: '#F97316',
    types: ['daily_idea_aggregation'],
  },
  {
    page: '人才',
    color: '#3B82F6',
    types: ['daily_scheduled_queries', 'daily_tag_organize'],
  },
  {
    page: '手记',
    color: '#EC4899',
    types: ['daily_diary_comment'],
  },
  {
    page: '系统',
    color: '#6B7280',
    types: ['daily_backup'],
  },
]

// Group call types by first-level page
const PAGE_GROUPS = [
  {
    page: 'Studio',
    color: '#8B5CF6',
    children: [
      { page: 'TODO', color: '#8B5CF6', types: ['todo-auto-tag', 'todo-organize-tags', 'todo-analysis'] },
      { page: '项目管理', color: '#10B981', types: ['project-summary', 'project-update-parse'] },
    ],
  },
  {
    page: '灵感',
    color: '#F97316',
    types: ['idea-classify', 'idea-insight'],
  },
  {
    page: '人才',
    color: '#3B82F6',
    types: ['text-entry', 'pdf-parse', 'image-parse', 'semantic-search', 'chat-analyze', 'chat-answer', 'organize-tags', 'interview-evaluation'],
  },
  {
    page: '龙图阁',
    color: '#8B5CF6',
    types: ['scholar-categorize'],
  },
]

const loading = ref(true)
const saving = ref(false)
const callTypes = ref({})
const defaults = ref({})
const globalModel = ref('')
const availableModels = ref([])

// Scheduler config
const schedulerTypes = ref({})
const schedulerDescriptions = ref({})
const schedulers = ref({})
const schedulerInstructions = ref({})
const expandedPrompts = ref({})
const savingSchedulers = ref(false)
const showTimePicker = ref(false)
const timePickerHour = ref(8)
const timePickerMinute = ref(0)
const timePickerKey = ref(null)

// Call-type prompt editing (inline in model-defaults)
const callTypePrompts = ref({})  // { 'interview-evaluation': { prompt, default } }
const expandedCallTypePrompts = ref({})
const savingCallTypePrompt = ref(null)  // currently saving call type key
const CALL_TYPE_PROMPT_ENDPOINTS = {
  'interview-evaluation': '/api/entry/interview-evaluation/prompt',
}
const callTypePromptHints = {
  'interview-evaluation': '可用占位符：{talent_name} {talent_summary_line} {result} {rating} {rating_label} {records_text}',
}

const networkModels = computed(() => availableModels.value.filter(m => m.location === 'network'))
const localModels = computed(() => availableModels.value.filter(m => m.location === 'local'))

// Only show groups that have known call types from backend
const pageGroups = computed(() => {
  const known = Object.keys(callTypes.value)
  if (!known.length) return []
  const grouped = new Set()
  const result = PAGE_GROUPS
    .map(g => {
      if (g.children) {
        const children = g.children
          .map(c => {
            const types = c.types.filter(t => known.includes(t))
            types.forEach(t => grouped.add(t))
            return { ...c, types }
          })
          .filter(c => c.types.length > 0)
        return { ...g, children }
      }
      const types = g.types.filter(t => known.includes(t))
      types.forEach(t => grouped.add(t))
      return { ...g, types }
    })
    .filter(g => g.children ? g.children.length > 0 : g.types.length > 0)
  // Collect any ungrouped call types into a "其他" group
  const ungrouped = known.filter(t => !grouped.has(t))
  if (ungrouped.length) {
    result.push({ page: '其他', color: '#9ca3af', types: ungrouped })
  }
  return result
})

const schedulerGroups = computed(() => {
  const known = Object.keys(schedulerTypes.value)
  if (!known.length) return []
  const grouped = new Set()
  const result = SCHEDULER_GROUPS
    .map(g => {
      if (g.children) {
        const children = g.children
          .map(c => {
            const types = c.types.filter(t => known.includes(t))
            types.forEach(t => grouped.add(t))
            return { ...c, types }
          })
          .filter(c => c.types.length > 0)
        return { ...g, children }
      }
      const types = g.types.filter(t => known.includes(t))
      types.forEach(t => grouped.add(t))
      return { ...g, types }
    })
    .filter(g => g.children ? g.children.length > 0 : g.types.length > 0)
  const ungrouped = known.filter(t => !grouped.has(t))
  if (ungrouped.length) {
    result.push({ page: '其他', color: '#9ca3af', types: ungrouped })
  }
  return result
})

function formatTime(h, m) {
  return `${String(h ?? 0).padStart(2, '0')}:${String(m ?? 0).padStart(2, '0')}`
}

function openSchedulerTimePicker(key) {
  const cfg = schedulers.value[key] || {}
  timePickerHour.value = cfg.cron_hour ?? 0
  timePickerMinute.value = cfg.cron_minute ?? 0
  timePickerKey.value = key
  showTimePicker.value = true
}

function onTimeConfirm() {
  const key = timePickerKey.value
  if (!key || !schedulers.value[key]) return
  schedulers.value[key].cron_hour = timePickerHour.value
  schedulers.value[key].cron_minute = timePickerMinute.value
}

function togglePromptExpand(key) {
  expandedPrompts.value[key] = !expandedPrompts.value[key]
}

function resetPrompt(key) {
  if (schedulerInstructions.value[key]) {
    schedulerInstructions.value[key].prompt = schedulerInstructions.value[key].default
  }
}

function toggleCallTypePrompt(callType) {
  expandedCallTypePrompts.value[callType] = !expandedCallTypePrompts.value[callType]
}

async function saveCallTypePrompt(callType) {
  const endpoint = CALL_TYPE_PROMPT_ENDPOINTS[callType]
  if (!endpoint) return
  savingCallTypePrompt.value = callType
  try {
    await api.put(endpoint, { instructions: callTypePrompts.value[callType].prompt })
    showToast('Saved')
  } catch (e) {
    showToast('Save failed')
  } finally {
    savingCallTypePrompt.value = null
  }
}

onMounted(async () => {
  try {
    // Load call-type prompt data in parallel
    const promptRequests = Object.entries(CALL_TYPE_PROMPT_ENDPOINTS).map(
      ([key, url]) => api.get(url).then(res => [key, res.data]).catch(() => [key, null])
    )
    const [modelRes, schedulerRes, ...promptResults] = await Promise.all([
      api.get('/api/settings/model-defaults'),
      api.get('/api/settings/schedulers'),
      ...promptRequests,
    ])
    callTypes.value = modelRes.data.call_types
    defaults.value = { ...modelRes.data.defaults }
    globalModel.value = modelRes.data.global_model
    availableModels.value = modelRes.data.available_models
    schedulerTypes.value = schedulerRes.data.scheduler_types || {}
    schedulerDescriptions.value = schedulerRes.data.scheduler_descriptions || {}
    schedulers.value = JSON.parse(JSON.stringify(schedulerRes.data.schedulers || {}))
    schedulerInstructions.value = JSON.parse(JSON.stringify(schedulerRes.data.instructions || {}))
    // Populate call-type prompts
    for (const [key, data] of promptResults) {
      if (data) {
        callTypePrompts.value[key] = {
          prompt: data.instructions || '',
          default: data.default || '',
        }
      }
    }
  } catch (e) {
    showToast('Failed to load settings')
  } finally {
    loading.value = false
  }
})

function onModelChange(callType, value) {
  if (value) {
    defaults.value[callType] = value
  } else {
    delete defaults.value[callType]
  }
}

async function saveDefaults() {
  saving.value = true
  try {
    const res = await api.put('/api/settings/model-defaults', { defaults: defaults.value })
    defaults.value = { ...res.data.defaults }
    showToast('Saved')
  } catch (e) {
    showToast('Save failed')
  } finally {
    saving.value = false
  }
}

async function saveSchedulers() {
  savingSchedulers.value = true
  try {
    const res = await api.put('/api/settings/schedulers', {
      schedulers: JSON.parse(JSON.stringify(schedulers.value)),
      instructions: JSON.parse(JSON.stringify(schedulerInstructions.value)),
    })
    schedulers.value = JSON.parse(JSON.stringify(res.data.schedulers || {}))
    showToast('Saved')
  } catch (e) {
    showToast('Save failed')
  } finally {
    savingSchedulers.value = false
  }
}
</script>

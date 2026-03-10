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
          <h2 class="text-sm font-bold text-gray-600 mb-1 flex items-center gap-1.5">
            <span class="inline-block w-1 h-4 rounded-full bg-emerald-500"></span>
            定时任务
          </h2>
          <p class="text-xs text-gray-400 mb-3">配置各定时任务的执行时间，修改后即时生效</p>

          <div class="space-y-2">
            <div
              v-for="(label, key) in schedulerTypes"
              :key="key"
              class="bg-white rounded-xl shadow-sm p-3 flex items-center justify-between gap-3"
            >
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-gray-800">{{ label }}</div>
                <div class="text-xs text-gray-400">{{ schedulerDescriptions[key] || key }}</div>
              </div>
              <!-- Interval type -->
              <template v-if="schedulers[key]?.interval_hours !== undefined">
                <div class="flex items-center gap-1">
                  <span class="text-xs text-gray-500">每</span>
                  <input
                    type="number"
                    :value="schedulers[key].interval_hours"
                    @change="schedulers[key].interval_hours = Math.max(1, Number($event.target.value) || 1)"
                    class="w-14 text-sm text-center border border-gray-200 rounded-lg px-1 py-1.5 bg-gray-50"
                    min="1"
                    max="24"
                  />
                  <span class="text-xs text-gray-500">小时</span>
                </div>
              </template>
              <!-- Cron type -->
              <template v-else>
                <span
                  class="text-sm text-blue-500 cursor-pointer hover:text-blue-700 font-mono bg-blue-50 px-2 py-1 rounded"
                  @click="openSchedulerTimePicker(key)"
                >{{ formatTime(schedulers[key]?.cron_hour, schedulers[key]?.cron_minute) }}</span>
              </template>
            </div>
          </div>

          <div class="mt-4 flex justify-end">
            <van-button type="primary" size="small" :loading="savingSchedulers" @click="saveSchedulers">Save</van-button>
          </div>
        </div>

        <!-- 企微推送设置 -->
        <div class="mb-6">
          <h2 class="text-sm font-bold text-gray-600 mb-1 flex items-center gap-1.5">
            <span class="inline-block w-1 h-4 rounded-full bg-amber-500"></span>
            企微推送
          </h2>
          <p class="text-xs text-gray-400 mb-3">管理推送机器人及订阅功能</p>
          <MessageHubTab />
        </div>

        <!-- Model Defaults -->
        <div class="mb-4">
          <h2 class="text-sm font-bold text-gray-600 mb-1 flex items-center gap-1.5">
            <span class="inline-block w-1 h-4 rounded-full bg-violet-500"></span>
            模型配置
          </h2>
          <p class="text-xs text-gray-400 mb-3">Choose a model for each task. Blank means use the global default ({{ globalModel }}).</p>

          <div v-for="group in pageGroups" :key="group.page" class="mb-5">
            <h3 class="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-1.5">
              <span class="inline-block w-1 h-4 rounded-full" :style="{ backgroundColor: group.color }"></span>
              {{ group.page }}
            </h3>
            <div class="space-y-2">
              <div
                v-for="callType in group.types"
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

          <div class="mt-4 flex justify-end">
            <van-button type="primary" size="small" :loading="saving" @click="saveDefaults">Save</van-button>
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

// Group call types by first-level page
const PAGE_GROUPS = [
  {
    page: 'Studio',
    color: '#8B5CF6',
    types: ['todo-auto-tag', 'todo-organize-tags', 'todo-analysis'],
  },
  {
    page: '灵感',
    color: '#F97316',
    types: ['idea-classify', 'idea-insight'],
  },
  {
    page: '人才卡',
    color: '#3B82F6',
    types: ['text-entry', 'pdf-parse', 'image-parse', 'semantic-search', 'chat-analyze', 'chat-answer', 'organize-tags'],
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
const savingSchedulers = ref(false)
const showTimePicker = ref(false)
const timePickerHour = ref(8)
const timePickerMinute = ref(0)
const timePickerKey = ref(null)

const networkModels = computed(() => availableModels.value.filter(m => m.location === 'network'))
const localModels = computed(() => availableModels.value.filter(m => m.location === 'local'))

// Only show groups that have known call types from backend
const pageGroups = computed(() => {
  const known = Object.keys(callTypes.value)
  if (!known.length) return []
  const grouped = new Set()
  const result = PAGE_GROUPS
    .map(g => {
      const types = g.types.filter(t => known.includes(t))
      types.forEach(t => grouped.add(t))
      return { ...g, types }
    })
    .filter(g => g.types.length > 0)
  // Collect any ungrouped call types into a "其他" group
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

onMounted(async () => {
  try {
    const [modelRes, schedulerRes] = await Promise.all([
      api.get('/api/settings/model-defaults'),
      api.get('/api/settings/schedulers'),
    ])
    callTypes.value = modelRes.data.call_types
    defaults.value = { ...modelRes.data.defaults }
    globalModel.value = modelRes.data.global_model
    availableModels.value = modelRes.data.available_models
    schedulerTypes.value = schedulerRes.data.scheduler_types || {}
    schedulerDescriptions.value = schedulerRes.data.scheduler_descriptions || {}
    schedulers.value = JSON.parse(JSON.stringify(schedulerRes.data.schedulers || {}))
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
    const res = await api.put('/api/settings/schedulers', { schedulers: JSON.parse(JSON.stringify(schedulers.value)) })
    schedulers.value = JSON.parse(JSON.stringify(res.data.schedulers || {}))
    showToast('Saved')
  } catch (e) {
    showToast('Save failed')
  } finally {
    savingSchedulers.value = false
  }
}
</script>

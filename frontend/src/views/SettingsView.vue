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
        <!-- Model Defaults -->
        <div class="mb-4">
          <p class="text-xs text-gray-400 mb-4">Choose a model for each task. Blank means use the global default ({{ globalModel }}).</p>

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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { showToast } from 'vant'

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

onMounted(async () => {
  try {
    const res = await api.get('/api/settings/model-defaults')
    callTypes.value = res.data.call_types
    defaults.value = { ...res.data.defaults }
    globalModel.value = res.data.global_model
    availableModels.value = res.data.available_models
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
</script>

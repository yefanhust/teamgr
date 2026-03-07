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
        <div class="mb-6">
          <h2 class="text-sm font-semibold text-gray-500 mb-1">Default Model per Task</h2>
          <p class="text-xs text-gray-400 mb-3">Choose a model for each task. Blank means use the global default ({{ globalModel }}).</p>

          <div class="space-y-2">
            <div
              v-for="(label, callType) in callTypes"
              :key="callType"
              class="bg-white rounded-xl shadow-sm p-3 flex items-center justify-between gap-3"
            >
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-gray-800">{{ label }}</div>
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

const loading = ref(true)
const saving = ref(false)
const callTypes = ref({})
const defaults = ref({})
const globalModel = ref('')
const availableModels = ref([])

const networkModels = computed(() => availableModels.value.filter(m => m.location === 'network'))
const localModels = computed(() => availableModels.value.filter(m => m.location === 'local'))

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

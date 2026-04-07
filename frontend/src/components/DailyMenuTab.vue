<template>
  <div class="max-w-3xl mx-auto px-4 py-4 space-y-4">
    <!-- Date navigation -->
    <div class="flex items-center justify-between bg-white rounded-lg px-4 py-3 shadow-sm">
      <van-icon name="arrow-left" size="20" class="cursor-pointer text-gray-500" @click="prevDay" />
      <div class="text-center cursor-pointer" @click="showDatePicker = true">
        <div class="text-base font-bold">{{ displayDate }}</div>
        <div class="text-xs text-gray-400">{{ displayWeekday }}</div>
      </div>
      <van-icon name="arrow" size="20" class="cursor-pointer text-gray-500" @click="nextDay" />
    </div>

    <!-- Actions bar -->
    <div class="flex gap-2">
      <van-button
        size="small"
        type="primary"
        icon="plus"
        :loading="generating"
        @click="generateMenu"
      >
        {{ currentMenu ? '重新生成' : '生成菜谱' }}
      </van-button>
      <van-button
        v-if="currentMenu"
        size="small"
        icon="bullhorn-o"
        :loading="pushing"
        @click="pushMenu"
      >
        推送到 Bark
      </van-button>
      <van-button size="small" icon="setting-o" @click="showSettings = true">
        设置
      </van-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <van-loading size="24" vertical>加载中...</van-loading>
    </div>

    <!-- Generating -->
    <div v-else-if="generating" class="text-center py-12">
      <van-loading size="24" vertical>AI 正在生成菜谱...</van-loading>
    </div>

    <!-- No menu -->
    <div v-else-if="!currentMenu" class="text-center py-12">
      <van-empty description="暂无菜谱，点击上方按钮生成" />
    </div>

    <!-- Menu display -->
    <template v-else>
      <!-- Baby meals -->
      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <div class="px-4 py-3 bg-orange-50 border-b border-orange-100">
          <span class="text-sm font-bold text-orange-700">宝宝餐</span>
        </div>
        <div v-for="meal in babyMeals" :key="meal.meal_type" class="border-b border-gray-50 last:border-0">
          <div class="px-4 py-2 bg-gray-50 text-xs font-medium text-gray-500">{{ meal.meal_type }}</div>
          <div v-for="(dish, idx) in meal.dishes" :key="idx" class="px-4 py-3">
            <div class="flex items-start justify-between cursor-pointer" @click="toggleDish('baby', meal.meal_type, idx)">
              <div class="font-medium text-sm">{{ dish.name }}</div>
              <van-icon
                :name="isDishExpanded('baby', meal.meal_type, idx) ? 'arrow-up' : 'arrow-down'"
                size="14"
                class="text-gray-400 mt-0.5 flex-shrink-0"
              />
            </div>
            <div v-if="isDishExpanded('baby', meal.meal_type, idx)" class="mt-2 space-y-2">
              <div v-if="dish.ingredients && dish.ingredients.length" class="text-xs text-gray-500">
                <span class="font-medium text-gray-600">食材：</span>{{ dish.ingredients.join('、') }}
              </div>
              <div v-if="dish.steps && dish.steps.length" class="text-xs text-gray-500 space-y-1">
                <div class="font-medium text-gray-600">做法：</div>
                <div v-for="(step, si) in dish.steps" :key="si" class="pl-2">{{ si + 1 }}. {{ step }}</div>
              </div>
              <div v-if="dish.tips" class="text-xs text-orange-600 bg-orange-50 rounded px-2 py-1">
                {{ dish.tips }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Adult meals -->
      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <div class="px-4 py-3 bg-blue-50 border-b border-blue-100">
          <span class="text-sm font-bold text-blue-700">大人餐</span>
          <span class="text-xs text-blue-400 ml-2">{{ currentMenu.adult_count }}人份</span>
        </div>
        <div v-for="meal in adultMeals" :key="meal.meal_type" class="border-b border-gray-50 last:border-0">
          <div class="px-4 py-2 bg-gray-50 text-xs font-medium text-gray-500">{{ meal.meal_type }}</div>
          <div v-for="(dish, idx) in meal.dishes" :key="idx" class="px-4 py-3">
            <div class="flex items-start justify-between cursor-pointer" @click="toggleDish('adult', meal.meal_type, idx)">
              <div class="font-medium text-sm">{{ dish.name }}</div>
              <van-icon
                :name="isDishExpanded('adult', meal.meal_type, idx) ? 'arrow-up' : 'arrow-down'"
                size="14"
                class="text-gray-400 mt-0.5 flex-shrink-0"
              />
            </div>
            <div v-if="isDishExpanded('adult', meal.meal_type, idx)" class="mt-2 space-y-2">
              <div v-if="dish.ingredients && dish.ingredients.length" class="text-xs text-gray-500">
                <span class="font-medium text-gray-600">食材：</span>{{ dish.ingredients.join('、') }}
              </div>
              <div v-if="dish.steps && dish.steps.length" class="text-xs text-gray-500 space-y-1">
                <div class="font-medium text-gray-600">做法：</div>
                <div v-for="(step, si) in dish.steps" :key="si" class="pl-2">{{ si + 1 }}. {{ step }}</div>
              </div>
              <div v-if="dish.tips" class="text-xs text-blue-600 bg-blue-50 rounded px-2 py-1">
                {{ dish.tips }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Shopping list -->
      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <div class="px-4 py-3 bg-green-50 border-b border-green-100 flex items-center justify-between">
          <span class="text-sm font-bold text-green-700">购物清单</span>
          <van-button size="mini" icon="records" @click="copyShoppingList">复制</van-button>
        </div>
        <div v-for="cat in shoppingList" :key="cat.category" class="px-4 py-2 border-b border-gray-50 last:border-0">
          <div class="text-xs font-medium text-gray-600 mb-1">{{ cat.category }}</div>
          <div class="flex flex-wrap gap-1">
            <span v-for="item in cat.items" :key="item" class="text-xs bg-gray-100 text-gray-600 rounded px-2 py-0.5">
              {{ item }}
            </span>
          </div>
        </div>
      </div>

      <!-- Meta info -->
      <div class="text-xs text-gray-400 text-center pb-4">
        生成于 {{ formatTime(currentMenu.created_at) }}
        <span v-if="currentMenu.model_name">· {{ currentMenu.model_name }}</span>
      </div>
    </template>

    <!-- Date calendar popup -->
    <van-calendar
      v-model:show="showDatePicker"
      :min-date="minDate"
      :max-date="maxDate"
      :default-date="currentDate"
      :show-confirm="false"
      @confirm="onDateConfirm"
    />

    <!-- Settings popup -->
    <van-popup v-model:show="showSettings" position="bottom" round :style="{ maxHeight: '85vh' }">
      <div class="px-4 py-4 space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-base font-bold">御膳房设置</span>
          <van-icon name="cross" size="20" class="cursor-pointer" @click="showSettings = false" />
        </div>

        <!-- Adult count -->
        <div>
          <div class="text-sm font-medium text-gray-700 mb-2">大人数量</div>
          <van-stepper v-model="settingsForm.adult_count" :min="1" :max="10" integer />
        </div>

        <!-- Scheduler time -->
        <div>
          <div class="text-sm font-medium text-gray-700 mb-2">每日自动生成时间</div>
          <div class="flex items-center gap-2">
            <van-stepper v-model="settingsForm.scheduler.cron_hour" :min="0" :max="23" integer />
            <span class="text-gray-500">时</span>
            <van-stepper v-model="settingsForm.scheduler.cron_minute" :min="0" :max="59" integer />
            <span class="text-gray-500">分</span>
          </div>
          <div class="text-xs text-gray-400 mt-1">每天此时间自动生成次日菜谱并推送</div>
        </div>

        <!-- Model selection -->
        <div>
          <div class="text-sm font-medium text-gray-700 mb-2">生成模型</div>
          <select v-model="settingsForm.model" class="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
            <option value="">跟随全局设置</option>
            <option v-for="m in availableModels" :key="m.name" :value="m.name">
              {{ m.name }}{{ m.location === 'local' ? ' (本地)' : '' }}
            </option>
          </select>
        </div>

        <!-- Bark settings -->
        <div class="space-y-3">
          <div class="text-sm font-medium text-gray-700">Bark 推送设置</div>

          <div class="flex items-center justify-between">
            <span class="text-sm text-gray-600">启用 Bark 推送</span>
            <van-switch v-model="settingsForm.bark.enabled" size="20" />
          </div>

          <van-field
            v-model="settingsForm.bark.server_url"
            label="服务器"
            placeholder="https://api.day.app"
            label-width="60"
            size="small"
          />

          <!-- Device list -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-xs text-gray-500">推送设备（{{ settingsForm.bark.devices.length }}）</span>
              <van-button size="mini" icon="plus" @click="addBarkDevice">添加设备</van-button>
            </div>
            <div v-for="(device, idx) in settingsForm.bark.devices" :key="idx" class="flex gap-2 items-start bg-gray-50 rounded-lg p-2">
              <div class="flex-1 space-y-1">
                <van-field
                  v-model="device.name"
                  placeholder="设备名称（如：我的 iPhone）"
                  size="small"
                  :border="false"
                  class="!bg-white rounded"
                />
                <van-field
                  v-model="device.key"
                  placeholder="Bark Device Key"
                  size="small"
                  :border="false"
                  class="!bg-white rounded"
                />
              </div>
              <van-icon name="delete-o" size="18" class="text-gray-400 cursor-pointer mt-2 flex-shrink-0" @click="removeBarkDevice(idx)" />
            </div>
            <div v-if="!settingsForm.bark.devices.length" class="text-xs text-gray-400 text-center py-2">
              暂无设备，点击「添加设备」开始配置
            </div>
          </div>

          <van-button
            size="small"
            type="default"
            icon="bullhorn-o"
            :loading="testingBark"
            :disabled="!settingsForm.bark.devices.some(d => d.key)"
            @click="testBarkPush"
          >
            测试推送（全部设备）
          </van-button>

          <!-- Bark setup guide -->
          <div class="bg-gray-50 rounded-lg p-3 text-xs text-gray-500 space-y-1">
            <div class="font-medium text-gray-600 mb-1">Bark 设置步骤：</div>
            <div>1. 在 iOS App Store 搜索并下载「Bark」App</div>
            <div>2. 打开 Bark App，首页显示推送 URL</div>
            <div class="pl-3 text-gray-400">格式: https://api.day.app/YOUR_KEY/</div>
            <div>3. 复制 URL 中 api.day.app/ 后面的那串字符，即为 Device Key</div>
            <div>4. 点击「添加设备」，填入设备名称和 Key</div>
            <div>5. 可添加多个设备，每人手机装 Bark 后各自获取 Key</div>
            <div>6. 点击「测试推送」验证所有设备是否收到通知</div>
            <div class="mt-1 text-gray-400">* 如使用自建 Bark 服务器，请修改上方服务器地址</div>
          </div>
        </div>

        <van-button type="primary" block :loading="savingSettings" @click="saveSettings">
          保存设置
        </van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { showToast } from 'vant'
import api from '../api'

// State
const loading = ref(false)
const generating = ref(false)
const pushing = ref(false)
const currentMenu = ref(null)
const currentDate = ref(new Date())
const expandedDishes = ref(new Set())

// Date calendar
const showDatePicker = ref(false)
const minDate = new Date(2024, 0, 1)
const maxDate = new Date(2027, 11, 31)

// Settings
const showSettings = ref(false)
const savingSettings = ref(false)
const testingBark = ref(false)
const settingsForm = ref({
  adult_count: 1,
  bark: {
    enabled: false,
    server_url: 'https://api.day.app',
    devices: [],  // [{name, key}]
  },
  scheduler: { cron_hour: 20, cron_minute: 0 },
  model: '',
})
const availableModels = ref([])

// Computed
const displayDate = computed(() => {
  const d = currentDate.value
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
})

const displayWeekday = computed(() => {
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return weekdays[currentDate.value.getDay()]
})

const babyMeals = computed(() => currentMenu.value?.menu_data?.baby_meals || [])
const adultMeals = computed(() => currentMenu.value?.menu_data?.adult_meals || [])
const shoppingList = computed(() => currentMenu.value?.menu_data?.shopping_list || [])

// Methods
function dateToStr(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${dd}`
}

function prevDay() {
  const d = new Date(currentDate.value)
  d.setDate(d.getDate() - 1)
  currentDate.value = d
}

function nextDay() {
  const d = new Date(currentDate.value)
  d.setDate(d.getDate() + 1)
  currentDate.value = d
}

function onDateConfirm(date) {
  currentDate.value = date
  showDatePicker.value = false
}

function toggleDish(section, mealType, idx) {
  const key = `${section}-${mealType}-${idx}`
  const s = new Set(expandedDishes.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedDishes.value = s
}

function isDishExpanded(section, mealType, idx) {
  return expandedDishes.value.has(`${section}-${mealType}-${idx}`)
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function loadMenu() {
  loading.value = true
  try {
    const res = await api.get('/api/kitchen/daily-menu', { params: { date: dateToStr(currentDate.value) } })
    currentMenu.value = res.data.menu
    expandedDishes.value = new Set()
  } catch (e) {
    showToast({ message: '加载失败', type: 'fail' })
  } finally {
    loading.value = false
  }
}

async function generateMenu() {
  generating.value = true
  try {
    const res = await api.post('/api/kitchen/daily-menu/generate', {
      date: dateToStr(currentDate.value),
    })
    currentMenu.value = res.data.menu
    expandedDishes.value = new Set()
    showToast({ message: '菜谱生成成功', type: 'success' })
  } catch (e) {
    const msg = e.response?.data?.detail || '生成失败'
    showToast({ message: msg, type: 'fail' })
  } finally {
    generating.value = false
  }
}

async function pushMenu() {
  if (!currentMenu.value) return
  pushing.value = true
  try {
    await api.post(`/api/kitchen/daily-menu/${currentMenu.value.id}/push`)
    showToast({ message: '推送成功', type: 'success' })
  } catch (e) {
    const msg = e.response?.data?.detail || '推送失败'
    showToast({ message: msg, type: 'fail' })
  } finally {
    pushing.value = false
  }
}

function copyShoppingList() {
  if (!shoppingList.value.length) return
  const text = shoppingList.value.map(cat => {
    return `【${cat.category}】${cat.items.join('、')}`
  }).join('\n')
  navigator.clipboard.writeText(text).then(() => {
    showToast({ message: '已复制', type: 'success' })
  }).catch(() => {
    showToast({ message: '复制失败', type: 'fail' })
  })
}

async function loadSettings() {
  try {
    const res = await api.get('/api/kitchen/settings')
    const { settings: s, scheduler, model, available_models } = res.data
    settingsForm.value.adult_count = s.adult_count || 1
    // Migrate old single device_key to devices array
    let devices = s.bark?.devices || []
    if (!devices.length && s.bark?.device_key) {
      devices = [{ name: '默认设备', key: s.bark.device_key }]
    }
    settingsForm.value.bark = {
      enabled: s.bark?.enabled || false,
      server_url: s.bark?.server_url || 'https://api.day.app',
      devices,
    }
    settingsForm.value.scheduler = {
      cron_hour: scheduler?.cron_hour ?? 20,
      cron_minute: scheduler?.cron_minute ?? 0,
    }
    settingsForm.value.model = model || ''
    if (available_models) availableModels.value = available_models
  } catch (e) {
    // ignore - use defaults
  }
}

function addBarkDevice() {
  settingsForm.value.bark.devices.push({ name: '', key: '' })
}

function removeBarkDevice(idx) {
  settingsForm.value.bark.devices.splice(idx, 1)
}

async function saveSettings() {
  savingSettings.value = true
  try {
    await api.put('/api/kitchen/settings', settingsForm.value)
    showToast({ message: '设置已保存', type: 'success' })
    showSettings.value = false
  } catch (e) {
    showToast({ message: '保存失败', type: 'fail' })
  } finally {
    savingSettings.value = false
  }
}

async function testBarkPush() {
  // Save settings first, then test
  testingBark.value = true
  try {
    await api.put('/api/kitchen/settings', settingsForm.value)
    await api.post('/api/kitchen/daily-menu/push-test')
    showToast({ message: '测试推送已发送', type: 'success' })
  } catch (e) {
    const msg = e.response?.data?.detail || '测试失败'
    showToast({ message: msg, type: 'fail' })
  } finally {
    testingBark.value = false
  }
}

// Watch date change
watch(currentDate, () => {
  loadMenu()
})

onMounted(() => {
  loadMenu()
  loadSettings()
})
</script>

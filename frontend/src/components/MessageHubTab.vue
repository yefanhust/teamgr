<template>
  <div class="max-w-3xl mx-auto px-4 py-4">
    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-12">
      <van-loading size="36px">加载中...</van-loading>
    </div>

    <template v-else>
      <!-- Group bots by channel -->
      <div v-for="(group, channel) in botsByChannel" :key="channel" class="mb-6">
        <h3 class="text-sm font-bold text-gray-500 mb-3 flex items-center gap-1.5">
          <span class="inline-block w-1 h-4 rounded-full bg-amber-500"></span>
          {{ channelLabels[channel] || channel }}
        </h3>

        <!-- Bot cards -->
        <div v-for="bot in group" :key="bot.id" class="bg-white rounded-xl shadow-sm mb-4 overflow-hidden">
          <!-- Bot header -->
          <div class="px-4 py-3 flex items-center justify-between border-b border-gray-100">
            <div class="flex items-center gap-2 flex-1 min-w-0">
              <span class="text-lg">🤖</span>
              <!-- Editable name -->
              <input
                v-if="editingBotId === bot.id"
                v-model="editingBotName"
                class="text-sm font-bold text-gray-800 border-b border-blue-400 outline-none bg-transparent px-0.5"
                @blur="finishEditBotName(bot)"
                @keypress.enter="finishEditBotName(bot)"
                @keydown.escape="editingBotId = null"
                ref="botNameInput"
              />
              <span
                v-else
                class="text-sm font-bold text-gray-800 cursor-pointer hover:text-blue-600"
                @click="startEditBotName(bot)"
              >{{ bot.name }}</span>
              <span class="text-xs text-gray-400 truncate">{{ bot.webhook_url_masked }}</span>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <van-switch
                :model-value="bot.enabled"
                size="18px"
                @update:model-value="toggleBot(bot, $event)"
              />
              <van-icon
                name="delete-o"
                size="16"
                class="text-gray-400 cursor-pointer hover:text-red-500"
                @click="confirmDeleteBot(bot)"
              />
            </div>
          </div>

          <!-- Bot body -->
          <div class="px-4 py-3">
            <!-- Custom message input -->
            <div class="flex gap-2 mb-3">
              <input
                v-model="customMessages[bot.id]"
                type="text"
                placeholder="输入自定义消息..."
                class="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-blue-400"
                @keypress.enter="sendCustomMessage(bot)"
              />
              <van-button
                type="primary"
                size="small"
                :loading="sendingCustom[bot.id]"
                :disabled="!customMessages[bot.id]?.trim()"
                @click="sendCustomMessage(bot)"
              >发送</van-button>
            </div>

            <!-- Subscribed functions -->
            <div v-if="bot.functions?.length" class="mb-3">
              <div class="text-xs text-gray-400 mb-2">已订阅功能：</div>
              <div class="space-y-2">
                <div
                  v-for="func in bot.functions"
                  :key="func.trigger"
                  class="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2"
                >
                  <div class="flex items-center gap-2 flex-1 min-w-0">
                    <span class="text-sm text-gray-700">{{ triggerTypes[func.trigger] || func.trigger }}</span>
                    <span
                      class="text-xs text-blue-500 cursor-pointer hover:text-blue-700 font-mono bg-blue-50 px-1.5 py-0.5 rounded"
                      @click="startEditTime(bot, func)"
                    >{{ formatTime(func.cron_hour, func.cron_minute) }}</span>
                  </div>
                  <div class="flex items-center gap-1.5 flex-shrink-0">
                    <van-button
                      size="mini"
                      :loading="testingTrigger[bot.id + '_' + func.trigger]"
                      @click="testTrigger(bot, func.trigger)"
                    >测试</van-button>
                    <van-icon
                      name="cross"
                      size="14"
                      class="text-gray-400 cursor-pointer hover:text-red-500"
                      @click="confirmDeleteFunction(bot, func.trigger)"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- Add function button -->
            <div class="flex justify-center">
              <van-button
                size="small"
                icon="plus"
                plain
                :disabled="getAvailableTriggers(bot).length === 0"
                @click="showAddFunction(bot)"
              >添加功能</van-button>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="bots.length === 0" class="text-center py-12 text-gray-400">
        <div class="text-4xl mb-3">📡</div>
        <p class="text-sm">暂无推送机器人</p>
        <p class="text-xs mt-1">点击下方按钮添加</p>
      </div>

      <!-- Add bot button -->
      <div class="flex justify-center mt-4 mb-8">
        <van-button
          type="primary"
          plain
          icon="plus"
          size="small"
          @click="showAddBot = true"
        >添加机器人</van-button>
      </div>
    </template>

    <!-- Add Bot Dialog -->
    <van-dialog
      v-model:show="showAddBot"
      title="添加机器人"
      show-cancel-button
      :before-close="onAddBotClose"
    >
      <div class="px-6 py-4 space-y-3">
        <div>
          <label class="text-xs text-gray-500 mb-1 block">名称</label>
          <input
            v-model="newBotName"
            type="text"
            placeholder="如：工作通知"
            class="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-blue-400"
          />
        </div>
        <div>
          <label class="text-xs text-gray-500 mb-1 block">渠道</label>
          <select
            v-model="newBotChannel"
            class="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white"
          >
            <option value="wecom">企微</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-500 mb-1 block">Webhook URL</label>
          <input
            v-model="newBotWebhook"
            type="text"
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
            class="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-blue-400"
          />
        </div>
      </div>
    </van-dialog>

    <!-- Add Function Action Sheet -->
    <van-action-sheet
      v-model:show="showFunctionSheet"
      :actions="functionSheetActions"
      cancel-text="取消"
      @select="onSelectFunction"
    />

    <!-- Time Picker Dialog -->
    <van-dialog
      v-model:show="showTimePicker"
      title="选择推送时间"
      show-cancel-button
      @confirm="onTimeDialogConfirm"
    >
      <div class="time-picker-container">
        <!-- Hour column -->
        <div class="time-column">
          <div
            class="time-drum"
            @wheel.prevent="timePickerHour = wrapInt(timePickerHour + ($event.deltaY < 0 ? 1 : -1), 0, 23)"
            @touchstart.prevent="onTouchStart($event, 'hour')"
            @touchmove.prevent="onTouchMove($event, 'hour')"
            @touchend="onTouchEnd"
          >
            <span class="drum-item drum-far" @click="timePickerHour = wrapInt(timePickerHour + 2, 0, 23)">
              {{ String(wrapInt(timePickerHour + 2, 0, 23)).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-near" @click="timePickerHour = wrapInt(timePickerHour + 1, 0, 23)">
              {{ String(wrapInt(timePickerHour + 1, 0, 23)).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-active" @click="focusTimeInput('hour')">
              {{ String(timePickerHour).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-near" @click="timePickerHour = wrapInt(timePickerHour - 1, 0, 23)">
              {{ String(wrapInt(timePickerHour - 1, 0, 23)).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-far" @click="timePickerHour = wrapInt(timePickerHour - 2, 0, 23)">
              {{ String(wrapInt(timePickerHour - 2, 0, 23)).padStart(2, '0') }}
            </span>
            <!-- Highlight band -->
            <div class="drum-highlight"></div>
            <!-- Fade overlays -->
            <div class="drum-fade-top"></div>
            <div class="drum-fade-bottom"></div>
          </div>
          <span class="time-label">时</span>
        </div>

        <span class="time-separator">:</span>

        <!-- Minute column -->
        <div class="time-column">
          <div
            class="time-drum"
            @wheel.prevent="timePickerMinute = wrapInt(timePickerMinute + ($event.deltaY < 0 ? 1 : -1), 0, 59)"
            @touchstart.prevent="onTouchStart($event, 'minute')"
            @touchmove.prevent="onTouchMove($event, 'minute')"
            @touchend="onTouchEnd"
          >
            <span class="drum-item drum-far" @click="timePickerMinute = wrapInt(timePickerMinute + 2, 0, 59)">
              {{ String(wrapInt(timePickerMinute + 2, 0, 59)).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-near" @click="timePickerMinute = wrapInt(timePickerMinute + 1, 0, 59)">
              {{ String(wrapInt(timePickerMinute + 1, 0, 59)).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-active" @click="focusTimeInput('minute')">
              {{ String(timePickerMinute).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-near" @click="timePickerMinute = wrapInt(timePickerMinute - 1, 0, 59)">
              {{ String(wrapInt(timePickerMinute - 1, 0, 59)).padStart(2, '0') }}
            </span>
            <span class="drum-item drum-far" @click="timePickerMinute = wrapInt(timePickerMinute - 2, 0, 59)">
              {{ String(wrapInt(timePickerMinute - 2, 0, 59)).padStart(2, '0') }}
            </span>
            <div class="drum-highlight"></div>
            <div class="drum-fade-top"></div>
            <div class="drum-fade-bottom"></div>
          </div>
          <span class="time-label">分</span>
        </div>
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '../api'
import { showToast, showConfirmDialog } from 'vant'

const channelLabels = { wecom: '企微' }

const loading = ref(true)
const bots = ref([])
const triggerTypes = ref({})

// Custom messages per bot
const customMessages = ref({})
const sendingCustom = ref({})

// Testing triggers
const testingTrigger = ref({})

// Bot editing
const editingBotId = ref(null)
const editingBotName = ref('')
const botNameInput = ref(null)

// Add bot dialog
const showAddBot = ref(false)
const newBotName = ref('')
const newBotChannel = ref('wecom')
const newBotWebhook = ref('')

// Add function sheet
const showFunctionSheet = ref(false)
const currentBotForFunction = ref(null)

// Time picker
const showTimePicker = ref(false)
const timePickerHour = ref(8)
const timePickerMinute = ref(0)
const timePickerContext = ref(null) // { bot, trigger, isNew }

function clampInt(val, min, max) {
  const n = parseInt(val, 10)
  if (isNaN(n)) return min
  return Math.min(max, Math.max(min, n))
}

function wrapInt(val, min, max) {
  const range = max - min + 1
  return ((((val - min) % range) + range) % range) + min
}

// Touch swipe support for mobile time picker
const touchStartY = ref(0)
const touchAccum = ref(0)
const TOUCH_THRESHOLD = 30 // pixels per step

function onTouchStart(e, _field) {
  touchStartY.value = e.touches[0].clientY
  touchAccum.value = 0
}

function onTouchMove(e, field) {
  const dy = touchStartY.value - e.touches[0].clientY
  const accumulated = touchAccum.value + dy
  const steps = Math.trunc(accumulated / TOUCH_THRESHOLD)
  if (steps !== 0) {
    if (field === 'hour') {
      timePickerHour.value = wrapInt(timePickerHour.value + steps, 0, 23)
    } else {
      timePickerMinute.value = wrapInt(timePickerMinute.value + steps, 0, 59)
    }
    touchAccum.value = accumulated - steps * TOUCH_THRESHOLD
  } else {
    touchAccum.value = accumulated
  }
  touchStartY.value = e.touches[0].clientY
}

function onTouchEnd() {
  touchAccum.value = 0
}

// Tap to edit via prompt (mobile-friendly alternative to text input)
function focusTimeInput(field) {
  const current = field === 'hour' ? timePickerHour.value : timePickerMinute.value
  const max = field === 'hour' ? 23 : 59
  const label = field === 'hour' ? '时 (0-23)' : '分 (0-59)'
  const val = prompt(`输入${label}`, String(current))
  if (val !== null && val.trim() !== '') {
    if (field === 'hour') {
      timePickerHour.value = clampInt(val, 0, max)
    } else {
      timePickerMinute.value = clampInt(val, 0, max)
    }
  }
}

// Computed: group bots by channel
const botsByChannel = computed(() => {
  const groups = {}
  for (const bot of bots.value) {
    const ch = bot.channel || 'wecom'
    if (!groups[ch]) groups[ch] = []
    groups[ch].push(bot)
  }
  return groups
})

// Computed: available triggers for a bot (not yet subscribed)
function getAvailableTriggers(bot) {
  const subscribed = new Set((bot.functions || []).map(f => f.trigger))
  return Object.entries(triggerTypes.value)
    .filter(([key]) => !subscribed.has(key))
    .map(([key, label]) => ({ key, label }))
}

const functionSheetActions = computed(() => {
  if (!currentBotForFunction.value) return []
  return getAvailableTriggers(currentBotForFunction.value).map(t => ({
    name: t.label,
    value: t.key,
  }))
})

function formatTime(h, m) {
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

// ---- Load data ----
onMounted(async () => {
  try {
    const [botsRes, typesRes] = await Promise.all([
      api.get('/api/notification/bots'),
      api.get('/api/notification/trigger-types'),
    ])
    bots.value = botsRes.data.bots || []
    triggerTypes.value = typesRes.data.trigger_types || {}
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
})

// ---- Bot CRUD ----
function startEditBotName(bot) {
  editingBotId.value = bot.id
  editingBotName.value = bot.name
  nextTick(() => {
    const inputs = botNameInput.value
    if (inputs) {
      const el = Array.isArray(inputs) ? inputs[0] : inputs
      el?.focus()
    }
  })
}

async function finishEditBotName(bot) {
  const name = editingBotName.value.trim()
  editingBotId.value = null
  if (!name || name === bot.name) return
  try {
    const res = await api.put(`/api/notification/bots/${bot.id}`, { name })
    Object.assign(bot, res.data)
  } catch (e) {
    showToast('更新失败')
  }
}

async function toggleBot(bot, enabled) {
  try {
    const res = await api.put(`/api/notification/bots/${bot.id}`, { enabled })
    Object.assign(bot, res.data)
  } catch (e) {
    showToast('更新失败')
  }
}

function confirmDeleteBot(bot) {
  showConfirmDialog({
    title: '删除机器人',
    message: `确定删除「${bot.name}」？`,
  }).then(async () => {
    try {
      await api.delete(`/api/notification/bots/${bot.id}`)
      bots.value = bots.value.filter(b => b.id !== bot.id)
      showToast('已删除')
    } catch (e) {
      showToast('删除失败')
    }
  }).catch(() => {})
}

async function onAddBotClose(action) {
  if (action === 'confirm') {
    const name = newBotName.value.trim()
    const webhook = newBotWebhook.value.trim()
    if (!name || !webhook) {
      showToast('请填写完整信息')
      return false
    }
    try {
      const res = await api.post('/api/notification/bots', {
        name,
        channel: newBotChannel.value,
        webhook_url: webhook,
      })
      bots.value.push(res.data)
      newBotName.value = ''
      newBotWebhook.value = ''
      showToast('添加成功')
      return true
    } catch (e) {
      showToast('添加失败')
      return false
    }
  }
  return true
}

// ---- Custom message ----
async function sendCustomMessage(bot) {
  const msg = customMessages.value[bot.id]?.trim()
  if (!msg) return
  sendingCustom.value[bot.id] = true
  try {
    await api.post(`/api/notification/bots/${bot.id}/send`, { content: msg })
    customMessages.value[bot.id] = ''
    showToast('发送成功')
  } catch (e) {
    showToast('发送失败')
  } finally {
    sendingCustom.value[bot.id] = false
  }
}

// ---- Functions (trigger subscriptions) ----
function showAddFunction(bot) {
  currentBotForFunction.value = bot
  showFunctionSheet.value = true
}

function onSelectFunction(action) {
  showFunctionSheet.value = false
  const trigger = action.value
  // Show time picker for the new function
  timePickerHour.value = 8
  timePickerMinute.value = 0
  timePickerContext.value = {
    bot: currentBotForFunction.value,
    trigger,
    isNew: true,
  }
  showTimePicker.value = true
}

function startEditTime(bot, func) {
  timePickerHour.value = func.cron_hour
  timePickerMinute.value = func.cron_minute
  timePickerContext.value = { bot, trigger: func.trigger, isNew: false }
  showTimePicker.value = true
}

async function onTimeDialogConfirm() {
  const ctx = timePickerContext.value
  if (!ctx) return

  const hour = timePickerHour.value
  const minute = timePickerMinute.value

  if (ctx.isNew) {
    // Add new function
    try {
      const res = await api.post(`/api/notification/bots/${ctx.bot.id}/functions`, {
        trigger: ctx.trigger,
        cron_hour: hour,
        cron_minute: minute,
      })
      Object.assign(ctx.bot, res.data)
      showToast('功能已添加')
    } catch (e) {
      showToast(e.response?.data?.detail || '添加失败')
    }
  } else {
    // Update existing function time
    try {
      const res = await api.put(`/api/notification/bots/${ctx.bot.id}/functions/${ctx.trigger}`, {
        cron_hour: hour,
        cron_minute: minute,
      })
      Object.assign(ctx.bot, res.data)
      showToast('时间已更新')
    } catch (e) {
      showToast('更新失败')
    }
  }
}

function confirmDeleteFunction(bot, trigger) {
  const label = triggerTypes.value[trigger] || trigger
  showConfirmDialog({
    title: '移除功能',
    message: `确定移除「${label}」？`,
  }).then(async () => {
    try {
      const res = await api.delete(`/api/notification/bots/${bot.id}/functions/${trigger}`)
      Object.assign(bot, res.data)
      showToast('已移除')
    } catch (e) {
      showToast('移除失败')
    }
  }).catch(() => {})
}

// ---- Test trigger ----
async function testTrigger(bot, trigger) {
  const key = bot.id + '_' + trigger
  testingTrigger.value[key] = true
  try {
    await api.post(`/api/notification/bots/${bot.id}/test/${trigger}`)
    showToast('推送成功')
  } catch (e) {
    showToast(e.response?.data?.detail || '推送失败')
  } finally {
    testingTrigger.value[key] = false
  }
}
</script>

<style scoped>
.time-picker-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 20px 0 12px;
}

.time-column {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.time-drum {
  position: relative;
  width: 72px;
  height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 14px;
  background: #f8fafc;
  cursor: ns-resize;
  user-select: none;
  -webkit-user-select: none;
}

.drum-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 36px;
  flex-shrink: 0;
  font-family: 'SF Mono', 'Menlo', 'Monaco', 'Consolas', monospace;
  font-weight: 600;
  transition: color 0.15s, font-size 0.15s, opacity 0.15s;
  cursor: pointer;
}

.drum-far {
  font-size: 16px;
  color: #cbd5e1;
  opacity: 0.5;
}

.drum-near {
  font-size: 20px;
  color: #94a3b8;
  opacity: 0.75;
}

.drum-active {
  font-size: 30px;
  color: #1e293b;
  opacity: 1;
}

.drum-highlight {
  position: absolute;
  top: 50%;
  left: 6px;
  right: 6px;
  height: 38px;
  transform: translateY(-50%);
  background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(59,130,246,0.04));
  border: 1.5px solid rgba(59,130,246,0.2);
  border-radius: 10px;
  pointer-events: none;
}

.drum-fade-top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to bottom, #f8fafc, transparent);
  pointer-events: none;
  border-radius: 14px 14px 0 0;
}

.drum-fade-bottom {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to top, #f8fafc, transparent);
  pointer-events: none;
  border-radius: 0 0 14px 14px;
}

.time-separator {
  font-size: 32px;
  font-weight: 700;
  color: #94a3b8;
  margin: 0 2px;
  padding-bottom: 20px;
}

.time-label {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}
</style>

<template>
  <div>
    <div class="drum-toolbar">
      <span class="drum-toolbar-cancel" @click="$emit('cancel')">取消</span>
      <span class="drum-toolbar-title">{{ title }}</span>
      <span class="drum-toolbar-confirm" @click="$emit('confirm')">确认</span>
    </div>
  <div class="time-picker-container">
    <!-- Hour column -->
    <div class="time-column">
      <div
        class="time-drum"
        @wheel.prevent="hour = wrapInt(hour + ($event.deltaY < 0 ? 1 : -1), 0, 23)"
        @touchstart.prevent="onTouchStart($event, 'hour')"
        @touchmove.prevent="onTouchMove($event, 'hour')"
        @touchend="onTouchEnd"
      >
        <span class="drum-item drum-far" @click="hour = wrapInt(hour + 2, 0, 23)">
          {{ String(wrapInt(hour + 2, 0, 23)).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-near" @click="hour = wrapInt(hour + 1, 0, 23)">
          {{ String(wrapInt(hour + 1, 0, 23)).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-active" @click="focusTimeInput('hour')">
          {{ String(hour).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-near" @click="hour = wrapInt(hour - 1, 0, 23)">
          {{ String(wrapInt(hour - 1, 0, 23)).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-far" @click="hour = wrapInt(hour - 2, 0, 23)">
          {{ String(wrapInt(hour - 2, 0, 23)).padStart(2, '0') }}
        </span>
        <div class="drum-highlight"></div>
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
        @wheel.prevent="minute = wrapInt(minute + ($event.deltaY < 0 ? 1 : -1), 0, 59)"
        @touchstart.prevent="onTouchStart($event, 'minute')"
        @touchmove.prevent="onTouchMove($event, 'minute')"
        @touchend="onTouchEnd"
      >
        <span class="drum-item drum-far" @click="minute = wrapInt(minute + 2, 0, 59)">
          {{ String(wrapInt(minute + 2, 0, 59)).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-near" @click="minute = wrapInt(minute + 1, 0, 59)">
          {{ String(wrapInt(minute + 1, 0, 59)).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-active" @click="focusTimeInput('minute')">
          {{ String(minute).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-near" @click="minute = wrapInt(minute - 1, 0, 59)">
          {{ String(wrapInt(minute - 1, 0, 59)).padStart(2, '0') }}
        </span>
        <span class="drum-item drum-far" @click="minute = wrapInt(minute - 2, 0, 59)">
          {{ String(wrapInt(minute - 2, 0, 59)).padStart(2, '0') }}
        </span>
        <div class="drum-highlight"></div>
        <div class="drum-fade-top"></div>
        <div class="drum-fade-bottom"></div>
      </div>
      <span class="time-label">分</span>
    </div>
  </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelHour: { type: Number, default: 0 },
  modelMinute: { type: Number, default: 0 },
  title: { type: String, default: '选择时间' },
})

const emit = defineEmits(['update:modelHour', 'update:modelMinute', 'confirm', 'cancel'])

const hour = ref(props.modelHour)
const minute = ref(props.modelMinute)

watch(() => props.modelHour, v => { hour.value = v })
watch(() => props.modelMinute, v => { minute.value = v })
watch(hour, v => emit('update:modelHour', v))
watch(minute, v => emit('update:modelMinute', v))

function clampInt(val, min, max) {
  const n = parseInt(val, 10)
  if (isNaN(n)) return min
  return Math.min(max, Math.max(min, n))
}

function wrapInt(val, min, max) {
  const range = max - min + 1
  return ((((val - min) % range) + range) % range) + min
}

// Touch swipe support
const touchStartY = ref(0)
const touchAccum = ref(0)
const TOUCH_THRESHOLD = 30

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
      hour.value = wrapInt(hour.value + steps, 0, 23)
    } else {
      minute.value = wrapInt(minute.value + steps, 0, 59)
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

function focusTimeInput(field) {
  const current = field === 'hour' ? hour.value : minute.value
  const max = field === 'hour' ? 23 : 59
  const label = field === 'hour' ? '时 (0-23)' : '分 (0-59)'
  const val = prompt(`输入${label}`, String(current))
  if (val !== null && val.trim() !== '') {
    if (field === 'hour') {
      hour.value = clampInt(val, 0, max)
    } else {
      minute.value = clampInt(val, 0, max)
    }
  }
}
</script>

<style scoped>
.drum-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.drum-toolbar-cancel {
  font-size: 14px;
  color: #969799;
  cursor: pointer;
}

.drum-toolbar-title {
  font-size: 16px;
  font-weight: 600;
  color: #323233;
}

.drum-toolbar-confirm {
  font-size: 14px;
  color: #1989fa;
  cursor: pointer;
  font-weight: 500;
}

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

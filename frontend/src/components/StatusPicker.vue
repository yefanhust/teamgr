<template>
  <div class="sp-wrapper" ref="wrapperRef">
    <button
      class="sp-pill"
      :class="['sp-pill-' + modelValue, size === 'sm' ? 'sp-pill-sm' : '']"
      @click.stop="toggle"
    >
      <span class="sp-dot" :class="'sp-dot-' + modelValue"></span>
      <span class="sp-label">{{ currentLabel }}</span>
      <svg class="sp-arrow" :class="{ 'sp-arrow-open': isOpen }" viewBox="0 0 12 7" width="10" height="6">
        <path d="M1 1l5 5 5-5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
    <Teleport to="body">
      <Transition name="sp-fade">
        <div v-if="isOpen" class="sp-overlay" @click="close">
          <div class="sp-dropdown" :style="dropdownPos" @click.stop>
            <div
              v-for="opt in options"
              :key="opt.value"
              class="sp-option"
              :class="{ 'sp-option-active': modelValue === opt.value }"
              @click="select(opt.value)"
            >
              <span class="sp-opt-dot" :class="'sp-dot-' + opt.value"></span>
              <span class="sp-opt-label">{{ opt.label }}</span>
              <svg v-if="modelValue === opt.value" class="sp-check" viewBox="0 0 16 16" width="16" height="16">
                <path d="M3 8.5l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: 'active' },
  size: { type: String, default: '' }, // '' | 'sm'
})

const emit = defineEmits(['update:modelValue'])

const options = [
  { value: 'active', label: '进行中' },
  { value: 'suspended', label: '挂起' },
  { value: 'completed', label: '已完成' },
]

const currentLabel = computed(() => options.find(o => o.value === props.modelValue)?.label || '未知')

const isOpen = ref(false)
const wrapperRef = ref(null)
const dropdownPos = ref({})

function toggle() {
  if (isOpen.value) { close(); return }
  // Calculate position from pill
  const rect = wrapperRef.value?.getBoundingClientRect()
  if (!rect) return
  const spaceBelow = window.innerHeight - rect.bottom
  const dropH = 156 // approximate height of 3 options
  if (spaceBelow >= dropH + 8) {
    // Show below
    dropdownPos.value = {
      top: rect.bottom + 4 + 'px',
      left: Math.max(4, Math.min(rect.left, window.innerWidth - 180)) + 'px',
    }
  } else {
    // Show above
    dropdownPos.value = {
      top: (rect.top - dropH - 4) + 'px',
      left: Math.max(4, Math.min(rect.left, window.innerWidth - 180)) + 'px',
    }
  }
  isOpen.value = true
}

function close() {
  isOpen.value = false
}

function select(value) {
  emit('update:modelValue', value)
  close()
}
</script>

<style scoped>
/* ── Pill button ── */
.sp-wrapper {
  display: inline-flex;
  position: relative;
}

.sp-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 14px;
  border: 1.5px solid #d1d5db;
  background: white;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  transition: all 0.15s ease;
  white-space: nowrap;
  user-select: none;
}

.sp-pill-sm {
  padding: 3px 8px;
  font-size: 11px;
  border-radius: 10px;
  gap: 4px;
}

.sp-pill:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.sp-pill:active {
  transform: scale(0.97);
}

/* Pill color variants */
.sp-pill-active {
  color: #15803d;
  border-color: #86efac;
  background: #f0fdf4;
}
.sp-pill-active:hover { background: #dcfce7; border-color: #4ade80; }

.sp-pill-suspended {
  color: #b45309;
  border-color: #fcd34d;
  background: #fffbeb;
}
.sp-pill-suspended:hover { background: #fef3c7; border-color: #fbbf24; }

.sp-pill-completed {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
}
.sp-pill-completed:hover { background: #dbeafe; border-color: #60a5fa; }

/* Dot */
.sp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sp-pill-sm .sp-dot { width: 6px; height: 6px; }

.sp-dot-active { background: #22c55e; }
.sp-dot-suspended { background: #f59e0b; }
.sp-dot-completed { background: #3b82f6; }

/* Arrow */
.sp-arrow {
  flex-shrink: 0;
  transition: transform 0.2s ease;
  opacity: 0.6;
}
.sp-pill-sm .sp-arrow { width: 8px; height: 5px; }
.sp-arrow-open { transform: rotate(180deg); }

/* ── Overlay ── */
.sp-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

/* ── Dropdown panel ── */
.sp-dropdown {
  position: fixed;
  width: 172px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15), 0 1px 3px rgba(0, 0, 0, 0.08);
  border: 1px solid #e5e7eb;
  padding: 6px;
  z-index: 10000;
}

/* ── Option ── */
.sp-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s ease;
  font-size: 14px;
  color: #374151;
}

.sp-option:hover {
  background: #f3f4f6;
}

.sp-option-active {
  background: #f0f9ff;
  font-weight: 600;
}

.sp-opt-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sp-opt-label {
  flex: 1;
}

.sp-check {
  color: #3b82f6;
  flex-shrink: 0;
}

/* ── Transition ── */
.sp-fade-enter-active { transition: opacity 0.15s ease; }
.sp-fade-leave-active { transition: opacity 0.1s ease; }
.sp-fade-enter-from, .sp-fade-leave-to { opacity: 0; }
</style>

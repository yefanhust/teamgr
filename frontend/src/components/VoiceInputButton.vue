<template>
  <span
    v-if="isSupported"
    class="voice-btn"
    :class="{ 'voice-btn--active': isListening }"
    @click.stop.prevent="toggle"
    :title="isListening ? '停止录音' : '语音输入'"
  >
    <svg v-if="!isListening" xmlns="http://www.w3.org/2000/svg" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="9" y="1" width="6" height="11" rx="3" />
      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
    <van-icon v-else name="stop-circle-o" :size="size" />
  </span>
</template>

<script setup>
import { watch } from 'vue'
import { showToast } from 'vant'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'

const props = defineProps({
  modelValue: { type: String, default: '' },
  lang: { type: String, default: 'zh-CN' },
  mode: { type: String, default: 'append' },  // 'append' | 'replace'
  size: { type: [String, Number], default: 18 }
})

const emit = defineEmits(['update:modelValue'])

const { isSupported, isListening, transcript, interimTranscript, error, start, stop } = useSpeechRecognition()

let baseText = ''

function toggle() {
  if (isListening.value) {
    stop()
  } else {
    baseText = props.mode === 'append' ? props.modelValue : ''
    start(props.lang)
  }
}

watch([transcript, interimTranscript], ([final, interim]) => {
  if (!isListening.value && !final) return
  const combined = final + interim
  if (combined) {
    emit('update:modelValue', baseText + combined)
  }
})

watch(transcript, (val) => {
  if (val && !isListening.value) {
    // Final result after stop
    emit('update:modelValue', baseText + val)
  }
})

watch(error, (val) => {
  if (val) {
    showToast({ message: val, position: 'bottom' })
  }
})
</script>

<style scoped>
.voice-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  color: #999;
  flex-shrink: 0;
  transition: all 0.2s;
  -webkit-tap-highlight-color: transparent;
}

.voice-btn:active {
  opacity: 0.7;
}

.voice-btn--active {
  color: #fff;
  background: #ee0a24;
  animation: voice-pulse 1.2s ease-in-out infinite;
}

@keyframes voice-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(238, 10, 36, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(238, 10, 36, 0); }
}
</style>

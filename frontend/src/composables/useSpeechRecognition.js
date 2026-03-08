import { ref, onUnmounted } from 'vue'

const SpeechRecognition = typeof window !== 'undefined'
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null

export function useSpeechRecognition() {
  const isSupported = !!SpeechRecognition
  const isListening = ref(false)
  const transcript = ref('')
  const interimTranscript = ref('')
  const error = ref('')

  let recognition = null

  function start(lang = 'zh-CN') {
    if (!isSupported) {
      error.value = '当前浏览器不支持语音输入'
      return
    }

    if (isListening.value) {
      stop()
      return
    }

    error.value = ''
    transcript.value = ''
    interimTranscript.value = ''

    recognition = new SpeechRecognition()
    recognition.lang = lang
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onresult = (event) => {
      let final = ''
      let interim = ''
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      transcript.value = final
      interimTranscript.value = interim
    }

    recognition.onerror = (event) => {
      if (event.error === 'not-allowed') {
        error.value = '麦克风权限被拒绝，请在浏览器设置中允许'
      } else if (event.error === 'no-speech') {
        error.value = ''
      } else {
        error.value = `语音识别错误: ${event.error}`
      }
      isListening.value = false
    }

    recognition.onend = () => {
      isListening.value = false
    }

    recognition.start()
    isListening.value = true
  }

  function stop() {
    if (recognition) {
      recognition.stop()
      recognition = null
    }
    isListening.value = false
  }

  onUnmounted(() => {
    stop()
  })

  return {
    isSupported,
    isListening,
    transcript,
    interimTranscript,
    error,
    start,
    stop
  }
}

import { ref, onUnmounted } from 'vue'

/**
 * TTS composable using backend edge-tts (Microsoft Neural TTS).
 * Streams MP3 from /api/scholar/scheduled/results/{id}/tts
 */
export function useTTS() {
  const isSupported = true
  const isLoading = ref(false)
  const isSpeaking = ref(false)
  const isPaused = ref(false)
  const progress = ref(0)
  const playbackRate = ref(1.0)
  const RATES = [0.75, 1.0, 1.25, 1.5, 2.0]

  let audio = null
  let progressTimer = null
  let loadTimeout = null

  function _cleanup() {
    if (loadTimeout) {
      clearTimeout(loadTimeout)
      loadTimeout = null
    }
    if (progressTimer) {
      clearInterval(progressTimer)
      progressTimer = null
    }
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
      audio = null
    }
  }

  function _trackProgress() {
    if (progressTimer) clearInterval(progressTimer)
    progressTimer = setInterval(() => {
      if (audio && audio.duration && isFinite(audio.duration)) {
        progress.value = Math.round((audio.currentTime / audio.duration) * 100)
      }
    }, 300)
  }

  function speak(resultId) {
    stop()

    const token = localStorage.getItem('teamgr_token')
    if (!token) return

    isLoading.value = true
    isSpeaking.value = false
    isPaused.value = false
    progress.value = 0

    audio = new Audio()
    audio.preload = 'auto'

    let hasStarted = false
    function _tryPlay() {
      if (hasStarted || !audio) return
      hasStarted = true
      if (loadTimeout) {
        clearTimeout(loadTimeout)
        loadTimeout = null
      }
      isLoading.value = false
      isSpeaking.value = true
      audio.playbackRate = playbackRate.value
      audio.play().catch(() => {
        isSpeaking.value = false
        isLoading.value = false
      })
      _trackProgress()
    }

    // Use multiple events — canplay fires earlier and more reliably than canplaythrough
    audio.oncanplay = _tryPlay
    audio.oncanplaythrough = _tryPlay

    audio.onplay = () => {
      isSpeaking.value = true
      isPaused.value = false
    }

    audio.onpause = () => {
      if (audio && audio.currentTime < audio.duration) {
        isPaused.value = true
      }
    }

    audio.onended = () => {
      isSpeaking.value = false
      isPaused.value = false
      progress.value = 100
      if (progressTimer) {
        clearInterval(progressTimer)
        progressTimer = null
      }
    }

    audio.onerror = () => {
      isLoading.value = false
      isSpeaking.value = false
      isPaused.value = false
    }

    // Timeout: if still loading after 3 minutes, give up
    loadTimeout = setTimeout(() => {
      if (isLoading.value && !hasStarted) {
        stop()
      }
    }, 180000)

    audio.src = `/api/scholar/scheduled/results/${resultId}/tts?token=${encodeURIComponent(token)}`
    audio.load()
  }

  function pause() {
    if (audio && isSpeaking.value) {
      audio.pause()
      isPaused.value = true
    }
  }

  function resume() {
    if (audio && isPaused.value) {
      audio.play()
      isPaused.value = false
    }
  }

  function setRate(rate) {
    playbackRate.value = rate
    if (audio) {
      audio.playbackRate = rate
    }
  }

  function cycleRate() {
    const idx = RATES.indexOf(playbackRate.value)
    const next = RATES[(idx + 1) % RATES.length]
    setRate(next)
  }

  function seek(percent) {
    if (audio && audio.duration && isFinite(audio.duration)) {
      audio.currentTime = (percent / 100) * audio.duration
      progress.value = Math.round(percent)
    }
  }

  function stop() {
    _cleanup()
    isLoading.value = false
    isSpeaking.value = false
    isPaused.value = false
    progress.value = 0
  }

  function toggle(resultId) {
    if (isSpeaking.value && !isPaused.value) {
      pause()
    } else if (isPaused.value) {
      resume()
    } else {
      speak(resultId)
    }
  }

  onUnmounted(() => {
    stop()
  })

  return {
    isSupported,
    isLoading,
    isSpeaking,
    isPaused,
    progress,
    playbackRate,
    RATES,
    speak,
    pause,
    resume,
    stop,
    toggle,
    setRate,
    cycleRate,
    seek,
  }
}

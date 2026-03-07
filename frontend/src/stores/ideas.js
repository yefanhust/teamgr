import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useIdeasStore = defineStore('ideas', () => {
  const fragments = ref([])
  const insights = ref([])
  const history = ref([])
  const historyTotal = ref(0)
  const loading = ref(false)

  async function fetchFragments() {
    const res = await api.get('/api/ideas/fragments')
    fragments.value = res.data
  }

  async function deleteFragment(id) {
    await api.delete(`/api/ideas/fragments/${id}`)
    fragments.value = fragments.value.filter(f => f.id !== id)
  }

  async function submitIdea(content) {
    const res = await api.post('/api/ideas/input', { content })
    return res.data
  }

  async function getInputStatus(inputId) {
    const res = await api.get(`/api/ideas/input/status/${inputId}`)
    return res.data
  }

  async function fetchHistory(page = 1) {
    const res = await api.get('/api/ideas/history', { params: { page } })
    history.value = res.data.items
    historyTotal.value = res.data.total
  }

  async function fetchInsights() {
    const res = await api.get('/api/ideas/insights')
    insights.value = res.data
  }

  async function likeInsight(id) {
    await api.post(`/api/ideas/insights/${id}/like`)
    const item = insights.value.find(i => i.id === id)
    if (item) item.liked = true
  }

  async function unlikeInsight(id) {
    await api.delete(`/api/ideas/insights/${id}/like`)
    const item = insights.value.find(i => i.id === id)
    if (item) item.liked = false
  }

  async function triggerInsightGeneration() {
    await api.post('/api/ideas/insights/generate')
  }

  return {
    fragments,
    insights,
    history,
    historyTotal,
    loading,
    fetchFragments,
    deleteFragment,
    submitIdea,
    getInputStatus,
    fetchHistory,
    fetchInsights,
    likeInsight,
    unlikeInsight,
    triggerInsightGeneration,
  }
})

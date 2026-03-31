import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useTalentStore = defineStore('talent', () => {
  const talents = ref([])
  const tags = ref([])
  const dimensions = ref([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const currentPage = ref(1)
  const pageSize = ref(50)
  const hasMore = computed(() => talents.value.length < total.value)

  async function fetchTalents(params = {}) {
    loading.value = true
    currentPage.value = 1
    try {
      const res = await api.get('/api/talents', { params: { page: 1, page_size: pageSize.value, ...params } })
      talents.value = res.data.items
      total.value = res.data.total
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (loadingMore.value || !hasMore.value) return
    loadingMore.value = true
    try {
      const nextPage = currentPage.value + 1
      const res = await api.get('/api/talents', { params: { page: nextPage, page_size: pageSize.value } })
      talents.value = [...talents.value, ...res.data.items]
      total.value = res.data.total
      currentPage.value = nextPage
    } finally {
      loadingMore.value = false
    }
  }

  async function fetchTags() {
    const res = await api.get('/api/talents/tags/all')
    tags.value = res.data
  }

  async function fetchDimensions() {
    const res = await api.get('/api/talents/dimensions')
    dimensions.value = res.data
  }

  async function getTalent(id) {
    const res = await api.get(`/api/talents/${id}`)
    return res.data
  }

  async function createTalent(data) {
    const res = await api.post('/api/talents', data)
    return res.data
  }

  async function updateTalent(id, data) {
    const res = await api.put(`/api/talents/${id}`, data)
    return res.data
  }

  async function deleteTalent(id) {
    await api.delete(`/api/talents/${id}`)
    talents.value = talents.value.filter(t => t.id !== id)
    total.value = Math.max(0, total.value - 1)
  }

  async function searchTalents(q) {
    const res = await api.get('/api/talents/search', { params: { q } })
    return res.data
  }

  async function semanticSearch(query) {
    const res = await api.post('/api/talents/semantic-search', { query })
    return res.data
  }

  async function submitTextEntry(talentId, content) {
    const res = await api.post('/api/entry/text', {
      talent_id: talentId,
      content,
    })
    return res.data
  }

  async function uploadPdf(talentId, file) {
    const formData = new FormData()
    formData.append('talent_id', talentId)
    formData.append('file', file)
    const res = await api.post('/api/entry/pdf', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  }

  async function uploadImage(talentId, files) {
    const formData = new FormData()
    formData.append('talent_id', talentId)
    for (const file of files) {
      formData.append('files', file)
    }
    const res = await api.post('/api/entry/image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  }

  async function getEntryLogs(talentId) {
    const res = await api.get(`/api/entry/logs/${talentId}`)
    return res.data
  }

  async function deleteEntryLog(entryId) {
    await api.delete(`/api/entry/logs/${entryId}`)
  }

  async function createTag(name, color = '#3B82F6') {
    const res = await api.post('/api/talents/tags', { name, color })
    return res.data
  }

  async function updateTag(tagId, name, color) {
    const res = await api.put(`/api/talents/tags/${tagId}`, { name, color })
    const idx = tags.value.findIndex(t => t.id === tagId)
    if (idx !== -1) tags.value[idx] = res.data
    return res.data
  }

  async function deleteTag(tagId) {
    await api.delete(`/api/talents/tags/${tagId}`)
    tags.value = tags.value.filter(t => t.id !== tagId)
  }

  async function deleteInterviewFeedback(talentId, index) {
    await api.delete(`/api/entry/interview-evaluation/${talentId}/${index}`)
  }

  async function generateInterviewEvaluation(talentId, entryLogIds, rating) {
    const res = await api.post('/api/entry/interview-evaluation', {
      talent_id: talentId,
      entry_log_ids: entryLogIds,
      rating,
    }, { timeout: 120000 })
    return res.data
  }

  async function reparseEntries(talentId, entryLogIds) {
    const res = await api.post('/api/entry/reparse-entries', {
      talent_id: talentId,
      entry_log_ids: entryLogIds,
    }, { timeout: 120000 })
    return res.data
  }

  async function saveDirectInterviewFeedback(talentId, rating, evaluation) {
    const res = await api.post('/api/entry/interview-feedback-direct', {
      talent_id: talentId,
      rating,
      evaluation,
    })
    return res.data
  }

  return {
    talents,
    tags,
    dimensions,
    total,
    loading,
    loadingMore,
    hasMore,
    fetchTalents,
    loadMore,
    fetchTags,
    fetchDimensions,
    getTalent,
    createTalent,
    updateTalent,
    deleteTalent,
    searchTalents,
    semanticSearch,
    submitTextEntry,
    uploadPdf,
    uploadImage,
    getEntryLogs,
    deleteEntryLog,
    createTag,
    updateTag,
    deleteTag,
    deleteInterviewFeedback,
    generateInterviewEvaluation,
    reparseEntries,
    saveDirectInterviewFeedback,
  }
})

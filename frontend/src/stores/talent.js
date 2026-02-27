import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useTalentStore = defineStore('talent', () => {
  const talents = ref([])
  const tags = ref([])
  const dimensions = ref([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchTalents(params = {}) {
    loading.value = true
    try {
      const res = await api.get('/api/talents', { params })
      talents.value = res.data.items
      total.value = res.data.total
    } finally {
      loading.value = false
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

  return {
    talents,
    tags,
    dimensions,
    total,
    loading,
    fetchTalents,
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
    getEntryLogs,
    deleteEntryLog,
    createTag,
    updateTag,
    deleteTag,
  }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useDiaryStore = defineStore('diary', () => {
  const verified = ref(false)
  const password = ref('')
  const entries = ref([])
  const tags = ref([])
  const currentPage = ref(1)
  const totalPages = ref(1)
  const total = ref(0)
  const pageSize = ref(20)
  const selectedTagId = ref(null)
  const loading = ref(false)

  function _headers() {
    return { 'X-Diary-Password': password.value }
  }

  async function verifyPassword(pwd) {
    try {
      const res = await api.post('/api/diary/verify-password', { password: pwd })
      if (res.data.verified) {
        verified.value = true
        password.value = pwd
        return true
      }
      return false
    } catch {
      return false
    }
  }

  async function fetchEntries(page = 1, tagId = null) {
    loading.value = true
    try {
      const params = { page, page_size: pageSize.value }
      if (tagId) params.tag_id = tagId
      const res = await api.get('/api/diary/entries', { params, headers: _headers() })
      entries.value = res.data.entries
      currentPage.value = res.data.page
      totalPages.value = res.data.total_pages
      total.value = res.data.total
    } catch (e) {
      console.error('fetchEntries error:', e)
    } finally {
      loading.value = false
    }
  }

  async function createEntry(data) {
    const res = await api.post('/api/diary/entries', data, { headers: _headers() })
    // Refresh list after create
    await fetchEntries(1, selectedTagId.value)
    return res.data
  }

  async function updateEntry(id, data) {
    const res = await api.put(`/api/diary/entries/${id}`, data, { headers: _headers() })
    // Refresh list
    await fetchEntries(currentPage.value, selectedTagId.value)
    return res.data
  }

  async function deleteEntry(id) {
    await api.delete(`/api/diary/entries/${id}`, { headers: _headers() })
    await fetchEntries(currentPage.value, selectedTagId.value)
  }

  async function fetchTags() {
    const res = await api.get('/api/diary/tags', { headers: _headers() })
    tags.value = res.data
  }

  async function createTag(data) {
    const res = await api.post('/api/diary/tags', data, { headers: _headers() })
    await fetchTags()
    return res.data
  }

  async function updateTag(id, data) {
    const res = await api.put(`/api/diary/tags/${id}`, data, { headers: _headers() })
    await fetchTags()
    return res.data
  }

  async function deleteTag(id) {
    await api.delete(`/api/diary/tags/${id}`, { headers: _headers() })
    await fetchTags()
  }

  async function setCommentFeedback(entryId, feedback) {
    await api.post(`/api/diary/entries/${entryId}/comment-feedback`, { feedback }, { headers: _headers() })
    // Update local entry
    const entry = entries.value.find(e => e.id === entryId)
    if (entry) entry.comment_feedback = feedback
  }

  function logout() {
    verified.value = false
    password.value = ''
    entries.value = []
    tags.value = []
  }

  // Auto-refresh entries to pick up auto-tags (poll once after a short delay)
  async function refreshAfterAutoTag() {
    await new Promise(resolve => setTimeout(resolve, 3000))
    if (verified.value) {
      await fetchEntries(currentPage.value, selectedTagId.value)
    }
  }

  return {
    verified, password, entries, tags,
    currentPage, totalPages, total, pageSize,
    selectedTagId, loading,
    verifyPassword, fetchEntries, createEntry, updateEntry, deleteEntry,
    fetchTags, createTag, updateTag, deleteTag,
    setCommentFeedback, logout, refreshAfterAutoTag,
  }
})

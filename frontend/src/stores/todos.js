import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useTodosStore = defineStore('todos', () => {
  const pending = ref([])
  const completed = ref([])
  const tags = ref([])

  async function fetchAll() {
    const res = await api.get('/api/todos')
    pending.value = res.data.pending
    completed.value = res.data.completed
  }

  async function fetchTags() {
    const res = await api.get('/api/todos/tags/all')
    tags.value = res.data
  }

  async function createTodo(title, highPriority = false, deadline = null) {
    const res = await api.post('/api/todos', { title, high_priority: highPriority, deadline })
    pending.value.unshift(res.data)
    _sortPending()
    // Refresh tags in case new ones were auto-created
    await fetchTags()
    return res.data
  }

  async function updateTodo(id, data) {
    const res = await api.put(`/api/todos/${id}`, data)
    const pidx = pending.value.findIndex(t => t.id === id)
    if (pidx !== -1) {
      pending.value[pidx] = res.data
      _sortPending()
    }
    const cidx = completed.value.findIndex(t => t.id === id)
    if (cidx !== -1) {
      completed.value[cidx] = res.data
    }
    return res.data
  }

  async function completeTodo(id) {
    const res = await api.post(`/api/todos/${id}/complete`)
    pending.value = pending.value.filter(t => t.id !== id)
    completed.value.unshift(res.data)
    // If a repeat todo was spawned, add it to pending
    if (res.data.spawned) {
      pending.value.unshift(res.data.spawned)
      _sortPending()
    }
    return res.data
  }

  async function restartTodo(id) {
    const res = await api.post(`/api/todos/${id}/restart`)
    // Keep completed item in place (update it), add new clone to pending
    const cidx = completed.value.findIndex(t => t.id === id)
    if (cidx !== -1) completed.value[cidx] = res.data.completed
    pending.value.unshift(res.data.new)
    _sortPending()
    return res.data
  }

  async function deleteTodo(id) {
    await api.delete(`/api/todos/${id}`)
    pending.value = pending.value.filter(t => t.id !== id)
    completed.value = completed.value.filter(t => t.id !== id)
  }

  async function updateTag(tagId, name, color) {
    const res = await api.put(`/api/todos/tags/${tagId}`, { name, color })
    const idx = tags.value.findIndex(t => t.id === tagId)
    if (idx !== -1) tags.value[idx] = res.data
    return res.data
  }

  async function deleteTag(tagId) {
    await api.delete(`/api/todos/tags/${tagId}`)
    tags.value = tags.value.filter(t => t.id !== tagId)
  }

  async function updateVibeStatus(id, status, summary = null, plan = null) {
    const payload = { status }
    if (summary !== null) payload.summary = summary
    if (plan !== null) payload.plan = plan
    const res = await api.put(`/api/todos/${id}/vibe-status`, payload)
    const pidx = pending.value.findIndex(t => t.id === id)
    const cidx = completed.value.findIndex(t => t.id === id)
    if (res.data.completed) {
      if (cidx !== -1) completed.value[cidx] = res.data
      else completed.value.unshift(res.data)
      if (pidx !== -1) pending.value.splice(pidx, 1)
    } else {
      if (pidx !== -1) pending.value[pidx] = res.data
      else { pending.value.unshift(res.data); _sortPending() }
      if (cidx !== -1) completed.value.splice(cidx, 1)
    }
    return res.data
  }

  async function checkCommit(id) {
    const res = await api.post(`/api/todos/${id}/check-commit`)
    const pidx = pending.value.findIndex(t => t.id === id)
    if (pidx !== -1) pending.value[pidx] = res.data
    const cidx = completed.value.findIndex(t => t.id === id)
    if (cidx !== -1) completed.value[cidx] = res.data
    return res.data
  }

  function _sortPending() {
    pending.value.sort((a, b) => {
      if (a.high_priority !== b.high_priority) return b.high_priority ? 1 : -1
      return new Date(b.created_at) - new Date(a.created_at)
    })
  }

  return {
    pending,
    completed,
    tags,
    fetchAll,
    fetchTags,
    createTodo,
    updateTodo,
    completeTodo,
    restartTodo,
    deleteTodo,
    updateTag,
    deleteTag,
    updateVibeStatus,
    checkCommit,
  }
})

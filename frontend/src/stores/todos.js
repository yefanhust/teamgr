import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useTodosStore = defineStore('todos', () => {
  const pending = ref([])
  const completed = ref([])
  const tags = ref([])
  const reqTags = ref([])

  async function fetchAll() {
    const res = await api.get('/api/todos')
    pending.value = res.data.pending
    completed.value = res.data.completed
  }

  async function fetchTags() {
    const res = await api.get('/api/todos/tags/all?scope=todo')
    tags.value = res.data
  }

  async function fetchReqTags() {
    const res = await api.get('/api/todos/tags/all?scope=requirement')
    reqTags.value = res.data
  }

  async function createTodo(title, highPriority = false, deadline = null, deadlineTime = null) {
    const res = await api.post('/api/todos', { title, high_priority: highPriority, deadline, deadline_time: deadlineTime })
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
    // Check if it's a subtask (child of a pending parent)
    let isSubtask = false
    for (const p of pending.value) {
      if (p.children) {
        const cidx = p.children.findIndex(c => c.id === id)
        if (cidx !== -1) {
          p.children[cidx] = res.data
          p.children_completed_count = p.children.filter(c => c.completed).length
          isSubtask = true
          break
        }
      }
    }
    if (!isSubtask) {
      pending.value = pending.value.filter(t => t.id !== id)
      completed.value.unshift(res.data)
    }
    return res.data
  }

  async function restartTodo(id) {
    const res = await api.post(`/api/todos/${id}/restart`)
    // Remove completed item from list, add new clone to pending
    const cidx = completed.value.findIndex(t => t.id === id)
    if (cidx !== -1) completed.value.splice(cidx, 1)
    pending.value.unshift(res.data.new)
    _sortPending()
    return res.data
  }

  async function deleteTodo(id) {
    await api.delete(`/api/todos/${id}`)
    pending.value = pending.value.filter(t => t.id !== id)
    completed.value = completed.value.filter(t => t.id !== id)
  }

  async function createRequirement(title, highPriority = false) {
    const res = await api.post('/api/todos/requirements', { title, high_priority: highPriority })
    pending.value.unshift(res.data)
    _sortPending()
    await fetchReqTags()
    return res.data
  }

  async function submitRequirement(id) {
    const res = await api.post(`/api/todos/${id}/vibe-submit`)
    const pidx = pending.value.findIndex(t => t.id === id)
    if (pidx !== -1) pending.value[pidx] = res.data
    return res.data
  }

  async function createTag(name, scope = 'todo', color = '#3B82F6') {
    const res = await api.post('/api/todos/tags', { name, color, scope })
    if (scope === 'requirement') {
      reqTags.value.push(res.data)
    } else {
      tags.value.push(res.data)
    }
    return res.data
  }

  async function updateTag(tagId, name, color) {
    const res = await api.put(`/api/todos/tags/${tagId}`, { name, color })
    // Update in whichever list it belongs to
    const idx = tags.value.findIndex(t => t.id === tagId)
    if (idx !== -1) tags.value[idx] = res.data
    const ridx = reqTags.value.findIndex(t => t.id === tagId)
    if (ridx !== -1) reqTags.value[ridx] = res.data
    return res.data
  }

  async function deleteTag(tagId) {
    await api.delete(`/api/todos/tags/${tagId}`)
    tags.value = tags.value.filter(t => t.id !== tagId)
    reqTags.value = reqTags.value.filter(t => t.id !== tagId)
  }

  async function updateVibeStatus(id, status, summary = null, plan = null, comment = null) {
    const payload = { status }
    if (summary !== null) payload.summary = summary
    if (plan !== null) payload.plan = plan
    if (comment !== null) payload.comment = comment
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

  async function createSubtask(parentId, title, highPriority = false) {
    const res = await api.post(`/api/todos/${parentId}/subtasks`, { title, high_priority: highPriority })
    // Response is the updated parent with children
    const pidx = pending.value.findIndex(t => t.id === parentId)
    if (pidx !== -1) pending.value[pidx] = res.data
    return res.data
  }

  async function startTodo(id) {
    const res = await api.post(`/api/todos/${id}/start`)
    _updateItemInLists(id, res.data)
    _sortPending()
    return res.data
  }

  async function pauseTodo(id) {
    const res = await api.post(`/api/todos/${id}/pause`)
    _updateItemInLists(id, res.data)
    return res.data
  }

  async function stopTodo(id) {
    const res = await api.post(`/api/todos/${id}/stop`)
    _updateItemInLists(id, res.data)
    _sortPending()
    return res.data
  }

  function _updateItemInLists(id, data) {
    // Update in pending list (could be a top-level or update parent's child)
    const pidx = pending.value.findIndex(t => t.id === id)
    if (pidx !== -1) {
      pending.value[pidx] = data
      return
    }
    // Check if it's a child of a pending item
    for (const p of pending.value) {
      if (p.children) {
        const cidx = p.children.findIndex(c => c.id === id)
        if (cidx !== -1) {
          p.children[cidx] = data
          // Update parent's children counts
          p.children_completed_count = p.children.filter(c => c.completed).length
          return
        }
      }
    }
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
    reqTags,
    fetchAll,
    fetchTags,
    fetchReqTags,
    createTodo,
    updateTodo,
    completeTodo,
    restartTodo,
    deleteTodo,
    createTag,
    updateTag,
    deleteTag,
    updateVibeStatus,
    checkCommit,
    createRequirement,
    submitRequirement,
    createSubtask,
    startTodo,
    pauseTodo,
    stopTodo,
  }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useProjectsStore = defineStore('projects', () => {
  const projects = ref([])
  const currentProject = ref(null)
  const timelineBoard = ref({ groups: {}, total: 0 })
  const memberBoard = ref([])
  const loading = ref(false)

  async function fetchProjects(status = null, topOnly = false) {
    const params = {}
    if (status) params.status = status
    if (topOnly) params.top_only = true
    const res = await api.get('/api/projects', { params })
    projects.value = res.data
    return res.data
  }

  async function createProject(name, description = '', parentId = null) {
    const res = await api.post('/api/projects', {
      name,
      description,
      parent_id: parentId,
    })
    // Refresh list
    await fetchProjects()
    return res.data
  }

  async function getProject(id) {
    const res = await api.get(`/api/projects/${id}`)
    currentProject.value = res.data
    return res.data
  }

  async function updateProject(id, data) {
    const res = await api.put(`/api/projects/${id}`, data)
    await fetchProjects()
    return res.data
  }

  async function deleteProject(id) {
    await api.delete(`/api/projects/${id}`)
    await fetchProjects()
  }

  async function submitUpdate(projectId, talentId, content, model = null) {
    const payload = {
      project_id: projectId,
      talent_id: talentId,
      content,
    }
    if (model) payload.model = model
    const res = await api.post('/api/projects/updates', payload)
    // Refresh projects to update timestamps
    await fetchProjects()
    return res.data
  }

  async function fetchTimeline(range = 'month') {
    const res = await api.get('/api/projects/board/timeline', { params: { range } })
    timelineBoard.value = res.data
    return res.data
  }

  async function fetchMemberBoard() {
    const res = await api.get('/api/projects/board/members')
    memberBoard.value = res.data
    return res.data
  }

  async function getProjectInfo(id) {
    const res = await api.get(`/api/projects/${id}/info`)
    currentProject.value = res.data
    return res.data
  }

  async function refreshProjectInfo(id) {
    const res = await api.post(`/api/projects/${id}/refresh-info`)
    if (currentProject.value && currentProject.value.id === id) {
      currentProject.value.llm_summary = res.data.llm_summary
    }
    return res.data
  }

  async function searchProjects(q) {
    const res = await api.get('/api/projects/search', { params: { q } })
    return res.data
  }

  return {
    projects,
    currentProject,
    timelineBoard,
    memberBoard,
    loading,
    fetchProjects,
    createProject,
    getProject,
    updateProject,
    deleteProject,
    submitUpdate,
    fetchTimeline,
    fetchMemberBoard,
    getProjectInfo,
    refreshProjectInfo,
    searchProjects,
  }
})

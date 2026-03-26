import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useOrganizationStore = defineStore('organization', () => {
  const teams = ref([])
  const projectView = ref([])
  const loading = ref(false)

  async function fetchTeams() {
    loading.value = true
    try {
      const res = await api.get('/api/teams')
      teams.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function createTeam(name) {
    const res = await api.post('/api/teams', { name })
    teams.value.push(res.data)
    return res.data
  }

  async function updateTeam(id, data) {
    const res = await api.put(`/api/teams/${id}`, data)
    const idx = teams.value.findIndex(t => t.id === id)
    if (idx !== -1) teams.value[idx] = res.data
    return res.data
  }

  async function deleteTeam(id) {
    await api.delete(`/api/teams/${id}`)
    teams.value = teams.value.filter(t => t.id !== id)
  }

  async function addMember(teamId, talentId) {
    const res = await api.post(`/api/teams/${teamId}/members`, { talent_id: talentId })
    const idx = teams.value.findIndex(t => t.id === teamId)
    if (idx !== -1) teams.value[idx] = res.data
    return res.data
  }

  async function removeMember(teamId, talentId) {
    const res = await api.delete(`/api/teams/${teamId}/members/${talentId}`)
    const idx = teams.value.findIndex(t => t.id === teamId)
    if (idx !== -1) teams.value[idx] = res.data
    return res.data
  }

  async function setLeader(teamId, talentId) {
    const res = await api.put(`/api/teams/${teamId}/leader`, { talent_id: talentId })
    const idx = teams.value.findIndex(t => t.id === teamId)
    if (idx !== -1) teams.value[idx] = res.data
    return res.data
  }

  async function updateMemberTitle(teamId, talentId, title) {
    const res = await api.put(`/api/teams/${teamId}/members/${talentId}/title`, { position_title: title })
    const idx = teams.value.findIndex(t => t.id === teamId)
    if (idx !== -1) teams.value[idx] = res.data
    return res.data
  }

  async function fetchProjectView() {
    const res = await api.get('/api/teams/project-view')
    projectView.value = res.data
    return res.data
  }

  async function updateProjectStatus(projectId, status) {
    await api.put(`/api/projects/${projectId}`, { status })
    // Refresh project view to update counts and statuses
    await fetchProjectView()
  }

  return {
    teams,
    projectView,
    loading,
    fetchTeams,
    createTeam,
    updateTeam,
    deleteTeam,
    addMember,
    removeMember,
    setLeader,
    updateMemberTitle,
    fetchProjectView,
    updateProjectStatus,
  }
})

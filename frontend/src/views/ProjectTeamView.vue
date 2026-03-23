<template>
  <div class="project-team-container">
    <van-loading v-if="loading" class="loading-center" />

    <div v-else-if="store.projectView.length === 0" class="text-center py-16 text-gray-400">
      <div class="text-4xl mb-3">📊</div>
      <p>暂无团队数据，请先在"组织"中创建团队</p>
    </div>

    <div v-else class="team-sections">
      <div
        v-for="team in store.projectView"
        :key="team.id"
        class="team-section"
      >
        <h3 class="team-section-title">
          <van-icon name="friends-o" size="16" />
          {{ team.name }}
        </h3>

        <div class="team-section-body" :ref="el => setSectionRef(team.id, el)">
          <!-- SVG Connection Lines -->
          <svg class="connections-svg" :id="'svg-' + team.id">
            <line
              v-for="line in connectionLines[team.id] || []"
              :key="line.key"
              :x1="line.x1" :y1="line.y1"
              :x2="line.x2" :y2="line.y2"
              stroke="#94a3b8"
              stroke-width="1.5"
              stroke-dasharray="4 3"
            />
          </svg>

          <!-- Projects Row -->
          <div class="projects-row">
            <div
              v-for="project in team.projects"
              :key="project.id"
              class="project-box"
              :ref="el => setProjectRef(team.id, project.id, el)"
              @click="goToProject(project.id)"
            >
              <van-icon name="orders-o" size="14" color="#3b82f6" />
              <span class="project-name">{{ project.name }}</span>
              <van-tag :type="project.status === 'active' ? 'primary' : 'default'" size="mini">
                {{ project.status === 'active' ? '进行中' : project.status === 'completed' ? '已完成' : '归档' }}
              </van-tag>
            </div>
          </div>

          <!-- Members Row -->
          <div class="members-row">
            <!-- Members with projects -->
            <div
              v-for="member in membersWithProjects(team)"
              :key="member.talent_id"
              class="member-circle-wrap"
              :ref="el => setMemberRef(team.id, member.talent_id, el)"
              @click="goToTalent(member.talent_id)"
            >
              <div class="member-circle">
                <img
                  v-if="member.avatar_url"
                  :src="member.avatar_url"
                  class="member-avatar"
                />
                <van-icon v-else name="contact" size="24" color="#9ca3af" />
                <span v-if="member.project_count > 1" class="project-badge">{{ member.project_count }}</span>
              </div>
              <span class="member-label">{{ member.name }}</span>
            </div>

            <!-- Unassigned members (no projects) -->
            <div
              v-for="member in membersWithoutProjects(team)"
              :key="'idle-' + member.talent_id"
              class="member-circle-wrap idle"
              :ref="el => setMemberRef(team.id, member.talent_id, el)"
              @click="goToTalent(member.talent_id)"
            >
              <div class="member-circle idle-circle">
                <img
                  v-if="member.avatar_url"
                  :src="member.avatar_url"
                  class="member-avatar"
                />
                <van-icon v-else name="contact" size="24" color="#d1d5db" />
              </div>
              <span class="member-label idle-label">{{ member.name }}</span>
            </div>
          </div>

          <!-- Avatar Upload (hidden input) -->
          <input
            type="file"
            ref="avatarInput"
            accept="image/*"
            class="hidden"
            @change="handleAvatarUpload"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useOrganizationStore } from '../stores/organization'

const router = useRouter()
const store = useOrganizationStore()
const loading = ref(true)

// Element refs for SVG line computation
const sectionRefs = ref({})
const projectRefs = ref({})
const memberRefs = ref({})
const connectionLines = ref({})

function setSectionRef(teamId, el) {
  if (el) sectionRefs.value[teamId] = el
}
function setProjectRef(teamId, projectId, el) {
  if (el) {
    if (!projectRefs.value[teamId]) projectRefs.value[teamId] = {}
    projectRefs.value[teamId][projectId] = el
  }
}
function setMemberRef(teamId, talentId, el) {
  if (el) {
    if (!memberRefs.value[teamId]) memberRefs.value[teamId] = {}
    memberRefs.value[teamId][talentId] = el
  }
}

function membersWithProjects(team) {
  return team.members.filter(m => m.project_count > 0)
}

function membersWithoutProjects(team) {
  return team.members.filter(m => m.project_count === 0)
}

function computeLines() {
  const lines = {}
  for (const team of store.projectView) {
    lines[team.id] = []
    const sectionEl = sectionRefs.value[team.id]
    if (!sectionEl) continue
    const sectionRect = sectionEl.getBoundingClientRect()

    for (const member of team.members) {
      if (member.project_count === 0) continue
      const memberEl = memberRefs.value[team.id]?.[member.talent_id]
      if (!memberEl) continue
      const memberRect = memberEl.getBoundingClientRect()
      const mx = memberRect.left + memberRect.width / 2 - sectionRect.left
      const my = memberRect.top + 4 - sectionRect.top

      for (const pid of member.project_ids) {
        const projectEl = projectRefs.value[team.id]?.[pid]
        if (!projectEl) continue
        const projectRect = projectEl.getBoundingClientRect()
        const px = projectRect.left + projectRect.width / 2 - sectionRect.left
        const py = projectRect.top + projectRect.height - sectionRect.top

        lines[team.id].push({
          key: `${member.talent_id}-${pid}`,
          x1: px, y1: py,
          x2: mx, y2: my,
        })
      }
    }
  }
  connectionLines.value = lines
}

function goToTalent(talentId) {
  router.push(`/talent/${talentId}`)
}

function goToProject(projectId) {
  // Navigate to project - since there's no dedicated project page route,
  // we'll use search or a future project detail page
  router.push(`/search?project=${projectId}`)
}

onMounted(async () => {
  await store.fetchProjectView()
  loading.value = false
  await nextTick()
  setTimeout(computeLines, 100)
})

watch(() => store.projectView, async () => {
  await nextTick()
  setTimeout(computeLines, 100)
}, { deep: true })
</script>

<style scoped>
.project-team-container {
  padding: 12px 16px;
  min-height: 300px;
}

.loading-center {
  display: flex;
  justify-content: center;
  padding: 48px;
}

.team-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.team-section {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.team-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  background: #f8fafc;
  border-bottom: 1px solid #e5e7eb;
}

.team-section-body {
  position: relative;
  padding: 20px 16px;
  min-height: 160px;
}

.connections-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

.projects-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 32px;
  position: relative;
  z-index: 1;
}

.project-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #eff6ff;
  border: 1.5px solid #bfdbfe;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.project-box:hover {
  background: #dbeafe;
  border-color: #93c5fd;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
}

.project-name {
  font-size: 13px;
  font-weight: 500;
  color: #1e40af;
  max-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.members-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  position: relative;
  z-index: 1;
}

.member-circle-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.member-circle-wrap:hover .member-label {
  color: #3b82f6;
}

.member-circle {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #e5e7eb;
  transition: all 0.2s;
}

.member-circle:hover {
  border-color: #3b82f6;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.2);
}

.idle-circle {
  border-style: dashed;
  opacity: 0.6;
}

.member-avatar {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}

.project-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: #ef4444;
  color: white;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  border: 2px solid white;
}

.member-label {
  font-size: 12px;
  color: #6b7280;
  max-width: 60px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.idle-label {
  color: #9ca3af;
}

.hidden {
  display: none;
}
</style>

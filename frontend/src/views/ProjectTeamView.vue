<template>
  <div class="project-team-container">
    <van-loading v-if="loading" class="loading-center" />

    <div v-else-if="sortedTeams.length === 0" class="text-center py-16 text-gray-400">
      <div class="text-4xl mb-3">📊</div>
      <p>暂无团队数据，请先在"组织"中创建团队并添加成员</p>
    </div>

    <div v-else class="team-sections">
      <div
        v-for="team in sortedTeams"
        :key="team.id"
        class="team-section"
      >
        <h3
          class="team-section-title"
          @click="toggleCollapse(team.id)"
        >
          <van-icon
            :name="isCollapsed(team.id) ? 'arrow' : 'arrow-down'"
            size="14"
            class="collapse-icon"
          />
          <van-icon name="friends-o" size="16" />
          {{ team.name }}
          <span class="member-count">{{ team.members.length }}人</span>
          <span v-if="team.projects.length === 0" class="no-project-hint">（无项目）</span>
          <span v-else class="project-count">{{ team.projects.length }}个项目</span>
        </h3>

        <div v-show="!isCollapsed(team.id)" class="team-canvas">
          <!-- Hierarchical project trees -->
          <div class="project-trees">
            <div
              v-for="project in team.projects"
              :key="project.id"
              class="project-tree"
              :style="getOffsetStyle('p', team.id, project.id)"
              @pointerdown.prevent="onTreePointerDown($event, team.id, project.id)"
            >
              <!-- Project node -->
              <div class="project-node">
                <van-icon name="orders-o" size="14" color="#3b82f6" />
                <span class="project-node-name">{{ project.name }}</span>
                <van-tag :type="project.status === 'active' ? 'primary' : 'default'" size="mini">
                  {{ project.status === 'active' ? '进行中' : project.status === 'completed' ? '已完成' : '归档' }}
                </van-tag>
              </div>
              <!-- Tree connector -->
              <div v-if="projectMembers(team, project.id).length > 0" class="tree-connector">
                <div class="tree-trunk"></div>
                <div class="tree-branches">
                  <div
                    v-for="(member, mi) in projectMembers(team, project.id)"
                    :key="member.talent_id"
                    class="tree-branch"
                  >
                    <div class="branch-line"></div>
                    <div class="member-leaf" :data-talent-id="member.talent_id">
                      <div class="member-circle">
                        <img v-if="member.avatar_url" :src="member.avatar_url" class="member-avatar" />
                        <van-icon v-else name="contact" size="20" color="#9ca3af" />
                        <span v-if="member.project_count > 1" class="project-badge">{{ member.project_count }}</span>
                      </div>
                      <span class="member-name">{{ member.name }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Unassigned members (no projects) -->
          <div v-if="membersWithoutProjects(team).length > 0" class="idle-members">
            <span class="idle-label-header">未分配项目</span>
            <div class="idle-row">
              <div
                v-for="member in membersWithoutProjects(team)"
                :key="'idle-' + member.talent_id"
                class="member-leaf idle"
                @click="goToTalent(member.talent_id)"
              >
                <div class="member-circle idle-circle">
                  <img v-if="member.avatar_url" :src="member.avatar_url" class="member-avatar" />
                  <van-icon v-else name="contact" size="20" color="#d1d5db" />
                </div>
                <span class="member-name idle-name">{{ member.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useOrganizationStore } from '../stores/organization'

const router = useRouter()
const store = useOrganizationStore()
const loading = ref(true)

// Collapse state — persisted
const COLLAPSE_KEY = 'teamgr_project_view_collapsed'
const collapsedTeams = ref(new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '[]')))

function isCollapsed(teamId) {
  return collapsedTeams.value.has(teamId)
}

function toggleCollapse(teamId) {
  const s = new Set(collapsedTeams.value)
  if (s.has(teamId)) s.delete(teamId)
  else s.add(teamId)
  collapsedTeams.value = s
  localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...s]))
}

// Drag offsets — persisted
const OFFSETS_KEY = 'teamgr_project_view_offsets'
function loadOffsets() {
  try {
    const s = localStorage.getItem(OFFSETS_KEY)
    return s ? JSON.parse(s) : {}
  } catch { return {} }
}
function saveOffsets() {
  localStorage.setItem(OFFSETS_KEY, JSON.stringify(dragOffsets))
}
const dragOffsets = reactive(loadOffsets())

// Drag state
const dragging = ref(null)
const hasDragged = ref(false)

function offsetKey(type, teamId, itemId) {
  return `${type}-${teamId}-${itemId}`
}

function getOffsetStyle(type, teamId, itemId) {
  const k = offsetKey(type, teamId, itemId)
  const o = dragOffsets[k]
  if (!o || (o.x === 0 && o.y === 0)) return {}
  return { transform: `translate(${o.x}px, ${o.y}px)` }
}

const teamsWithMembers = computed(() => {
  return store.projectView.filter(t => t.members.length > 0)
})

const sortedTeams = computed(() => {
  return [...teamsWithMembers.value].sort((a, b) => {
    const ap = a.projects.length > 0 ? 0 : 1
    const bp = b.projects.length > 0 ? 0 : 1
    return ap - bp
  })
})

function projectMembers(team, projectId) {
  return team.members.filter(m => m.project_ids.includes(projectId))
}

function membersWithoutProjects(team) {
  return team.members.filter(m => m.project_count === 0)
}

// Drag: entire project tree moves together
function onTreePointerDown(e, teamId, projectId) {
  const k = offsetKey('p', teamId, projectId)
  const o = dragOffsets[k] || { x: 0, y: 0 }
  dragging.value = {
    teamId, projectId,
    startX: e.clientX, startY: e.clientY,
    startOx: o.x, startOy: o.y,
    target: e.target,
  }
  hasDragged.value = false
  e.currentTarget.setPointerCapture(e.pointerId)
  e.currentTarget.addEventListener('pointermove', onTreePointerMove)
  e.currentTarget.addEventListener('pointerup', onTreePointerUp, { once: true })
}

function onTreePointerMove(e) {
  if (!dragging.value) return
  const d = dragging.value
  const dx = e.clientX - d.startX
  const dy = e.clientY - d.startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged.value = true
  const k = offsetKey('p', d.teamId, d.projectId)
  dragOffsets[k] = { x: d.startOx + dx, y: d.startOy + dy }
}

function onTreePointerUp(e) {
  if (!dragging.value) return
  const d = dragging.value
  dragging.value = null
  e.currentTarget.removeEventListener('pointermove', onTreePointerMove)
  e.currentTarget.releasePointerCapture(e.pointerId)
  if (hasDragged.value) {
    saveOffsets()
    return
  }
  // Not dragged — handle as click
  const clickedEl = d.target
  // Check if clicked on a member leaf
  const memberLeaf = clickedEl.closest('.member-leaf')
  if (memberLeaf) {
    const talentId = memberLeaf.dataset.talentId
    if (talentId) goToTalent(parseInt(talentId))
    return
  }
  // Check if clicked on the project node
  const projectNode = clickedEl.closest('.project-node')
  if (projectNode) {
    goToProject(d.projectId)
  }
}

function goToTalent(talentId) {
  router.push(`/talent/${talentId}`)
}

function goToProject(projectId) {
  // Navigate to Studio with project focus query param
  localStorage.setItem('todoActiveTab', '1')
  router.push(`/?pmFocus=${projectId}`)
}

onMounted(async () => {
  await store.fetchProjectView()
  loading.value = false
})
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
  gap: 16px;
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
  cursor: pointer;
  user-select: none;
}

.team-section-title:hover {
  background: #f1f5f9;
}

.collapse-icon {
  color: #9ca3af;
  transition: transform 0.2s;
}

.member-count {
  font-size: 12px;
  font-weight: 400;
  color: #6b7280;
  margin-left: 4px;
}

.project-count {
  font-size: 12px;
  font-weight: 400;
  color: #3b82f6;
  margin-left: 2px;
}

.no-project-hint {
  font-size: 12px;
  font-weight: 400;
  color: #9ca3af;
}

.team-canvas {
  padding: 24px 20px;
  min-height: 200px;
  overflow-x: auto;
}

/* Project trees layout */
.project-trees {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
  align-items: flex-start;
}

.project-tree {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.project-tree:active {
  cursor: grabbing;
}

/* Project node */
.project-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #eff6ff;
  border: 1.5px solid #bfdbfe;
  border-radius: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s;
  white-space: nowrap;
}

.project-node:hover {
  background: #dbeafe;
  border-color: #93c5fd;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
}

.project-node-name {
  font-size: 13px;
  font-weight: 500;
  color: #1e40af;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Tree connector lines */
.tree-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.tree-trunk {
  width: 1.5px;
  height: 16px;
  background: #cbd5e1;
}

.tree-branches {
  display: flex;
  gap: 0;
  position: relative;
}

/* Horizontal bar connecting all branches at the top */
.tree-branches::before {
  content: '';
  position: absolute;
  top: 0;
  height: 1.5px;
  background: #cbd5e1;
}

.tree-branches:has(.tree-branch:nth-child(2))::before {
  left: 32px;
  right: 32px;
}

.tree-branches:not(:has(.tree-branch:nth-child(2)))::before {
  display: none;
}

.tree-branch {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 64px;
}

.branch-line {
  width: 1.5px;
  height: 14px;
  background: #cbd5e1;
}

/* Member leaf node */
.member-leaf {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  padding: 2px;
}

.member-leaf:hover .member-name {
  color: #3b82f6;
}

.member-circle {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #e5e7eb;
  transition: border-color 0.2s;
}

.member-circle:hover {
  border-color: #3b82f6;
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
  top: -3px;
  right: -3px;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  background: #ef4444;
  color: white;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 3px;
  border: 1.5px solid white;
}

.member-name {
  font-size: 11px;
  color: #6b7280;
  max-width: 56px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.idle-name {
  color: #9ca3af;
}

/* Idle members section */
.idle-members {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px dashed #e5e7eb;
}

.idle-label-header {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 10px;
  display: block;
}

.idle-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
</style>

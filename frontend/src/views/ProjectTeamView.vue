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
        <h3 class="team-section-title">
          <van-icon name="friends-o" size="16" />
          {{ team.name }}
          <span v-if="team.projects.length === 0" class="no-project-hint">（无项目）</span>
        </h3>

        <div
          class="team-section-body"
          :ref="el => setSectionRef(team.id, el)"
          @pointerdown.self="onMarqueeStart($event, team.id)"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
        >
          <!-- Marquee Selection Rectangle -->
          <div
            v-if="marquee && marquee.teamId === team.id"
            class="marquee-rect"
            :style="marqueeStyle"
          ></div>
          <!-- SVG Connection Lines -->
          <svg class="connections-svg">
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
          <div v-if="team.projects.length > 0" class="projects-row">
            <div
              v-for="project in team.projects"
              :key="project.id"
              class="project-box"
              :ref="el => setProjectRef(team.id, project.id, el)"
              :style="getOffsetStyle('p', team.id, project.id)"
              @pointerdown.prevent="onItemPointerDown($event, team.id, 'p', project.id)"
              @click.prevent
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
            <div
              v-for="member in membersWithProjects(team)"
              :key="member.talent_id"
              class="member-circle-wrap"
              :class="{ selected: isSelected(team.id, member.talent_id) }"
              :ref="el => setMemberRef(team.id, member.talent_id, el)"
              :style="getOffsetStyle('m', team.id, member.talent_id)"
              @pointerdown.prevent="onItemPointerDown($event, team.id, 'm', member.talent_id)"
              @click.prevent
            >
              <div class="member-circle">
                <img v-if="member.avatar_url" :src="member.avatar_url" class="member-avatar" />
                <van-icon v-else name="contact" size="24" color="#9ca3af" />
                <span v-if="member.project_count > 1" class="project-badge">{{ member.project_count }}</span>
              </div>
              <span class="member-label">{{ member.name }}</span>
            </div>

            <div
              v-for="member in membersWithoutProjects(team)"
              :key="'idle-' + member.talent_id"
              class="member-circle-wrap idle"
              :class="{ selected: isSelected(team.id, member.talent_id) }"
              :ref="el => setMemberRef(team.id, member.talent_id, el)"
              :style="getOffsetStyle('m', team.id, member.talent_id)"
              @pointerdown.prevent="onItemPointerDown($event, team.id, 'm', member.talent_id)"
              @click.prevent
            >
              <div class="member-circle idle-circle">
                <img v-if="member.avatar_url" :src="member.avatar_url" class="member-avatar" />
                <van-icon v-else name="contact" size="24" color="#d1d5db" />
              </div>
              <span class="member-label idle-label">{{ member.name }}</span>
            </div>
          </div>

          <!-- Selection hint -->
          <div v-if="selectedInTeam(team.id) > 0" class="selection-hint">
            已选 {{ selectedInTeam(team.id) }} 人，拖动任意选中成员可批量移动
            <span class="clear-selection" @click="clearSelection(team.id)">清除</span>
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

// Element refs for SVG line computation
const sectionRefs = ref({})
const projectRefs = ref({})
const memberRefs = ref({})
const connectionLines = ref({})

// Drag offsets — persisted to localStorage
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

// Multi-select: Set of "teamId-talentId"
const selectedMembers = reactive(new Set())

// Drag state
const dragging = ref(null)
const hasDragged = ref(false)

// Marquee selection state
const marquee = ref(null) // { teamId, startX, startY, curX, curY, sectionRect }

const marqueeStyle = computed(() => {
  if (!marquee.value) return {}
  const m = marquee.value
  const x = Math.min(m.startX, m.curX)
  const y = Math.min(m.startY, m.curY)
  const w = Math.abs(m.curX - m.startX)
  const h = Math.abs(m.curY - m.startY)
  return {
    left: x + 'px', top: y + 'px',
    width: w + 'px', height: h + 'px',
  }
})

function offsetKey(type, teamId, itemId) {
  return `${type}-${teamId}-${itemId}`
}

function selKey(teamId, talentId) {
  return `${teamId}-${talentId}`
}

function isSelected(teamId, talentId) {
  return selectedMembers.has(selKey(teamId, talentId))
}

function selectedInTeam(teamId) {
  let count = 0
  for (const k of selectedMembers) {
    if (k.startsWith(teamId + '-')) count++
  }
  return count
}

function clearSelection(teamId) {
  for (const k of [...selectedMembers]) {
    if (k.startsWith(teamId + '-')) selectedMembers.delete(k)
  }
}

function getOffsetStyle(type, teamId, itemId) {
  const k = offsetKey(type, teamId, itemId)
  const o = dragOffsets[k]
  if (!o || (o.x === 0 && o.y === 0)) return {}
  return { transform: `translate(${o.x}px, ${o.y}px)`, zIndex: 5 }
}

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

const teamsWithMembers = computed(() => {
  return store.projectView.filter(t => t.members.length > 0)
})

// Sort: teams with projects first, teams without projects last
const sortedTeams = computed(() => {
  return [...teamsWithMembers.value].sort((a, b) => {
    const ap = a.projects.length > 0 ? 0 : 1
    const bp = b.projects.length > 0 ? 0 : 1
    return ap - bp
  })
})

function membersWithProjects(team) {
  return team.members.filter(m => m.project_count > 0)
}

function membersWithoutProjects(team) {
  return team.members.filter(m => m.project_count === 0)
}

// Marquee selection handlers
function onMarqueeStart(e, teamId) {
  const sectionEl = sectionRefs.value[teamId]
  if (!sectionEl) return
  const rect = sectionEl.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  marquee.value = { teamId, startX: x, startY: y, curX: x, curY: y, sectionRect: rect }
  sectionEl.setPointerCapture(e.pointerId)
}

function updateMarqueeSelection() {
  const m = marquee.value
  if (!m) return
  const mx1 = Math.min(m.startX, m.curX)
  const my1 = Math.min(m.startY, m.curY)
  const mx2 = Math.max(m.startX, m.curX)
  const my2 = Math.max(m.startY, m.curY)

  // Clear previous selection in this team
  clearSelection(m.teamId)

  // Check each member in this team
  const teamMembers = memberRefs.value[m.teamId]
  if (!teamMembers) return
  for (const [talentId, el] of Object.entries(teamMembers)) {
    const elRect = el.getBoundingClientRect()
    const ex = elRect.left - m.sectionRect.left + elRect.width / 2
    const ey = elRect.top - m.sectionRect.top + elRect.height / 2
    if (ex >= mx1 && ex <= mx2 && ey >= my1 && ey <= my2) {
      selectedMembers.add(selKey(m.teamId, parseInt(talentId)))
    }
  }
}

// Drag handlers
function onItemPointerDown(e, teamId, type, itemId) {
  const k = offsetKey(type, teamId, itemId)
  const o = dragOffsets[k] || { x: 0, y: 0 }

  // Record start offsets for all selected members in this team (for batch drag)
  const batchStartOffsets = {}
  if (type === 'm' && isSelected(teamId, itemId) && selectedInTeam(teamId) > 1) {
    for (const sk of selectedMembers) {
      if (!sk.startsWith(teamId + '-')) continue
      const tid = parseInt(sk.split('-')[1])
      const mk = offsetKey('m', teamId, tid)
      batchStartOffsets[mk] = { ...(dragOffsets[mk] || { x: 0, y: 0 }) }
    }
  }

  dragging.value = {
    teamId, type, itemId,
    startX: e.clientX, startY: e.clientY,
    startOx: o.x, startOy: o.y,
    batchStartOffsets,
    isBatch: Object.keys(batchStartOffsets).length > 1,
  }
  hasDragged.value = false
  e.target.closest('.team-section-body')?.setPointerCapture(e.pointerId)
}

function onPointerMove(e) {
  // Marquee mode
  if (marquee.value) {
    const m = marquee.value
    m.curX = e.clientX - m.sectionRect.left
    m.curY = e.clientY - m.sectionRect.top
    updateMarqueeSelection()
    return
  }
  if (!dragging.value) return
  const d = dragging.value
  const dx = e.clientX - d.startX
  const dy = e.clientY - d.startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged.value = true

  if (d.isBatch) {
    for (const [mk, startO] of Object.entries(d.batchStartOffsets)) {
      dragOffsets[mk] = { x: startO.x + dx, y: startO.y + dy }
    }
  } else {
    const k = offsetKey(d.type, d.teamId, d.itemId)
    dragOffsets[k] = { x: d.startOx + dx, y: d.startOy + dy }
  }
  computeLines()
}

function onPointerUp(e) {
  // Marquee mode
  if (marquee.value) {
    marquee.value = null
    e.target.closest('.team-section-body')?.releasePointerCapture(e.pointerId)
    return
  }
  if (!dragging.value) return
  const d = dragging.value
  dragging.value = null
  e.target.closest('.team-section-body')?.releasePointerCapture(e.pointerId)

  if (!hasDragged.value) {
    if (d.type === 'p') {
      goToProject(d.itemId)
    } else {
      const sk = selKey(d.teamId, d.itemId)
      if (selectedMembers.has(sk)) {
        selectedMembers.delete(sk)
      } else {
        selectedMembers.add(sk)
      }
    }
  }
  if (hasDragged.value) saveOffsets()
  computeLines()
}

function computeLines() {
  const lines = {}
  for (const team of teamsWithMembers.value) {
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

.no-project-hint {
  font-size: 12px;
  font-weight: 400;
  color: #9ca3af;
}

.team-section-body {
  position: relative;
  padding: 20px 16px;
  min-height: 120px;
  touch-action: none;
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
  cursor: grab;
  transition: box-shadow 0.2s;
  user-select: none;
  touch-action: none;
}

.project-box:active {
  cursor: grabbing;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.25);
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
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.member-circle-wrap:active {
  cursor: grabbing;
}

.member-circle-wrap:hover .member-label {
  color: #3b82f6;
}

.member-circle-wrap.selected .member-circle {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}

.member-circle-wrap.selected .member-label {
  color: #3b82f6;
  font-weight: 600;
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
  transition: border-color 0.2s, box-shadow 0.2s;
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

.selection-hint {
  margin-top: 12px;
  padding: 6px 12px;
  background: #eff6ff;
  border-radius: 6px;
  font-size: 12px;
  color: #3b82f6;
  text-align: center;
}

.clear-selection {
  margin-left: 8px;
  cursor: pointer;
  text-decoration: underline;
  color: #6b7280;
}

.clear-selection:hover {
  color: #ef4444;
}

.marquee-rect {
  position: absolute;
  border: 1.5px dashed #3b82f6;
  background: rgba(59, 130, 246, 0.08);
  border-radius: 3px;
  pointer-events: none;
  z-index: 10;
}

.hidden {
  display: none;
}
</style>

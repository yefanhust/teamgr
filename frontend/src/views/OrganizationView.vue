<template>
  <div class="org-container" ref="containerRef">
    <!-- Toolbar -->
    <div class="org-toolbar">
      <van-button size="small" icon="plus" type="primary" @click="showCreateTeam = true">新建团队</van-button>
      <van-button size="small" icon="replay" @click="resetView">重置视图</van-button>
    </div>

    <!-- Canvas -->
    <div
      class="org-canvas"
      ref="canvasRef"
      @pointerdown="onCanvasPointerDown"
      @pointermove="onCanvasPointerMove"
      @pointerup="onCanvasPointerUp"
      @wheel="onWheel"
    >
      <div
        class="org-canvas-inner"
        :style="{
          transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
          transformOrigin: '0 0',
        }"
      >
        <!-- Team Cards -->
        <div
          v-for="team in store.teams"
          :key="team.id"
          class="team-card"
          :style="{ left: team.position_x + 'px', top: team.position_y + 'px' }"
          @pointerdown.stop="onTeamPointerDown($event, team)"
        >
          <div class="team-header">
            <span class="team-name">{{ team.name }}</span>
            <div class="team-actions" @pointerdown.stop>
              <van-icon name="edit" size="14" class="action-icon" @click="startEditTeam(team)" />
              <van-icon name="delete-o" size="14" class="action-icon danger" @click="confirmDeleteTeam(team)" />
            </div>
          </div>

          <!-- Members -->
          <div class="team-members">
            <div
              v-for="member in team.members"
              :key="member.talent_id"
              class="member-row"
            >
              <div class="member-info" @pointerdown.stop @click="goToTalent(member.talent_id)">
                <van-icon v-if="member.is_leader" name="star" size="12" color="#F59E0B" class="leader-icon" />
                <span class="member-name" :class="{ 'is-leader': member.is_leader }">{{ member.name }}</span>
                <span v-if="member.position_title" class="member-title">{{ member.position_title }}</span>
              </div>
              <div class="member-actions" @pointerdown.stop>
                <van-icon
                  v-if="hasLeader(team)"
                  name="edit"
                  size="12"
                  class="action-icon"
                  @click="startEditTitle(team, member)"
                />
                <van-icon
                  name="star-o"
                  size="12"
                  :color="member.is_leader ? '#F59E0B' : '#999'"
                  class="action-icon"
                  @click="handleSetLeader(team.id, member.talent_id)"
                />
                <van-icon name="cross" size="12" class="action-icon danger" @click="handleRemoveMember(team.id, member.talent_id)" />
              </div>
            </div>
          </div>

          <div class="team-footer" @pointerdown.stop>
            <van-button size="mini" icon="plus" @click="openAddMember(team)">添加成员</van-button>
          </div>
        </div>

        <!-- Empty State -->
        <div v-if="store.teams.length === 0 && !store.loading" class="empty-state">
          <div class="text-4xl mb-3">🏢</div>
          <p class="text-gray-400">暂无团队，点击上方按钮创建</p>
        </div>
      </div>
    </div>

    <!-- Create Team Dialog -->
    <van-dialog
      v-model:show="showCreateTeam"
      title="新建团队"
      show-cancel-button
      @confirm="handleCreateTeam"
    >
      <div class="px-4 py-2">
        <van-field v-model="newTeamName" label="团队名称" placeholder="请输入团队名称" />
      </div>
    </van-dialog>

    <!-- Edit Team Dialog -->
    <van-dialog
      v-model:show="showEditTeam"
      title="编辑团队"
      show-cancel-button
      @confirm="handleEditTeam"
    >
      <div class="px-4 py-2">
        <van-field v-model="editTeamName" label="团队名称" placeholder="请输入团队名称" />
      </div>
    </van-dialog>

    <!-- Delete Team Confirm -->
    <van-dialog
      v-model:show="showDeleteTeam"
      title="确认删除"
      :message="`删除团队「${deletingTeam?.name}」后不可恢复，确定？`"
      show-cancel-button
      @confirm="handleDeleteTeam"
    />

    <!-- Add Member Dialog -->
    <van-popup v-model:show="showAddMember" position="bottom" round :style="{ height: '60vh' }">
      <div class="flex flex-col h-full">
        <div class="flex items-center justify-between px-4 py-3 border-b">
          <span class="font-medium text-gray-700">添加成员到「{{ addingToTeam?.name }}」</span>
          <van-icon name="cross" size="18" class="text-gray-400" @click="showAddMember = false" />
        </div>
        <van-search v-model="memberSearchQuery" placeholder="搜索姓名..." shape="round" class="flex-shrink-0" />
        <div class="flex-1 overflow-y-auto px-4">
          <div
            v-for="talent in filteredTalents"
            :key="talent.id"
            class="flex items-center justify-between py-3 border-b border-gray-100"
          >
            <div>
              <span class="text-sm font-medium text-gray-800">{{ talent.name }}</span>
              <span v-if="talent.current_role" class="text-xs text-gray-400 ml-2">{{ talent.current_role }}</span>
            </div>
            <van-button
              v-if="!isInTeam(talent.id)"
              size="mini"
              type="primary"
              @click="handleAddMember(talent.id)"
            >
              添加
            </van-button>
            <van-tag v-else type="default" size="medium">已添加</van-tag>
          </div>
          <div v-if="filteredTalents.length === 0" class="text-center py-8 text-gray-400 text-sm">
            暂无匹配的人才
          </div>
        </div>
      </div>
    </van-popup>

    <!-- Edit Title Dialog -->
    <van-dialog
      v-model:show="showEditTitle"
      title="编辑职位"
      show-cancel-button
      @confirm="handleEditTitle"
    >
      <div class="px-4 py-2">
        <van-field v-model="editTitleValue" label="职位" placeholder="请输入职位" />
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { useOrganizationStore } from '../stores/organization'
import { useTalentStore } from '../stores/talent'

const router = useRouter()
const store = useOrganizationStore()
const talentStore = useTalentStore()

// Canvas state
const containerRef = ref(null)
const canvasRef = ref(null)
const panX = ref(0)
const panY = ref(0)
const zoom = ref(1)
const isPanning = ref(false)
const panStartX = ref(0)
const panStartY = ref(0)
const panStartPanX = ref(0)
const panStartPanY = ref(0)

// Team dragging
const draggingTeam = ref(null)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragStartTeamX = ref(0)
const dragStartTeamY = ref(0)
const hasDragged = ref(false)

// Dialogs
const showCreateTeam = ref(false)
const newTeamName = ref('')
const showEditTeam = ref(false)
const editTeamName = ref('')
const editingTeam = ref(null)
const showDeleteTeam = ref(false)
const deletingTeam = ref(null)
const showAddMember = ref(false)
const addingToTeam = ref(null)
const memberSearchQuery = ref('')
const showEditTitle = ref(false)
const editTitleValue = ref('')
const editingTitleTeam = ref(null)
const editingTitleMember = ref(null)

const filteredTalents = computed(() => {
  const q = memberSearchQuery.value.trim().toLowerCase()
  if (!q) return talentStore.talents
  return talentStore.talents.filter(t =>
    t.name.toLowerCase().includes(q) ||
    (t.name_pinyin || '').toLowerCase().includes(q)
  )
})

function isInTeam(talentId) {
  if (!addingToTeam.value) return false
  return addingToTeam.value.members.some(m => m.talent_id === talentId)
}

function hasLeader(team) {
  return team.members.some(m => m.is_leader)
}

onMounted(async () => {
  await Promise.all([
    store.fetchTeams(),
    talentStore.fetchTalents(),
  ])
})

// Canvas panning
function onCanvasPointerDown(e) {
  if (draggingTeam.value) return
  isPanning.value = true
  panStartX.value = e.clientX
  panStartY.value = e.clientY
  panStartPanX.value = panX.value
  panStartPanY.value = panY.value
  canvasRef.value?.setPointerCapture(e.pointerId)
}

function onCanvasPointerMove(e) {
  if (draggingTeam.value) {
    const dx = (e.clientX - dragStartX.value) / zoom.value
    const dy = (e.clientY - dragStartY.value) / zoom.value
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged.value = true
    draggingTeam.value.position_x = dragStartTeamX.value + dx
    draggingTeam.value.position_y = dragStartTeamY.value + dy
    return
  }
  if (!isPanning.value) return
  panX.value = panStartPanX.value + (e.clientX - panStartX.value)
  panY.value = panStartPanY.value + (e.clientY - panStartY.value)
}

function onCanvasPointerUp(e) {
  if (draggingTeam.value) {
    if (hasDragged.value) {
      store.updateTeam(draggingTeam.value.id, {
        position_x: draggingTeam.value.position_x,
        position_y: draggingTeam.value.position_y,
      })
    }
    draggingTeam.value = null
    hasDragged.value = false
    return
  }
  isPanning.value = false
  canvasRef.value?.releasePointerCapture(e.pointerId)
}

function onWheel(e) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  zoom.value = Math.max(0.3, Math.min(3, zoom.value + delta))
}

// Team dragging
function onTeamPointerDown(e, team) {
  draggingTeam.value = team
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragStartTeamX.value = team.position_x
  dragStartTeamY.value = team.position_y
  hasDragged.value = false
  canvasRef.value?.setPointerCapture(e.pointerId)
}

function resetView() {
  panX.value = 0
  panY.value = 0
  zoom.value = 1
}

function goToTalent(talentId) {
  router.push(`/talent/${talentId}`)
}

// Team CRUD
async function handleCreateTeam() {
  const name = newTeamName.value.trim()
  if (!name) { showToast('请输入团队名称'); return }
  try {
    await store.createTeam(name)
    showToast('创建成功')
    newTeamName.value = ''
  } catch (e) {
    showToast('创建失败')
  }
}

function startEditTeam(team) {
  editingTeam.value = team
  editTeamName.value = team.name
  showEditTeam.value = true
}

async function handleEditTeam() {
  const name = editTeamName.value.trim()
  if (!name) { showToast('请输入团队名称'); return }
  try {
    await store.updateTeam(editingTeam.value.id, { name })
    showToast('已更新')
  } catch (e) {
    showToast('更新失败')
  }
}

function confirmDeleteTeam(team) {
  deletingTeam.value = team
  showDeleteTeam.value = true
}

async function handleDeleteTeam() {
  try {
    await store.deleteTeam(deletingTeam.value.id)
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

// Members
function openAddMember(team) {
  addingToTeam.value = team
  memberSearchQuery.value = ''
  showAddMember.value = true
}

async function handleAddMember(talentId) {
  try {
    await store.addMember(addingToTeam.value.id, talentId)
    // Update local reference
    const updated = store.teams.find(t => t.id === addingToTeam.value.id)
    if (updated) addingToTeam.value = updated
    showToast('添加成功')
  } catch (e) {
    showToast(e.response?.data?.detail || '添加失败')
  }
}

async function handleRemoveMember(teamId, talentId) {
  try {
    await store.removeMember(teamId, talentId)
    showToast('已移除')
  } catch (e) {
    showToast('移除失败')
  }
}

async function handleSetLeader(teamId, talentId) {
  try {
    await store.setLeader(teamId, talentId)
    showToast('已设为 Leader')
  } catch (e) {
    showToast('操作失败')
  }
}

function startEditTitle(team, member) {
  editingTitleTeam.value = team
  editingTitleMember.value = member
  editTitleValue.value = member.position_title || ''
  showEditTitle.value = true
}

async function handleEditTitle() {
  try {
    await store.updateMemberTitle(
      editingTitleTeam.value.id,
      editingTitleMember.value.talent_id,
      editTitleValue.value.trim()
    )
    showToast('已更新')
  } catch (e) {
    showToast('更新失败')
  }
}
</script>

<style scoped>
.org-container {
  position: relative;
  width: 100%;
  height: calc(100vh - 110px);
  overflow: hidden;
}

.org-toolbar {
  position: absolute;
  top: 8px;
  left: 12px;
  z-index: 10;
  display: flex;
  gap: 8px;
}

.org-canvas {
  width: 100%;
  height: 100%;
  cursor: grab;
  touch-action: none;
  background:
    radial-gradient(circle, #e5e7eb 1px, transparent 1px);
  background-size: 24px 24px;
}

.org-canvas:active {
  cursor: grabbing;
}

.org-canvas-inner {
  position: relative;
  width: 100%;
  height: 100%;
}

.team-card {
  position: absolute;
  min-width: 200px;
  max-width: 320px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  cursor: move;
  user-select: none;
  touch-action: none;
}

.team-card:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.team-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #f3f4f6;
  background: #f8fafc;
  border-radius: 12px 12px 0 0;
}

.team-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.team-actions {
  display: flex;
  gap: 6px;
}

.action-icon {
  cursor: pointer;
  color: #9ca3af;
  transition: color 0.2s;
}

.action-icon:hover {
  color: #3b82f6;
}

.action-icon.danger:hover {
  color: #ef4444;
}

.team-members {
  padding: 4px 0;
  max-height: 280px;
  overflow-y: auto;
}

.member-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  transition: background 0.15s;
}

.member-row:hover {
  background: #f9fafb;
}

.member-info {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  flex: 1;
  min-width: 0;
}

.leader-icon {
  flex-shrink: 0;
}

.member-name {
  font-size: 13px;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.member-name:hover {
  color: #3b82f6;
  text-decoration: underline;
}

.member-name.is-leader {
  font-weight: 600;
  color: #b45309;
}

.member-title {
  font-size: 11px;
  color: #9ca3af;
  white-space: nowrap;
  margin-left: 4px;
}

.member-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.member-row:hover .member-actions {
  opacity: 1;
}

.team-footer {
  padding: 8px 12px;
  border-top: 1px solid #f3f4f6;
}

.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}
</style>

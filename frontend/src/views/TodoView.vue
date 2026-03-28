<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Top Navigation -->
    <TopNavBar />

    <!-- Main Tabs -->
    <van-tabs v-model:active="activeTab" sticky offset-top="52" class="todo-tabs">
      <!-- ==================== Tab 1: TODO ==================== -->
      <van-tab title="TODO" :badge="todoPendingCount || ''">
        <div class="max-w-3xl mx-auto px-4 py-4 space-y-4">
          <!-- Tag Filter -->
          <div v-if="allTags.length > 0" class="pb-1">
            <div class="flex items-center gap-2 mb-2">
              <van-checkbox
                :model-value="allSelected"
                shape="square"
                icon-size="16px"
                class="flex-shrink-0 select-all-checkbox"
                @update:model-value="selectAll"
              >
                全选
              </van-checkbox>
              <van-button
                size="mini"
                icon="sort"
                :loading="organizing"
                @click="organizeTags"
              >
                一键整理
              </van-button>
              <van-icon
                name="edit"
                size="16"
                class="text-gray-400 cursor-pointer hover:text-blue-500 ml-1"
                @click="openOrganizePromptEditor"
              />
            </div>
            <!-- Organize progress -->
            <div v-if="organizing || organizeStatus" class="mb-3 bg-gray-50 rounded-lg p-3 text-sm">
              <div v-if="organizeStatus" class="flex items-center gap-2 mb-1">
                <van-icon v-if="organizeStatus === 'done'" name="checked" color="#10B981" size="14" />
                <van-icon v-else-if="organizeStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
                <van-loading v-else size="14" />
                <span class="text-gray-600">{{ organizeStatusText }}</span>
              </div>
              <pre v-if="thinkingStream" ref="thinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed italic">{{ thinkingStream }}</pre>
              <pre v-if="organizeStream" ref="organizePre" class="text-xs text-gray-500 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono leading-relaxed">{{ organizeStream }}</pre>
            </div>
            <!-- Hierarchical tags display -->
            <template v-if="tagTree.length > 0">
              <div v-for="group in tagTree" :key="group.id" class="mb-2">
                <div class="flex gap-2 flex-wrap items-center">
                  <span class="text-xs text-gray-500 font-medium flex-shrink-0" :style="{ color: group.color }">{{ group.name }}</span>
                  <template v-for="tag in group.children" :key="tag.id">
                    <input
                      v-if="editingTagId === tag.id"
                      v-model="editingTagName"
                      class="edit-tag-input"
                      @blur="finishEditTag(tag)"
                      @keypress.enter="finishEditTag(tag)"
                      @keydown.escape="cancelEditTag"
                      ref="tagEditInput"
                    />
                    <van-tag
                      v-else
                      :type="selectedTagIds.has(tag.id) ? 'primary' : 'default'"
                      :color="selectedTagIds.has(tag.id) ? tag.color : undefined"
                      size="medium"
                      class="cursor-pointer tag-closeable"
                      closeable
                      @click="toggleTag(tag.id)"
                      @dblclick.stop="startEditTag(tag)"
                      @close.stop="confirmDeleteTag(tag)"
                    >
                      {{ tag.name }}
                    </van-tag>
                  </template>
                </div>
              </div>
            </template>
            <!-- Flat tags (no hierarchy yet) -->
            <div v-if="orphanTags.length > 0" class="flex gap-2 flex-wrap items-center">
              <template v-for="tag in orphanTags" :key="tag.id">
                <input
                  v-if="editingTagId === tag.id"
                  v-model="editingTagName"
                  class="edit-tag-input"
                  @blur="finishEditTag(tag)"
                  @keypress.enter="finishEditTag(tag)"
                  @keydown.escape="cancelEditTag"
                  ref="tagEditInput"
                />
                <van-tag
                  v-else
                  :type="selectedTagIds.has(tag.id) ? 'primary' : 'default'"
                  :color="selectedTagIds.has(tag.id) ? tag.color : undefined"
                  size="medium"
                  class="cursor-pointer tag-closeable"
                  closeable
                  @click="toggleTag(tag.id)"
                  @dblclick.stop="startEditTag(tag)"
                  @close.stop="confirmDeleteTag(tag)"
                >
                  {{ tag.name }}
                </van-tag>
              </template>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="flex justify-center py-8">
            <van-loading size="28px">加载中...</van-loading>
          </div>

          <template v-else>
            <!-- Pending List -->
            <section>
              <h2 class="text-sm font-semibold text-gray-500 mb-3 flex items-center gap-2">
                <span class="w-1 h-4 bg-blue-500 rounded-full inline-block"></span>
                任务
                <span v-if="filteredPending.length" class="text-xs text-gray-400 font-normal">({{ filteredPending.length }})</span>
              </h2>

              <div v-if="filteredPending.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
                <p class="text-sm">暂无任务</p>
              </div>

              <div v-else class="space-y-2">
                <div v-for="item in filteredPending" :key="item.id">
                  <van-swipe-cell>
                    <div
                      class="bg-white rounded-xl shadow-sm p-3 flex items-center gap-3"
                      :class="item.high_priority ? 'border-l-4 border-red-400' : ''"
                    >
                      <van-checkbox
                        :model-value="false"
                        shape="round"
                        icon-size="20px"
                        @update:model-value="handleComplete(item.id)"
                      />
                      <div class="flex-1 min-w-0" @click="openDetail(item)">
                        <div class="flex items-center gap-2">
                          <input
                            v-if="inlineEditId === item.id"
                            v-model="inlineEditTitle"
                            class="edit-title-input"
                            @blur="finishInlineEdit(item)"
                            @keypress.enter="finishInlineEdit(item)"
                            @keydown.escape="cancelInlineEdit"
                            @click.stop
                            ref="titleEditInput"
                          />
                          <span
                            v-else
                            class="text-sm text-gray-800 truncate min-w-0"
                            @dblclick.stop="startInlineEdit(item)"
                          >{{ item.title }}</span>
                          <van-tag v-if="item.high_priority" type="danger" size="small" class="flex-shrink-0">高优</van-tag>
                          <!-- Subtask progress badge -->
                          <span
                            v-if="item.children_count > 0"
                            class="text-xs px-1.5 py-0.5 rounded flex-shrink-0 cursor-pointer"
                            :class="item.children_completed_count === item.children_count ? 'bg-green-50 text-green-600' : 'bg-blue-50 text-blue-500'"
                            @click.stop="toggleExpand(item.id)"
                          >
                            {{ item.children_completed_count }}/{{ item.children_count }}
                          </span>
                        </div>
                        <div class="flex items-center gap-1 mt-1 flex-wrap">
                          <van-tag
                            v-for="tag in (item.tags || [])"
                            :key="tag.id"
                            :color="tag.color"
                            size="small"
                            plain
                          >
                            {{ tag.name }}
                          </van-tag>
                          <span v-if="item.description" class="text-xs text-gray-400 truncate max-w-[120px]">{{ item.description }}</span>
                          <span class="text-xs text-gray-400">{{ formatDateTime(item.created_at) }}</span>
                          <!-- Working time display -->
                          <span
                            v-if="item.work_status === 'in_progress'"
                            class="text-xs px-1.5 py-0.5 rounded bg-green-50 text-green-600 font-medium"
                          >
                            {{ formatWorkingTime(item) }}
                          </span>
                          <span
                            v-else-if="(item.total_working_seconds || 0) > 0"
                            class="text-xs px-1.5 py-0.5 rounded bg-gray-50 text-gray-500"
                          >
                            {{ formatSeconds(item.total_working_seconds) }}
                          </span>
                          <span
                            v-if="(item.stop_count || 0) > 0"
                            class="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-400"
                            :title="`已停止 ${item.stop_count} 次`"
                          >
                            停{{ item.stop_count }}次
                          </span>
                          <span
                            v-if="item.deadline"
                            class="text-xs px-1.5 py-0.5 rounded"
                            :class="item.deadline_urgent ? 'bg-red-50 text-red-500 font-medium' : 'bg-gray-50 text-gray-500'"
                            @click.stop="openDeadlinePicker(item)"
                          >
                            截止 {{ item.deadline }}{{ item.deadline_time ? ' ' + item.deadline_time : '' }}
                          </span>
                          <span
                            v-else
                            class="text-xs text-blue-400 cursor-pointer"
                            @click.stop="openDeadlinePicker(item)"
                          >
                            + 截止日期
                          </span>
                          <span v-if="item.repeat_rule" class="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-500">
                            {{ repeatLabel(item) }}
                          </span>
                        </div>
                      </div>
                      <!-- Start / Pause / Stop buttons -->
                      <van-icon
                        v-if="item.work_status !== 'in_progress'"
                        name="play-circle-o"
                        size="20"
                        color="#10B981"
                        class="cursor-pointer flex-shrink-0"
                        @click="handleStart(item.id)"
                      />
                      <van-icon
                        v-if="item.work_status === 'in_progress'"
                        name="pause-circle-o"
                        size="20"
                        color="#F59E0B"
                        class="cursor-pointer flex-shrink-0"
                        @click="handlePause(item.id)"
                      />
                      <van-icon
                        v-if="item.work_status === 'in_progress' || item.work_status === 'paused'"
                        name="stop-circle-o"
                        size="20"
                        color="#EF4444"
                        class="cursor-pointer flex-shrink-0"
                        @click="handleStop(item.id)"
                      />
                      <!-- Expand/Add subtasks -->
                      <van-icon
                        name="plus"
                        size="16"
                        :color="expandedIds.has(item.id) ? '#3B82F6' : '#9CA3AF'"
                        class="cursor-pointer flex-shrink-0"
                        @click="toggleExpand(item.id)"
                      />
                      <van-icon
                        v-if="!item.high_priority"
                        name="arrow-up"
                        size="16"
                        color="#EF4444"
                        class="cursor-pointer"
                        @click="togglePriority(item, true)"
                      />
                      <van-icon
                        v-else
                        name="arrow-down"
                        size="16"
                        color="#9CA3AF"
                        class="cursor-pointer"
                        @click="togglePriority(item, false)"
                      />
                      <van-icon
                        name="delete-o"
                        size="16"
                        color="#9CA3AF"
                        class="cursor-pointer"
                        @click="handleDelete(item.id)"
                      />
                    </div>
                  </van-swipe-cell>
                  <!-- Expanded subtasks -->
                  <div v-if="expandedIds.has(item.id)" class="ml-8 mt-1 space-y-1">
                    <div
                      v-for="child in (item.children || [])"
                      :key="child.id"
                      class="bg-gray-50 rounded-lg p-2 flex items-center gap-2"
                    >
                      <van-checkbox
                        :model-value="child.completed"
                        shape="round"
                        icon-size="16px"
                        @update:model-value="handleComplete(child.id)"
                      />
                      <span
                        class="text-sm flex-1 min-w-0 truncate"
                        :class="child.completed ? 'text-gray-400 line-through' : 'text-gray-700'"
                      >{{ child.title }}</span>
                      <!-- Child start/pause/stop -->
                      <template v-if="!child.completed">
                        <span
                          v-if="child.work_status === 'in_progress'"
                          class="text-xs text-green-600"
                        >{{ formatWorkingTime(child) }}</span>
                        <span
                          v-else-if="(child.total_working_seconds || 0) > 0"
                          class="text-xs text-gray-400"
                        >{{ formatSeconds(child.total_working_seconds) }}</span>
                        <span
                          v-if="(child.stop_count || 0) > 0"
                          class="text-xs text-red-400"
                        >停{{ child.stop_count }}次</span>
                        <van-icon
                          v-if="child.work_status !== 'in_progress'"
                          name="play-circle-o"
                          size="16"
                          color="#10B981"
                          class="cursor-pointer flex-shrink-0"
                          @click="handleStart(child.id)"
                        />
                        <van-icon
                          v-if="child.work_status === 'in_progress'"
                          name="pause-circle-o"
                          size="16"
                          color="#F59E0B"
                          class="cursor-pointer flex-shrink-0"
                          @click="handlePause(child.id)"
                        />
                        <van-icon
                          v-if="child.work_status === 'in_progress' || child.work_status === 'paused'"
                          name="stop-circle-o"
                          size="16"
                          color="#EF4444"
                          class="cursor-pointer flex-shrink-0"
                          @click="handleStop(child.id)"
                        />
                      </template>
                      <van-icon
                        name="delete-o"
                        size="14"
                        color="#D1D5DB"
                        class="cursor-pointer flex-shrink-0"
                        @click="handleDelete(child.id)"
                      />
                    </div>
                    <!-- Add subtask input -->
                    <div class="flex items-center gap-2 mt-1">
                      <van-field
                        v-model="subtaskInputs[item.id]"
                        placeholder="添加子任务..."
                        class="todo-input flex-1 subtask-input"
                        size="small"
                        @keyup.enter="addSubtask(item.id)"
                      />
                      <van-button
                        size="small"
                        type="primary"
                        icon="plus"
                        :disabled="!subtaskInputs[item.id]?.trim()"
                        @click="addSubtask(item.id)"
                      >
                        添加
                      </van-button>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </template>

          <!-- Input Section -->
          <div class="bg-white rounded-xl shadow-sm p-4">
            <div class="flex gap-2 items-center">
              <van-field
                v-model="newTitle"
                placeholder="添加新任务..."
                class="todo-input flex-1"
                @keyup.enter="addTodo"
              />
              <VoiceInputButton v-model="newTitle" />
              <van-button
                type="primary"
                icon="plus"
                :disabled="!newTitle.trim()"
                :loading="adding"
                @click="addTodo"
              >
                添加
              </van-button>
            </div>
            <div class="flex items-center gap-4 mt-2">
              <van-checkbox v-model="newHighPriority" shape="square" icon-size="16px">
                <span class="text-sm text-gray-500">高优先级</span>
              </van-checkbox>
              <span
                class="text-sm cursor-pointer"
                :class="newDeadline ? 'text-blue-500' : 'text-gray-400'"
                @click="showNewDeadlinePicker = true"
              >
                {{ newDeadline ? '截止 ' + newDeadline + (newDeadlineTime ? ' ' + newDeadlineTime : '') : '+ 截止日期' }}
              </span>
              <span
                v-if="newDeadline"
                class="text-xs text-gray-400 cursor-pointer"
                @click="newDeadline = ''; newDeadlineTime = ''"
              >
                清除
              </span>
            </div>
          </div>
        </div>
      </van-tab>

      <!-- ==================== Tab 2: 项目管理 ==================== -->
      <van-tab title="项目管理">
        <div class="max-w-3xl mx-auto px-4 py-4 space-y-4">
          <!-- Header: Update button + Create button -->
          <div class="flex items-center justify-between">
            <van-button type="primary" icon="edit" size="small" @click="showPmUpdatePopup = true">Update</van-button>
            <van-button plain type="primary" icon="plus" size="small" @click="showPmCreatePopup = true">新建项目</van-button>
          </div>

          <!-- Sub tabs: 项目列表 / 时间看板 / 人员看板 -->
          <van-tabs v-model:active="pmSubTab" type="card" class="vibe-tabs">
            <!-- Sub-tab: 项目列表 -->
            <van-tab title="项目列表">
              <div ref="pmListRef" class="space-y-3 mt-3">
                <div v-if="pmProjects.length === 0" class="bg-white rounded-xl shadow-sm p-8 text-center">
                  <p class="text-gray-400 text-sm mb-3">暂无项目</p>
                  <van-button size="small" plain type="primary" icon="plus" @click="showPmCreatePopup = true">创建第一个项目</van-button>
                </div>
                <template v-for="(proj, idx) in pmTopProjects" :key="proj.id">
                  <!-- Drop indicator line -->
                  <div v-if="pmDrag.active && pmDrag.dropIndex === idx" class="h-0.5 bg-blue-500 rounded-full mx-2 -my-1 relative z-10"></div>
                  <van-swipe-cell class="pm-project-item" :class="{ 'opacity-40': pmDrag.active && pmDrag.projectId === proj.id }">
                    <div class="bg-white rounded-xl shadow-sm overflow-hidden flex" @click="openProjectInfo(proj.id)">
                      <!-- Drag handle -->
                      <div class="flex items-center px-2 text-gray-300 cursor-grab active:cursor-grabbing touch-none flex-shrink-0"
                        @pointerdown.stop="onPmDragStart($event, proj.id, idx)"
                        @click.stop
                      >
                        <span class="text-base leading-none select-none">☰</span>
                      </div>
                      <div class="p-4 pl-1 flex-1 min-w-0">
                        <div class="flex items-center justify-between mb-2">
                          <div class="flex items-center gap-2">
                            <span class="w-2 h-2 rounded-full" :class="proj.status === 'active' ? 'bg-green-500' : proj.status === 'suspended' ? 'bg-yellow-500' : proj.status === 'completed' ? 'bg-blue-400' : 'bg-gray-300'"></span>
                            <span class="font-medium text-gray-800">{{ proj.name }}</span>
                          </div>
                          <div class="flex items-center gap-2">
                            <StatusPicker size="sm" :model-value="proj.status" @update:model-value="changePmStatus(proj.id, $event)" @click.stop />
                            <van-icon name="delete-o" size="16" color="#EF4444" class="pm-delete-btn cursor-pointer" @click.stop="deletePmProject(proj.id)" />
                            <van-icon name="arrow" size="14" color="#999" />
                          </div>
                        </div>
                        <p v-if="proj.description" class="text-xs text-gray-400 mb-2 line-clamp-1">{{ proj.description }}</p>
                        <div class="flex items-center gap-4 text-xs text-gray-400">
                          <span><van-icon name="friends-o" size="12" /> {{ proj.member_count }} 人</span>
                          <span><van-icon name="notes-o" size="12" /> {{ proj.update_count }} 条更新</span>
                          <span v-if="proj.last_update_at">最近: {{ formatShortDate(proj.last_update_at) }}</span>
                        </div>
                        <!-- Sub-projects -->
                        <div v-if="proj.children && proj.children.length > 0" class="mt-3 pl-3 border-l-2 border-gray-100 space-y-2">
                          <div v-for="child in sortedChildren(proj.children)" :key="child.id"
                            class="flex items-center justify-between p-2 bg-gray-50 rounded-lg cursor-pointer transition-opacity"
                            :class="{ 'opacity-40': child.status === 'completed' }"
                            @click.stop="openProjectInfo(child.id)"
                          >
                            <div class="flex items-center gap-2">
                              <span class="w-1.5 h-1.5 rounded-full" :class="child.status === 'active' ? 'bg-green-400' : child.status === 'suspended' ? 'bg-yellow-400' : child.status === 'completed' ? 'bg-blue-400' : 'bg-gray-300'"></span>
                              <span class="text-sm text-gray-700">{{ child.name }}</span>
                            </div>
                            <div class="flex items-center gap-2">
                              <StatusPicker size="sm" :model-value="child.status" @update:model-value="changePmStatus(child.id, $event)" @click.stop />
                              <span class="text-xs text-gray-400">{{ child.member_count }}人 / {{ child.update_count }}更新</span>
                              <van-icon name="delete-o" size="14" color="#EF4444" class="pm-delete-btn cursor-pointer" @click.stop="deletePmProject(child.id)" />
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <template #right>
                      <van-button square type="danger" text="删除" class="h-full" @click="deletePmProject(proj.id)" />
                    </template>
                  </van-swipe-cell>
                </template>
                <!-- Drop indicator at the end -->
                <div v-if="pmDrag.active && pmDrag.dropIndex === pmTopProjects.length" class="h-0.5 bg-blue-500 rounded-full mx-2 -mt-1"></div>
              </div>
            </van-tab>

            <!-- Sub-tab: 时间看板 -->
            <van-tab title="时间看板">
              <div class="mt-3 space-y-3">
                <div class="flex items-center gap-2 mb-2">
                  <van-tag :type="pmTimeRange === 'week' ? 'primary' : 'default'" size="medium" class="cursor-pointer" @click="pmTimeRange = 'week'; loadPmTimeline()">本周</van-tag>
                  <van-tag :type="pmTimeRange === 'month' ? 'primary' : 'default'" size="medium" class="cursor-pointer" @click="pmTimeRange = 'month'; loadPmTimeline()">本月</van-tag>
                  <van-tag :type="pmTimeRange === 'all' ? 'primary' : 'default'" size="medium" class="cursor-pointer" @click="pmTimeRange = 'all'; loadPmTimeline()">全部</van-tag>
                </div>
                <div v-if="Object.keys(pmTimeline.groups || {}).length === 0" class="bg-white rounded-xl shadow-sm p-8 text-center">
                  <p class="text-gray-400 text-sm">该时间段暂无更新记录</p>
                </div>
                <div v-for="(updates, dateKey) in (pmTimeline.groups || {})" :key="dateKey" class="bg-white rounded-xl shadow-sm overflow-hidden">
                  <div class="px-4 py-2 bg-gray-50 border-b border-gray-100">
                    <span class="text-sm font-medium text-gray-600">{{ dateKey }}</span>
                    <span class="text-xs text-gray-400 ml-2">{{ updates.length }} 条更新</span>
                  </div>
                  <!-- Group by project within each date -->
                  <div v-for="pg in groupUpdatesByProject(updates)" :key="pg.project_id" class="border-b border-gray-100 last:border-b-0">
                    <div class="px-4 py-2 flex items-center gap-2 bg-blue-50/50">
                      <van-tag type="primary" size="small" plain>{{ pg.project_name }}</van-tag>
                      <span class="text-xs text-gray-400">{{ pg.updates.length }} 条</span>
                    </div>
                    <div class="divide-y divide-gray-50">
                      <div v-for="upd in pg.updates" :key="upd.id" class="px-4 py-2 pl-6">
                        <div class="flex items-center gap-2 mb-1">
                          <span class="text-sm font-medium text-gray-700">{{ upd.talent_name }}</span>
                        </div>
                        <p class="text-sm text-gray-600">{{ upd.parsed_data?.progress || upd.raw_input }}</p>
                        <div v-if="upd.parsed_data?.blockers" class="text-xs text-red-400 mt-1">阻碍: {{ upd.parsed_data.blockers }}</div>
                        <div v-if="upd.parsed_data?.next_steps" class="text-xs text-blue-400 mt-1">下一步: {{ upd.parsed_data.next_steps }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </van-tab>

            <!-- Sub-tab: 人员看板 -->
            <van-tab title="人员看板">
              <div class="mt-3 space-y-3">
                <div v-if="pmMembers.length === 0" class="bg-white rounded-xl shadow-sm p-8 text-center">
                  <p class="text-gray-400 text-sm">暂无人员参与数据</p>
                </div>
                <div v-for="member in pmMembers" :key="member.talent_id" class="bg-white rounded-xl shadow-sm overflow-hidden">
                  <div class="px-4 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                    <span class="font-medium text-gray-800"><van-icon name="user-o" size="14" class="mr-1" />{{ member.talent_name }}</span>
                    <span class="text-xs text-gray-400">参与 {{ member.projects.length }} 个项目</span>
                  </div>
                  <div class="divide-y divide-gray-50">
                    <div v-for="mp in member.projects" :key="mp.project_id" class="px-4 py-3">
                      <div class="flex items-center justify-between mb-1">
                        <div class="flex items-center gap-2">
                          <span class="text-sm font-medium text-gray-700">{{ mp.project_name }}</span>
                          <van-tag v-if="mp.role" size="small" plain type="primary">{{ mp.role }}</van-tag>
                        </div>
                        <StatusPicker size="sm" :model-value="mp.project_status" @update:model-value="changePmStatus(mp.project_id, $event)" />
                      </div>
                      <p v-if="mp.latest_update" class="text-xs text-gray-500">最新: {{ mp.latest_update.parsed_data?.progress || mp.latest_update.raw_input }}</p>
                      <p v-if="mp.latest_update?.parsed_data?.completion_pct != null" class="mt-1">
                        <van-progress :percentage="mp.latest_update.parsed_data.completion_pct" stroke-width="6" />
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </van-tab>
          </van-tabs>
        </div>
      </van-tab>

      <!-- ==================== Tab 3: 研发 ==================== -->
      <van-tab title="研发">
        <div class="max-w-3xl mx-auto px-4 py-4">
          <van-tabs v-model:active="vibeTab" type="card" class="vibe-tabs">
            <!-- Sub-tab: 需求 -->
            <van-tab title="需求" :badge="vibeRequirements.length || ''">
              <div class="py-3 space-y-3">
                <!-- Tag filter for requirements (separate from TODO tags) -->
                <div v-if="reqAllTags.length > 0" class="pb-1">
                  <div class="flex items-center gap-2 mb-2">
                    <van-checkbox
                      :model-value="reqAllSelected"
                      shape="square"
                      icon-size="16px"
                      class="flex-shrink-0 select-all-checkbox"
                      @update:model-value="reqSelectAll"
                    >
                      全选
                    </van-checkbox>
                    <van-button
                      size="mini"
                      icon="sort"
                      :loading="reqOrganizing"
                      @click="organizeReqTags"
                    >
                      一键整理
                    </van-button>
                  </div>
                  <!-- Organize progress for requirement tags -->
                  <div v-if="reqOrganizing || reqOrganizeStatus" class="mb-3 bg-gray-50 rounded-lg p-3 text-sm">
                    <div v-if="reqOrganizeStatus" class="flex items-center gap-2 mb-1">
                      <van-icon v-if="reqOrganizeStatus === 'done'" name="checked" color="#10B981" size="14" />
                      <van-icon v-else-if="reqOrganizeStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
                      <van-loading v-else size="14" />
                      <span class="text-gray-600">{{ reqOrganizeStatusText }}</span>
                    </div>
                    <pre v-if="reqThinkingStream" ref="reqThinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto">{{ reqThinkingStream }}</pre>
                    <pre v-if="reqOrganizeStream" ref="reqOrganizePre" class="text-xs text-green-600 whitespace-pre-wrap max-h-32 overflow-y-auto mt-1">{{ reqOrganizeStream }}</pre>
                  </div>
                  <template v-if="reqTagTree.length > 0">
                    <div v-for="group in reqTagTree" :key="'req-'+group.id" class="mb-2">
                      <div class="flex gap-2 flex-wrap items-center">
                        <span class="text-xs text-gray-500 font-medium flex-shrink-0" :style="{ color: group.color }">{{ group.name }}</span>
                        <van-tag
                          v-for="tag in group.children"
                          :key="tag.id"
                          :type="reqSelectedTagIds.has(tag.id) ? 'primary' : 'default'"
                          :color="reqSelectedTagIds.has(tag.id) ? tag.color : undefined"
                          size="medium"
                          class="cursor-pointer"
                          @click="reqToggleTag(tag.id)"
                        >
                          {{ tag.name }}
                        </van-tag>
                      </div>
                    </div>
                  </template>
                  <div v-if="reqOrphanTags.length > 0" class="flex gap-2 flex-wrap items-center">
                    <van-tag
                      v-for="tag in reqOrphanTags"
                      :key="tag.id"
                      :type="reqSelectedTagIds.has(tag.id) ? 'primary' : 'default'"
                      :color="reqSelectedTagIds.has(tag.id) ? tag.color : undefined"
                      size="medium"
                      class="cursor-pointer"
                      @click="reqToggleTag(tag.id)"
                    >
                      {{ tag.name }}
                    </van-tag>
                  </div>
                </div>

                <!-- Batch actions -->
                <div v-if="filteredRequirements.length > 0" class="flex items-center gap-3">
                  <van-checkbox
                    :model-value="allReqSelected"
                    shape="square"
                    icon-size="16px"
                    class="flex-shrink-0 select-all-checkbox"
                    @update:model-value="toggleReqSelectAll"
                  >
                    <span class="text-sm text-gray-500">全选</span>
                  </van-checkbox>
                  <van-button
                    v-if="selectedReqIds.size > 0"
                    size="small"
                    type="primary"
                    icon="guide-o"
                    :loading="batchSubmitting"
                    @click="submitSelectedRequirements"
                  >
                    提交选中 ({{ selectedReqIds.size }})
                  </van-button>
                  <span v-if="batchSubmitProgress" class="text-xs text-gray-400">{{ batchSubmitProgress }}</span>
                </div>

                <!-- Requirements list -->
                <div v-if="filteredRequirements.length === 0 && !addingReq" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
                  <p class="text-sm">暂无需求</p>
                  <p class="text-xs mt-1">在下方创建新需求，完善后点击"提交"进入研发</p>
                </div>
                <div v-for="item in filteredRequirements" :key="item.id" class="bg-white rounded-xl shadow-sm p-3">
                  <div class="flex items-start gap-3">
                    <van-checkbox
                      :model-value="selectedReqIds.has(item.id)"
                      shape="square"
                      icon-size="16px"
                      class="flex-shrink-0 mt-1"
                      @update:model-value="toggleReqSelection(item.id)"
                    />
                    <div class="flex-1 min-w-0" @click="openDetail(item)">
                      <div class="flex items-start gap-2">
                        <span class="text-sm text-gray-800 font-medium min-w-0 break-words">{{ item.title }}</span>
                        <van-tag v-if="item.high_priority" type="danger" size="small" class="flex-shrink-0">高优</van-tag>
                      </div>
                      <p v-if="item.description" class="text-xs text-gray-400 mt-1 whitespace-pre-wrap line-clamp-3">{{ item.description }}</p>
                      <div class="flex items-center gap-1 mt-1 flex-wrap">
                        <van-tag
                          v-for="tag in (item.tags || [])"
                          :key="tag.id"
                          :color="tag.color"
                          size="small"
                          plain
                        >
                          {{ tag.name }}
                        </van-tag>
                        <span class="text-xs text-gray-400">{{ formatDateTime(item.created_at) }}</span>
                      </div>
                      <!-- Action buttons -->
                      <div class="flex items-center gap-2 mt-2">
                        <van-button
                          size="small"
                          type="primary"
                          icon="guide-o"
                          :loading="submittingReqId === item.id"
                          @click.stop="submitRequirement(item)"
                        >
                          提交
                        </van-button>
                        <van-button
                          size="small"
                          plain
                          icon="delete-o"
                          @click.stop="deleteRequirement(item)"
                        />
                      </div>
                    </div>
                    <van-icon
                      v-if="!item.high_priority"
                      name="arrow-up"
                      size="16"
                      color="#EF4444"
                      class="cursor-pointer flex-shrink-0 mt-1"
                      @click="togglePriority(item, true)"
                    />
                    <van-icon
                      v-else
                      name="arrow-down"
                      size="16"
                      color="#9CA3AF"
                      class="cursor-pointer flex-shrink-0 mt-1"
                      @click="togglePriority(item, false)"
                    />
                  </div>
                </div>

                <!-- Requirement input -->
                <div class="bg-white rounded-xl shadow-sm p-4">
                  <div class="flex gap-2 items-start">
                    <van-field
                      v-model="newReqTitle"
                      type="textarea"
                      placeholder="添加新需求..."
                      class="todo-input flex-1"
                      autosize
                      rows="1"
                      @keyup.enter="addRequirement"
                    />
                    <VoiceInputButton v-model="newReqTitle" />
                    <van-button
                      type="primary"
                      icon="plus"
                      :disabled="!newReqTitle.trim()"
                      :loading="addingReq"
                      @click="addRequirement"
                    >
                      添加
                    </van-button>
                  </div>
                  <div class="flex items-center gap-4 mt-2">
                    <van-checkbox v-model="newReqHighPriority" shape="square" icon-size="16px">
                      <span class="text-sm text-gray-500">高优先级</span>
                    </van-checkbox>
                  </div>
                </div>
              </div>
            </van-tab>

            <!-- Sub-tab: 规划中 -->
            <van-tab title="规划中" :badge="vibePlanning.length || ''">
              <div class="py-3 space-y-2">
                <div v-if="vibePlanning.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
                  <p class="text-sm">暂无规划中的任务</p>
                </div>
                <div v-for="item in vibePlanning" :key="item.id" class="bg-white rounded-xl shadow-sm p-3">
                  <div class="flex items-start gap-3">
                    <div class="flex-shrink-0 mt-1">
                      <span class="inline-block w-2 h-2 rounded-full bg-indigo-400 animate-pulse"></span>
                    </div>
                    <div class="flex-1 min-w-0">
                      <div class="flex items-start gap-2">
                        <span class="text-sm text-gray-800 font-medium min-w-0 break-words">{{ item.title }}</span>
                        <van-tag color="#6366F1" size="small" class="flex-shrink-0">规划中</van-tag>
                        <van-tag v-if="item.high_priority" type="danger" size="small" class="flex-shrink-0">高优</van-tag>
                      </div>
                      <!-- Plan content -->
                      <div v-if="editingPlanId === item.id" class="mt-2">
                        <div class="flex items-center gap-1 mb-1">
                          <VoiceInputButton v-model="editingPlanContent" :size="14" />
                        </div>
                        <textarea
                          ref="planEditArea"
                          v-model="editingPlanContent"
                          class="w-full text-xs text-gray-700 bg-indigo-50 border border-indigo-200 rounded-lg p-2.5 leading-relaxed resize-y min-h-[200px] max-h-[70vh] outline-none focus:border-indigo-400"
                          @blur="finishEditPlan(item)"
                          @keydown.escape="cancelEditPlan"
                          @input="autoResizePlanTextarea"
                        ></textarea>
                      </div>
                      <div
                        v-else-if="item.vibe_plan"
                        class="mt-2 bg-indigo-50 rounded-lg p-2 border border-indigo-100 cursor-pointer"
                        @dblclick.stop="startEditPlan(item)"
                      >
                        <div class="flex items-center gap-1 mb-0.5">
                          <van-icon name="notes-o" size="12" color="#6366F1" />
                          <span class="text-xs font-medium text-indigo-600">实现计划</span>
                          <span class="text-xs text-gray-400 ml-auto">双击编辑</span>
                        </div>
                        <div class="text-sm text-gray-600 leading-snug vibe-summary-content" v-html="renderMarkdown(item.vibe_plan)"></div>
                      </div>
                      <div
                        v-else
                        class="mt-2 bg-gray-50 rounded-lg p-2.5 border border-dashed border-gray-200 text-center cursor-pointer"
                        @dblclick.stop="startEditPlan(item)"
                      >
                        <span class="text-xs text-gray-400">暂无计划，双击添加</span>
                      </div>
                      <div class="flex items-center gap-1 mt-1 flex-wrap">
                        <van-tag
                          v-for="tag in (item.tags || [])"
                          :key="tag.id"
                          :color="tag.color"
                          size="small"
                          plain
                        >
                          {{ tag.name }}
                        </van-tag>
                      </div>
                      <!-- User suggestion input -->
                      <div class="mt-2">
                        <div class="flex items-center gap-1 mb-1">
                          <VoiceInputButton v-model="rethinkComments[item.id]" :size="14" />
                        </div>
                        <textarea
                          v-model="rethinkComments[item.id]"
                          class="w-full text-sm text-gray-700 bg-amber-50 border border-amber-200 rounded-lg p-2 leading-relaxed resize-y min-h-[48px] max-h-[200px] outline-none focus:border-amber-400"
                          placeholder="输入你对计划的修改建议..."
                          rows="2"
                        ></textarea>
                      </div>
                      <!-- Action buttons -->
                      <div class="flex items-center gap-2 mt-2">
                        <van-button
                          size="small"
                          type="primary"
                          icon="success"
                          @click="approvePlan(item)"
                        >
                          同意
                        </van-button>
                        <van-button
                          size="small"
                          plain
                          icon="replay"
                          @click="rethinkPlan(item)"
                          :loading="rethinkingId === item.id"
                          :disabled="!rethinkComments[item.id]?.trim()"
                        >
                          三思而行
                        </van-button>
                        <van-button
                          size="small"
                          plain
                          icon="delete-o"
                          type="danger"
                          @click="deleteVibeTask(item)"
                        >
                          删除
                        </van-button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </van-tab>

            <!-- Sub-tab: 实现中 -->
            <van-tab title="实现中" :badge="vibePending.length || ''">
              <div class="py-3 space-y-2">
                <div v-if="vibePending.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
                  <p class="text-sm">暂无实现中的任务</p>
                  <p class="text-xs mt-1">在"需求"中创建需求并提交即可开始研发</p>
                </div>
                <div v-for="item in vibePending" :key="item.id" class="bg-white rounded-xl shadow-sm p-3">
                  <div class="flex items-center gap-3">
                    <div class="flex-shrink-0">
                      <span class="inline-block w-2 h-2 rounded-full" :class="item.vibe_status === 'implementing' ? 'bg-yellow-400 animate-pulse' : 'bg-blue-400'"></span>
                    </div>
                    <div class="flex-1 min-w-0" @click="openDetail(item)">
                      <div class="flex items-start gap-2">
                        <span class="text-sm text-gray-800 font-medium min-w-0 break-words">{{ item.title }}</span>
                        <van-tag v-if="item.high_priority" type="danger" size="small" class="flex-shrink-0">高优</van-tag>
                        <van-tag v-if="item.vibe_status === 'implementing'" color="#F59E0B" size="small" class="flex-shrink-0">实现中</van-tag>
                      </div>
                      <p v-if="item.description" class="text-xs text-gray-400 mt-1 whitespace-pre-wrap line-clamp-3">{{ item.description }}</p>
                      <div class="flex items-center gap-1 mt-1 flex-wrap">
                        <van-tag
                          v-for="tag in (item.tags || [])"
                          :key="tag.id"
                          :color="tag.color"
                          size="small"
                          plain
                        >
                          {{ tag.name }}
                        </van-tag>
                        <span class="text-xs text-gray-400">{{ formatDateTime(item.created_at) }}</span>
                      </div>
                      <div class="flex items-center gap-2 mt-2">
                        <van-button
                          size="small"
                          plain
                          icon="delete-o"
                          type="danger"
                          @click.stop="deleteVibeTask(item)"
                        >
                          删除
                        </van-button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </van-tab>

            <!-- Sub-tab: 待验证 -->
            <van-tab title="待验证" :badge="vibeVerifying.length || ''">
              <div class="py-3 space-y-2">
                <div v-if="vibeVerifying.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
                  <p class="text-sm">暂无待验证的任务</p>
                </div>
                <div v-for="item in vibeVerifying" :key="item.id" class="bg-white rounded-xl shadow-sm p-3">
                  <div class="flex items-start gap-3">
                    <van-loading v-if="item.vibe_status === 'committing'" size="20px" class="mt-0.5" />
                    <div class="flex-1 min-w-0" @click="openDetail(item)">
                      <div class="flex items-start gap-2">
                        <span class="text-sm text-gray-800 min-w-0 break-words">{{ item.title }}</span>
                        <van-tag v-if="item.vibe_status === 'committing'" color="#F59E0B" size="small">
                          <van-loading size="10" class="mr-1" />提交中
                        </van-tag>
                        <van-tag v-else color="#8B5CF6" size="small">待验证</van-tag>
                        <span v-if="item.vibe_verified_at" class="text-xs text-gray-400">{{ formatDateTime(item.vibe_verified_at) }}</span>
                      </div>
                      <!-- Vibe Summary -->
                      <div v-if="item.vibe_summary && item.vibe_summary.trim()" class="mt-2 bg-purple-50 rounded-lg p-2 border border-purple-100">
                        <div class="flex items-center gap-1 mb-0.5">
                          <van-icon name="description" size="12" color="#8B5CF6" />
                          <span class="text-xs font-medium text-purple-600">变更总结</span>
                        </div>
                        <div class="text-sm text-gray-600 leading-snug vibe-summary-content" v-html="renderMarkdown(item.vibe_summary)"></div>
                      </div>
                      <div v-else class="mt-2 bg-purple-50 rounded-lg p-2 border border-purple-100">
                        <div class="flex items-center gap-1 mb-0.5">
                          <van-icon name="description" size="12" color="#8B5CF6" />
                          <span class="text-xs font-medium text-purple-600">变更总结</span>
                        </div>
                        <p class="text-xs text-gray-400 italic">暂无变更总结</p>
                      </div>
                      <div class="flex items-center gap-1 mt-1 flex-wrap">
                        <van-tag
                          v-for="tag in (item.tags || [])"
                          :key="tag.id"
                          :color="tag.color"
                          size="small"
                          plain
                        >
                          {{ tag.name }}
                        </van-tag>
                      </div>
                      <!-- Action buttons (only for verifying, not committing) -->
                      <div v-if="item.vibe_status === 'verifying'" class="flex items-center gap-2 mt-2">
                        <van-button
                          size="small"
                          type="success"
                          icon="passed"
                          :disabled="committingId === item.id"
                          @click.stop="confirmVibeVerified(item)"
                        >
                          已验证
                        </van-button>
                        <van-button
                          size="small"
                          type="warning"
                          plain
                          icon="edit"
                          @click.stop="openImproveDialog(item)"
                        >
                          改进
                        </van-button>
                        <van-button
                          size="small"
                          type="danger"
                          plain
                          icon="delete-o"
                          @click.stop="deleteVibeTask(item)"
                        >
                          删除
                        </van-button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </van-tab>

            <!-- Sub-tab: 已提交 -->
            <van-tab title="已提交">
              <div class="py-3 space-y-2">
                <div v-if="vibeCommitted.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
                  <p class="text-sm">暂无已提交的任务</p>
                </div>
                <div v-for="item in vibeCommitted" :key="item.id" class="bg-white rounded-xl shadow-sm p-3" :class="item.completed ? 'opacity-70' : ''">
                  <div class="flex items-center gap-3">
                    <van-icon name="passed" size="20" color="#10B981" />
                    <div class="flex-1 min-w-0" @click="openDetail(item)">
                      <div class="flex items-start gap-2">
                        <span class="text-sm text-gray-600 min-w-0 break-words">{{ item.title }}</span>
                        <van-tag color="#10B981" size="small" plain>已提交</van-tag>
                      </div>
                      <!-- Git commit ID -->
                      <div v-if="item.vibe_commit_id" class="mt-1.5 flex items-center gap-1.5">
                        <van-icon name="label-o" size="12" color="#6B7280" />
                        <code class="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded font-mono">{{ item.vibe_commit_id.slice(0, 7) }}</code>
                      </div>
                      <div v-if="item.vibe_summary" class="mt-2 bg-green-50 rounded-lg p-2 border border-green-100">
                        <div class="flex items-center gap-1 mb-0.5">
                          <van-icon name="description" size="12" color="#10B981" />
                          <span class="text-xs font-medium text-green-600">变更总结</span>
                        </div>
                        <div class="text-sm text-gray-600 leading-snug vibe-summary-content" v-html="renderMarkdown(item.vibe_summary)"></div>
                      </div>
                      <p v-else-if="item.description" class="text-xs text-gray-400 mt-1 whitespace-pre-wrap line-clamp-2">{{ item.description }}</p>
                      <div class="flex items-center gap-1 mt-1 flex-wrap">
                        <van-tag
                          v-for="tag in (item.tags || [])"
                          :key="tag.id"
                          :color="tag.color"
                          size="small"
                          plain
                        >
                          {{ tag.name }}
                        </van-tag>
                      </div>
                    </div>
                    <div class="flex flex-col gap-1.5 flex-shrink-0">
                      <van-button
                        size="small"
                        :type="item.completed ? 'default' : 'warning'"
                        :disabled="item.completed"
                        :plain="item.completed"
                        @click.stop="revertToVerifying(item)"
                      >
                        返回验证
                      </van-button>
                      <van-button
                        size="small"
                        type="danger"
                        plain
                        icon="delete-o"
                        @click.stop="deleteCommittedTask(item)"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </van-tab>
          </van-tabs>
        </div>
      </van-tab>

      <!-- ==================== Tab 4: 已完成 ==================== -->
      <van-tab title="已完成">
        <div class="max-w-3xl mx-auto px-4 py-4 space-y-4">
          <!-- Tag Filter (same tags, shared selection) -->
          <div v-if="allTags.length > 0" class="pb-1">
            <div class="flex items-center gap-2 mb-2">
              <van-checkbox
                :model-value="allSelected"
                shape="square"
                icon-size="16px"
                class="flex-shrink-0 select-all-checkbox"
                @update:model-value="selectAll"
              >
                全选
              </van-checkbox>
            </div>
            <template v-if="tagTree.length > 0">
              <div v-for="group in tagTree" :key="group.id" class="mb-2">
                <div class="flex gap-2 flex-wrap items-center">
                  <span class="text-xs text-gray-500 font-medium flex-shrink-0" :style="{ color: group.color }">{{ group.name }}</span>
                  <template v-for="tag in group.children" :key="tag.id">
                    <input
                      v-if="editingTagId === tag.id"
                      v-model="editingTagName"
                      class="edit-tag-input"
                      @blur="finishEditTag(tag)"
                      @keypress.enter="finishEditTag(tag)"
                      @keydown.escape="cancelEditTag"
                      ref="tagEditInput"
                    />
                    <van-tag
                      v-else
                      :type="selectedTagIds.has(tag.id) ? 'primary' : 'default'"
                      :color="selectedTagIds.has(tag.id) ? tag.color : undefined"
                      size="medium"
                      class="cursor-pointer tag-closeable"
                      closeable
                      @click="toggleTag(tag.id)"
                      @dblclick.stop="startEditTag(tag)"
                      @close.stop="confirmDeleteTag(tag)"
                    >
                      {{ tag.name }}
                    </van-tag>
                  </template>
                </div>
              </div>
            </template>
            <div v-if="orphanTags.length > 0" class="flex gap-2 flex-wrap items-center">
              <template v-for="tag in orphanTags" :key="tag.id">
                <input
                  v-if="editingTagId === tag.id"
                  v-model="editingTagName"
                  class="edit-tag-input"
                  @blur="finishEditTag(tag)"
                  @keypress.enter="finishEditTag(tag)"
                  @keydown.escape="cancelEditTag"
                  ref="tagEditInput"
                />
                <van-tag
                  v-else
                  :type="selectedTagIds.has(tag.id) ? 'primary' : 'default'"
                  :color="selectedTagIds.has(tag.id) ? tag.color : undefined"
                  size="medium"
                  class="cursor-pointer tag-closeable"
                  closeable
                  @click="toggleTag(tag.id)"
                  @dblclick.stop="startEditTag(tag)"
                  @close.stop="confirmDeleteTag(tag)"
                >
                  {{ tag.name }}
                </van-tag>
              </template>
            </div>
          </div>

          <div v-if="loading" class="flex justify-center py-8">
            <van-loading size="28px">加载中...</van-loading>
          </div>
          <div v-else-if="filteredCompleted.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
            <p class="text-sm">暂无已完成的任务</p>
          </div>
          <div v-else class="space-y-2">
            <van-swipe-cell v-for="item in filteredCompleted" :key="item.id">
              <div class="bg-white rounded-xl shadow-sm p-3 flex items-center gap-3 opacity-60">
                <van-checkbox
                  :model-value="true"
                  shape="round"
                  icon-size="20px"
                  @update:model-value="handleRestart(item.id)"
                />
                <div class="flex-1 min-w-0" @click="openDetail(item)">
                  <div class="flex items-start gap-2">
                    <span class="text-sm text-gray-500 line-through min-w-0 break-words">{{ item.title }}</span>
                    <van-tag v-if="item.high_priority" type="danger" size="small" plain class="flex-shrink-0">高优</van-tag>
                  </div>
                  <p v-if="item.description" class="text-xs text-gray-400 mt-1 whitespace-pre-wrap line-clamp-2">{{ item.description }}</p>
                  <div class="flex items-center gap-1 mt-1 flex-wrap">
                    <van-tag
                      v-for="tag in (item.tags || [])"
                      :key="tag.id"
                      :color="tag.color"
                      size="small"
                      plain
                    >
                      {{ tag.name }}
                    </van-tag>
                    <span class="text-xs text-gray-400">
                      完成于 {{ formatDateTime(item.completed_at) }}
                    </span>
                    <span v-if="item.created_at && item.completed_at" class="text-xs text-gray-400">
                      耗时 {{ formatDuration(item.created_at, item.completed_at) }}
                    </span>
                    <span v-if="(item.total_working_seconds || 0) > 0" class="text-xs text-green-500">
                      工作 {{ formatSeconds(item.total_working_seconds) }}
                    </span>
                    <span v-if="(item.stop_count || 0) > 0" class="text-xs text-red-400">
                      停{{ item.stop_count }}次
                    </span>
                    <span v-if="item.deadline" class="text-xs text-gray-400">
                      截止 {{ item.deadline }}{{ item.deadline_time ? ' ' + item.deadline_time : '' }}
                    </span>
                    <span v-if="item.repeat_rule" class="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-400">
                      {{ repeatLabel(item) }}
                    </span>
                  </div>
                </div>
                <van-icon
                  name="replay"
                  size="16"
                  color="#3B82F6"
                  class="cursor-pointer"
                  @click="handleRestart(item.id)"
                />
                <van-icon
                  name="delete-o"
                  size="16"
                  color="#9CA3AF"
                  class="cursor-pointer"
                  @click="handleDelete(item.id)"
                />
              </div>
            </van-swipe-cell>
          </div>
        </div>
      </van-tab>

      <!-- ==================== Tab 5: 效率分析 ==================== -->
      <van-tab title="效率分析">
        <div class="max-w-3xl mx-auto px-4 py-2">
          <van-tabs v-model:active="analysisSubTab" type="card" class="vibe-tabs">

            <!-- Sub-tab: 任务效率 -->
            <van-tab title="任务效率">
              <div class="space-y-3 mt-3">
                <!-- Duration Stats Chart -->
                <div class="bg-white rounded-xl shadow-sm p-4">
                  <div class="flex items-center justify-between mb-3">
                    <span class="text-sm font-medium text-gray-700">各类任务平均耗时</span>
                    <van-button size="mini" plain type="primary" :loading="generatingStats" @click="triggerDurationStats">刷新</van-button>
                  </div>
                  <div class="flex items-center gap-1 mb-3">
                    <button
                      v-for="w in [{key:'7d',label:'过去7天'},{key:'30d',label:'过去一月'},{key:'all',label:'历史汇总'}]"
                      :key="w.key"
                      class="px-2.5 py-1 text-xs rounded-full transition-colors"
                      :class="durationStatsWindow === w.key ? 'bg-purple-500 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'"
                      @click="switchDurationWindow(w.key)"
                    >{{ w.label }}</button>
                  </div>
                  <div v-if="durationStats.length > 0">
                    <div class="duration-chart-container" :style="{ height: Math.max(180, durationStats.length * 40 + 60) + 'px' }">
                      <canvas ref="durationChartCanvas"></canvas>
                    </div>
                  </div>
                  <div v-else class="text-center py-4">
                    <p class="text-gray-400 text-sm mb-3">暂无耗时统计数据</p>
                    <van-button size="small" plain type="primary" icon="chart-trending-o" :loading="generatingStats" @click="triggerDurationStats">生成耗时图表</van-button>
                  </div>
                </div>

                <!-- Task analysis streaming / status -->
                <div v-if="analysisStatus" class="bg-gray-50 rounded-lg p-3 text-sm">
                  <div class="flex items-center gap-2 mb-1">
                    <van-loading v-if="analysisStatus === 'running'" size="14" />
                    <van-icon v-else-if="analysisStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
                    <span class="text-gray-600">{{ analysisStatusText }}</span>
                  </div>
                  <pre v-if="analysisThinking" ref="analysisThinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed mb-2">{{ analysisThinking }}</pre>
                  <div v-if="analysisStream" ref="analysisStreamEl" class="analysis-content text-sm text-gray-700 leading-relaxed max-h-96 overflow-y-auto" v-html="renderMarkdown(analysisStream)"></div>
                </div>

                <!-- Latest task analysis -->
                <div v-if="analyses.length > 0" class="bg-white rounded-xl shadow-sm p-4">
                  <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2 flex-wrap">
                      <span class="text-xs text-purple-500 font-medium">{{ formatDateTime(analyses[0].created_at) }}</span>
                      <van-tag v-if="analyses[0].model_name" color="#8B5CF6" size="small" plain>{{ analyses[0].model_name }}</van-tag>
                    </div>
                    <van-button
                      v-if="!triggeringAnalysis"
                      size="mini" plain type="primary"
                      @click="triggerAnalysis"
                    >重新生成</van-button>
                  </div>
                  <div class="analysis-content text-sm text-gray-700 leading-relaxed" v-html="renderMarkdown(analyses[0].content)"></div>
                </div>

                <!-- No task analyses yet -->
                <div v-if="analyses.length === 0 && !analysisStatus" class="bg-white rounded-xl shadow-sm p-8 text-center">
                  <p class="text-gray-400 text-sm mb-4">暂无任务效率分析报告</p>
                  <van-button size="small" plain type="primary" icon="chart-trending-o" @click="triggerAnalysis">生成效率分析</van-button>
                </div>
              </div>
            </van-tab>

            <!-- Sub-tab: 项目效率 -->
            <van-tab title="项目效率">
              <div class="space-y-3 mt-3">
                <!-- Project analysis streaming / status -->
                <div v-if="projectAnalysisStatus" class="bg-gray-50 rounded-lg p-3 text-sm">
                  <div class="flex items-center gap-2 mb-1">
                    <van-loading v-if="projectAnalysisStatus === 'running'" size="14" />
                    <van-icon v-else-if="projectAnalysisStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
                    <span class="text-gray-600">{{ projectAnalysisStatusText }}</span>
                  </div>
                  <pre v-if="projectAnalysisThinking" ref="projectAnalysisThinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed mb-2">{{ projectAnalysisThinking }}</pre>
                  <div v-if="projectAnalysisStream" ref="projectAnalysisStreamEl" class="analysis-content text-sm text-gray-700 leading-relaxed max-h-96 overflow-y-auto" v-html="renderMarkdown(projectAnalysisStream)"></div>
                </div>

                <!-- Latest project analysis -->
                <div v-if="projectAnalyses.length > 0" class="bg-white rounded-xl shadow-sm p-4">
                  <div class="flex items-center justify-between mb-2">
                    <div class="flex items-center gap-2 flex-wrap">
                      <span class="text-xs text-teal-500 font-medium">{{ formatDateTime(projectAnalyses[0].created_at) }}</span>
                      <van-tag v-if="projectAnalyses[0].model_name" color="#14B8A6" size="small" plain>{{ projectAnalyses[0].model_name }}</van-tag>
                    </div>
                    <van-button
                      v-if="!triggeringProjectAnalysis"
                      size="mini" plain type="primary"
                      @click="triggerProjectAnalysis"
                    >重新生成</van-button>
                  </div>
                  <div class="analysis-content text-sm text-gray-700 leading-relaxed" v-html="renderMarkdown(projectAnalyses[0].content)"></div>
                </div>

                <!-- No project analyses yet -->
                <div v-if="projectAnalyses.length === 0 && !projectAnalysisStatus" class="bg-white rounded-xl shadow-sm p-8 text-center">
                  <p class="text-gray-400 text-sm mb-4">暂无项目效率分析报告</p>
                  <van-button size="small" plain type="primary" icon="chart-trending-o" @click="triggerProjectAnalysis">生成项目分析</van-button>
                </div>
              </div>
            </van-tab>

          </van-tabs>
        </div>
      </van-tab>

    </van-tabs>

    <!-- Calendar for new todo deadline -->
    <van-calendar
      v-model:show="showNewDeadlinePicker"
      :min-date="calendarMinDate"
      :show-confirm="false"
      @confirm="onNewDeadlineConfirm"
    />

    <!-- Calendar for editing existing todo deadline -->
    <van-calendar
      v-model:show="showEditDeadlinePicker"
      :min-date="calendarMinDate"
      :show-confirm="false"
      @confirm="onEditDeadlineConfirm"
    >
      <template #footer>
        <div class="px-4 pb-2">
          <van-button block plain type="default" size="small" @click="clearEditDeadline">
            清除截止日期
          </van-button>
        </div>
      </template>
    </van-calendar>

    <!-- Time picker after date selection -->
    <van-popup v-model:show="showTimePicker" position="bottom" round>
      <div class="p-4 space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-gray-700">选择截止时间</span>
          <span class="text-sm text-gray-400 cursor-pointer" @click="onTimePickerSkip">不设时间</span>
        </div>
        <div class="flex items-center gap-3">
          <div class="flex-1">
            <label class="text-xs text-gray-400 mb-1 block">开始时间</label>
            <input
              type="time"
              v-model="timeStartVal"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-base focus:outline-none focus:border-blue-400"
            />
          </div>
          <span class="text-gray-400 mt-5">—</span>
          <div class="flex-1">
            <label class="text-xs text-gray-400 mb-1 block">结束时间（可选）</label>
            <input
              type="time"
              v-model="timeEndVal"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-base focus:outline-none focus:border-blue-400"
            />
          </div>
        </div>
        <div class="flex gap-3">
          <van-button block plain type="default" size="small" @click="onTimePickerSkip">不设时间</van-button>
          <van-button block type="primary" size="small" @click="onTimePickerConfirm">确定</van-button>
        </div>
      </div>
    </van-popup>

    <!-- Tag Tasks Popup (from duration chart bar click) -->
    <van-popup
      v-model:show="showTagTasks"
      position="bottom"
      round
      :style="{ maxHeight: '70vh' }"
    >
      <div class="p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-gray-800">
            「{{ tagTasksTitle }}」已完成任务
            <span class="text-xs text-gray-400 font-normal ml-1">{{ tagTasksList.length }}条</span>
          </h3>
          <van-icon name="cross" size="20" class="cursor-pointer text-gray-400" @click="showTagTasks = false" />
        </div>
        <div v-if="tagTasksList.length === 0" class="text-center py-6 text-gray-400 text-sm">暂无任务</div>
        <div v-else class="space-y-2 overflow-y-auto" style="max-height: calc(70vh - 60px)">
          <div
            v-for="item in tagTasksList"
            :key="item.id"
            class="bg-gray-50 rounded-lg p-3 cursor-pointer active:bg-gray-100 transition-colors"
            @click="showTagTasks = false; openDetail(item)"
          >
            <div class="flex items-start gap-2">
              <span class="text-sm text-gray-700 min-w-0 break-words">{{ item.title }}</span>
              <van-tag v-if="item.high_priority" type="danger" size="small" plain class="flex-shrink-0">高优</van-tag>
            </div>
            <div class="flex items-center gap-1 mt-1 flex-wrap">
              <van-tag
                v-for="tag in (item.tags || [])"
                :key="tag.id"
                :color="tag.color"
                size="small"
                plain
              >{{ tag.name }}</van-tag>
              <span class="text-xs text-gray-400">完成于 {{ formatDateTime(item.completed_at) }}</span>
              <span v-if="item.created_at && item.completed_at" class="text-xs text-gray-400">
                耗时 {{ formatDuration(item.created_at, item.completed_at) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- Detail Popup -->
    <van-popup
      v-model:show="showDetail"
      position="bottom"
      round
      :style="{ maxHeight: '80vh' }"
    >
      <div v-if="detailItem" class="p-4 space-y-4" @click="showDetailTagPicker = false">
        <div class="flex items-center justify-between">
          <h3 class="text-base font-semibold text-gray-800">详情</h3>
          <van-icon name="cross" size="20" class="cursor-pointer text-gray-400" @click="showDetail = false" />
        </div>

        <!-- Title -->
        <div>
          <label class="text-xs text-gray-400 mb-1 block">标题</label>
          <van-field
            v-if="!detailItem.completed"
            v-model="detailItem.title"
            type="textarea"
            class="detail-field"
            autosize
            rows="1"
            @blur="saveDetail"
          />
          <p v-else class="text-sm text-gray-600 break-words">{{ detailItem.title }}</p>
        </div>

        <!-- Description -->
        <div>
          <div class="flex items-center gap-1 mb-1">
            <label class="text-xs text-gray-400">详情描述</label>
            <VoiceInputButton v-if="!detailItem.completed" v-model="detailItem.description" :size="14" />
          </div>
          <van-field
            v-if="!detailItem.completed"
            v-model="detailItem.description"
            type="textarea"
            class="detail-field"
            placeholder="添加详情描述..."
            autosize
            rows="3"
            @blur="saveDetail"
          />
          <p v-else class="text-sm text-gray-500 whitespace-pre-wrap">{{ detailItem.description || '无' }}</p>
        </div>

        <!-- Tags (editable) -->
        <div>
          <label class="text-xs text-gray-400 mb-1 block">标签</label>
          <div class="flex gap-1.5 flex-wrap items-center">
            <template v-for="tag in detailAssignedTags" :key="tag.id">
              <input
                v-if="editingTagId === tag.id"
                v-model="editingTagName"
                class="edit-tag-input"
                ref="detailTagEditInput"
                @blur="finishEditTag(tag)"
                @keypress.enter="finishEditTag(tag)"
                @keydown.escape="cancelEditTag"
              />
              <van-tag
                v-else
                type="primary"
                :color="tag.color"
                size="medium"
                class="cursor-pointer tag-closeable"
                closeable
                @dblclick.stop="startEditTag(tag)"
                @close.stop="removeDetailTag(tag.id)"
              >
                {{ tag.name }}
              </van-tag>
            </template>
            <div class="detail-tag-add-wrapper" @click.stop>
              <van-tag
                plain
                type="primary"
                size="medium"
                class="cursor-pointer"
                @click="showDetailTagPicker = !showDetailTagPicker"
              >+</van-tag>
            </div>
            <span v-if="detailAssignedTags.length === 0 && !showDetailTagPicker" class="text-xs text-gray-400">点击 + 添加标签</span>
          </div>
          <div v-if="showDetailTagPicker" class="flex gap-1.5 flex-wrap mt-1.5 items-center" @click.stop>
            <div class="new-tag-wrapper">
              <input
                v-model="newTagName"
                class="new-tag-input"
                placeholder="新标签..."
                @keypress.enter="createAndAddDetailTag"
              />
              <van-icon
                v-if="newTagName.trim()"
                name="success"
                class="new-tag-confirm"
                @click="createAndAddDetailTag"
              />
            </div>
            <van-tag
              v-for="tag in detailUnassignedTags"
              :key="tag.id"
              size="medium"
              :color="tag.color"
              type="primary"
              plain
              class="cursor-pointer"
              @click="addDetailTag(tag.id)"
            >
              {{ tag.name }}
            </van-tag>
          </div>
        </div>

        <!-- Repeat Config (hidden for requirements/vibe items) -->
        <div v-if="!detailItem.completed && !detailItem.vibe_status">
          <label class="text-xs text-gray-400 mb-1 block">重复配置</label>
          <div class="flex items-center gap-2 flex-wrap">
            <select
              v-model="detailRepeatRule"
              class="repeat-select"
              @change="saveRepeatConfig"
            >
              <option value="">不重复</option>
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月</option>
              <option value="yearly">每年</option>
            </select>
            <template v-if="detailRepeatRule">
              <span class="text-xs text-gray-500">每</span>
              <input
                v-model.number="detailRepeatInterval"
                type="number"
                min="1"
                max="365"
                class="repeat-interval-input"
                @change="saveRepeatConfig"
              />
              <span class="text-xs text-gray-500">{{ repeatUnitLabel }}</span>
              <van-checkbox
                v-model="detailRepeatIncludeWeekends"
                shape="square"
                icon-size="14px"
                @change="saveRepeatConfig"
              >
                <span class="text-xs text-gray-500">包含周末</span>
              </van-checkbox>
            </template>
          </div>
          <p v-if="detailItem.repeat_next_at" class="text-xs text-purple-400 mt-1">
            下次重复：{{ detailItem.repeat_next_at }}
          </p>
        </div>
        <div v-else-if="detailItem.repeat_rule">
          <label class="text-xs text-gray-400 mb-1 block">重复配置</label>
          <span class="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-400">{{ repeatLabel(detailItem) }}</span>
        </div>

        <!-- Commit ID -->
        <div v-if="detailItem.vibe_commit_id" class="flex items-center gap-1.5">
          <span class="text-xs text-gray-400">Commit</span>
          <code class="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded font-mono">{{ detailItem.vibe_commit_id.slice(0, 7) }}</code>
        </div>

        <!-- Meta -->
        <div class="flex items-center gap-4 text-xs text-gray-400 flex-wrap">
          <span>创建于 {{ formatDateTime(detailItem.created_at) }}</span>
          <span v-if="detailItem.started_at">
            开始于 {{ formatDateTime(detailItem.started_at) }}
          </span>
          <span v-if="detailItem.deadline">
            截止 {{ detailItem.deadline }}{{ detailItem.deadline_time ? ' ' + detailItem.deadline_time : '' }}
          </span>
          <span v-if="detailItem.completed_at">
            完成于 {{ formatDateTime(detailItem.completed_at) }}
          </span>
          <span v-if="(detailItem.total_working_seconds || 0) > 0" class="text-green-500">
            工作时间 {{ formatSeconds(detailItem.total_working_seconds) }}
          </span>
          <span v-if="(detailItem.stop_count || 0) > 0" class="text-red-400">
            停止 {{ detailItem.stop_count }} 次
          </span>
          <span v-if="detailItem.work_status === 'in_progress'" class="text-green-600 font-medium">
            进行中
          </span>
          <span v-else-if="detailItem.work_status === 'paused'" class="text-yellow-500">
            已暂停
          </span>
        </div>
      </div>
    </van-popup>

    <!-- Delete Tag Confirm -->
    <van-dialog
      v-model:show="showDeleteTagConfirm"
      title="删除标签"
      :message="`删除标签「${deletingTag?.name}」后，所有任务上的该标签也会移除，确定？`"
      show-cancel-button
      @confirm="handleDeleteTag"
    />

    <!-- PM: Update Popup -->
    <van-popup
      v-model:show="showPmUpdatePopup"
      position="bottom"
      round
      :style="{ maxHeight: '85vh' }"
    >
      <div class="p-4 space-y-4">
        <h3 class="text-lg font-semibold text-gray-800">记录项目进展</h3>

        <!-- Talent selector -->
        <div>
          <label class="text-sm text-gray-500 mb-1 block">队员</label>
          <van-field
            v-model="pmTalentSearch"
            placeholder="搜索队员（支持拼音首字母）"
            clearable
            @focus="searchPmTalents"
            @update:model-value="searchPmTalents"
            @keydown="handlePmTalentKeydown"
          />
          <div v-if="pmShowTalentList && pmTalentResults.length > 0" ref="pmTalentListRef" class="border border-gray-200 rounded-lg mt-1 max-h-40 overflow-y-auto bg-white shadow">
            <div
              v-for="(t, idx) in pmTalentResults"
              :key="t.id"
              class="px-3 py-2 text-sm cursor-pointer hover:bg-blue-50"
              :class="idx === pmTalentHighlightIndex ? 'bg-blue-100 text-blue-600' : pmSelectedTalent?.id === t.id ? 'bg-blue-50 text-blue-600' : 'text-gray-700'"
              @click="pmSelectedTalent = t; pmTalentSearch = t.name; pmShowTalentList = false"
            >
              {{ t.name }}<span v-if="t.current_role" class="text-xs text-gray-400 ml-2">{{ t.current_role }}</span>
            </div>
          </div>
          <div v-if="pmSelectedTalent" class="mt-1">
            <van-tag type="primary" size="medium" closeable @close="pmSelectedTalent = null; pmTalentSearch = ''">{{ pmSelectedTalent.name }}</van-tag>
          </div>
        </div>

        <!-- Project / sub-project selector -->
        <div>
          <label class="text-sm text-gray-500 mb-1 block">{{ pmSelectedParentForCreate ? '子项目' : '项目' }}</label>
          <van-field
            v-model="pmProjectSearch"
            :placeholder="pmSelectedParentForCreate ? '搜索或新建子项目' : '搜索项目或输入新项目名'"
            clearable
            @focus="searchPmProjects"
            @update:model-value="searchPmProjects"
          />
          <div v-if="pmShowProjectList && (pmFilteredProjectResults.length > 0 || pmProjectSearch.trim())" class="border border-gray-200 rounded-lg mt-1 max-h-40 overflow-y-auto bg-white shadow">
            <div
              v-for="p in pmFilteredProjectResults"
              :key="p.id"
              class="px-3 py-2 text-sm cursor-pointer hover:bg-blue-50"
              :class="pmSelectedProject?.id === p.id ? 'bg-blue-50 text-blue-600' : 'text-gray-700'"
              @click="selectPmProject(p)"
            >
              {{ p.name }}
              <span v-if="p.parent_name && !pmSelectedParentForCreate" class="text-gray-400 text-xs ml-1">({{ p.parent_name }})</span>
            </div>
            <!-- Create new project/sub-project -->
            <div
              v-if="pmProjectSearch.trim() && !pmFilteredProjectResults.some(p => p.name === pmProjectSearch.trim())"
              class="border-t border-gray-100 p-2"
            >
              <input v-model="pmInlineDesc" class="w-full text-xs border border-gray-200 rounded px-2 py-1 mb-1 outline-none focus:border-blue-300" placeholder="项目描述（可选）" />
              <div class="text-sm cursor-pointer hover:bg-green-50 text-green-600 px-1 py-1 rounded" @click="createPmProjectInline(pmSelectedParentForCreate)">
                + 创建{{ pmSelectedParentForCreate ? '子项目' : '项目' }}「{{ pmProjectSearch.trim() }}」{{ pmSelectedParentForCreate ? '（属于 ' + pmSelectedParentForCreate.name + '）' : '' }}
              </div>
            </div>
          </div>
          <!-- Selected display -->
          <div v-if="pmSelectedProject" class="mt-1 flex items-center gap-1 flex-wrap">
            <van-tag v-if="pmSelectedProject.parent_name" type="primary" size="small" plain>{{ pmSelectedProject.parent_name }}</van-tag>
            <span v-if="pmSelectedProject.parent_name" class="text-gray-400 text-xs">›</span>
            <van-tag type="success" size="medium" closeable @close="clearPmProjectSelection">{{ pmSelectedProject.name }}</van-tag>
          </div>
        </div>

        <!-- Parent project selector (optional) -->
        <div>
          <label class="text-sm text-gray-500 mb-1 block">父项目<span class="text-gray-300 ml-1">（可选，不选则记录到顶层项目）</span></label>
          <div v-if="pmSelectedParentForCreate" class="flex items-center gap-1 mb-1">
            <van-tag type="primary" size="medium" closeable @close="pmSelectedParentForCreate = null">{{ pmSelectedParentForCreate.name }}</van-tag>
          </div>
          <van-field
            v-if="!pmSelectedParentForCreate"
            v-model="pmParentProjectSearch"
            placeholder="搜索父项目..."
            clearable
            @focus="searchPmParentProjects"
            @update:model-value="searchPmParentProjects"
          />
          <div v-if="pmShowParentProjectList && (pmParentProjectResults.length > 0 || pmParentProjectSearch.trim())" class="border border-gray-200 rounded-lg mt-1 max-h-40 overflow-y-auto bg-white shadow">
            <div
              v-for="p in pmParentProjectResults"
              :key="p.id"
              class="px-3 py-2 text-sm cursor-pointer hover:bg-blue-50"
              :class="pmSelectedParentForCreate?.id === p.id ? 'bg-blue-50 text-blue-600' : 'text-gray-700'"
              @click="pmSelectedParentForCreate = p; pmParentProjectSearch = ''; pmShowParentProjectList = false; onParentSelected(p)"
            >
              <span class="font-medium">{{ p.name }}</span>
              <span v-if="p.children?.length" class="text-xs text-gray-400 ml-2">{{ p.children.length }} 子项目</span>
            </div>
            <div
              v-if="pmParentProjectSearch.trim() && !pmParentProjectResults.some(p => p.name === pmParentProjectSearch.trim())"
              class="border-t border-gray-100 p-2"
            >
              <input v-model="pmInlineDesc" class="w-full text-xs border border-gray-200 rounded px-2 py-1 mb-1 outline-none focus:border-blue-300" placeholder="项目描述（可选）" />
              <div class="text-sm cursor-pointer hover:bg-green-50 text-green-600 px-1 py-1 rounded" @click="createPmParentProjectInline">
                + 创建父项目「{{ pmParentProjectSearch.trim() }}」
              </div>
            </div>
          </div>
        </div>

        <!-- Content input -->
        <div>
          <div class="flex items-center justify-between mb-1">
            <div class="flex items-center gap-1">
              <label class="text-sm text-gray-500">进展内容</label>
              <VoiceInputButton v-model="pmUpdateContent" :size="14" />
            </div>
            <div
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs cursor-pointer hover:bg-blue-100 transition"
              @click="showPmModelPicker = true"
            >
              <span>{{ pmCurrentModel || '选择模型' }}</span>
              <van-icon name="arrow-down" size="10" />
            </div>
          </div>
          <van-field
            v-model="pmUpdateContent"
            type="textarea"
            rows="4"
            placeholder="描述该队员在该项目上的当前进展..."
            maxlength="2000"
            show-word-limit
          />
        </div>

        <!-- Submit -->
        <van-button
          type="primary"
          block
          :loading="pmSubmitting"
          :disabled="!pmSelectedTalent || !pmSelectedProject || !pmUpdateContent.trim()"
          @click="submitPmUpdate"
        >
          提交
        </van-button>

        <!-- Hint -->
        <p class="text-xs text-gray-400 text-center">提交后 LLM 将在后台自动解析进展内容</p>
      </div>
    </van-popup>

    <!-- PM: Model Picker -->
    <van-action-sheet
      v-model:show="showPmModelPicker"
      :actions="pmModelActions"
      cancel-text="取消"
      close-on-click-action
      @select="onPmModelSelect"
    />

    <!-- PM: Create Project Popup -->
    <van-popup
      v-model:show="showPmCreatePopup"
      position="bottom"
      round
      :style="{ maxHeight: '60vh' }"
    >
      <div class="p-4 space-y-4">
        <h3 class="text-lg font-semibold text-gray-800">创建项目</h3>
        <van-field v-model="pmNewName" label="项目名" placeholder="输入项目名称" />
        <div class="flex items-center gap-1">
          <van-field v-model="pmNewDesc" label="描述" type="textarea" rows="2" placeholder="项目描述（可选）" class="flex-1" />
          <VoiceInputButton v-model="pmNewDesc" :size="14" />
        </div>
        <div>
          <label class="text-sm text-gray-500 mb-1 block">父项目（可选，创建为子项目）</label>
          <van-field
            v-model="pmParentSearch"
            placeholder="搜索父项目"
            clearable
            @focus="pmShowParentList = true"
            @update:model-value="searchPmParent"
          />
          <div v-if="pmShowParentList && pmParentResults.length > 0" class="border border-gray-200 rounded-lg mt-1 max-h-32 overflow-y-auto bg-white shadow">
            <div
              v-for="p in pmParentResults"
              :key="p.id"
              class="px-3 py-2 text-sm cursor-pointer hover:bg-blue-50"
              @click="pmSelectedParent = p; pmParentSearch = p.name; pmShowParentList = false"
            >
              {{ p.name }}
            </div>
          </div>
          <div v-if="pmSelectedParent" class="mt-1">
            <van-tag type="primary" size="medium" closeable @close="pmSelectedParent = null; pmParentSearch = ''">{{ pmSelectedParent.name }}</van-tag>
          </div>
        </div>
        <van-button type="primary" block :disabled="!pmNewName.trim()" :loading="pmCreating" @click="createPmProject">创建</van-button>
      </div>
    </van-popup>

    <!-- PM: Project Info Popup -->
    <van-popup
      v-model:show="showPmInfoPopup"
      position="bottom"
      round
      closeable
      :style="{ height: '90vh' }"
    >
      <div v-if="pmInfoLoading" class="flex justify-center py-16">
        <van-loading size="28px">加载项目信息...</van-loading>
      </div>
      <div v-else-if="pmInfoData" class="p-4 overflow-y-auto" style="max-height: calc(90vh - 40px)">
        <div class="flex items-center justify-between mb-4">
          <input
            v-if="pmEditingName"
            v-model="pmEditNameText"
            ref="pmNameInput"
            class="text-xl font-bold text-gray-800 border-b-2 border-blue-400 outline-none bg-transparent w-full"
            @blur="savePmName"
            @keydown.enter="$event.target.blur()"
            @keydown.escape="pmEditingName = false"
          />
          <h3 v-else class="text-xl font-bold text-gray-800 cursor-pointer hover:text-blue-600" @dblclick="startEditPmName">{{ pmInfoData.name }}</h3>
          <div class="flex items-center gap-2">
            <StatusPicker :model-value="pmInfoData.status" @update:model-value="changePmStatus(pmInfoData.id, $event)" />
            <van-button size="mini" plain type="primary" icon="replay" :loading="pmInfoRefreshing" @click="refreshPmInfo">刷新</van-button>
          </div>
        </div>

        <!-- Description (double-click to edit) -->
        <div class="mb-4">
          <div v-if="pmEditingDesc">
            <div class="flex items-center gap-1 mb-1">
              <VoiceInputButton v-model="pmEditDescText" :size="14" />
            </div>
            <textarea
              v-model="pmEditDescText"
              class="w-full text-base border border-blue-300 rounded-lg p-3 outline-none resize-y min-h-[60px]"
              @blur="savePmDesc"
              @keydown.escape="pmEditingDesc = false"
              @input="autoResizeTextarea($event.target)"
              ref="pmDescTextarea"
            ></textarea>
          </div>
          <p
            v-else
            class="text-sm text-gray-500 cursor-pointer hover:bg-gray-50 rounded p-1 -m-1"
            @dblclick="startEditPmDesc"
          >
            {{ pmInfoData.description || '暂无描述（双击编辑）' }}
          </p>
        </div>

        <!-- Parent project (configurable for top-level projects) -->
        <div class="mb-3">
          <div v-if="pmInfoData.parent_name" class="text-xs text-gray-400">
            父项目：<van-tag type="primary" size="small" plain closeable @close="clearPmInfoParent">{{ pmInfoData.parent_name }}</van-tag>
          </div>
          <div v-else>
            <div v-if="!pmInfoSettingParent" class="text-xs text-gray-400 cursor-pointer hover:text-blue-500" @click="pmInfoSettingParent = true">
              + 设置父项目
            </div>
            <div v-else class="flex items-center gap-2">
              <van-field
                v-model="pmInfoParentSearch"
                placeholder="搜索父项目..."
                size="small"
                class="flex-1"
                style="padding: 0"
                clearable
                @focus="searchPmInfoParent"
                @update:model-value="searchPmInfoParent"
              />
              <van-icon name="cross" size="14" class="cursor-pointer text-gray-400" @click="pmInfoSettingParent = false; pmInfoParentSearch = ''; pmInfoParentResults = []" />
            </div>
            <div v-if="pmInfoSettingParent && pmInfoParentResults.length > 0" class="border border-gray-200 rounded-lg mt-1 max-h-32 overflow-y-auto bg-white shadow">
              <div
                v-for="p in pmInfoParentResults"
                :key="p.id"
                class="px-3 py-1.5 text-sm cursor-pointer hover:bg-blue-50 text-gray-700"
                @click="setPmInfoParent(p)"
              >
                {{ p.name }}
              </div>
            </div>
          </div>
        </div>

        <!-- Created at + started at -->
        <div class="flex items-center gap-4 text-xs text-gray-400 mb-4">
          <span v-if="pmInfoData.created_at">创建于 {{ formatDateTime(pmInfoData.created_at) }}</span>
          <span v-if="pmInfoData.started_at">开始于 {{ formatDateTime(pmInfoData.started_at) }}</span>
        </div>

        <!-- Stats cards -->
        <div class="grid grid-cols-3 gap-3 mb-4">
          <div class="bg-blue-50 rounded-lg p-3 text-center">
            <p class="text-2xl font-bold text-blue-600">{{ pmInfoData.days_active }}</p>
            <p class="text-xs text-blue-400">进行天数</p>
          </div>
          <div class="bg-green-50 rounded-lg p-3 text-center">
            <p class="text-2xl font-bold text-green-600">{{ pmInfoData.member_count }}</p>
            <p class="text-xs text-green-400">参与人数</p>
          </div>
          <div class="bg-purple-50 rounded-lg p-3 text-center">
            <p class="text-2xl font-bold text-purple-600">{{ pmInfoData.update_count }}</p>
            <p class="text-xs text-purple-400">更新次数</p>
          </div>
        </div>

        <!-- Members -->
        <div v-if="pmInfoData.members?.length > 0" class="mb-4">
          <h4 class="text-sm font-semibold text-gray-600 mb-2">团队成员</h4>
          <div class="flex flex-wrap gap-2">
            <van-tag v-for="m in pmInfoData.members" :key="m.id" size="medium" plain type="primary">
              {{ m.talent_name }}<span v-if="m.role" class="text-gray-400"> · {{ m.role }}</span>
            </van-tag>
          </div>
        </div>

        <!-- LLM Summary -->
        <div class="bg-white rounded-xl border border-gray-200 p-4 mb-4">
          <h4 class="text-sm font-semibold text-gray-600 mb-2">项目概览（AI 生成）</h4>
          <div v-if="pmEditingSummary">
            <textarea
              v-model="pmEditSummaryText"
              ref="pmSummaryTextarea"
              class="w-full text-base border border-blue-300 rounded-lg p-3 outline-none resize-y min-h-[120px]"
              @blur="savePmSummary"
              @keydown.escape="pmEditingSummary = false"
              @input="autoResizeTextarea($event.target)"
            ></textarea>
            <p class="text-xs text-gray-400 mt-1">支持 Markdown 格式，点击外部保存</p>
          </div>
          <div
            v-else
            class="cursor-pointer hover:bg-gray-50 rounded p-1 -m-1"
            @dblclick="startEditPmSummary"
          >
            <div v-if="pmInfoData.llm_summary" class="analysis-content text-sm text-gray-700 leading-relaxed" v-html="renderMarkdown(pmInfoData.llm_summary)"></div>
            <p v-else class="text-sm text-gray-400">暂无概览（双击编辑）</p>
          </div>
        </div>

        <!-- Update timeline -->
        <div v-if="pmInfoData.recent_updates?.length > 0">
          <h4 class="text-sm font-semibold text-gray-600 mb-2">更新记录</h4>
          <div class="space-y-2">
            <div v-for="upd in pmInfoData.recent_updates" :key="upd.id" class="border-l-2 border-blue-300 pl-3 py-1">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-xs text-gray-400">{{ formatDateTime(upd.created_at) }}</span>
                <span class="text-sm font-medium text-gray-700">{{ upd.talent_name }}</span>
              </div>
              <div v-if="pmEditingUpdateId === upd.id">
                <textarea
                  v-model="pmEditUpdateText"
                  ref="pmUpdateInput"
                  class="w-full text-base border border-blue-300 rounded-lg p-3 outline-none resize-y min-h-[48px]"
                  @blur="saveUpdateRecord(upd)"
                  @keydown.escape="pmEditingUpdateId = null"
                  @input="autoResizeTextarea($event.target)"
                ></textarea>
              </div>
              <p
                v-else
                class="text-sm text-gray-600 cursor-pointer hover:bg-gray-50 rounded p-1 -m-1"
                @dblclick="startEditUpdate(upd)"
              >{{ upd.parsed_data?.progress || upd.raw_input }}</p>
              <p v-if="upd.parsed_data?.completion_pct != null" class="text-xs text-blue-500 mt-1">完成度: {{ upd.parsed_data.completion_pct }}%</p>
            </div>
          </div>
        </div>

        <!-- Actions: change status / delete -->
        <div class="mt-6 flex gap-3">
          <van-button v-if="pmInfoData.status === 'active'" size="small" type="primary" plain @click="changePmStatus(pmInfoData.id, 'completed')">标记完成</van-button>
          <van-button v-if="pmInfoData.status === 'completed'" size="small" type="success" plain @click="changePmStatus(pmInfoData.id, 'archived')">归档</van-button>
          <van-button v-if="pmInfoData.status !== 'active'" size="small" type="warning" plain @click="changePmStatus(pmInfoData.id, 'active')">重新激活</van-button>
          <van-button size="small" type="danger" plain @click="deletePmProject(pmInfoData.id)">删除</van-button>
        </div>
      </div>
    </van-popup>

    <!-- Improve Dialog -->
    <van-dialog
      v-model:show="showImproveDialog"
      title="改进"
      show-cancel-button
      confirm-button-text="提交"
      width="90vw"
      class="improve-dialog"
      @confirm="submitImprove"
    >
      <div class="px-4 py-3">
        <div class="flex items-center justify-between mb-2">
          <p class="text-sm text-gray-500">请输入改进意见，Claude 将根据反馈修改代码：</p>
          <VoiceInputButton v-model="improveFeedback" :size="16" />
        </div>
        <textarea
          v-model="improveFeedback"
          class="w-full border border-gray-300 rounded-lg p-3 text-base resize-y min-h-[160px] outline-none focus:border-indigo-400"
          rows="6"
          placeholder="需要改进的地方..."
        ></textarea>
      </div>
    </van-dialog>

    <!-- Drag ghost panel -->
    <Teleport to="body">
      <div v-if="pmDrag.active && pmDrag.ghostHtml"
        class="pm-drag-ghost"
        :style="{
          left: pmDrag.ghostX + 'px',
          top: pmDrag.ghostY + 'px',
          width: pmDrag.ghostWidth + 'px',
        }"
        v-html="pmDrag.ghostHtml"
      ></div>
    </Teleport>

    <!-- Organize Prompt Editor -->
    <van-popup
      v-model:show="showPromptEditor"
      position="bottom"
      round
      :style="{ height: '80vh' }"
    >
      <div class="flex flex-col h-full">
        <div class="flex items-center justify-between px-4 py-3 border-b">
          <van-button size="small" @click="showPromptEditor = false">取消</van-button>
          <span class="font-medium text-gray-700">编辑整理规则</span>
          <van-button size="small" type="primary" @click="saveOrganizePrompt">保存</van-button>
        </div>
        <textarea
          v-model="organizePromptText"
          class="flex-1 w-full p-4 text-sm text-gray-700 leading-relaxed focus:outline-none resize-none"
        />
        <div class="flex justify-end px-4 py-2 border-t">
          <span class="text-xs text-gray-400 cursor-pointer hover:text-blue-500" @click="resetOrganizePrompt">恢复默认</span>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTodosStore } from '../stores/todos'
import { useProjectsStore } from '../stores/projects'
import { showToast, showConfirmDialog } from 'vant'
import api from '../api'
import { Chart, BarController, CategoryScale, LinearScale, BarElement, Tooltip, Legend } from 'chart.js'
import VoiceInputButton from '../components/VoiceInputButton.vue'
import StatusPicker from '../components/StatusPicker.vue'

Chart.register(BarController, CategoryScale, LinearScale, BarElement, Tooltip, Legend)
import TopNavBar from '../components/TopNavBar.vue'

const store = useTodosStore()
const pmStore = useProjectsStore()
const _route = useRoute()
const _router = useRouter()

// Tab state — restore from localStorage so refresh keeps the user on the same tab
const activeTab = ref(parseInt(localStorage.getItem('todoActiveTab')) || 0)
const vibeTab = ref(parseInt(localStorage.getItem('todoVibeTab')) || 0)
const pmSubTab = ref(parseInt(localStorage.getItem('todoPmSubTab')) || 0)
const analysisSubTab = ref(parseInt(localStorage.getItem('todoAnalysisSubTab')) || 0)

// ---- Project Management state ----
const showPmUpdatePopup = ref(false)
const showPmCreatePopup = ref(false)
const showPmInfoPopup = ref(false)

// Update form
const pmTalentSearch = ref('')
const pmShowTalentList = ref(false)
const pmTalentResults = ref([])
const pmTalentHighlightIndex = ref(-1)
const pmTalentListRef = ref(null)
const pmSelectedTalent = ref(null)
const pmProjectSearch = ref('')
const pmShowProjectList = ref(false)
const pmProjectResults = ref([])
const pmSelectedProject = ref(null)
const pmUpdateContent = ref('')
const pmSubmitting = ref(false)
const pmLastResult = ref(null)
const showPmModelPicker = ref(false)
const pmCurrentModel = ref('')
const pmAvailableModels = ref([])

// Create form
const pmNewName = ref('')
const pmNewDesc = ref('')
const pmParentSearch = ref('')
const pmShowParentList = ref(false)
const pmParentResults = ref([])
const pmSelectedParent = ref(null)
const pmCreating = ref(false)

// Project info
const pmInfoData = ref(null)
const pmInfoLoading = ref(false)
const pmInfoRefreshing = ref(false)
const pmEditingName = ref(false)
const pmEditNameText = ref('')
const pmNameInput = ref(null)
const pmEditingDesc = ref(false)
const pmEditDescText = ref('')
const pmDescTextarea = ref(null)
const pmEditingSummary = ref(false)
const pmEditSummaryText = ref('')
const pmSummaryTextarea = ref(null)
const pmEditingUpdateId = ref(null)
const pmEditUpdateText = ref('')
const pmUpdateInput = ref(null)
const pmInfoSettingParent = ref(false)
const pmInfoParentSearch = ref('')
const pmInfoParentResults = ref([])

// Boards
const pmTimeRange = ref('month')
const pmTimeline = ref({ groups: {}, total: 0 })
const pmMembers = ref([])

// Projects list
const pmProjects = computed(() => pmStore.projects)
const pmTopProjects = computed(() => {
  const tops = pmProjects.value.filter(p => !p.parent_id)
  // Server returns projects sorted by display_order already, just preserve that order
  return tops
})

// Sort children: active first, suspended next, completed last
function sortedChildren(children) {
  const order = { active: 0, suspended: 1, completed: 2 }
  return [...children].sort((a, b) => {
    return (order[a.status] ?? 0) - (order[b.status] ?? 0)
  })
}

// Project drag reorder
const pmDrag = reactive({
  active: false,
  projectId: null,
  startIndex: -1,
  startY: 0,
  dropIndex: -1,
  ghostX: 0,
  ghostY: 0,
  ghostWidth: 0,
  ghostHtml: '',
})
const pmListRef = ref(null)

function onPmDragStart(e, projectId, index) {
  pmDrag.projectId = projectId
  pmDrag.startIndex = index
  pmDrag.startY = e.clientY
  pmDrag.active = false
  pmDrag.dropIndex = -1

  // Capture the card element for ghost clone
  const itemEl = e.target.closest('.pm-project-item')
  if (itemEl) {
    const rect = itemEl.getBoundingClientRect()
    pmDrag.ghostWidth = rect.width
    pmDrag.ghostHtml = itemEl.innerHTML
    pmDrag.ghostX = rect.left
    pmDrag.ghostY = rect.top
  }

  window.addEventListener('pointermove', onPmDragMove)
  window.addEventListener('pointerup', onPmDragEnd, { once: true })
}

function onPmDragMove(e) {
  if (!pmDrag.projectId) return
  if (!pmDrag.active && Math.abs(e.clientY - pmDrag.startY) < 5) return
  pmDrag.active = true

  // Update ghost position (centered horizontally on cursor, offset above cursor)
  pmDrag.ghostX = e.clientX
  pmDrag.ghostY = e.clientY

  const container = pmListRef.value
  if (!container) return
  const items = container.querySelectorAll('.pm-project-item')
  let dropIdx = items.length
  for (let i = 0; i < items.length; i++) {
    const rect = items[i].getBoundingClientRect()
    if (e.clientY < rect.top + rect.height / 2) {
      dropIdx = i
      break
    }
  }
  pmDrag.dropIndex = dropIdx
}

function onPmDragEnd() {
  window.removeEventListener('pointermove', onPmDragMove)
  if (pmDrag.active && pmDrag.dropIndex !== -1) {
    const projects = [...pmTopProjects.value]
    const fromIdx = pmDrag.startIndex
    let toIdx = pmDrag.dropIndex
    if (toIdx > fromIdx) toIdx--
    if (fromIdx !== toIdx) {
      const [moved] = projects.splice(fromIdx, 1)
      projects.splice(toIdx, 0, moved)
      const order = projects.map(p => p.id)
      api.put('/api/projects/reorder', { order }).then(() => pmStore.fetchProjects())
    }
  }
  pmDrag.active = false
  pmDrag.projectId = null
  pmDrag.startIndex = -1
  pmDrag.dropIndex = -1
  pmDrag.ghostHtml = ''
}
const pmSelectedParentForCreate = ref(null)
const pmParentProjectSearch = ref('')
const pmInlineDesc = ref('')
const pmShowParentProjectList = ref(false)
const pmParentProjectResults = ref([])

// Filtered project results: if a parent is selected, show only its children; otherwise show all
const pmFilteredProjectResults = computed(() => {
  const results = pmProjectResults.value
  if (pmSelectedParentForCreate.value) {
    // Show children of the selected parent
    return results.filter(p => p.parent_id === pmSelectedParentForCreate.value.id)
  }
  // No parent selected: show all projects (flat, with parent_name for context)
  return results
})


const newTitle = ref('')
const newHighPriority = ref(false)
const newDeadline = ref('')
const newDeadlineTime = ref('')
const loading = ref(false)
const adding = ref(false)

// Subtask & Start/Pause state
const expandedIds = ref(new Set())
const subtaskInputs = reactive({})
const workingTimerTick = ref(0)  // incremented every second to trigger reactivity

// Inline title editing
const inlineEditId = ref(null)
const inlineEditTitle = ref('')
const titleEditInput = ref(null)

// Detail popup
const showDetail = ref(false)
const detailItem = ref(null)
const detailItemTagIds = ref(new Set())
const detailRepeatRule = ref('')
const detailRepeatInterval = ref(1)
const detailRepeatIncludeWeekends = ref(false)

// Calendar pickers
const calendarMinDate = new Date()
const showNewDeadlinePicker = ref(false)
const showEditDeadlinePicker = ref(false)
const editingTodoId = ref(null)

// Time picker
const showTimePicker = ref(false)
const timePickerTarget = ref('')  // 'new' or 'edit'
const pendingDate = ref('')  // date string waiting for time selection
const timeStartVal = ref('12:00')
const timeEndVal = ref('')

// Analysis
const analyses = ref([])
const triggeringAnalysis = ref(false)
const analysisStatus = ref('')
const analysisStatusText = ref('')
const analysisStream = ref('')
const analysisThinking = ref('')
const analysisThinkingPre = ref(null)
const analysisStreamEl = ref(null)
const durationStats = ref([])
const durationChartCanvas = ref(null)
const generatingStats = ref(false)
const durationStatsWindow = ref('30d')
const showTagTasks = ref(false)
const tagTasksTitle = ref('')
const tagTasksList = ref([])

// Project Analysis
const projectAnalyses = ref([])
const triggeringProjectAnalysis = ref(false)
const projectAnalysisStatus = ref('')
const projectAnalysisStatusText = ref('')
const projectAnalysisStream = ref('')
const projectAnalysisThinking = ref('')
const projectAnalysisThinkingPre = ref(null)
const projectAnalysisStreamEl = ref(null)
let durationChartInstance = null

// Tag filter state (TODO scope)
const selectedTagIds = ref(new Set())
const editingTagId = ref(null)
const editingTagName = ref('')
const tagEditInput = ref(null)
const showDeleteTagConfirm = ref(false)
const deletingTag = ref(null)

// Detail tag picker
const showDetailTagPicker = ref(false)
const detailTagEditInput = ref(null)
const newTagName = ref('')

// Tag filter state (requirement scope)
const reqSelectedTagIds = ref(new Set())

// Requirement tag organize state
const reqOrganizing = ref(false)
const reqOrganizeStream = ref('')
const reqThinkingStream = ref('')
const reqThinkingPre = ref(null)
const reqOrganizePre = ref(null)
const reqOrganizeStatus = ref('')
const reqOrganizeStatusText = ref('')

// Tag organize state
const organizing = ref(false)
const organizeStream = ref('')
const thinkingStream = ref('')
const thinkingPre = ref(null)
// Organize prompt editor state
const showPromptEditor = ref(false)
const organizePromptText = ref('')
const organizePromptDefault = ref('')
const organizePre = ref(null)
const organizeStatus = ref('')
const organizeStatusText = ref('')

// Auto-scroll streaming outputs
function autoScroll(el) {
  if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight })
}
watch(thinkingStream, () => autoScroll(thinkingPre.value), { flush: 'post' })
watch(organizeStream, () => autoScroll(organizePre.value), { flush: 'post' })
watch(reqThinkingStream, () => autoScroll(reqThinkingPre.value), { flush: 'post' })
watch(reqOrganizeStream, () => autoScroll(reqOrganizePre.value), { flush: 'post' })
watch(analysisThinking, () => autoScroll(analysisThinkingPre.value), { flush: 'post' })
watch(analysisStream, () => autoScroll(analysisStreamEl.value), { flush: 'post' })
watch(projectAnalysisThinking, () => autoScroll(projectAnalysisThinkingPre.value), { flush: 'post' })
watch(projectAnalysisStream, () => autoScroll(projectAnalysisStreamEl.value), { flush: 'post' })

// All tags shorthand
const allTags = computed(() => store.tags)

// Build tag tree from flat tags with parent_id
const parentTags = computed(() => allTags.value.filter(t => !t.parent_id && allTags.value.some(c => c.parent_id === t.id)))
const childTags = computed(() => allTags.value.filter(t => t.parent_id))
const orphanTags = computed(() => allTags.value.filter(t => !t.parent_id && !allTags.value.some(c => c.parent_id === t.id)))
const tagTree = computed(() => {
  return parentTags.value.map(p => ({
    ...p,
    children: childTags.value.filter(c => c.parent_id === p.id),
  }))
})

const allSelected = computed(() => {
  const leafTags = [...childTags.value, ...orphanTags.value]
  if (leafTags.length === 0) return true
  return leafTags.every(t => selectedTagIds.value.has(t.id))
})

// Filter todos by selected tags
function filterByTags(items) {
  if (allSelected.value) return items
  if (selectedTagIds.value.size === 0) return []
  return items.filter(item => {
    const tags = item.tags || []
    if (tags.length === 0) return false
    return tags.some(tag => selectedTagIds.value.has(tag.id))
  })
}

// Requirement tag computeds (separate from TODO tags)
const reqAllTags = computed(() => store.reqTags)
const reqParentTags = computed(() => reqAllTags.value.filter(t => !t.parent_id && reqAllTags.value.some(c => c.parent_id === t.id)))
const reqChildTags = computed(() => reqAllTags.value.filter(t => t.parent_id))
const reqOrphanTags = computed(() => reqAllTags.value.filter(t => !t.parent_id && !reqAllTags.value.some(c => c.parent_id === t.id)))
const reqTagTree = computed(() => {
  return reqParentTags.value.map(p => ({
    ...p,
    children: reqChildTags.value.filter(c => c.parent_id === p.id),
  }))
})
const reqAllSelected = computed(() => {
  const leafTags = [...reqChildTags.value, ...reqOrphanTags.value]
  if (leafTags.length === 0) return true
  return leafTags.every(t => reqSelectedTagIds.value.has(t.id))
})
function filterByReqTags(items) {
  if (reqAllSelected.value) return items
  if (reqSelectedTagIds.value.size === 0) return []
  return items.filter(item => {
    const tags = item.tags || []
    if (tags.length === 0) return false
    return tags.some(tag => reqSelectedTagIds.value.has(tag.id))
  })
}
function reqSelectAll() {
  const leafs = [...reqChildTags.value, ...reqOrphanTags.value]
  if (reqAllSelected.value) {
    reqSelectedTagIds.value = new Set()
  } else {
    reqSelectedTagIds.value = new Set(leafs.map(t => t.id))
  }
}
function reqToggleTag(tagId) {
  const s = new Set(reqSelectedTagIds.value)
  if (s.has(tagId)) {
    s.delete(tagId)
  } else {
    s.add(tagId)
  }
  reqSelectedTagIds.value = s
}

const todoPendingCount = computed(() =>
  store.pending.filter(t => !t.vibe_status).length
)
const filteredPending = computed(() => filterByTags(
  store.pending.filter(t => !t.vibe_status)
))
const filteredCompleted = computed(() => filterByTags(
  store.completed.filter(t => !t.vibe_status)
))

// Vibe task computed lists
const vibeRequirements = computed(() =>
  store.pending.filter(t => t.vibe_status === 'requirement')
)
const filteredRequirements = computed(() => filterByReqTags(vibeRequirements.value))
const vibePlanning = computed(() =>
  store.pending.filter(t => t.vibe_status === 'planning')
)
const vibePending = computed(() =>
  store.pending.filter(t => t.vibe_status === 'implementing')
)
const vibeVerifying = computed(() =>
  [...store.pending, ...store.completed]
    .filter(t => t.vibe_status === 'verifying' || t.vibe_status === 'committing')
    .sort((a, b) => {
      const ta = a.vibe_verified_at ? new Date(a.vibe_verified_at).getTime() : 0
      const tb = b.vibe_verified_at ? new Date(b.vibe_verified_at).getTime() : 0
      return tb - ta
    })
)
const vibeCommitted = computed(() =>
  [...store.pending, ...store.completed].filter(t => t.vibe_status === 'committed')
)

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([store.fetchAll(), store.fetchTags(), store.fetchReqTags(), loadAnalyses(), loadDurationStats(), loadProjectAnalyses(), loadPmProjects(), loadPmTimeline(), loadPmMembers(), fetchPmModelSettings()])
    // Select all leaf tags (TODO scope)
    const leafs = allTags.value.filter(t => t.parent_id || !allTags.value.some(c => c.parent_id === t.id))
    selectedTagIds.value = new Set(leafs.map(t => t.id))
    // Select all leaf tags (requirement scope)
    const reqLeafs = reqAllTags.value.filter(t => t.parent_id || !reqAllTags.value.some(c => c.parent_id === t.id))
    reqSelectedTagIds.value = new Set(reqLeafs.map(t => t.id))
    // Auto-check git commits for committed tasks without commit_id
    checkCommitsForAll()
    // Open specific project info if navigated from project view
    handlePmFocusQuery()
  } finally {
    loading.value = false
  }
})

function handlePmFocusQuery() {
  const pid = _route.query.pmFocus
  if (pid) {
    _router.replace({ query: { ..._route.query, pmFocus: undefined } })
    openProjectInfo(parseInt(pid))
  }
}

// Also watch for route query changes (handles case when TodoView is already mounted)
watch(() => _route.query.pmFocus, (pid) => {
  if (pid && !loading.value) {
    _router.replace({ query: { ..._route.query, pmFocus: undefined } })
    activeTab.value = 1
    openProjectInfo(parseInt(pid))
  }
})

// Auto-refresh duration stats when switching to 效率分析 tab (index 2)
watch(activeTab, async (tab) => {
  localStorage.setItem('todoActiveTab', tab)
  if (tab === 1) {
    loadPmProjects()
    loadPmTimeline()
    loadPmMembers()
  }
  if (tab === 4) {
    loadDurationStats()
    loadProjectAnalyses()
    // Check if background analysis tasks are running and reconnect
    reconnectAnalysisIfRunning()
    reconnectProjectAnalysisIfRunning()
  }
}, { immediate: true })

watch(vibeTab, (tab) => localStorage.setItem('todoVibeTab', tab))
watch(pmSubTab, (tab) => localStorage.setItem('todoPmSubTab', tab))
watch(analysisSubTab, (tab) => localStorage.setItem('todoAnalysisSubTab', tab))

// Poll for status changes when there are implementing tasks
let vibePollingTimer = null

watch(vibePending, (tasks) => {
  if (tasks.length > 0 && !vibePollingTimer) {
    vibePollingTimer = setInterval(() => {
      store.fetchAll()
    }, 5000)
  } else if (tasks.length === 0 && vibePollingTimer) {
    clearInterval(vibePollingTimer)
    vibePollingTimer = null
  }
}, { immediate: true })

// Working time live timer (tick every second for in_progress tasks)
let workingTimer = null
watch(() => store.pending, (items) => {
  const hasInProgress = items.some(t =>
    t.work_status === 'in_progress' ||
    (t.children || []).some(c => c.work_status === 'in_progress')
  )
  if (hasInProgress && !workingTimer) {
    workingTimer = setInterval(() => { workingTimerTick.value++ }, 1000)
  } else if (!hasInProgress && workingTimer) {
    clearInterval(workingTimer)
    workingTimer = null
  }
}, { immediate: true, deep: true })

onUnmounted(() => {
  if (vibePollingTimer) {
    clearInterval(vibePollingTimer)
    vibePollingTimer = null
  }
  if (workingTimer) {
    clearInterval(workingTimer)
    workingTimer = null
  }
  if (durationChartInstance) {
    durationChartInstance.destroy()
    durationChartInstance = null
  }
})

function selectAll() {
  const leafs = [...childTags.value, ...orphanTags.value]
  if (allSelected.value) {
    selectedTagIds.value = new Set()
  } else {
    selectedTagIds.value = new Set(leafs.map(t => t.id))
  }
}

function toggleTag(tagId) {
  const s = new Set(selectedTagIds.value)
  if (s.has(tagId)) {
    s.delete(tagId)
  } else {
    s.add(tagId)
  }
  selectedTagIds.value = s
}

async function addTodo() {
  if (!newTitle.value.trim()) return
  adding.value = true
  try {
    await store.createTodo(newTitle.value.trim(), newHighPriority.value, newDeadline.value || null, newDeadlineTime.value || null)
    newTitle.value = ''
    newHighPriority.value = false
    newDeadline.value = ''
    newDeadlineTime.value = ''
    const leafs = allTags.value.filter(t => t.parent_id || !allTags.value.some(c => c.parent_id === t.id))
    selectedTagIds.value = new Set(leafs.map(t => t.id))
  } catch (e) {
    showToast('添加失败')
  } finally {
    adding.value = false
  }
}

async function handleComplete(id) {
  try {
    await store.completeTodo(id)
  } catch (e) {
    showToast('操作失败')
  }
}

async function handleRestart(id) {
  try {
    await store.restartTodo(id)
    showToast('已恢复到TODO')
  } catch (e) {
    showToast('操作失败')
  }
}

async function togglePriority(item, high) {
  try {
    await store.updateTodo(item.id, { high_priority: high })
  } catch (e) {
    showToast('操作失败')
  }
}

async function handleDelete(id) {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后不可恢复' })
    await store.deleteTodo(id)
    showToast('已删除')
  } catch (e) {
    // cancelled or error
  }
}

// --- Inline title editing ---

async function startInlineEdit(item) {
  inlineEditId.value = item.id
  inlineEditTitle.value = item.title
  await nextTick()
  const inputs = titleEditInput.value
  if (inputs) {
    const el = Array.isArray(inputs) ? inputs[0] : inputs
    el?.focus()
    el?.select()
  }
}

function cancelInlineEdit() {
  inlineEditId.value = null
  inlineEditTitle.value = ''
}

async function finishInlineEdit(item) {
  const title = inlineEditTitle.value.trim()
  inlineEditId.value = null
  if (!title || title === item.title) return
  try {
    await store.updateTodo(item.id, { title })
  } catch (e) {
    showToast('更新失败')
  }
}

// --- Detail popup ---

function openDetail(item) {
  if (inlineEditId.value === item.id) return
  detailItem.value = { ...item }
  detailItemTagIds.value = new Set((item.tags || []).map(t => t.id))
  detailRepeatRule.value = item.repeat_rule || ''
  detailRepeatInterval.value = item.repeat_interval || 1
  detailRepeatIncludeWeekends.value = !!item.repeat_include_weekends
  showDetailTagPicker.value = false
  newTagName.value = ''
  showDetail.value = true
}

// Available tags for the detail popup (based on item's scope)
const detailAvailableTags = computed(() => {
  if (!detailItem.value) return []
  // All vibe items (any vibe_status) use requirement-scope tags
  if (detailItem.value.vibe_status) {
    return store.reqTags.filter(t => t.parent_id)
      .concat(store.reqTags.filter(t => !t.parent_id && !store.reqTags.some(c => c.parent_id === t.id)))
  }
  return store.tags.filter(t => t.parent_id)
    .concat(store.tags.filter(t => !t.parent_id && !store.tags.some(c => c.parent_id === t.id)))
})

// Tags currently assigned to the detail item (use item's own tags directly)
const detailAssignedTags = computed(() => {
  if (!detailItem.value) return []
  return detailItem.value.tags || []
})

// Tags not yet assigned to the detail item (for the picker)
const detailUnassignedTags = computed(() => {
  if (!detailItem.value) return []
  const assignedIds = new Set((detailItem.value.tags || []).map(t => t.id))
  return detailAvailableTags.value.filter(t => !assignedIds.has(t.id))
})

async function addDetailTag(tagId) {
  showDetailTagPicker.value = false
  if (!detailItem.value) return
  const s = new Set(detailItemTagIds.value)
  s.add(tagId)
  detailItemTagIds.value = s
  try {
    const updated = await store.updateTodo(detailItem.value.id, { tag_ids: [...s] })
    detailItem.value = { ...updated }
  } catch (e) {
    showToast('标签添加失败')
  }
}

async function createAndAddDetailTag() {
  const name = newTagName.value.trim()
  if (!name || !detailItem.value) return
  const scope = detailItem.value.vibe_status ? 'requirement' : 'todo'
  try {
    const tag = await store.createTag(name, scope)
    newTagName.value = ''
    await addDetailTag(tag.id)
    // Refresh tag filter selection to include new tag
    if (scope === 'requirement') {
      reqSelectedTagIds.value = new Set([...reqSelectedTagIds.value, tag.id])
    } else {
      selectedTagIds.value = new Set([...selectedTagIds.value, tag.id])
    }
  } catch (e) {
    showToast('标签创建失败')
  }
}

async function removeDetailTag(tagId) {
  if (!detailItem.value) return
  const s = new Set(detailItemTagIds.value)
  s.delete(tagId)
  detailItemTagIds.value = s
  try {
    const updated = await store.updateTodo(detailItem.value.id, { tag_ids: [...s] })
    detailItem.value = { ...updated }
  } catch (e) {
    showToast('标签移除失败')
  }
}

async function toggleDetailTag(tagId) {
  if (!detailItem.value) return
  const s = new Set(detailItemTagIds.value)
  if (s.has(tagId)) {
    s.delete(tagId)
  } else {
    s.add(tagId)
  }
  detailItemTagIds.value = s
  try {
    const updated = await store.updateTodo(detailItem.value.id, { tag_ids: [...s] })
    detailItem.value = { ...updated }
  } catch (e) {
    showToast('标签更新失败')
  }
}

async function saveDetail() {
  if (!detailItem.value) return
  try {
    await store.updateTodo(detailItem.value.id, {
      title: detailItem.value.title.trim(),
      description: detailItem.value.description,
    })
  } catch (e) {
    showToast('保存失败')
  }
}

// --- Tag editing ---

async function startEditTag(tag) {
  editingTagId.value = tag.id
  editingTagName.value = tag.name
  await nextTick()
  // Try both the main filter and detail popup input refs
  const inputs = tagEditInput.value || detailTagEditInput.value
  if (inputs) {
    const el = Array.isArray(inputs) ? inputs[0] : inputs
    el?.focus()
    el?.select()
  }
}

function cancelEditTag() {
  editingTagId.value = null
  editingTagName.value = ''
}

async function finishEditTag(tag) {
  const newName = editingTagName.value.trim()
  editingTagId.value = null
  if (!newName || newName === tag.name) return
  try {
    await store.updateTag(tag.id, newName, tag.color)
    await store.fetchAll()
    // Refresh detail item if open
    if (detailItem.value) {
      const list = [...store.pending, ...store.completed]
      const updated = list.find(t => t.id === detailItem.value.id)
      if (updated) detailItem.value = { ...updated }
    }
    showToast('标签已更新')
  } catch (e) {
    showToast(e.response?.data?.detail || '更新失败')
  }
}

function confirmDeleteTag(tag) {
  deletingTag.value = tag
  showDeleteTagConfirm.value = true
}

async function handleDeleteTag() {
  try {
    await store.deleteTag(deletingTag.value.id)
    showToast('标签已删除')
    const s = new Set(selectedTagIds.value)
    s.delete(deletingTag.value.id)
    selectedTagIds.value = s
    await store.fetchAll()
  } catch (e) {
    showToast('删除失败')
  }
}

// --- Tag organize ---

function handleSSELine(line) {
  if (!line.startsWith('data: ')) return
  try {
    const data = JSON.parse(line.slice(6))
    if (data.type === 'thinking') {
      organizeStatusText.value = `模型正在思考中... (${data.elapsed}s)`
    } else if (data.type === 'thinking_chunk') {
      organizeStatusText.value = '模型正在思考中...'
      thinkingStream.value += data.content
    } else if (data.type === 'thinking_done') {
      organizeStatusText.value = `思考完成 (${data.elapsed}s)，正在生成分类结果...`
    } else if (data.type === 'chunk') {
      organizeStream.value += data.content
    } else if (data.type === 'delete') {
      const count = data.deletes.length
      organizeStream.value += `\n--- 删除了 ${count} 个标签 ---\n` + data.deletes.map(d => `  ${d}`).join('\n') + '\n'
    } else if (data.type === 'rename') {
      const count = data.renames.length
      organizeStream.value += `\n--- 重命名了 ${count} 个标签 ---\n` + data.renames.map(r => `  ${r}`).join('\n') + '\n'
    } else if (data.type === 'merge') {
      const count = data.merges.length
      organizeStream.value += `\n--- 合并了 ${count} 组相似标签 ---\n` + data.merges.map(m => `  ${m}`).join('\n') + '\n'
    } else if (data.type === 'done') {
      store.tags = data.tags
      const leafs = data.tags.filter(t => t.parent_id || !data.tags.some(c => c.parent_id === t.id))
      selectedTagIds.value = new Set(leafs.map(t => t.id))
      const parentCount = data.tags.filter(t => !t.parent_id && data.tags.some(c => c.parent_id === t.id)).length
      organizeStatus.value = 'done'
      organizeStatusText.value = `整理完成：${parentCount} 个分类，${leafs.length} 个标签`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 3000)
    } else if (data.type === 'error') {
      organizeStatus.value = 'error'
      organizeStatusText.value = `整理失败：${data.content}`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 5000)
    }
  } catch (e) {
    console.error('SSE parse error:', e, 'line:', line)
  }
}

async function organizeTags() {
  organizing.value = true
  organizeStream.value = ''
  thinkingStream.value = ''
  organizeStatus.value = 'running'
  organizeStatusText.value = `正在分析 ${allTags.value.length} 个标签...`

  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/todos/tags/organize', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        handleSSELine(line)
      }
    }
    if (buffer.trim()) handleSSELine(buffer)

    if (organizeStatus.value === 'running') {
      await store.fetchTags()
      const leafs = allTags.value.filter(t => t.parent_id || !allTags.value.some(c => c.parent_id === t.id))
      selectedTagIds.value = new Set(leafs.map(t => t.id))
      organizeStatus.value = 'done'
      organizeStatusText.value = '整理完成'
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 3000)
    }
  } catch (e) {
    organizeStatus.value = 'error'
    organizeStatusText.value = `整理失败：${e.message}`
    setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; thinkingStream.value = '' }, 5000)
  } finally {
    organizing.value = false
  }
}

// --- Organize prompt editor ---

async function openOrganizePromptEditor() {
  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/todos/tags/organize-prompt', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    const data = await res.json()
    organizePromptText.value = data.instructions
    organizePromptDefault.value = data.default
    showPromptEditor.value = true
  } catch (e) {
    showToast('加载失败')
  }
}

async function saveOrganizePrompt() {
  try {
    const token = localStorage.getItem('teamgr_token')
    await fetch('/api/todos/tags/organize-prompt', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ instructions: organizePromptText.value }),
    })
    showToast('已保存')
    showPromptEditor.value = false
  } catch (e) {
    showToast('保存失败')
  }
}

function resetOrganizePrompt() {
  organizePromptText.value = organizePromptDefault.value
}

// --- Requirement tag organize ---

function handleReqSSELine(line) {
  if (!line.startsWith('data: ')) return
  try {
    const data = JSON.parse(line.slice(6))
    if (data.type === 'thinking') {
      reqOrganizeStatusText.value = `模型正在思考中... (${data.elapsed}s)`
    } else if (data.type === 'thinking_chunk') {
      reqOrganizeStatusText.value = '模型正在思考中...'
      reqThinkingStream.value += data.content
    } else if (data.type === 'thinking_done') {
      reqOrganizeStatusText.value = `思考完成 (${data.elapsed}s)，正在生成分类结果...`
    } else if (data.type === 'chunk') {
      reqOrganizeStream.value += data.content
    } else if (data.type === 'merge') {
      const count = data.merges.length
      reqOrganizeStream.value += `\n--- 合并了 ${count} 组相似标签 ---\n` + data.merges.map(m => `  ${m}`).join('\n') + '\n'
    } else if (data.type === 'done') {
      store.reqTags = data.tags
      const leafs = data.tags.filter(t => t.parent_id || !data.tags.some(c => c.parent_id === t.id))
      reqSelectedTagIds.value = new Set(leafs.map(t => t.id))
      const parentCount = data.tags.filter(t => !t.parent_id && data.tags.some(c => c.parent_id === t.id)).length
      reqOrganizeStatus.value = 'done'
      reqOrganizeStatusText.value = `整理完成：${parentCount} 个分类，${leafs.length} 个标签`
      setTimeout(() => { reqOrganizeStatus.value = ''; reqOrganizeStream.value = ''; reqThinkingStream.value = '' }, 3000)
    } else if (data.type === 'error') {
      reqOrganizeStatus.value = 'error'
      reqOrganizeStatusText.value = `整理失败：${data.content}`
      setTimeout(() => { reqOrganizeStatus.value = ''; reqOrganizeStream.value = ''; reqThinkingStream.value = '' }, 5000)
    }
  } catch (e) {
    console.error('SSE parse error:', e, 'line:', line)
  }
}

async function organizeReqTags() {
  reqOrganizing.value = true
  reqOrganizeStream.value = ''
  reqThinkingStream.value = ''
  reqOrganizeStatus.value = 'running'
  reqOrganizeStatusText.value = `正在分析 ${reqAllTags.value.length} 个标签...`

  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/todos/tags/organize?scope=requirement', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        handleReqSSELine(line)
      }
    }
    if (buffer.trim()) handleReqSSELine(buffer)

    if (reqOrganizeStatus.value === 'running') {
      await store.fetchReqTags()
      const leafs = reqAllTags.value.filter(t => t.parent_id || !reqAllTags.value.some(c => c.parent_id === t.id))
      reqSelectedTagIds.value = new Set(leafs.map(t => t.id))
      reqOrganizeStatus.value = 'done'
      reqOrganizeStatusText.value = '整理完成'
      setTimeout(() => { reqOrganizeStatus.value = ''; reqOrganizeStream.value = ''; reqThinkingStream.value = '' }, 3000)
    }
  } catch (e) {
    reqOrganizeStatus.value = 'error'
    reqOrganizeStatusText.value = `整理失败：${e.message}`
    setTimeout(() => { reqOrganizeStatus.value = ''; reqOrganizeStream.value = ''; reqThinkingStream.value = '' }, 5000)
  } finally {
    reqOrganizing.value = false
  }
}

function openDeadlinePicker(item) {
  editingTodoId.value = item.id
  showEditDeadlinePicker.value = true
}

function onNewDeadlineConfirm(date) {
  showNewDeadlinePicker.value = false
  pendingDate.value = formatDate(date)
  timePickerTarget.value = 'new'
  timeStartVal.value = '12:00'
  timeEndVal.value = ''
  showTimePicker.value = true
}

function onEditDeadlineConfirm(date) {
  showEditDeadlinePicker.value = false
  if (!editingTodoId.value) return
  pendingDate.value = formatDate(date)
  timePickerTarget.value = 'edit'
  // Pre-fill with existing time if editing a todo that already has time
  const todo = store.pending.find(t => t.id === editingTodoId.value) || store.completed.find(t => t.id === editingTodoId.value)
  if (todo && todo.deadline_time) {
    const parts = todo.deadline_time.split('-')
    timeStartVal.value = parts[0] || '12:00'
    timeEndVal.value = parts[1] || ''
  } else {
    timeStartVal.value = '12:00'
    timeEndVal.value = ''
  }
  showTimePicker.value = true
}

function onTimePickerConfirm() {
  const start = timeStartVal.value
  if (!start) { onTimePickerSkip(); return }
  const timeStr = timeEndVal.value ? `${start}-${timeEndVal.value}` : start
  showTimePicker.value = false
  if (timePickerTarget.value === 'new') {
    newDeadline.value = pendingDate.value
    newDeadlineTime.value = timeStr
  } else if (timePickerTarget.value === 'edit') {
    applyEditDeadline(pendingDate.value, timeStr)
  }
}

function onTimePickerSkip() {
  showTimePicker.value = false
  if (timePickerTarget.value === 'new') {
    newDeadline.value = pendingDate.value
    newDeadlineTime.value = ''
  } else if (timePickerTarget.value === 'edit') {
    applyEditDeadline(pendingDate.value, '')
  }
}

async function applyEditDeadline(dateStr, timeStr) {
  if (!editingTodoId.value) return
  try {
    const data = { deadline: dateStr }
    data.deadline_time = timeStr || ''
    await store.updateTodo(editingTodoId.value, data)
  } catch (e) {
    showToast('设置失败')
  }
  editingTodoId.value = null
}

async function clearEditDeadline() {
  showEditDeadlinePicker.value = false
  if (!editingTodoId.value) return
  try {
    await store.updateTodo(editingTodoId.value, { deadline: '' })
  } catch (e) {
    showToast('操作失败')
  }
  editingTodoId.value = null
}

// --- Repeat config ---

const repeatUnitLabel = computed(() => {
  const map = { daily: '天', weekly: '周', monthly: '月', yearly: '年' }
  return map[detailRepeatRule.value] || ''
})

function formatDuration(startIso, endIso) {
  const ms = new Date(endIso) - new Date(startIso)
  if (ms < 0) return ''
  const minutes = Math.floor(ms / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  if (days > 0) {
    const remH = hours % 24
    return remH > 0 ? `${days}天${remH}小时` : `${days}天`
  }
  if (hours > 0) {
    const remM = minutes % 60
    return remM > 0 ? `${hours}小时${remM}分钟` : `${hours}小时`
  }
  return minutes > 0 ? `${minutes}分钟` : '不到1分钟'
}

function formatSeconds(totalSecs) {
  if (!totalSecs || totalSecs <= 0) return ''
  const h = Math.floor(totalSecs / 3600)
  const m = Math.floor((totalSecs % 3600) / 60)
  const s = totalSecs % 60
  if (h > 0) return m > 0 ? `${h}h${m}m` : `${h}h`
  if (m > 0) return `${m}m`
  return `${s}s`
}

function formatWorkingTime(item) {
  // Trigger reactivity from timer tick
  void workingTimerTick.value
  const base = item.total_working_seconds || 0
  if (item.work_status !== 'in_progress' || !item.paused_at) return formatSeconds(base)
  const elapsed = Math.max(0, Math.floor((Date.now() - new Date(item.paused_at).getTime()) / 1000))
  return formatSeconds(base + elapsed)
}

function toggleExpand(id) {
  const s = new Set(expandedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedIds.value = s
}

async function addSubtask(parentId) {
  const title = subtaskInputs[parentId]?.trim()
  if (!title) return
  try {
    await store.createSubtask(parentId, title)
    subtaskInputs[parentId] = ''
  } catch (e) {
    showToast('添加子任务失败')
  }
}

async function handleStart(id) {
  try {
    await store.startTodo(id)
  } catch (e) {
    showToast('操作失败')
  }
}

async function handlePause(id) {
  try {
    await store.pauseTodo(id)
  } catch (e) {
    showToast('操作失败')
  }
}

async function handleStop(id) {
  try {
    await store.stopTodo(id)
  } catch (e) {
    showToast('操作失败')
  }
}

async function loadAnalyses() {
  try {
    const res = await api.get('/api/todos/analysis')
    analyses.value = res.data
  } catch (e) {
    // silent
  }
}

async function loadDurationStats() {
  try {
    const res = await api.get('/api/todos/duration-stats', { params: { window: durationStatsWindow.value } })
    durationStats.value = res.data
    await nextTick()
    renderDurationChart()
  } catch (e) {
    // silent
  }
}

async function triggerDurationStats() {
  generatingStats.value = true
  try {
    await api.post(`/api/todos/duration-stats/trigger?window=${durationStatsWindow.value}`)
    await loadDurationStats()
  } catch (e) {
    showToast('生成失败')
  } finally {
    generatingStats.value = false
  }
}

function switchDurationWindow(w) {
  if (durationStatsWindow.value === w) return
  durationStatsWindow.value = w
  loadDurationStats()
}

// Plugin: draw std-dev whisker lines at the end of each bar
const errorBarPlugin = {
  id: 'errorBar',
  afterDatasetsDraw(chart) {
    const meta = chart.getDatasetMeta(0)
    if (!meta || !meta.data) return
    const ctx = chart.ctx
    const stdData = chart.data.datasets[0]._stdHours
    if (!stdData) return
    const xScale = chart.scales.x
    ctx.save()
    ctx.strokeStyle = '#374151'
    ctx.lineWidth = 1.5
    meta.data.forEach((bar, i) => {
      const std = stdData[i]
      if (!std) return
      const avg = chart.data.datasets[0].data[i]
      const xLo = xScale.getPixelForValue(Math.max(0, avg - std))
      const xHi = xScale.getPixelForValue(avg + std)
      const yCenter = bar.y
      const capH = Math.min(bar.height * 0.4, 8)
      // horizontal line from avg-std to avg+std, centered on bar end
      ctx.beginPath()
      ctx.moveTo(xLo, yCenter)
      ctx.lineTo(xHi, yCenter)
      ctx.stroke()
      // cap at low end
      ctx.beginPath()
      ctx.moveTo(xLo, yCenter - capH)
      ctx.lineTo(xLo, yCenter + capH)
      ctx.stroke()
      // cap at high end
      ctx.beginPath()
      ctx.moveTo(xHi, yCenter - capH)
      ctx.lineTo(xHi, yCenter + capH)
      ctx.stroke()
    })
    ctx.restore()
  },
}

function renderDurationChart() {
  if (!durationChartCanvas.value || durationStats.value.length === 0) return

  if (durationChartInstance) {
    durationChartInstance.destroy()
    durationChartInstance = null
  }

  const stats = [...durationStats.value].sort((a, b) => a.avg_duration_minutes - b.avg_duration_minutes)
  const labels = stats.map(s => `${s.tag_name} (${s.task_count})`)

  // Convert minutes to hours for display
  const avgHours = stats.map(s => +(s.avg_duration_minutes / 60).toFixed(1))
  const stdHours = stats.map(s => +(s.std_dev_minutes / 60).toFixed(1))

  const dataset = {
    label: '平均耗时 (小时)',
    data: avgHours,
    backgroundColor: 'rgba(139, 92, 246, 0.6)',
    borderColor: 'rgba(139, 92, 246, 1)',
    borderWidth: 1,
    _stdHours: stdHours,
  }

  const tagNames = stats.map(s => s.tag_name)

  durationChartInstance = new Chart(durationChartCanvas.value, {
    type: 'bar',
    data: { labels, datasets: [dataset] },
    plugins: [errorBarPlugin],
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      onClick(evt, elements) {
        if (elements.length > 0) {
          const idx = elements[0].index
          onChartBarClick(tagNames[idx])
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(ctx) {
              const avg = ctx.raw
              const std = stdHours[ctx.dataIndex]
              const fmtVal = v => v < 1 ? `${Math.round(v * 60)}分钟` : `${v}小时`
              return `平均: ${fmtVal(avg)}` + (std ? ` ± ${fmtVal(std)}` : ' (仅1条，无方差)')
            },
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          title: { display: true, text: '小时', font: { size: 11 } },
          ticks: { font: { size: 11 } },
        },
        y: {
          ticks: { font: { size: 11 }, cursor: 'pointer' },
        },
      },
    },
  })
}

function onChartBarClick(tagName) {
  const windowDays = durationStatsWindow.value === '7d' ? 7 : durationStatsWindow.value === '30d' ? 30 : null
  const cutoff = windowDays ? new Date(Date.now() - windowDays * 86400000) : null
  const tasks = store.completed.filter(t => {
    if (t.vibe_status) return false
    if (cutoff && new Date(t.completed_at) < cutoff) return false
    const tNames = (t.tags || []).map(tag => tag.name)
    if (tagName === '无标签') return tNames.length === 0
    return tNames.includes(tagName)
  })
  tasks.sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at))
  tagTasksTitle.value = tagName
  tagTasksList.value = tasks
  showTagTasks.value = true
}

async function triggerAnalysis() {
  triggeringAnalysis.value = true
  analysisStream.value = ''
  analysisThinking.value = ''
  analysisStatus.value = 'running'
  analysisStatusText.value = '正在分析已完成的任务...'

  let receivedDone = false
  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/todos/analysis/trigger', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'thinking' || data.type === 'thinking_chunk') {
            analysisStatusText.value = `模型正在思考中... ${data.elapsed ? '(' + data.elapsed + 's)' : ''}`
            if (data.content) analysisThinking.value += data.content
          } else if (data.type === 'thinking_done') {
            analysisStatusText.value = `思考完成 (${data.elapsed}s)，正在生成分析...`
          } else if (data.type === 'chunk') {
            if (analysisStatusText.value.includes('思考') || analysisStatusText.value.includes('分析已完成')) {
              // keep
            } else {
              analysisStatusText.value = '正在生成分析...'
            }
            analysisStream.value += data.content
          } else if (data.type === 'done') {
            receivedDone = true
            await loadAnalyses()
            // Fallback: if DB load returned empty, use stream content directly
            if (analyses.value.length === 0 && (analysisStream.value || data.content)) {
              analyses.value = [{
                id: 0,
                content: analysisStream.value || data.content,
                generated_date: new Date().toISOString().slice(0, 10),
                model_name: '',
                created_at: new Date().toISOString(),
              }]
            }
            analysisStatus.value = ''
            analysisStatusText.value = ''
            analysisStream.value = ''
            analysisThinking.value = ''
          } else if (data.type === 'error') {
            receivedDone = true
            analysisStatus.value = 'error'
            analysisStatusText.value = `分析失败：${data.content}`
            setTimeout(() => { analysisStatus.value = ''; analysisStatusText.value = '' }, 5000)
          }
        } catch (e) { /* skip malformed */ }
      }
    }
  } catch (e) {
    if (!receivedDone) {
      analysisStatus.value = 'error'
      analysisStatusText.value = `分析失败：${e.message}`
      setTimeout(() => { analysisStatus.value = ''; analysisStatusText.value = '' }, 5000)
    }
  } finally {
    triggeringAnalysis.value = false
    // Safety net: if stream ended without done event, the background task
    // may have completed and saved to DB. Try loading results.
    if (!receivedDone && analysisStatus.value === 'running') {
      const streamContent = analysisStream.value
      await loadAnalyses()
      // Fallback: use stream content if DB load returned empty
      if (analyses.value.length === 0 && streamContent) {
        analyses.value = [{
          id: 0, content: streamContent,
          generated_date: new Date().toISOString().slice(0, 10),
          model_name: '', created_at: new Date().toISOString(),
        }]
      }
      analysisStatus.value = ''
      analysisStatusText.value = ''
      analysisStream.value = ''
      analysisThinking.value = ''
    }
  }
}

async function reconnectAnalysisIfRunning() {
  if (triggeringAnalysis.value) return  // already streaming
  try {
    const res = await api.get('/api/todos/analysis/status')
    if (res.data.status === 'running') {
      // Background task is still running, reconnect to stream
      triggerAnalysis()
    } else if (res.data.status === 'done') {
      // Task finished while we were away, reload results
      await loadAnalyses()
    }
  } catch (e) { /* silent */ }
}

async function reconnectProjectAnalysisIfRunning() {
  if (triggeringProjectAnalysis.value) return
  try {
    const res = await api.get('/api/projects/analysis/status')
    if (res.data.status === 'running') {
      triggerProjectAnalysis()
    } else if (res.data.status === 'done') {
      await loadProjectAnalyses()
    }
  } catch (e) { /* silent */ }
}

// --- Project Analysis ---

async function loadProjectAnalyses() {
  try {
    const res = await api.get('/api/projects/analysis')
    projectAnalyses.value = res.data
  } catch (e) {
    // silent
  }
}

async function triggerProjectAnalysis() {
  triggeringProjectAnalysis.value = true
  projectAnalysisStream.value = ''
  projectAnalysisThinking.value = ''
  projectAnalysisStatus.value = 'running'
  projectAnalysisStatusText.value = '正在分析活跃项目...'

  let receivedDone = false
  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/projects/analysis/trigger', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'thinking' || data.type === 'thinking_chunk') {
            projectAnalysisStatusText.value = `模型正在思考中... ${data.elapsed ? '(' + data.elapsed + 's)' : ''}`
            if (data.content) projectAnalysisThinking.value += data.content
          } else if (data.type === 'thinking_done') {
            projectAnalysisStatusText.value = `思考完成 (${data.elapsed}s)，正在生成分析...`
          } else if (data.type === 'chunk') {
            if (!projectAnalysisStatusText.value.includes('思考')) {
              projectAnalysisStatusText.value = '正在生成分析...'
            }
            projectAnalysisStream.value += data.content
          } else if (data.type === 'done') {
            receivedDone = true
            await loadProjectAnalyses()
            // Fallback: if DB load returned empty, use stream content directly
            if (projectAnalyses.value.length === 0 && (projectAnalysisStream.value || data.content)) {
              projectAnalyses.value = [{
                id: 0,
                content: projectAnalysisStream.value || data.content,
                generated_date: new Date().toISOString().slice(0, 10),
                model_name: '',
                created_at: new Date().toISOString(),
              }]
            }
            projectAnalysisStatus.value = ''
            projectAnalysisStatusText.value = ''
            projectAnalysisStream.value = ''
            projectAnalysisThinking.value = ''
          } else if (data.type === 'error') {
            receivedDone = true
            projectAnalysisStatus.value = 'error'
            projectAnalysisStatusText.value = `分析失败：${data.content}`
            setTimeout(() => { projectAnalysisStatus.value = ''; projectAnalysisStatusText.value = '' }, 5000)
          }
        } catch (e) { /* skip malformed */ }
      }
    }
  } catch (e) {
    if (!receivedDone) {
      projectAnalysisStatus.value = 'error'
      projectAnalysisStatusText.value = `分析失败：${e.message}`
      setTimeout(() => { projectAnalysisStatus.value = ''; projectAnalysisStatusText.value = '' }, 5000)
    }
  } finally {
    triggeringProjectAnalysis.value = false
    // Safety net: if stream ended without done event, the background task
    // may have completed and saved to DB. Try loading results.
    if (!receivedDone && projectAnalysisStatus.value === 'running') {
      const streamContent = projectAnalysisStream.value
      await loadProjectAnalyses()
      // Fallback: use stream content if DB load returned empty
      if (projectAnalyses.value.length === 0 && streamContent) {
        projectAnalyses.value = [{
          id: 0, content: streamContent,
          generated_date: new Date().toISOString().slice(0, 10),
          model_name: '', created_at: new Date().toISOString(),
        }]
      }
      projectAnalysisStatus.value = ''
      projectAnalysisStatusText.value = ''
      projectAnalysisStream.value = ''
      projectAnalysisThinking.value = ''
    }
  }
}

// --- Requirement creation ---
const newReqTitle = ref('')
const newReqHighPriority = ref(false)
const addingReq = ref(false)
const submittingReqId = ref(null)
const selectedReqIds = ref(new Set())
const batchSubmitting = ref(false)
const batchSubmitProgress = ref('')

const allReqSelected = computed(() => {
  const reqs = filteredRequirements.value
  return reqs.length > 0 && reqs.every(r => selectedReqIds.value.has(r.id))
})

function toggleReqSelection(id) {
  const s = new Set(selectedReqIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selectedReqIds.value = s
}

function toggleReqSelectAll() {
  const reqs = filteredRequirements.value
  if (allReqSelected.value) {
    selectedReqIds.value = new Set()
  } else {
    selectedReqIds.value = new Set(reqs.map(r => r.id))
  }
}

async function submitSelectedRequirements() {
  const ids = [...selectedReqIds.value].filter(id =>
    filteredRequirements.value.some(r => r.id === id)
  )
  if (ids.length === 0) return
  try {
    await showConfirmDialog({
      title: '批量提交需求',
      message: `确认提交 ${ids.length} 个需求进入研发？将按顺序依次提交。`,
    })
  } catch { return }

  batchSubmitting.value = true
  let submitted = 0
  for (const id of ids) {
    const item = store.pending.find(t => t.id === id)
    if (!item || item.vibe_status !== 'requirement') continue
    batchSubmitProgress.value = `正在提交 (${submitted + 1}/${ids.length}): ${item.title}`
    submittingReqId.value = id
    try {
      await store.submitRequirement(id)
      submitted++
    } catch (e) {
      showToast(`提交「${item.title}」失败: ${e.response?.data?.detail || '未知错误'}`)
    }
    submittingReqId.value = null
  }
  selectedReqIds.value = new Set()
  batchSubmitting.value = false
  batchSubmitProgress.value = ''
  if (submitted > 0) showToast(`已提交 ${submitted} 个需求`)
}

async function addRequirement() {
  if (!newReqTitle.value.trim()) return
  addingReq.value = true
  try {
    await store.createRequirement(newReqTitle.value.trim(), newReqHighPriority.value)
    newReqTitle.value = ''
    newReqHighPriority.value = false
    // Refresh requirement tags in case new ones were auto-created
    const leafs = reqAllTags.value.filter(t => t.parent_id || !reqAllTags.value.some(c => c.parent_id === t.id))
    reqSelectedTagIds.value = new Set(leafs.map(t => t.id))
  } catch (e) {
    showToast(e.response?.data?.detail || '创建失败')
  } finally {
    addingReq.value = false
  }
}

async function submitRequirement(item) {
  try {
    await showConfirmDialog({
      title: '提交需求',
      message: `确认提交「${item.title}」进入研发？Claude 将分析并开始处理。`,
    })
    submittingReqId.value = item.id
    await store.submitRequirement(item.id)
    showToast('已提交，Claude 正在处理...')
  } catch (e) {
    if (e !== 'cancel') showToast(e.response?.data?.detail || '提交失败')
  } finally {
    submittingReqId.value = null
  }
}

async function deleteRequirement(item) {
  try {
    await showConfirmDialog({
      title: '删除需求',
      message: `确认删除「${item.title}」？此操作不可撤销。`,
    })
    await store.deleteTodo(item.id)
    showToast('已删除')
  } catch (e) {
    // cancelled
  }
}

async function deleteVibeTask(item) {
  try {
    await showConfirmDialog({
      title: '删除任务',
      message: `确认删除「${item.title}」？关联的 Claude session 也会一并删除，此操作不可撤销。`,
    })
    await store.deleteTodo(item.id)
    showToast('已删除')
  } catch (e) {
    // cancelled
  }
}

// --- Vibe planning ---
const editingPlanId = ref(null)
const editingPlanContent = ref('')
const planEditArea = ref(null)
const rethinkingId = ref(null)
const rethinkComments = reactive({})

// --- Vibe improve ---
const showImproveDialog = ref(false)
const improveItem = ref(null)
const improveFeedback = ref('')
const committingId = ref(null)

function autoResizePlanTextarea() {
  const el = planEditArea.value
  if (el) {
    const textarea = Array.isArray(el) ? el[0] : el
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = textarea.scrollHeight + 'px'
    }
  }
}

function startEditPlan(item) {
  editingPlanId.value = item.id
  editingPlanContent.value = item.vibe_plan || ''
  nextTick(() => {
    const el = planEditArea.value
    if (el) {
      const textarea = Array.isArray(el) ? el[0] : el
      if (textarea) {
        textarea.focus()
        textarea.style.height = 'auto'
        textarea.style.height = textarea.scrollHeight + 'px'
      }
    }
  })
}

function cancelEditPlan() {
  editingPlanId.value = null
  editingPlanContent.value = ''
}

async function finishEditPlan(item) {
  const newPlan = editingPlanContent.value
  editingPlanId.value = null
  if (newPlan !== (item.vibe_plan || '')) {
    await store.updateVibeStatus(item.id, 'planning', null, newPlan)
  }
}

async function approvePlan(item) {
  const comment = rethinkComments[item.id]?.trim() || null
  await store.updateVibeStatus(item.id, 'implementing', null, null, comment)
  if (comment) rethinkComments[item.id] = ''
  showToast('已进入实现阶段')
}

async function rethinkPlan(item) {
  const comment = rethinkComments[item.id]?.trim()
  if (!comment) {
    showToast('请输入修改意见')
    return
  }
  rethinkingId.value = item.id
  try {
    await api.post(`/api/todos/${item.id}/vibe-replan`, { comment })
    rethinkComments[item.id] = ''
    showToast('Claude 正在重新思考...')
    // Poll for plan update
    const oldPlan = item.vibe_plan
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000))
      await store.fetchAll()
      const updated = store.pending.find(t => t.id === item.id)
      if (updated && updated.vibe_plan !== oldPlan) {
        showToast('计划已更新')
        return
      }
    }
    showToast('等待超时，请稍后刷新')
  } catch (e) {
    showToast(e.response?.data?.detail || '操作失败')
  } finally {
    rethinkingId.value = null
  }
}

// --- Vibe workflow ---

async function confirmVibeVerified(item) {
  try {
    await showConfirmDialog({
      title: '确认验证通过',
      message: `确认「${item.title}」已验证通过？将自动提交并推送代码。`,
    })
    committingId.value = item.id
    await api.post(`/api/todos/${item.id}/vibe-commit`)
    showToast('正在提交代码...')
    // Poll until committed (5 min max — Claude commit msg generation + push can be slow)
    for (let i = 0; i < 100; i++) {
      await new Promise(r => setTimeout(r, 3000))
      await store.fetchAll()
      const updated = [...store.pending, ...store.completed].find(t => t.id === item.id)
      if (!updated || updated.vibe_status === 'committed') {
        showToast('代码已提交并推送')
        committingId.value = null
        return
      }
      if (updated.vibe_status === 'verifying') {
        showToast('提交失败，请检查日志')
        committingId.value = null
        return
      }
    }
    showToast('提交超时，请检查日志')
    committingId.value = null
  } catch (e) {
    committingId.value = null
    // cancelled or error
  }
}

function openImproveDialog(item) {
  improveItem.value = item
  improveFeedback.value = ''
  showImproveDialog.value = true
}

async function submitImprove() {
  if (!improveFeedback.value.trim()) {
    showToast('请输入改进意见')
    return
  }
  try {
    await api.post(`/api/todos/${improveItem.value.id}/vibe-improve`, {
      feedback: improveFeedback.value.trim(),
    })
    showImproveDialog.value = false
    showToast('已发送改进意见，Claude 将重新修改')
    await store.fetchAll()
  } catch (e) {
    showToast(e.response?.data?.detail || '操作失败')
  }
}

async function revertToVerifying(item) {
  try {
    await showConfirmDialog({
      title: '返回验证',
      message: `确认将「${item.title}」退回到待验证？`,
    })
    await store.updateVibeStatus(item.id, 'verifying')
    showToast('已退回待验证')
  } catch (e) {
    // cancelled
  }
}

async function deleteCommittedTask(item) {
  try {
    await showConfirmDialog({
      title: '删除任务',
      message: `确认删除「${item.title}」？此操作不可撤销。`,
    })
    await store.deleteTodo(item.id)
    showToast('已删除')
  } catch (e) {
    // cancelled
  }
}

async function checkCommitsForAll() {
  const tasks = vibeCommitted.value.filter(t => !t.vibe_commit_id)
  for (const task of tasks) {
    try {
      await store.checkCommit(task.id)
    } catch (e) {
      // ignore
    }
  }
}

// ---- Project Management methods ----

const pmModelActions = computed(() => {
  return pmAvailableModels.value.map(m => ({
    name: m.name,
    subname: m.location === 'local' ? '本地' : '网络',
    color: m.name === pmCurrentModel.value ? '#1989fa' : undefined,
    className: m.name === pmCurrentModel.value ? 'font-bold' : '',
  }))
})

async function fetchPmModelSettings() {
  try {
    const res = await api.get('/api/settings/model')
    pmCurrentModel.value = res.data.current_model
    pmAvailableModels.value = res.data.available_models
  } catch (e) { /* ignore */ }
}

function onPmModelSelect(action) {
  pmCurrentModel.value = action.name
}

async function loadPmProjects() {
  try { await pmStore.fetchProjects() } catch (e) { console.error('Failed to load projects', e) }
}

async function loadPmTimeline() {
  try {
    const data = await pmStore.fetchTimeline(pmTimeRange.value)
    pmTimeline.value = data
  } catch (e) { console.error('Failed to load timeline', e) }
}

async function loadPmMembers() {
  try {
    pmMembers.value = await pmStore.fetchMemberBoard()
  } catch (e) { console.error('Failed to load member board', e) }
}

async function searchPmTalents() {
  try {
    const res = await api.get('/api/talents/search', { params: { q: pmTalentSearch.value } })
    pmTalentResults.value = res.data
    pmTalentHighlightIndex.value = -1
    pmShowTalentList.value = true
  } catch (e) { pmTalentResults.value = [] }
}

function handlePmTalentKeydown(e) {
  if (!pmShowTalentList.value || pmTalentResults.value.length === 0) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    pmTalentHighlightIndex.value = Math.min(pmTalentHighlightIndex.value + 1, pmTalentResults.value.length - 1)
    scrollTalentHighlightIntoView()
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    pmTalentHighlightIndex.value = Math.max(pmTalentHighlightIndex.value - 1, 0)
    scrollTalentHighlightIntoView()
  } else if (e.key === 'Enter' && pmTalentHighlightIndex.value >= 0) {
    e.preventDefault()
    const t = pmTalentResults.value[pmTalentHighlightIndex.value]
    pmSelectedTalent.value = t
    pmTalentSearch.value = t.name
    pmShowTalentList.value = false
    pmTalentHighlightIndex.value = -1
  }
}

function scrollTalentHighlightIntoView() {
  nextTick(() => {
    const container = pmTalentListRef.value
    if (!container) return
    const items = container.children
    const target = items[pmTalentHighlightIndex.value]
    if (target) target.scrollIntoView({ block: 'nearest' })
  })
}

function handlePmUpdateEsc(e) {
  if (e.key === 'Escape') {
    showPmUpdatePopup.value = false
  }
}
watch(showPmUpdatePopup, (val) => {
  if (val) {
    document.addEventListener('keydown', handlePmUpdateEsc)
  } else {
    document.removeEventListener('keydown', handlePmUpdateEsc)
  }
})

async function searchPmParentProjects() {
  try {
    const res = await pmStore.searchProjects(pmParentProjectSearch.value)
    // Only show top-level projects as potential parents
    pmParentProjectResults.value = res.filter(p => !p.parent_id)
    pmShowParentProjectList.value = true
  } catch (e) { pmParentProjectResults.value = [] }
}

async function createPmParentProjectInline() {
  const name = pmParentProjectSearch.value.trim()
  if (!name) return
  try {
    const proj = await pmStore.createProject(name, pmInlineDesc.value.trim())
    pmSelectedParentForCreate.value = proj
    pmParentProjectSearch.value = ''
    pmInlineDesc.value = ''
    pmShowParentProjectList.value = false
    onParentSelected(proj)
    showToast('父项目已创建')
  } catch (e) {
    showToast('创建失败')
  }
}

function onParentSelected(parent) {
  // When parent is selected, clear current project selection and refresh project list
  pmSelectedProject.value = null
  pmProjectSearch.value = ''
  searchPmProjects()
}

async function searchPmProjects() {
  try {
    const res = await pmStore.searchProjects(pmProjectSearch.value)
    pmProjectResults.value = res
    pmShowProjectList.value = true
  } catch (e) { pmProjectResults.value = [] }
}

function selectPmProject(proj) {
  // Attach parent info if parent is selected or project has one
  if (pmSelectedParentForCreate.value) {
    pmSelectedProject.value = { ...proj, parent_name: pmSelectedParentForCreate.value.name, parent_id: pmSelectedParentForCreate.value.id }
  } else if (proj.parent_name) {
    pmSelectedProject.value = proj
    // Auto-fill parent project field
    pmSelectedParentForCreate.value = { id: proj.parent_id, name: proj.parent_name }
  } else {
    pmSelectedProject.value = proj
  }
  pmProjectSearch.value = ''
  pmShowProjectList.value = false
}

function clearPmProjectSelection() {
  pmSelectedProject.value = null
  pmProjectSearch.value = ''
}

async function searchPmParent() {
  try {
    const res = await pmStore.searchProjects(pmParentSearch.value)
    pmParentResults.value = res
    pmShowParentList.value = true
  } catch (e) { pmParentResults.value = [] }
}

async function createPmProjectInline(parentProj = null) {
  const name = pmProjectSearch.value.trim()
  if (!name) return
  try {
    const proj = await pmStore.createProject(name, pmInlineDesc.value.trim(), parentProj?.id || null)
    // Attach parent info for display
    if (parentProj) {
      pmSelectedProject.value = { ...proj, parent_name: parentProj.name, parent_id: parentProj.id }
    } else {
      pmSelectedProject.value = proj
    }
    pmProjectSearch.value = ''
    pmInlineDesc.value = ''
    pmShowProjectList.value = false
    showToast(parentProj ? `已创建为「${parentProj.name}」的子项目` : '项目已创建')
  } catch (e) {
    showToast('创建失败')
  }
}

async function createPmProject() {
  if (!pmNewName.value.trim()) return
  pmCreating.value = true
  try {
    await pmStore.createProject(pmNewName.value.trim(), pmNewDesc.value.trim(), pmSelectedParent.value?.id || null)
    showToast('项目创建成功')
    pmNewName.value = ''
    pmNewDesc.value = ''
    pmSelectedParent.value = null
    pmParentSearch.value = ''
    showPmCreatePopup.value = false
  } catch (e) {
    showToast('创建失败')
  } finally {
    pmCreating.value = false
  }
}

async function submitPmUpdate() {
  if (!pmSelectedTalent.value || !pmSelectedProject.value || !pmUpdateContent.value.trim()) return
  pmSubmitting.value = true
  try {
    await pmStore.submitUpdate(
      pmSelectedProject.value.id,
      pmSelectedTalent.value.id,
      pmUpdateContent.value.trim(),
      pmCurrentModel.value || null
    )
    // Clear talent and content, keep project selection for next entry
    pmSelectedTalent.value = null
    pmTalentSearch.value = ''
    pmShowTalentList.value = false
    pmTalentResults.value = []
    pmUpdateContent.value = ''
    showToast('已提交，LLM 正在后台处理')
    // Refresh boards in background
    loadPmTimeline()
    loadPmMembers()
  } catch (e) {
    showToast('提交失败')
  } finally {
    pmSubmitting.value = false
  }
}

async function openProjectInfo(id) {
  showPmInfoPopup.value = true
  pmInfoLoading.value = true
  pmInfoData.value = null
  pmInfoSettingParent.value = false
  pmInfoParentSearch.value = ''
  pmInfoParentResults.value = []
  pmEditingName.value = false
  pmEditingDesc.value = false
  pmEditingSummary.value = false
  pmEditingUpdateId.value = null
  try {
    pmInfoData.value = await pmStore.getProjectInfo(id)
  } catch (e) {
    showToast('加载项目信息失败')
  } finally {
    pmInfoLoading.value = false
  }
}

async function refreshPmInfo() {
  if (!pmInfoData.value) return
  pmInfoRefreshing.value = true
  try {
    await pmStore.refreshProjectInfo(pmInfoData.value.id)
    pmInfoData.value = await pmStore.getProjectInfo(pmInfoData.value.id)
    showToast('已刷新')
  } catch (e) {
    showToast('刷新失败')
  } finally {
    pmInfoRefreshing.value = false
  }
}

function startEditPmName() {
  pmEditNameText.value = pmInfoData.value?.name || ''
  pmEditingName.value = true
  nextTick(() => { pmNameInput.value?.focus(); pmNameInput.value?.select() })
}

async function savePmName() {
  pmEditingName.value = false
  if (!pmInfoData.value) return
  const newName = pmEditNameText.value.trim()
  if (!newName || newName === pmInfoData.value.name) return
  try {
    await pmStore.updateProject(pmInfoData.value.id, { name: newName })
    pmInfoData.value.name = newName
    // Also update the name in the project list
    const proj = pmProjects.value.find(p => p.id === pmInfoData.value.id)
    if (proj) proj.name = newName
    const sub = pmProjects.value.flatMap(p => p.children || []).find(c => c.id === pmInfoData.value.id)
    if (sub) sub.name = newName
  } catch (e) {
    showToast('保存失败')
  }
}

function autoResizeTextarea(el) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function startEditPmDesc() {
  pmEditDescText.value = pmInfoData.value?.description || ''
  pmEditingDesc.value = true
  nextTick(() => {
    const el = pmDescTextarea.value
    if (el) { autoResizeTextarea(el); el.focus() }
  })
}

async function savePmDesc() {
  pmEditingDesc.value = false
  if (!pmInfoData.value) return
  const newDesc = pmEditDescText.value.trim()
  if (newDesc === (pmInfoData.value.description || '')) return
  try {
    await pmStore.updateProject(pmInfoData.value.id, { description: newDesc })
    pmInfoData.value.description = newDesc
  } catch (e) {
    showToast('保存失败')
  }
}

function startEditPmSummary() {
  pmEditSummaryText.value = pmInfoData.value?.llm_summary || ''
  pmEditingSummary.value = true
  nextTick(() => {
    const el = pmSummaryTextarea.value
    if (el) { autoResizeTextarea(el); el.focus() }
  })
}

async function savePmSummary() {
  pmEditingSummary.value = false
  if (!pmInfoData.value) return
  const newSummary = pmEditSummaryText.value.trim()
  if (newSummary === (pmInfoData.value.llm_summary || '')) return
  try {
    await pmStore.updateProject(pmInfoData.value.id, { llm_summary: newSummary })
    pmInfoData.value.llm_summary = newSummary
    showToast('已保存')
  } catch (e) {
    showToast('保存失败')
  }
}

function startEditUpdate(upd) {
  pmEditingUpdateId.value = upd.id
  pmEditUpdateText.value = upd.raw_input || ''
  nextTick(() => {
    const el = pmUpdateInput.value
    const input = Array.isArray(el) ? el[0] : el
    if (input) { autoResizeTextarea(input); input.focus() }
  })
}

async function saveUpdateRecord(upd) {
  pmEditingUpdateId.value = null
  const newText = pmEditUpdateText.value.trim()
  if (!newText || newText === (upd.raw_input || '')) return
  try {
    await pmStore.updateProjectUpdate(upd.id, newText)
    upd.raw_input = newText
    // Also update the display text
    if (upd.parsed_data) upd.parsed_data.progress = newText
    showToast('已保存')
  } catch (e) {
    showToast('保存失败')
  }
}

async function searchPmInfoParent() {
  try {
    const res = await pmStore.searchProjects(pmInfoParentSearch.value)
    // Only top-level projects, exclude current project
    pmInfoParentResults.value = res.filter(p => !p.parent_id && p.id !== pmInfoData.value?.id)
  } catch (e) { pmInfoParentResults.value = [] }
}

async function setPmInfoParent(parent) {
  if (!pmInfoData.value) return
  try {
    await pmStore.updateProject(pmInfoData.value.id, { parent_id: parent.id })
    pmInfoData.value.parent_id = parent.id
    pmInfoData.value.parent_name = parent.name
    pmInfoSettingParent.value = false
    pmInfoParentSearch.value = ''
    pmInfoParentResults.value = []
    loadPmProjects()
    showToast('已设置父项目')
  } catch (e) { showToast('设置失败') }
}

async function clearPmInfoParent() {
  if (!pmInfoData.value) return
  try {
    await pmStore.updateProject(pmInfoData.value.id, { parent_id: null })
    pmInfoData.value.parent_id = null
    pmInfoData.value.parent_name = null
    loadPmProjects()
    showToast('已移除父项目')
  } catch (e) { showToast('操作失败') }
}

async function changePmStatus(id, status) {
  try {
    await pmStore.updateProject(id, { status })
    if (pmInfoData.value && pmInfoData.value.id === id) {
      pmInfoData.value = await pmStore.getProjectInfo(id)
    }
    loadPmProjects()
    showToast('状态已更新')
  } catch (e) { showToast('更新失败') }
}

async function deletePmProject(id) {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后不可恢复，确定？' })
    await pmStore.deleteProject(id)
    showPmInfoPopup.value = false
    showToast('已删除')
  } catch (e) { /* cancelled */ }
}

function groupUpdatesByProject(updates) {
  const map = {}
  for (const upd of updates) {
    const pid = upd.project_id
    if (!map[pid]) {
      map[pid] = { project_id: pid, project_name: upd.project_name, updates: [] }
    }
    map[pid].updates.push(upd)
  }
  return Object.values(map)
}

function formatShortDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z')
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h4 class="font-semibold text-gray-800 mt-1 mb-0">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-semibold text-gray-800 mt-1 mb-0">$1</h3>')
    .replace(/^# (.+)$/gm, '<h3 class="font-bold text-gray-800 mt-1 mb-0">$1</h3>')
    .replace(/^- (.+)$/gm, '<li class="ml-3 list-disc">$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-3 list-decimal">$2</li>')
    .replace(/\n{2,}/g, '<br>')
    .replace(/\n/g, '<br>')
}

function repeatLabel(item) {
  const map = { daily: '天', weekly: '周', monthly: '月', yearly: '年' }
  const unit = map[item.repeat_rule] || ''
  const interval = item.repeat_interval || 1
  return interval === 1 ? `每${unit}` : `每${interval}${unit}`
}

async function saveRepeatConfig() {
  if (!detailItem.value) return
  try {
    const updated = await store.updateTodo(detailItem.value.id, {
      repeat_rule: detailRepeatRule.value || '',
      repeat_interval: detailRepeatInterval.value || 1,
      repeat_include_weekends: detailRepeatIncludeWeekends.value,
    })
    detailItem.value = { ...detailItem.value, ...updated }
  } catch (e) {
    showToast('保存失败')
  }
}

function formatDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatDateTime(isoStr) {
  if (!isoStr) return ''
  // Backend stores UTC (datetime.utcnow), append Z so browser converts to local timezone
  const d = new Date(isoStr.endsWith('Z') ? isoStr : isoStr + 'Z')
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.pm-delete-btn {
  opacity: 0.3;
  transition: opacity 0.2s;
}
.pm-delete-btn:hover {
  opacity: 1;
}
.nav-card {
  transition: all 0.15s ease;
}
.nav-card:active {
  transform: scale(0.97);
  opacity: 0.8;
}
.todo-tabs :deep(.van-tabs__nav) {
  background: #fff;
}
.vibe-tabs {
  margin-top: 8px;
}
.subtask-input {
  font-size: 13px !important;
  padding: 4px 10px !important;
  border-radius: 8px !important;
}
.rotate-180 {
  transform: rotate(180deg);
}
.todo-input {
  border: 1px solid #d1d5db !important;
  border-radius: 12px !important;
  padding: 8px 12px !important;
  overflow: hidden;
}
.todo-input::after {
  display: none !important;
}
.todo-input:focus-within {
  border-color: #3b82f6 !important;
}
.tag-closeable :deep(.van-tag__close) {
  opacity: 0;
  width: 0;
  margin-left: 0;
  transition: all 0.2s;
}
.tag-closeable:hover :deep(.van-tag__close) {
  opacity: 1;
  width: 12px;
  margin-left: 2px;
}
.edit-title-input {
  border: 1.5px solid #3b82f6;
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 14px;
  width: 100%;
  outline: none;
  background: #fff;
}
.detail-field {
  border: 1px solid #e5e7eb !important;
  border-radius: 8px !important;
  padding: 6px 10px !important;
}
.detail-field::after {
  display: none !important;
}
.repeat-select {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
  background: #fff;
  outline: none;
  color: #374151;
}
.repeat-select:focus {
  border-color: #8b5cf6;
}
.repeat-interval-input {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
  width: 60px;
  text-align: center;
  outline: none;
  background: #fff;
}
.repeat-interval-input:focus {
  border-color: #8b5cf6;
}
.new-tag-wrapper {
  display: inline-flex;
  align-items: center;
  position: relative;
}
.new-tag-input {
  border: 1px dashed #9ca3af;
  border-radius: 4px;
  padding: 2px 8px;
  padding-right: 24px;
  font-size: 12px;
  width: 100px;
  outline: none;
  background: #fff;
}
.new-tag-input:focus {
  border-color: #3b82f6;
  border-style: solid;
}
.new-tag-confirm {
  position: absolute;
  right: 4px;
  color: #3b82f6;
  font-size: 16px;
  cursor: pointer;
}
.edit-tag-input {
  border: 1.5px solid #3b82f6;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 13px;
  width: 80px;
  outline: none;
  background: #fff;
}
.detail-tag-add-wrapper {
  display: inline-block;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.analysis-content :deep(h3),
.analysis-content :deep(h4) {
  margin-top: 0.75rem;
  margin-bottom: 0.25rem;
}
.analysis-content :deep(li) {
  margin-left: 1rem;
  padding-left: 0.25rem;
}
.analysis-content :deep(strong) {
  color: #374151;
}
.duration-chart-container {
  position: relative;
  width: 100%;
}
.vibe-summary-content :deep(li) {
  margin-left: 0.5rem;
  padding-left: 0.125rem;
  line-height: 1.35;
}
.vibe-summary-content :deep(h3),
.vibe-summary-content :deep(h4) {
  line-height: 1.25;
}
.vibe-summary-content :deep(strong) {
  color: #374151;
}
:deep(.van-tag) {
  white-space: nowrap;
  flex-shrink: 0;
}
</style>

<style>
/* PC端改进对话框限制最大宽度 */
.improve-dialog {
  max-width: 560px !important;
}

/* Drag ghost panel */
.pm-drag-ghost {
  position: fixed;
  pointer-events: none;
  z-index: 9999;
  transform: translate(-50%, -50%) scale(0.95);
  opacity: 0.75;
  filter: blur(1px);
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  transition: opacity 0.1s;
}
</style>

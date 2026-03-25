<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
        <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
        <h1 class="text-lg font-bold text-gray-800">{{ talent?.name || '人才详情' }}</h1>
        <van-popover v-model:show="showActions" :actions="actions" @select="onAction" placement="bottom-end">
          <template #reference>
            <van-icon name="ellipsis" size="20" class="cursor-pointer" />
          </template>
        </van-popover>
      </div>
    </div>

    <!-- Phase 1: Uploaded, awaiting processing -->
    <div
      v-if="hasUploaded"
      class="max-w-3xl mx-auto px-4 pt-3"
    >
      <div class="bg-green-50 border border-green-200 rounded-xl px-4 py-3 flex items-center gap-2">
        <van-icon name="passed" size="16" color="#16a34a" />
        <span class="text-sm text-green-700">简历已上传，等待后台解析...</span>
      </div>
    </div>

    <!-- Phase 2: Processing -->
    <div
      v-if="hasActiveProcessing"
      class="max-w-3xl mx-auto px-4 pt-3"
    >
      <div class="bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3 flex items-center gap-2">
        <van-loading size="14px" color="#d97706" />
        <span class="text-sm text-yellow-700">后台解析中...</span>
      </div>
    </div>

    <!-- Update Available Banner -->
    <div
      v-if="updateAvailable && !hasProcessing"
      class="max-w-3xl mx-auto px-4 pt-3"
    >
      <div class="bg-green-50 border border-green-200 rounded-xl px-4 py-3 flex items-center justify-between">
        <span class="text-sm text-green-700">信息已更新</span>
        <van-button size="small" type="success" plain round @click="refreshData">
          刷新查看
        </van-button>
      </div>
    </div>

    <div v-if="talent" class="max-w-3xl mx-auto px-4 py-4 space-y-4">
      <!-- Basic Info Card -->
      <div class="bg-white rounded-xl shadow-sm p-5">
        <h2 class="text-xl font-bold text-gray-800">{{ talent.name }}</h2>
        <div v-if="talent.tags.length" class="flex gap-1 flex-wrap mt-2">
          <template v-for="tag in talent.tags" :key="tag.id">
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
              :color="tag.color"
              size="medium"
              class="cursor-pointer tag-closeable"
              closeable
              @dblclick.stop="startEditTag(tag)"
              @close.stop="confirmRemoveTag(tag)"
            >
              {{ tag.name }}
            </van-tag>
          </template>
        </div>
        <p v-if="talent.summary" class="text-sm text-blue-600 mt-2 italic">
          "{{ talent.summary }}"
        </p>

        <div class="grid grid-cols-2 gap-2 text-sm">
          <div v-if="talent.current_role">
            <span class="text-gray-500">职位：</span>{{ talent.current_role }}
          </div>
          <div v-if="talent.department">
            <span class="text-gray-500">部门：</span>{{ talent.department }}
          </div>
          <div v-if="talent.email">
            <span class="text-gray-500">邮箱：</span>{{ talent.email }}
          </div>
          <div v-if="talent.phone">
            <span class="text-gray-500">电话：</span>{{ talent.phone }}
          </div>
        </div>
        <!-- Talent Status -->
        <div class="flex items-center gap-2 mt-3">
          <span class="text-sm text-gray-500">状态：</span>
          <van-tag
            v-if="talent.status"
            :color="statusColor(talent.status)"
            size="medium"
            class="cursor-pointer"
            @click="showStatusSheet = true"
          >{{ talent.status }}</van-tag>
          <van-tag
            v-else
            type="default"
            size="medium"
            class="cursor-pointer"
            @click="showStatusSheet = true"
          >未设置</van-tag>
        </div>
      </div>

      <!-- Status ActionSheet -->
      <van-action-sheet
        v-model:show="showStatusSheet"
        :actions="statusActions"
        cancel-text="取消"
        @select="onStatusSelect"
      />

      <!-- Dimension Cards -->
      <div
        v-for="dim in dimensions"
        :key="dim.key"
        class="bg-white rounded-xl shadow-sm p-5"
      >
        <h3 class="text-base font-semibold text-gray-700 mb-3 flex items-center justify-between">
          <span class="flex items-center">
            <span class="w-1 h-4 bg-blue-500 rounded-full mr-2 inline-block"></span>
            {{ dim.label }}
          </span>
          <van-button
            v-if="dim.key === 'interview_feedback'"
            size="small"
            plain
            type="primary"
            icon="edit"
            @click="showDirectFeedbackDialog = true"
          >直接录入</van-button>
        </h3>

        <!-- Custom rendering for interview_feedback -->
        <div v-if="dim.key === 'interview_feedback'" class="text-sm text-gray-600">
          <div v-if="interviewFeedbacks.length === 0" class="text-gray-400">暂无面试评价</div>
          <div v-else class="space-y-4">
            <div
              v-for="(fb, idx) in interviewFeedbacks"
              :key="idx"
              class="rounded-lg border p-4"
              :class="fb.result === '通过' ? 'border-green-200 bg-green-50/50' : 'border-red-200 bg-red-50/50'"
            >
              <div class="flex items-center gap-2 mb-2 flex-wrap">
                <van-tag :type="fb.result === '通过' ? 'success' : 'danger'" size="medium">{{ fb.result }}</van-tag>
                <van-tag
                  size="medium"
                  :color="['S','A+','A'].includes(fb.rating) ? '#059669' : '#dc2626'"
                  plain
                >{{ fb.rating }} - {{ fb.rating_label }}</van-tag>
                <span class="text-xs text-gray-400 ml-auto">{{ fb.created_at }}</span>
                <van-icon name="description" size="14" class="text-gray-400 cursor-pointer hover:text-blue-500" @click="copyEvaluation(fb.evaluation)" />
                <van-icon name="delete-o" size="14" class="text-gray-400 cursor-pointer hover:text-red-500" @click="confirmDeleteFeedback(fb._rawIndex)" />
              </div>
              <textarea v-if="isEditing('interview_feedback', fb._rawIndex, 'evaluation')" v-model="editValue" class="edit-value-input edit-value-input-wide eval-edit-input" ref="editInput"
                @blur="finishEdit" @keydown.escape.prevent="cancelEdit" @input="autoResize"></textarea>
              <div v-else class="whitespace-pre-line text-gray-700 text-sm leading-relaxed editable-value" @dblclick.stop="startEdit('interview_feedback', [fb._rawIndex, 'evaluation'], fb.evaluation)">{{ fb.evaluation }}</div>
            </div>
          </div>
        </div>

        <div v-else-if="getCardValue(dim.key)" class="text-sm text-gray-600">
          <!-- Array of objects (e.g. career_history, children) -->
          <template v-if="Array.isArray(getCardValue(dim.key))">
            <div v-if="getCardValue(dim.key).length === 0" class="text-gray-400">暂无数据</div>
            <template v-else-if="typeof getCardValue(dim.key)[0] === 'object'">
              <div
                v-for="(item, idx) in getCardValue(dim.key)"
                :key="idx"
                class="border-l-2 border-blue-200 pl-3 py-1 mb-2"
              >
                <div v-for="(v, k) in item" :key="k">
                  <template v-if="v && v !== ''">
                    <span class="text-gray-500">{{ k }}：</span>
                    <textarea v-if="isEditing(dim.key, idx, k)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
                      @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.escape="cancelEdit" rows="1" @input="autoResize" />
                    <span v-else-if="Array.isArray(v)" class="editable-value" @dblclick.stop="startEdit(dim.key, [idx, k], v, true)">{{ v.join('、') }}</span>
                    <div v-else-if="formatStructuredText(String(v))" class="formatted-text editable-value" v-html="formatStructuredText(String(v))" @dblclick.stop="startEdit(dim.key, [idx, k], v)"></div>
                    <span v-else class="editable-value whitespace-pre-line" @dblclick.stop="startEdit(dim.key, [idx, k], v)">{{ v }}</span>
                  </template>
                </div>
              </div>
            </template>
            <!-- Array of strings -->
            <ul v-else class="list-disc list-inside space-y-1">
              <li v-for="(item, idx) in getCardValue(dim.key)" :key="idx">
                <textarea v-if="isEditing(dim.key, idx)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
                  @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.escape="cancelEdit" rows="1" @input="autoResize" />
                <span v-else class="editable-value" @dblclick.stop="startEdit(dim.key, [idx], item)">{{ item }}</span>
              </li>
            </ul>
          </template>

          <!-- Object type -->
          <template v-else-if="typeof getCardValue(dim.key) === 'object'">
            <div class="space-y-2">
              <div v-for="(val, key) in getCardValue(dim.key)" :key="key">
                <span class="text-gray-500">{{ key }}：</span>
                <template v-if="val && val !== '' && !(Array.isArray(val) && val.length === 0)">
                  <!-- Array of objects inside an object field -->
                  <template v-if="Array.isArray(val) && val.length > 0 && typeof val[0] === 'object'">
                    <div
                      v-for="(subItem, si) in val"
                      :key="si"
                      class="border-l-2 border-blue-200 pl-3 py-1 ml-2 mt-1 mb-2"
                    >
                      <div v-for="(sv, sk) in subItem" :key="sk">
                        <template v-if="sv && sv !== ''">
                          <span class="text-gray-500">{{ sk }}：</span>
                          <textarea v-if="isEditing(dim.key, key, si, sk)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
                            @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.escape="cancelEdit" rows="1" @input="autoResize" />
                          <span v-else class="editable-value" @dblclick.stop="startEdit(dim.key, [key, si, sk], sv, Array.isArray(sv))">{{ Array.isArray(sv) ? sv.join('、') : sv }}</span>
                        </template>
                      </div>
                    </div>
                  </template>
                  <template v-else>
                    <textarea v-if="isEditing(dim.key, key)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
                      @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.escape="cancelEdit" rows="1" @input="autoResize" />
                    <span v-else-if="Array.isArray(val)" class="editable-value" @dblclick.stop="startEdit(dim.key, [key], val, true)">{{ val.join('、') }}</span>
                    <span v-else-if="typeof val === 'object' && val !== null" class="editable-value" @dblclick.stop="startEdit(dim.key, [key], Object.entries(val).filter(([,v]) => v).map(([k,v]) => `${k}: ${v}`).join(', '))">{{ Object.entries(val).filter(([,v]) => v).map(([k,v]) => `${k}: ${v}`).join(', ') || '' }}</span>
                    <div v-else-if="formatStructuredText(String(val))" class="formatted-text editable-value" v-html="formatStructuredText(String(val))" @dblclick.stop="startEdit(dim.key, [key], val)"></div>
                    <span v-else class="editable-value whitespace-pre-line" @dblclick.stop="startEdit(dim.key, [key], val)">{{ val }}</span>
                  </template>
                </template>
                <template v-else>
                  <textarea v-if="isEditing(dim.key, key)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
                    @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.escape="cancelEdit" rows="1" @input="autoResize" />
                  <span v-else class="text-gray-300 editable-value" @dblclick.stop="startEdit(dim.key, [key], '')">未填写</span>
                </template>
              </div>
            </div>
          </template>

          <!-- String type -->
          <template v-else>
            <textarea v-if="isEditing(dim.key)" v-model="editValue" class="edit-value-input edit-value-input-wide" ref="editInput"
              @blur="finishEdit" @keydown.enter.prevent="finishEdit" @keydown.escape="cancelEdit" rows="1" @input="autoResize" />
            <div v-else-if="getCardValue(dim.key) && formatStructuredText(getCardValue(dim.key))" class="formatted-text editable-value" v-html="formatStructuredText(getCardValue(dim.key))" @dblclick.stop="startEdit(dim.key, [], getCardValue(dim.key))"></div>
            <p v-else-if="getCardValue(dim.key)" class="editable-value whitespace-pre-line" @dblclick.stop="startEdit(dim.key, [], getCardValue(dim.key))">{{ getCardValue(dim.key) }}</p>
            <p v-else class="text-gray-400">暂无数据</p>
          </template>
        </div>
        <div v-else class="text-sm text-gray-400">暂无数据</div>
      </div>

      <!-- Entry History -->
      <div class="bg-white rounded-xl shadow-sm p-5">
        <h3 class="text-base font-semibold text-gray-700 mb-3 flex items-center justify-between">
          <span class="flex items-center">
            <span class="w-1 h-4 bg-green-500 rounded-full mr-2 inline-block"></span>
            信息录入历史
          </span>
          <van-button
            v-if="!selectMode && entryLogs.length > 0"
            size="small"
            plain
            type="primary"
            icon="list-switch"
            @click="enterSelectMode"
          >选择面试实录</van-button>
          <van-button
            v-if="selectMode"
            size="small"
            plain
            @click="exitSelectMode"
          >取消选择</van-button>
        </h3>

        <div v-if="entryLogs.length === 0" class="text-sm text-gray-400">
          暂无录入记录
        </div>
        <div v-else class="space-y-3" ref="entryLogsContainer" :class="selectMode ? 'select-none' : ''">
          <div
            v-for="log in entryLogs"
            :key="log.id"
            :data-log-id="log.id"
            class="pl-3 py-1 rounded-lg transition-all duration-150"
            :class="[
              selectedLogIds.has(log.id) ? 'border-l-4 border-blue-500 bg-blue-50/50' : 'border-l-2 border-gray-200',
              selectMode ? 'cursor-pointer' : '',
            ]"
            @pointerdown="onLogPointerDown($event, log.id)"
            @pointerenter="onLogPointerEnter(log.id)"
          >
            <div class="flex items-center justify-between mb-1">
              <div class="flex items-center gap-2 text-xs text-gray-400 flex-wrap">
                <van-checkbox
                  v-if="selectMode"
                  :model-value="selectedLogIds.has(log.id)"
                  @update:model-value="toggleLogSelection(log.id)"
                  shape="square"
                  icon-size="16px"
                  @click.stop
                />
                <van-tag size="small" :type="log.source === 'pdf' || log.source === 'docx' ? 'warning' : log.source === 'image' ? 'success' : 'primary'">
                  {{ log.source === 'pdf' ? 'PDF' : log.source === 'docx' ? 'Word' : log.source === 'image' ? '图片' : '手动' }}
                </van-tag>
                <van-tag v-if="log.status === 'uploaded'" size="small" type="success" plain>已上传</van-tag>
                <van-tag v-if="log.status === 'processing'" size="small" type="warning" plain>解析中</van-tag>
                <van-tag v-if="log.status === 'failed'" size="small" type="danger" plain>失败</van-tag>
                <van-tag v-if="log.model_name && (log.source === 'pdf' || log.source === 'docx' || log.source === 'image')" size="small" plain class="model-tag">{{ log.model_name }}</van-tag>
                {{ formatDate(log.created_at) }}
              </div>
              <van-icon
                v-if="!selectMode"
                name="delete-o"
                size="16"
                color="#ee0a24"
                class="cursor-pointer"
                @click="confirmDeleteLog(log.id)"
              />
            </div>
            <p class="text-sm text-gray-600 whitespace-pre-line">{{ expandedLogs.has(log.id) ? log.content : log.content.slice(0, 200) }}<span
              v-if="log.content.length > 200"
              class="text-blue-500 cursor-pointer ml-1"
              @click.stop="toggleLogExpand(log.id)"
            >{{ expandedLogs.has(log.id) ? '收起' : '...展开' }}</span></p>
            <!-- Parsed content summary for PDF/Word/image entries -->
            <template v-if="!selectMode && log.llm_response && log.status === 'done' && (log.source === 'pdf' || log.source === 'docx' || log.source === 'image')">
              <div class="mt-2">
                <span
                  class="text-xs text-blue-600 cursor-pointer hover:underline"
                  @click="toggleDebugSection(log.id, 'summary')"
                >{{ debugSections[log.id + ':summary'] ? '▼ 收起解析结果' : '▶ 查看解析结果' }}
                  <van-tag size="small" plain class="ml-1" style="font-size:10px">{{ getParsedSummaryLines(log).length }}项</van-tag>
                </span>
              </div>
              <div v-if="debugSections[log.id + ':summary']" class="mt-1.5 bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-gray-700 space-y-1.5">
                <template v-for="(line, li) in getParsedSummaryLines(log)" :key="li">
                  <div>
                    <span class="text-gray-500">{{ line.label }}：</span>
                    <span class="text-gray-800">{{ line.value }}</span>
                  </div>
                </template>
                <div v-if="getParsedSummaryLines(log).length === 0" class="text-gray-400">（未提取到信息）</div>
              </div>
              <!-- Debug expandable panels -->
              <div class="mt-1.5 flex gap-2 flex-wrap">
                <span
                  v-if="getParsedDebug(log).extracted_text"
                  class="text-xs text-orange-500 cursor-pointer hover:underline"
                  @click="toggleDebugSection(log.id, 'text')"
                >{{ debugSections[log.id + ':text'] ? '▼ 收起原始文本' : '▶ 原始文本' }}
                  <van-tag v-if="getParsedDebug(log).parse_mode" size="small" plain class="ml-1" style="font-size:10px">{{ getParsedDebug(log).parse_mode }}</van-tag>
                  <van-tag v-if="getParsedDebug(log).extracted_text_length" size="small" plain class="ml-1" style="font-size:10px">{{ getParsedDebug(log).extracted_text_length }}字</van-tag>
                </span>
                <span
                  class="text-xs text-purple-500 cursor-pointer hover:underline"
                  @click="toggleDebugSection(log.id, 'llm')"
                >{{ debugSections[log.id + ':llm'] ? '▼ 收起原始JSON' : '▶ 原始JSON' }}</span>
              </div>
              <div v-if="debugSections[log.id + ':text']" class="mt-2 bg-orange-50 border border-orange-200 rounded-lg p-3 max-h-80 overflow-auto">
                <pre class="text-xs text-gray-700 whitespace-pre-wrap break-words">{{ getParsedDebug(log).extracted_text || '(无提取文本)' }}</pre>
              </div>
              <div v-if="debugSections[log.id + ':llm']" class="mt-2 bg-purple-50 border border-purple-200 rounded-lg p-3 max-h-80 overflow-auto">
                <pre class="text-xs text-gray-700 whitespace-pre-wrap break-words">{{ formatLlmResponse(log.llm_response) }}</pre>
              </div>
            </template>
            <!-- Failed entry: show error -->
            <template v-if="!selectMode && log.llm_response && log.status === 'failed'">
              <div class="mt-2 bg-red-50 border border-red-200 rounded-lg p-3">
                <pre class="text-xs text-red-700 whitespace-pre-wrap break-words">{{ formatLlmResponse(log.llm_response) }}</pre>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- Floating Selection Toolbar -->
      <div
        v-if="selectMode && selectedLogIds.size > 0"
        class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-30 px-4 py-3"
      >
        <div class="max-w-3xl mx-auto flex items-center justify-between">
          <span class="text-sm text-gray-600">已选 <strong class="text-blue-600">{{ selectedLogIds.size }}</strong> 条</span>
          <div class="flex gap-2">
            <van-button size="small" plain @click="exitSelectMode">取消</van-button>
            <van-button size="small" type="primary" @click="showEvalDialog = true">生成面试评价</van-button>
          </div>
        </div>
      </div>

      <!-- Quick Entry Button -->
      <div class="pb-8" :class="selectMode && selectedLogIds.size > 0 ? 'mb-16' : ''">
        <van-button
          type="primary"
          block
          round
          @click="$router.push(`/entry?talent_id=${talent.id}`)"
        >
          为此人才录入信息
        </van-button>
      </div>
    </div>

    <div v-else class="flex items-center justify-center h-64">
      <van-loading size="36px">加载中...</van-loading>
    </div>

    <!-- Delete Talent Confirm -->
    <van-dialog
      v-model:show="showDeleteConfirm"
      title="确认删除"
      message="删除后不可恢复，确定删除该人才卡？"
      show-cancel-button
      @confirm="handleDelete"
    />

    <!-- Delete Entry Log Confirm -->
    <van-dialog
      v-model:show="showDeleteLogConfirm"
      title="删除记录"
      message="确定删除这条录入记录？"
      show-cancel-button
      @confirm="handleDeleteLog"
    />

    <!-- Remove Tag Confirm -->
    <van-dialog
      v-model:show="showRemoveTagConfirm"
      title="移除标签"
      :message="`确定从该人才卡移除标签「${removingTag?.name}」？`"
      show-cancel-button
      @confirm="handleRemoveTag"
    />

    <!-- Delete Feedback Confirm -->
    <van-dialog
      v-model:show="showDeleteFeedbackConfirm"
      title="删除评价"
      message="确定删除这条面试评价？"
      show-cancel-button
      @confirm="handleDeleteFeedback"
    />

    <!-- Interview Evaluation Dialog -->
    <van-popup
      v-model:show="showEvalDialog"
      position="bottom"
      round
      closeable
      @close="onEvalDialogClose"
    >
      <div class="p-5">
        <h3 class="text-base font-bold text-gray-800 mb-4">生成面试评价</h3>

        <div class="mb-4">
          <p class="text-sm text-gray-500 mb-2">已选择 <strong>{{ selectedLogIds.size }}</strong> 条面试实录</p>
        </div>

        <!-- Rating -->
        <div class="mb-5">
          <label class="text-sm font-medium text-gray-600 mb-2 block">评级</label>
          <div class="space-y-2">
            <div
              v-for="opt in ratingOptions"
              :key="opt.value"
              class="flex items-center gap-3 px-3 py-2 rounded-lg border cursor-pointer transition-all"
              :class="evalForm.rating === opt.value ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'"
              @click="evalForm.rating = opt.value"
            >
              <div
                class="w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0"
                :class="evalForm.rating === opt.value ? 'border-blue-500' : 'border-gray-300'"
              >
                <div v-if="evalForm.rating === opt.value" class="w-2.5 h-2.5 rounded-full bg-blue-500"></div>
              </div>
              <span class="font-medium text-sm" :class="opt.negative ? 'text-red-600' : 'text-gray-800'">{{ opt.value }}</span>
              <span class="text-xs text-gray-500">{{ opt.label }}</span>
            </div>
          </div>
        </div>

        <van-button
          type="primary"
          block
          round
          :loading="evalGenerating"
          loading-text="提交中..."
          :disabled="!evalForm.rating"
          @click="doGenerateEvaluation"
        >开始生成</van-button>
      </div>
    </van-popup>

    <!-- Direct Interview Feedback Dialog -->
    <van-popup
      v-model:show="showDirectFeedbackDialog"
      position="bottom"
      round
      closeable
      @close="onDirectFeedbackDialogClose"
    >
      <div class="p-5">
        <h3 class="text-base font-bold text-gray-800 mb-4">直接录入面试结果</h3>

        <!-- Rating -->
        <div class="mb-4">
          <label class="text-sm font-medium text-gray-600 mb-2 block">评级</label>
          <div class="space-y-2">
            <div
              v-for="opt in ratingOptions"
              :key="opt.value"
              class="flex items-center gap-3 px-3 py-2 rounded-lg border cursor-pointer transition-all"
              :class="directFeedbackForm.rating === opt.value ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'"
              @click="directFeedbackForm.rating = opt.value"
            >
              <div
                class="w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0"
                :class="directFeedbackForm.rating === opt.value ? 'border-blue-500' : 'border-gray-300'"
              >
                <div v-if="directFeedbackForm.rating === opt.value" class="w-2.5 h-2.5 rounded-full bg-blue-500"></div>
              </div>
              <span class="font-medium text-sm" :class="opt.negative ? 'text-red-600' : 'text-gray-800'">{{ opt.value }}</span>
              <span class="text-xs text-gray-500">{{ opt.label }}</span>
            </div>
          </div>
        </div>

        <!-- Evaluation Text -->
        <div class="mb-5">
          <label class="text-sm font-medium text-gray-600 mb-2 block">面试评价</label>
          <textarea
            v-model="directFeedbackForm.evaluation"
            class="w-full border border-gray-300 rounded-lg p-3 text-sm text-gray-700 resize-none focus:outline-none focus:border-blue-500"
            rows="5"
            placeholder="请输入面试评价内容..."
          ></textarea>
        </div>

        <van-button
          type="primary"
          block
          round
          :loading="directFeedbackSaving"
          loading-text="保存中..."
          :disabled="!directFeedbackForm.rating || !directFeedbackForm.evaluation.trim()"
          @click="doSaveDirectFeedback"
        >保存</van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTalentStore } from '../stores/talent'
import { showToast } from 'vant'
import api from '../api'

const route = useRoute()
const router = useRouter()
const store = useTalentStore()

const talent = ref(null)
const dimensions = ref([])
const expandedLogs = ref(new Set())
const entryLogs = ref([])
const debugSections = ref({})
const showActions = ref(false)
const showDeleteConfirm = ref(false)
const showDeleteLogConfirm = ref(false)
const deleteLogId = ref(null)
const showDeleteFeedbackConfirm = ref(false)
const deleteFeedbackIdx = ref(null)
const updateAvailable = ref(false)
const editing = ref(null) // { dimKey, path: [], isArray: false }
const editValue = ref('')
const editInput = ref(null)
const editingTagId = ref(null)
const editingTagName = ref('')
const tagEditInput = ref(null)
const showRemoveTagConfirm = ref(false)

// Interview evaluation state
const selectMode = ref(false)
const selectedLogIds = ref(new Set())
const isDraggingSelect = ref(false)
const showEvalDialog = ref(false)
const evalGenerating = ref(false)
const evalResultText = ref('')
const evalForm = ref({ rating: '' })
const showDirectFeedbackDialog = ref(false)
const directFeedbackSaving = ref(false)
const directFeedbackForm = ref({ rating: '', evaluation: '' })
const entryLogsContainer = ref(null)

const ratingOptions = [
  { value: 'S', label: '强烈推荐', negative: false },
  { value: 'A+', label: '非常推荐', negative: false },
  { value: 'A', label: '推荐', negative: false },
  { value: 'A-', label: '不推荐，放弃', negative: true },
  { value: 'B', label: '强烈不推荐，放弃', negative: true },
]
const removingTag = ref(null)
const showStatusSheet = ref(false)
const statusActions = [
  { name: '面试通过', color: '#10B981' },
  { name: '面试否决', color: '#EF4444' },
  { name: '简历未通过', color: '#EF4444' },
  { name: '拒绝岗位', color: '#6B7280' },
  { name: '已离职', color: '#6B7280' },
  { name: '清除状态', color: '#9CA3AF' },
]

function statusColor(status) {
  if (status === '面试通过') return '#10B981'
  if (status === '面试否决' || status === '简历未通过') return '#EF4444'
  if (status === '拒绝岗位' || status === '已离职') return '#6B7280'
  return '#9CA3AF'
}

async function onStatusSelect(action) {
  showStatusSheet.value = false
  const newStatus = action.name === '清除状态' ? '' : action.name
  try {
    const updated = await store.updateTalent(talent.value.id, { status: newStatus })
    talent.value = updated
    showToast(newStatus ? `状态已设为「${newStatus}」` : '状态已清除')
  } catch (e) {
    showToast('更新失败')
  }
}

let pollTimer = null

const actions = [
  { text: '录入信息', icon: 'edit' },
  { text: '导出PDF', icon: 'down' },
  { text: '删除', icon: 'delete', color: '#ee0a24' },
]

// Filter out empty placeholder entries from interview_feedback
const interviewFeedbacks = computed(() => {
  const raw = talent.value?.card_data?.interview_feedback
  if (!Array.isArray(raw)) return []
  return raw
    .map((fb, i) => ({ ...fb, _rawIndex: i }))
    .filter(fb => fb && fb.evaluation)
})

const hasUploaded = computed(() => {
  return entryLogs.value.some(l => l.status === 'uploaded')
})

const hasActiveProcessing = computed(() => {
  return entryLogs.value.some(l => l.status === 'processing')
})

const hasProcessing = computed(() => {
  return hasUploaded.value || hasActiveProcessing.value
})

function formatStructuredText(text) {
  if (!text || typeof text !== 'string') return ''
  const hasHeaders = text.includes('【')
  const hasBullets = text.includes('•')
  const hasNumbered = /\d{1,2}[\.\、]\s*[A-Za-z\u4e00-\u9fff]/.test(text)
  if (!hasHeaders && !hasBullets && !hasNumbered) return ''

  let s = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\r\n/g, '\n').replace(/\r/g, '\n')

  if (hasHeaders) s = s.replace(/【/g, '\n【')
  if (hasNumbered) s = s.replace(/(\s)(\d{1,2}[\.\、]\s*[A-Za-z\u4e00-\u9fff])/g, '\n$2')
  if (hasBullets) s = s.replace(/(\s)(•)/g, '\n$2')

  const lines = s.split('\n').map(l => l.trim()).filter(Boolean)
  if (lines.length <= 1) return ''

  const parts = []
  for (const line of lines) {
    if (/^【.*?】/.test(line)) {
      const m = line.match(/^(【.*?】)\s*(.*)/)
      parts.push(`<div class="fmt-section"><span class="fmt-section-title">${m[1]}</span></div>`)
      if (m[2]) parts.push(`<div class="fmt-text">${m[2]}</div>`)
    } else if (/^\d{1,2}[\.\、]\s/.test(line)) {
      parts.push(`<div class="fmt-numbered">${line}</div>`)
    } else if (/^•/.test(line)) {
      parts.push(`<div class="fmt-bullet">${line}</div>`)
    } else {
      parts.push(`<div class="fmt-text">${line}</div>`)
    }
  }
  return parts.join('')
}

function isEmptyValue(v) {
  if (v === null || v === undefined || v === '') return true
  if (Array.isArray(v)) return v.length === 0
  if (typeof v === 'object') return Object.values(v).every(isEmptyValue)
  return false
}

function getCardValue(key) {
  const val = talent.value?.card_data?.[key]
  if (!val) return null
  // Filter out JSON Schema definitions mistakenly stored as data
  if (typeof val === 'object' && !Array.isArray(val)) {
    if ('type' in val && ('properties' in val || 'items' in val)) return null
    // For object types, always return so empty fields can be edited
    return val
  }
  // Recursively check if all values are empty
  if (isEmptyValue(val)) return null
  return val
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN')
}

async function onAction(action) {
  if (action.text === '录入信息') {
    router.push(`/entry?talent_id=${talent.value.id}`)
  } else if (action.text === '导出PDF') {
    try {
      const res = await api.get(`/api/talents/${talent.value.id}/export-pdf`, {
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${talent.value.name}_人才卡.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast('导出失败')
    }
  } else if (action.text === '删除') {
    showDeleteConfirm.value = true
  }
}

async function handleDelete() {
  try {
    await store.deleteTalent(talent.value.id)
    showToast('已删除')
    router.push('/talent-cards')
  } catch (e) {
    showToast('删除失败')
  }
}

function toggleLogExpand(logId) {
  const s = new Set(expandedLogs.value)
  if (s.has(logId)) s.delete(logId)
  else s.add(logId)
  expandedLogs.value = s
}

function toggleDebugSection(logId, section) {
  const key = logId + ':' + section
  debugSections.value = { ...debugSections.value, [key]: !debugSections.value[key] }
}

function getParsedDebug(log) {
  if (!log.llm_response) return {}
  try {
    const parsed = JSON.parse(log.llm_response)
    return parsed._debug || {}
  } catch {
    return {}
  }
}

function getParsedSummaryLines(log) {
  if (!log.llm_response) return []
  try {
    const parsed = JSON.parse(log.llm_response)
    const lines = []
    const info = parsed.extracted_info || {}
    if (info.name) lines.push({ label: '姓名', value: info.name })
    if (info.email) lines.push({ label: '邮箱', value: info.email })
    if (info.phone) lines.push({ label: '电话', value: info.phone })
    if (info.current_role) lines.push({ label: '职位', value: info.current_role })
    if (info.department) lines.push({ label: '部门', value: info.department })
    if (parsed.summary) lines.push({ label: '摘要', value: parsed.summary })
    const tags = parsed.suggested_tags
    if (tags && tags.length) lines.push({ label: '标签', value: tags.join('、') })
    const card = parsed.card_data || {}
    for (const [key, val] of Object.entries(card)) {
      if (!val || val === '' || (Array.isArray(val) && val.length === 0) || (typeof val === 'object' && !Array.isArray(val) && Object.keys(val).length === 0)) continue
      const dimLabel = dimensions.value.find(d => d.key === key)?.label || key
      if (typeof val === 'string') {
        lines.push({ label: dimLabel, value: val })
      } else if (Array.isArray(val)) {
        lines.push({ label: dimLabel, value: val.map(v => typeof v === 'object' ? JSON.stringify(v) : String(v)).join(' | ') })
      } else if (typeof val === 'object') {
        const parts = Object.entries(val).filter(([, v]) => v && v !== '' && !(Array.isArray(v) && v.length === 0)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        if (parts.length) lines.push({ label: dimLabel, value: parts.join(' | ') })
      }
    }
    return lines
  } catch {
    return []
  }
}

function formatLlmResponse(raw) {
  if (!raw) return ''
  try {
    const parsed = JSON.parse(raw)
    // Remove _debug from display to keep it clean
    const display = { ...parsed }
    delete display._debug
    return JSON.stringify(display, null, 2)
  } catch {
    return raw
  }
}

function confirmDeleteLog(logId) {
  deleteLogId.value = logId
  showDeleteLogConfirm.value = true
}

async function handleDeleteLog() {
  try {
    await store.deleteEntryLog(deleteLogId.value)
    entryLogs.value = entryLogs.value.filter(l => l.id !== deleteLogId.value)
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

async function refreshData() {
  const id = route.params.id
  try {
    const [talentData, logs] = await Promise.all([
      store.getTalent(id),
      store.getEntryLogs(id),
    ])
    talent.value = talentData
    entryLogs.value = logs
    updateAvailable.value = false
  } catch (e) {
    showToast('刷新失败')
  }
}

async function pollProcessingEntries() {
  if (!hasProcessing.value) {
    stopPolling()
    return
  }

  const pendingLogs = entryLogs.value.filter(l => l.status === 'processing' || l.status === 'uploaded')
  let anyDone = false

  for (const log of pendingLogs) {
    try {
      const res = await api.get(`/api/entry/status/${log.id}`)
      if (res.data.status === 'done') {
        log.status = 'done'
        anyDone = true
      } else if (res.data.status === 'failed') {
        log.status = 'failed'
      } else if (res.data.status !== log.status) {
        log.status = res.data.status
      }
    } catch (e) {
      // ignore
    }
  }

  if (anyDone) {
    updateAvailable.value = true
  }

  if (!hasProcessing.value) {
    stopPolling()
  }
}

function isEditing(dimKey, ...path) {
  if (!editing.value || editing.value.dimKey !== dimKey) return false
  const ep = editing.value.path
  if (ep.length !== path.length) return false
  return ep.every((p, i) => String(p) === String(path[i]))
}

function autoResize(e) {
  const el = e.target || e
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function startEdit(dimKey, path, value, isArray = false) {
  editing.value = { dimKey, path, isArray }
  editValue.value = isArray && Array.isArray(value) ? value.join('、') : String(value ?? '')
  nextTick(() => {
    const el = editInput.value
    const input = Array.isArray(el) ? el[0] : el
    if (input) {
      input.focus()
      input.select()
      autoResize(input)
    }
  })
}

function cancelEdit() {
  editing.value = null
  editValue.value = ''
}

async function finishEdit() {
  if (!editing.value) return
  const { dimKey, path, isArray } = editing.value
  const newVal = isArray
    ? editValue.value.split(/[、,，]/).map(s => s.trim()).filter(Boolean)
    : editValue.value
  editing.value = null

  const cardData = talent.value.card_data || {}
  let dimVal = path.length === 0
    ? newVal
    : JSON.parse(JSON.stringify(cardData[dimKey] ?? {}))

  if (path.length === 1) {
    dimVal[path[0]] = newVal
  } else if (path.length === 2) {
    dimVal[path[0]][path[1]] = newVal
  } else if (path.length === 3) {
    dimVal[path[0]][path[1]][path[2]] = newVal
  }

  try {
    const updated = await store.updateTalent(talent.value.id, { card_data: { [dimKey]: dimVal } })
    talent.value = updated
    showToast('已保存')
  } catch (e) {
    showToast('保存失败')
  }
}

async function startEditTag(tag) {
  editingTagId.value = tag.id
  editingTagName.value = tag.name
  await nextTick()
  const inputs = tagEditInput.value
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
    talent.value = await store.getTalent(talent.value.id)
    showToast('标签已更新')
  } catch (e) {
    showToast(e.response?.data?.detail || '更新失败')
  }
}

function confirmRemoveTag(tag) {
  removingTag.value = tag
  showRemoveTagConfirm.value = true
}

async function handleRemoveTag() {
  try {
    const remainingTagIds = talent.value.tags
      .filter(t => t.id !== removingTag.value.id)
      .map(t => t.id)
    talent.value = await store.updateTalent(talent.value.id, { tag_ids: remainingTagIds })
    showToast('标签已移除')
  } catch (e) {
    showToast('移除失败')
  }
}

// --- Interview evaluation: selection mode ---
let dragStartIdx = -1
let dragPreSelected = new Set()

function enterSelectMode() {
  selectMode.value = true
  selectedLogIds.value = new Set()
}

function exitSelectMode() {
  selectMode.value = false
  selectedLogIds.value = new Set()
  isDraggingSelect.value = false
  dragStartIdx = -1
}

function toggleLogSelection(logId) {
  const s = new Set(selectedLogIds.value)
  if (s.has(logId)) s.delete(logId)
  else s.add(logId)
  selectedLogIds.value = s
}

function getLogIndexById(logId) {
  return entryLogs.value.findIndex(l => l.id === logId)
}

function selectRange(fromIdx, toIdx) {
  const lo = Math.min(fromIdx, toIdx)
  const hi = Math.max(fromIdx, toIdx)
  const s = new Set(dragPreSelected)
  for (let i = lo; i <= hi; i++) {
    s.add(entryLogs.value[i].id)
  }
  selectedLogIds.value = s
}

function onLogPointerDown(event, logId) {
  if (!selectMode.value) return
  if (event.target.closest('.van-checkbox')) return
  event.preventDefault()
  isDraggingSelect.value = true
  dragStartIdx = getLogIndexById(logId)
  // Remember what was already selected before this drag
  dragPreSelected = new Set(selectedLogIds.value)
  // Toggle the clicked item
  if (dragPreSelected.has(logId)) dragPreSelected.delete(logId)
  selectRange(dragStartIdx, dragStartIdx)

  const onMove = (e) => {
    if (!isDraggingSelect.value) return
    // Find which log element the pointer is over
    const el = document.elementFromPoint(e.clientX, e.clientY)
    if (!el) return
    const logEl = el.closest('[data-log-id]')
    if (!logEl) return
    const hoveredId = Number(logEl.dataset.logId)
    const hoveredIdx = getLogIndexById(hoveredId)
    if (hoveredIdx >= 0) {
      selectRange(dragStartIdx, hoveredIdx)
    }
  }
  const onUp = () => {
    isDraggingSelect.value = false
    dragStartIdx = -1
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerup', onUp)
  }
  document.addEventListener('pointermove', onMove)
  document.addEventListener('pointerup', onUp)
}

function onLogPointerEnter(logId) {
  // No-op — drag handled via document pointermove
}

// --- Interview evaluation: generation (background) ---
let evalPollTimer = null

async function doGenerateEvaluation() {
  if (!evalForm.value.rating) {
    showToast('请选择评级')
    return
  }
  evalGenerating.value = true
  try {
    const res = await store.generateInterviewEvaluation(
      talent.value.id,
      Array.from(selectedLogIds.value),
      evalForm.value.rating,
    )
    // Background task started — close dialog and poll
    showEvalDialog.value = false
    exitSelectMode()
    showToast('面试评价生成中，可安全离开页面')
    evalForm.value = { rating: '' }
    // Start polling for completion
    startEvalPolling(res.entry_id)
  } catch (e) {
    showToast('提交失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    evalGenerating.value = false
  }
}

function startEvalPolling(entryId) {
  if (evalPollTimer) clearInterval(evalPollTimer)
  evalPollTimer = setInterval(async () => {
    try {
      const res = await api.get(`/api/entry/status/${entryId}`)
      if (res.data.status === 'done') {
        clearInterval(evalPollTimer)
        evalPollTimer = null
        showToast('面试评价已生成')
        refreshData()
      } else if (res.data.status === 'failed') {
        clearInterval(evalPollTimer)
        evalPollTimer = null
        showToast('面试评价生成失败')
      }
    } catch {
      // ignore poll errors
    }
  }, 3000)
}

function copyEvaluation(text) {
  if (!text) return
  navigator.clipboard.writeText(text).then(() => {
    showToast('已复制到剪贴板')
  }).catch(() => {
    showToast('复制失败')
  })
}

function confirmDeleteFeedback(idx) {
  deleteFeedbackIdx.value = idx
  showDeleteFeedbackConfirm.value = true
}

async function handleDeleteFeedback() {
  try {
    await store.deleteInterviewFeedback(talent.value.id, deleteFeedbackIdx.value)
    // Remove from local card_data
    const feedbacks = talent.value.card_data?.interview_feedback
    if (Array.isArray(feedbacks)) {
      feedbacks.splice(deleteFeedbackIdx.value, 1)
    }
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

function onEvalDialogClose() {
  evalResultText.value = ''
  evalForm.value = { rating: '' }
}

function onDirectFeedbackDialogClose() {
  directFeedbackForm.value = { rating: '', evaluation: '' }
}

async function doSaveDirectFeedback() {
  const { rating, evaluation } = directFeedbackForm.value
  if (!rating || !evaluation.trim()) {
    showToast('请填写完整信息')
    return
  }
  directFeedbackSaving.value = true
  try {
    await store.saveDirectInterviewFeedback(talent.value.id, rating, evaluation)
    showDirectFeedbackDialog.value = false
    directFeedbackForm.value = { rating: '', evaluation: '' }
    showToast('面试结果已保存')
    refreshData()
  } catch (e) {
    showToast('保存失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    directFeedbackSaving.value = false
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollProcessingEntries, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  const id = route.params.id
  try {
    const [talentData, , logs] = await Promise.all([
      store.getTalent(id),
      store.fetchDimensions(),
      store.getEntryLogs(id),
    ])
    talent.value = talentData
    dimensions.value = store.dimensions
    entryLogs.value = logs

    if (hasProcessing.value) {
      startPolling()
    }
  } catch (e) {
    showToast('加载失败')
    router.push('/talent-cards')
  }
})

onUnmounted(() => {
  stopPolling()
  if (evalPollTimer) clearInterval(evalPollTimer)
})
</script>

<style scoped>
.editable-value {
  cursor: pointer;
  border-radius: 3px;
  transition: background-color 0.15s;
}
.editable-value:hover {
  background-color: #f0f5ff;
}
.edit-value-input {
  border: 1.5px solid #3b82f6;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 13px;
  outline: none;
  background: #fff;
  min-width: 80px;
  resize: none;
  overflow: hidden;
  line-height: 1.5;
  font-family: inherit;
  display: block;
}
.edit-value-input-wide {
  width: 100%;
}
.eval-edit-input {
  font-size: 16px;
  padding: 8px 10px;
  min-height: 120px;
  line-height: 1.7;
}
.formatted-text .fmt-section {
  margin-top: 12px;
}
.formatted-text .fmt-section:first-child {
  margin-top: 0;
}
.formatted-text .fmt-section-title {
  font-weight: 600;
  color: #1e40af;
  font-size: 13px;
}
.formatted-text .fmt-text {
  line-height: 1.7;
  margin: 2px 0;
}
.formatted-text .fmt-numbered {
  margin-top: 8px;
  margin-bottom: 2px;
  padding-left: 8px;
  border-left: 2px solid #93c5fd;
  font-weight: 500;
  line-height: 1.6;
}
.formatted-text .fmt-bullet {
  padding-left: 20px;
  line-height: 1.7;
  margin: 1px 0;
  color: #4b5563;
}
.whitespace-pre-line {
  white-space: pre-line;
}
.model-tag {
  color: #8b5cf6 !important;
  border-color: #c4b5fd !important;
  font-family: monospace;
  font-size: 10px !important;
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
.edit-tag-input {
  border: 1.5px solid #3b82f6;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 13px;
  width: 80px;
  outline: none;
  background: #fff;
}
.select-none {
  user-select: none;
  -webkit-user-select: none;
}
</style>

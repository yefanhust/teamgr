<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Top Navigation -->
    <TopNavBar />
    <van-tabs v-model:active="activeTab" sticky offset-top="52" class="ideas-tabs" @change="onTabChange">
      <van-tab title="灵感洞见">
    <div class="max-w-3xl mx-auto px-4 py-4 space-y-6">
      <!-- ========== TAGS SECTION ========== -->
      <section v-if="allTags.length > 0">
        <!-- Organize progress -->
        <div v-if="organizing || organizeStatus" class="mb-3 bg-gray-50 rounded-lg p-3 text-sm">
          <div class="flex items-center gap-2 mb-1">
            <van-icon v-if="organizeStatus === 'done'" name="checked" color="#10B981" size="14" />
            <van-icon v-else-if="organizeStatus === 'error'" name="warning-o" color="#EF4444" size="14" />
            <van-loading v-else size="14" />
            <span class="text-gray-600">{{ organizeStatusText }}</span>
          </div>
          <pre v-if="orgThinkingStream" ref="orgThinkingPre" class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed italic">{{ orgThinkingStream }}</pre>
          <pre v-if="organizeStream" ref="orgOutputPre" class="text-xs text-gray-500 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono leading-relaxed">{{ organizeStream }}</pre>
        </div>

        <div class="flex items-center gap-2 mb-2">
          <van-checkbox
            :model-value="allTagsSelected"
            shape="square"
            icon-size="16px"
            class="flex-shrink-0"
            @update:model-value="selectAllTags"
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
          <span class="text-xs text-gray-400">{{ displayedFragments.length }}/{{ fragments.length }} 条碎片</span>
        </div>

        <!-- Tag categories display -->
        <template v-if="tagCategories.length > 0">
          <div v-for="cat in tagCategories" :key="cat.name" class="mb-3">
            <div class="text-xs text-gray-400 mb-1">{{ cat.name }}</div>
            <div class="flex flex-wrap gap-1">
              <van-tag
                v-for="tag in cat.children" :key="tag"
                :type="selectedTags.has(tag) ? 'primary' : 'default'"
                size="medium"
                class="cursor-pointer"
                @click="toggleTag(tag)"
              >
                {{ tag }}
              </van-tag>
            </div>
          </div>
        </template>

        <!-- Flat tags display (when no categories) -->
        <div v-else class="flex flex-wrap gap-1 mb-2">
          <van-tag
            v-for="tag in allTags" :key="tag"
            :type="selectedTags.has(tag) ? 'primary' : 'default'"
            size="medium"
            class="cursor-pointer"
            @click="toggleTag(tag)"
          >
            {{ tag }}
          </van-tag>
        </div>
      </section>

      <!-- ========== DAILY INSIGHTS SECTION ========== -->
      <section>
        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-bottom: 12px;">
          <h2 class="text-sm font-semibold text-gray-500 flex items-center gap-2" style="margin: 0;">
            <span class="w-1 h-4 bg-orange-400 rounded-full inline-block"></span>
            每日洞见
          </h2>
          <van-button
            size="mini"
            icon="fire-o"
            :loading="generatingInsights"
            @click="generateInsights"
          >
            生成洞见
          </van-button>
        </div>
        <div v-for="(group, date) in groupedInsights" :key="date" class="mb-4">
          <div class="text-xs text-gray-400 mb-2">{{ date }}</div>
          <div class="space-y-3">
            <div
              v-for="ins in group"
              :key="ins.id"
              class="bg-white rounded-xl shadow-sm p-4"
            >
              <p class="text-sm text-gray-800 whitespace-pre-line mb-3 leading-relaxed">{{ ins.content }}</p>
              <div
                v-if="ins.reasoning"
                class="text-xs text-gray-400 bg-gray-50 rounded-lg p-2 mb-3 italic leading-relaxed"
              >
                {{ ins.reasoning }}
              </div>
              <div class="flex items-center justify-between">
                <div class="text-xs text-gray-400">
                  <span v-if="ins.model_name" class="mr-2">{{ ins.model_name }}</span>
                  <span>{{ ins.liked ? '已收藏' : '未收藏的洞见次日会被丢弃' }}</span>
                </div>
                <van-button
                  :icon="ins.liked ? 'like' : 'like-o'"
                  :type="ins.liked ? 'primary' : 'default'"
                  size="small"
                  round
                  @click="toggleLike(ins)"
                >
                  {{ ins.liked ? '已赞' : '点赞保留' }}
                </van-button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ========== FRAGMENTS SECTION ========== -->
      <section>
        <h2 class="text-sm font-semibold text-gray-500 mb-3 flex items-center gap-2">
          <span class="w-1 h-4 bg-blue-500 rounded-full inline-block"></span>
          灵感碎片
          <span v-if="fragments.length" class="text-xs text-gray-400 font-normal">({{ displayedFragments.length }})</span>
        </h2>

        <div v-if="loading" class="flex justify-center py-8">
          <van-loading size="28px">加载中...</van-loading>
        </div>

        <div v-else-if="fragments.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400">
          <p class="text-sm">还没有灵感碎片，写下你的第一个想法吧</p>
        </div>

        <template v-else>
          <div v-for="(group, category) in groupedDisplayedFragments" :key="category" class="mb-4">
            <h3 class="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1">
              {{ category }}
              <span class="text-gray-300">({{ group.length }})</span>
            </h3>
            <div class="space-y-2">
              <van-swipe-cell v-for="frag in group" :key="frag.id">
                <div class="bg-white rounded-xl shadow-sm p-3">
                  <div class="flex items-start justify-between mb-1">
                    <h4 class="text-sm font-medium text-gray-800">{{ frag.title }}</h4>
                    <span class="text-xs text-gray-400 flex-shrink-0 ml-2">{{ formatDate(frag.updated_at) }}</span>
                  </div>
                  <div class="flex items-center flex-wrap gap-1">
                    <van-tag
                      v-for="tag in (frag.tags || [])"
                      :key="tag"
                      :type="selectedTags.has(tag) ? 'primary' : 'default'"
                      plain
                      size="small"
                      class="cursor-pointer"
                      @click="toggleTag(tag)"
                    >
                      {{ tag }}
                    </van-tag>
                    <span
                      v-if="frag.content"
                      class="text-xs text-blue-500 cursor-pointer ml-1"
                      @click="toggleExpand(frag.id)"
                    >
                      {{ expandedIds.has(frag.id) ? '收起' : '展开' }}
                    </span>
                  </div>
                  <p v-if="expandedIds.has(frag.id)" class="text-sm text-gray-600 whitespace-pre-line mt-2">{{ frag.content }}</p>
                </div>
                <template #right>
                  <van-button
                    square
                    type="danger"
                    text="删除"
                    class="h-full"
                    @click="handleDeleteFragment(frag.id)"
                  />
                </template>
              </van-swipe-cell>
            </div>
          </div>
        </template>
      </section>

      <!-- ========== INPUT SECTION ========== -->
      <section>
        <div class="bg-white rounded-xl shadow-sm p-4">
          <van-field
            v-model="inputText"
            type="textarea"
            :autosize="{ minHeight: 100 }"
            placeholder="写下你此刻的灵感、想法、碎片思考..."
            class="idea-input"
          />
          <div class="flex justify-between items-center mt-3">
            <VoiceInputButton v-model="inputText" />
            <van-button
              type="primary"
              icon="guide-o"
              :disabled="!inputText.trim() || submitting"
              :loading="submitting"
              @click="submitIdea"
            >
              记录灵感
            </van-button>
          </div>
        </div>

        <!-- Streaming output area -->
        <div v-if="streamState" class="mt-3 bg-white rounded-xl shadow-sm p-4">
          <div class="flex items-center gap-2 mb-2">
            <van-loading v-if="streamState === 'streaming'" size="16px" />
            <van-icon v-else-if="streamState === 'done'" name="checked" color="#10B981" size="18" />
            <van-icon v-else-if="streamState === 'error'" name="warning-o" color="#EF4444" size="18" />
            <span class="text-sm font-medium text-gray-600">
              {{ streamState === 'streaming' ? 'LLM 整理中...' : streamState === 'done' ? '整理完成' : '处理失败' }}
            </span>
          </div>

          <!-- Thinking stream -->
          <pre
            v-if="thinkingStream"
            ref="thinkingPre"
            class="text-xs text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto font-mono leading-relaxed italic bg-gray-50 rounded-lg p-2 mb-2"
          >{{ thinkingStream }}</pre>

          <!-- Output stream -->
          <pre
            v-if="outputStream"
            ref="outputPre"
            class="text-xs text-gray-600 whitespace-pre-wrap max-h-48 overflow-y-auto font-mono leading-relaxed bg-blue-50 rounded-lg p-2"
          >{{ outputStream }}</pre>

          <!-- Result summary -->
          <div v-if="streamState === 'done' && streamResult.length > 0" class="mt-3 space-y-2">
            <div v-for="(frag, idx) in streamResult" :key="idx" class="flex items-center gap-2 text-sm">
              <van-tag :type="frag.action === 'merge' ? 'warning' : 'success'" size="small">
                {{ frag.action === 'merge' ? '合并' : '新建' }}
              </van-tag>
              <span class="text-gray-700">{{ frag.title }}</span>
              <span class="text-xs text-gray-400">[{{ frag.category }}]</span>
            </div>
          </div>
        </div>
      </section>

    </div>
      </van-tab>

      <van-tab title="输入历史">
    <div class="max-w-3xl mx-auto px-4 py-4">
      <div v-if="loadingHistory" class="flex justify-center py-8">
        <van-loading size="28px">加载中...</van-loading>
      </div>

      <div v-else-if="history.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400 text-sm">
        暂无输入历史
      </div>

      <template v-else>
        <div class="space-y-2">
          <div v-for="log in history" :key="log.id" class="bg-white rounded-xl shadow-sm p-3">
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs text-gray-400">{{ formatDateTime(log.created_at) }}</span>
              <van-tag
                :type="log.status === 'done' ? 'success' : log.status === 'processing' ? 'warning' : 'danger'"
                size="small"
              >
                {{ log.status === 'done' ? '已处理' : log.status === 'processing' ? '处理中' : '失败' }}
              </van-tag>
            </div>
            <p class="text-sm text-gray-700 whitespace-pre-line">{{ log.raw_text }}</p>
          </div>
        </div>

        <div v-if="historyTotal > 20" class="flex justify-center pt-4 pb-2">
          <van-pagination
            v-model="historyPage"
            :total-items="historyTotal"
            :items-per-page="20"
            :show-page-size="3"
            force-ellipses
            @change="loadHistory"
          />
        </div>
      </template>
    </div>
      </van-tab>

      <van-tab title="流光剪影">
    <div class="max-w-3xl mx-auto px-4 py-4">
      <!-- Password gate -->
      <template v-if="!diaryStore.verified">
        <div class="bg-white rounded-xl shadow-sm p-8 text-center mt-8">
          <div class="text-4xl mb-3 opacity-60">&#x1F512;</div>
          <h3 class="text-lg font-semibold text-gray-700 mb-2">流光剪影</h3>
          <p class="text-base text-gray-400 mb-5">记录有价值、有意义或有趣的事情</p>
          <van-field
            v-model="diaryPwd"
            type="password"
            placeholder="请输入密码"
            class="diary-pwd-input mb-4"
            @keyup.enter="verifyDiaryPwd"
          />
          <van-button type="primary" block :loading="diaryVerifying" @click="verifyDiaryPwd">
            进入
          </van-button>
          <p v-if="diaryPwdError" class="text-xs text-red-500 mt-2">{{ diaryPwdError }}</p>
        </div>
      </template>

      <!-- Diary content -->
      <template v-else>
        <!-- Tag filter bar (aligned with TalentCardsView style) -->
        <div class="flex items-center gap-2 mb-2">
          <van-checkbox
            :model-value="diaryAllTagsSelected"
            shape="square"
            icon-size="16px"
            class="flex-shrink-0"
            @update:model-value="selectAllDiaryTags"
          >
            全选
          </van-checkbox>
          <span class="text-xs text-gray-400">{{ diaryStore.entries.length }} 条手记</span>
        </div>
        <div class="flex gap-2 flex-wrap items-center mb-4">
          <template v-for="t in diaryStore.tags" :key="t.id">
            <input
              v-if="diaryEditingTagId === t.id"
              v-model="diaryEditingTagName"
              class="diary-edit-tag-input"
              @blur="finishEditDiaryTag(t)"
              @keypress.enter="finishEditDiaryTag(t)"
              @keydown.escape="cancelEditDiaryTag"
              ref="diaryTagEditInput"
            />
            <van-tag
              v-else
              :type="diarySelectedTagIds.has(t.id) ? 'primary' : 'default'"
              :color="diarySelectedTagIds.has(t.id) ? t.color : undefined"
              size="medium"
              class="cursor-pointer diary-tag-closeable"
              closeable
              @click="toggleDiaryTagFilter(t.id)"
              @dblclick.stop="startEditDiaryTag(t)"
              @close.stop="confirmDeleteDiaryTag(t)"
            >
              {{ t.name }}
            </van-tag>
          </template>
        </div>

        <!-- AI comment prompt template -->
        <div
          class="mb-4 bg-gray-50 rounded-xl p-3 cursor-pointer"
          @click="toggleDiaryPromptPreview"
          @dblclick.stop="openDiaryPromptEditor"
        >
          <div class="flex items-center justify-between">
            <span class="text-sm text-gray-500 font-medium">AI 评论提示词模板</span>
            <span class="text-xs text-gray-400">{{ showDiaryPromptPreview ? '收起 · 双击编辑' : '查看 · 双击编辑' }}</span>
          </div>
          <template v-if="showDiaryPromptPreview">
            <pre class="mt-2 text-sm text-gray-600 whitespace-pre-wrap leading-relaxed font-sans">{{ diaryPromptText }}</pre>
            <div v-if="diaryLikedExamples.length > 0" class="mt-3 border-t border-gray-200 pt-2">
              <div class="text-xs text-amber-600 font-medium mb-1">&#x1F44D; 被赞的评论范例（会拼接到提示词后面）</div>
              <div v-for="(ex, i) in diaryLikedExamples" :key="i" class="bg-white rounded-lg p-2 mb-1 text-xs">
                <div class="text-gray-400">手记：{{ ex.content }}</div>
                <div class="text-gray-600 mt-1">评论：{{ ex.comment }}</div>
              </div>
            </div>
            <div v-if="diaryDislikedCount > 0" class="mt-2 text-xs text-red-400">
              &#x1F44E; {{ diaryDislikedCount }} 条被踩的评论，今晚定时任务会重新生成
            </div>
            <div v-if="diaryLikedExamples.length === 0 && diaryDislikedCount === 0" class="mt-2 text-xs text-gray-400">
              暂无赞/踩反馈。赞过的评论会作为范例拼接到提示词后，踩过的会在今晚重新生成。
            </div>
          </template>
        </div>

        <!-- Entry list -->
        <div v-if="diaryStore.loading" class="flex justify-center py-8">
          <van-loading size="28px">加载中...</van-loading>
        </div>

        <div v-else-if="diaryStore.entries.length === 0" class="bg-white rounded-xl shadow-sm p-6 text-center text-gray-400 text-base">
          还没有手记，点击右下角按钮开始记录
        </div>

        <template v-else>
          <div v-for="(group, gDate) in diaryGroupedEntries" :key="gDate" class="mb-4">
            <div class="text-sm text-gray-400 mb-2 font-medium">{{ gDate }}</div>
            <div class="space-y-2">
              <van-swipe-cell v-for="entry in group" :key="entry.id">
                <div
                  class="bg-white rounded-xl shadow-sm p-3 cursor-pointer"
                  @click="toggleDiaryExpand(entry.id)"
                >
                  <div class="flex items-start justify-between mb-1">
                    <h4 v-if="entry.title" class="text-base font-medium text-gray-800">{{ entry.title }}</h4>
                    <span class="text-sm text-gray-400 flex-shrink-0 ml-auto">{{ formatDate(entry.created_at) }}</span>
                  </div>
                  <p
                    class="text-base text-gray-600 whitespace-pre-line leading-relaxed"
                    :class="{ 'line-clamp-3': !diaryExpandedIds.has(entry.id) }"
                  >{{ entry.content }}</p>
                  <div v-if="entry.tags && entry.tags.length" class="flex flex-wrap gap-1 mt-2">
                    <van-tag
                      v-for="tag in entry.tags"
                      :key="tag.id"
                      plain
                      size="small"
                      :color="tag.color"
                    >
                      {{ tag.name }}
                    </van-tag>
                  </div>
                  <!-- AI comment -->
                  <div
                    v-if="entry.llm_comment && diaryExpandedIds.has(entry.id)"
                    class="mt-3 bg-amber-50 border-l-2 border-amber-300 rounded-r-lg p-3"
                  >
                    <div class="flex items-center justify-between mb-1">
                      <div class="flex items-center gap-1">
                        <span class="text-sm font-medium text-amber-600">AI 评论</span>
                        <span v-if="entry.commented_at" class="text-sm text-gray-400">{{ formatDate(entry.commented_at) }}</span>
                        <van-tag v-if="entry.comment_feedback === 'disliked'" type="danger" size="small" plain>待重新生成</van-tag>
                      </div>
                      <div class="flex items-center gap-1" @click.stop>
                        <span
                          class="cursor-pointer text-lg"
                          :class="entry.comment_feedback === 'liked' ? 'opacity-100' : 'opacity-30 hover:opacity-60'"
                          @click="setDiaryCommentFeedback(entry, 'liked')"
                          title="赞 — 作为优秀范例"
                        >&#x1F44D;</span>
                        <span
                          class="cursor-pointer text-lg"
                          :class="entry.comment_feedback === 'disliked' ? 'opacity-100' : 'opacity-30 hover:opacity-60'"
                          @click="setDiaryCommentFeedback(entry, 'disliked')"
                          title="踩 — 今晚重新生成"
                        >&#x1F44E;</span>
                      </div>
                    </div>
                    <p class="text-base text-gray-700 whitespace-pre-line leading-relaxed">{{ entry.llm_comment }}</p>
                  </div>
                  <div v-if="entry.llm_comment && !diaryExpandedIds.has(entry.id)" class="mt-1">
                    <span class="text-sm text-amber-500">有 AI 评论，点击展开</span>
                  </div>
                </div>
                <template #right>
                  <van-button square text="编辑" class="h-full" @click="openEditDiary(entry)" />
                  <van-button square type="danger" text="删除" class="h-full" @click="handleDeleteDiary(entry.id)" />
                </template>
              </van-swipe-cell>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="diaryStore.totalPages > 1" class="flex justify-center pt-4 pb-2">
            <van-pagination
              v-model="diaryPage"
              :total-items="diaryStore.total"
              :items-per-page="diaryStore.pageSize"
              :show-page-size="3"
              force-ellipses
              @change="loadDiaryEntries"
            />
          </div>
        </template>

        <!-- FAB: new entry -->
        <div class="fixed bottom-20 right-4 z-10">
          <van-button round type="primary" icon="edit" size="large" @click="openNewDiary" />
        </div>
      </template>
    </div>

    <!-- New/Edit diary popup -->
    <van-popup v-model:show="showDiaryEditor" position="bottom" round :style="{ maxHeight: '85vh' }">
      <div class="p-4">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-base font-semibold text-gray-700">{{ editingDiaryId ? '编辑手记' : '新建手记' }}</h3>
          <van-button size="small" type="primary" :loading="savingDiary" @click="saveDiary">保存</van-button>
        </div>
        <van-field
          v-model="diaryForm.title"
          placeholder="标题（可选）"
          class="mb-2 rounded-lg border border-gray-200"
        />
        <van-field
          v-model="diaryForm.content"
          type="textarea"
          :autosize="{ minHeight: 120 }"
          placeholder="写下你觉得有价值、有意义或有趣的事情..."
          class="mb-2 rounded-lg border border-gray-200"
        />
        <div class="flex items-center gap-2 mb-2">
          <VoiceInputButton v-model="diaryForm.content" />
          <span class="text-xs text-gray-400">点击麦克风语音输入</span>
        </div>
        <van-field
          v-model="diaryForm.diary_date"
          placeholder="日期 YYYY-MM-DD"
          class="mb-2 rounded-lg border border-gray-200"
        />
        <div class="mb-2">
          <p class="text-xs text-gray-400 mb-1">选择标签（保存后 AI 会自动补充标签）</p>
          <div class="flex flex-wrap gap-1">
            <van-tag
              v-for="t in diaryStore.tags"
              :key="t.id"
              :type="diaryForm.tag_ids.includes(t.id) ? 'primary' : 'default'"
              :color="diaryForm.tag_ids.includes(t.id) ? t.color : undefined"
              size="medium"
              class="cursor-pointer"
              @click="toggleDiaryFormTag(t.id)"
            >
              {{ t.name }}
            </van-tag>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- Delete Tag Confirm (same pattern as TalentCardsView) -->
    <van-dialog
      v-model:show="showDeleteDiaryTagConfirm"
      title="删除标签"
      :message="`删除标签「${deletingDiaryTag?.name}」后，所有手记上的该标签也会移除，确定？`"
      show-cancel-button
      @confirm="handleDeleteDiaryTag"
    />

    <!-- Diary comment prompt editor (same pattern as TalentCardsView organize prompt) -->
    <van-popup v-model:show="showDiaryPromptEditor" position="bottom" round :style="{ height: '80vh' }">
      <div class="flex flex-col h-full">
        <div class="flex items-center justify-between px-4 py-3 border-b">
          <van-button size="small" @click="showDiaryPromptEditor = false">取消</van-button>
          <span class="font-medium text-gray-700">编辑 AI 评论提示词</span>
          <van-button size="small" type="primary" @click="saveDiaryPrompt">保存</van-button>
        </div>
        <textarea
          v-model="diaryPromptEditText"
          class="flex-1 w-full p-4 text-sm text-gray-700 leading-relaxed focus:outline-none resize-none"
        />
        <div class="flex justify-end px-4 py-2 border-t">
          <span class="text-xs text-gray-400 cursor-pointer hover:text-blue-500" @click="diaryPromptEditText = diaryPromptDefault">恢复默认</span>
        </div>
      </div>
    </van-popup>
      </van-tab>
    </van-tabs>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useIdeasStore } from '../stores/ideas'
import { useDiaryStore } from '../stores/diary'
import { showToast, showConfirmDialog } from 'vant'
import VoiceInputButton from '../components/VoiceInputButton.vue'
import TopNavBar from '../components/TopNavBar.vue'

const store = useIdeasStore()
const diaryStore = useDiaryStore()

const activeTab = ref(0)
const inputText = ref('')
const submitting = ref(false)
const loading = ref(false)
const loadingHistory = ref(false)
const generatingInsights = ref(false)
const historyPage = ref(1)

// Streaming state
const streamState = ref(null) // null | 'streaming' | 'done' | 'error'
const thinkingStream = ref('')
const outputStream = ref('')
const streamResult = ref([])
const thinkingPre = ref(null)
const outputPre = ref(null)

// Fragment expand state
const expandedIds = ref(new Set())

// Tag filter state
const selectedTags = ref(new Set())
const tagCategories = ref([]) // [{name, children: [tag_name, ...]}]

// Organize state
const organizing = ref(false)
const organizeStream = ref('')
const orgThinkingStream = ref('')
const orgThinkingPre = ref(null)
const orgOutputPre = ref(null)
const organizeStatus = ref('')
const organizeStatusText = ref('')

const fragments = computed(() => store.fragments)
const insights = computed(() => store.insights)
const history = computed(() => store.history)
const historyTotal = computed(() => store.historyTotal)

// Collect all unique tags from fragments
const allTags = computed(() => {
  const tags = new Set()
  for (const f of fragments.value) {
    for (const t of (f.tags || [])) {
      tags.add(t)
    }
  }
  return [...tags].sort()
})

const allTagsSelected = computed(() => {
  if (allTags.value.length === 0) return true
  return allTags.value.every(t => selectedTags.value.has(t))
})

// Filter fragments by selected tags
const displayedFragments = computed(() => {
  if (selectedTags.value.size === 0 || allTagsSelected.value) {
    return fragments.value
  }
  return fragments.value.filter(f =>
    (f.tags || []).some(t => selectedTags.value.has(t))
  )
})

const groupedDisplayedFragments = computed(() => {
  const groups = {}
  for (const f of displayedFragments.value) {
    const cat = f.category || '未分类'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(f)
  }
  return groups
})

const groupedInsights = computed(() => {
  const groups = {}
  for (const i of insights.value) {
    const date = i.generated_date || '未知日期'
    if (!groups[date]) groups[date] = []
    groups[date].push(i)
  }
  return groups
})

// Auto-select all tags when fragments change
watch(allTags, (tags) => {
  selectedTags.value = new Set(tags)
}, { immediate: true })

function autoScroll(el) {
  if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight })
}
watch(orgThinkingStream, () => autoScroll(orgThinkingPre.value), { flush: 'post' })
watch(organizeStream, () => autoScroll(orgOutputPre.value), { flush: 'post' })

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([store.fetchFragments(), store.fetchInsights()])
  } finally {
    loading.value = false
  }
})

function toggleExpand(id) {
  const s = new Set(expandedIds.value)
  if (s.has(id)) {
    s.delete(id)
  } else {
    s.add(id)
  }
  expandedIds.value = s
}

function toggleTag(tag) {
  const s = new Set(selectedTags.value)
  if (s.has(tag)) {
    s.delete(tag)
  } else {
    s.add(tag)
  }
  selectedTags.value = s
}

function selectAllTags() {
  if (allTagsSelected.value) {
    selectedTags.value = new Set()
  } else {
    selectedTags.value = new Set(allTags.value)
  }
}

async function submitIdea() {
  if (!inputText.value.trim() || submitting.value) return
  submitting.value = true
  const text = inputText.value.trim()

  // Reset streaming state
  streamState.value = 'streaming'
  thinkingStream.value = ''
  outputStream.value = ''
  streamResult.value = []

  try {
    const token = localStorage.getItem('teamgr_token')
    const response = await fetch('/api/ideas/input/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content: text }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    inputText.value = ''

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const dataStr = line.slice(6).trim()
        if (!dataStr) continue

        try {
          const data = JSON.parse(dataStr)

          if (data.type === 'thinking_chunk') {
            thinkingStream.value += data.content
            await nextTick()
            if (thinkingPre.value) {
              thinkingPre.value.scrollTop = thinkingPre.value.scrollHeight
            }
          } else if (data.type === 'thinking_done') {
            // thinking done, output starts
          } else if (data.type === 'thinking') {
            // heartbeat during thinking, no-op
          } else if (data.type === 'chunk') {
            outputStream.value += data.content
            await nextTick()
            if (outputPre.value) {
              outputPre.value.scrollTop = outputPre.value.scrollHeight
            }
          } else if (data.type === 'done') {
            streamState.value = 'done'
            streamResult.value = data.fragments || []
            store.fetchFragments()
          } else if (data.type === 'error') {
            streamState.value = 'error'
            showToast('处理失败: ' + (data.content || '未知错误'))
          }
        } catch (e) {
          // ignore parse errors
        }
      }
    }

    // If stream ended without explicit done/error
    if (streamState.value === 'streaming') {
      streamState.value = 'done'
      store.fetchFragments()
    }

  } catch (e) {
    streamState.value = 'error'
    showToast('提交失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

async function handleDeleteFragment(id) {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后不可恢复' })
    await store.deleteFragment(id)
    showToast('已删除')
  } catch (e) {
    // cancelled or error
  }
}

async function toggleLike(insight) {
  try {
    if (insight.liked) {
      await store.unlikeInsight(insight.id)
    } else {
      await store.likeInsight(insight.id)
    }
  } catch (e) {
    showToast('操作失败')
  }
}

async function generateInsights() {
  generatingInsights.value = true
  try {
    await store.triggerInsightGeneration()
    await store.fetchInsights()
    showToast('洞见已生成')
  } catch (e) {
    showToast('生成失败: ' + (e.response?.data?.detail || '未知错误'))
  } finally {
    generatingInsights.value = false
  }
}

function handleOrganizeSSELine(line) {
  if (!line.startsWith('data: ')) return
  try {
    const data = JSON.parse(line.slice(6))
    if (data.type === 'thinking') {
      organizeStatusText.value = `模型正在思考中... (${data.elapsed}s)`
    } else if (data.type === 'thinking_chunk') {
      organizeStatusText.value = '模型正在思考中...'
      orgThinkingStream.value += data.content
    } else if (data.type === 'thinking_done') {
      organizeStatusText.value = `思考完成 (${data.elapsed}s)，正在生成整理结果...`
    } else if (data.type === 'chunk') {
      organizeStream.value += data.content
    } else if (data.type === 'merge') {
      const count = data.merges.length
      organizeStream.value += `\n--- 合并了 ${count} 组相似标签 ---\n` + data.merges.map(m => `  ${m}`).join('\n') + '\n'
    } else if (data.type === 'done') {
      tagCategories.value = data.categories || []
      store.fetchFragments()
      selectedTags.value = new Set(data.all_tags || [])
      organizeStatus.value = 'done'
      organizeStatusText.value = `整理完成：${(data.categories || []).length} 个分类，${(data.all_tags || []).length} 个标签`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 3000)
    } else if (data.type === 'error') {
      organizeStatus.value = 'error'
      organizeStatusText.value = `整理失败：${data.content}`
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 5000)
    }
  } catch (e) {
    console.error('SSE parse error:', e)
  }
}

async function organizeTags() {
  organizing.value = true
  organizeStream.value = ''
  orgThinkingStream.value = ''
  organizeStatus.value = 'running'
  organizeStatusText.value = `正在分析 ${allTags.value.length} 个标签...`

  try {
    const token = localStorage.getItem('teamgr_token')
    const res = await fetch('/api/ideas/tags/organize', {
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
      buffer = lines.pop() || ''
      for (const line of lines) {
        handleOrganizeSSELine(line)
      }
    }
    if (buffer.trim()) handleOrganizeSSELine(buffer)

    if (organizeStatus.value === 'running') {
      await store.fetchFragments()
      selectedTags.value = new Set(allTags.value)
      organizeStatus.value = 'done'
      organizeStatusText.value = '整理完成'
      setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 3000)
    }
  } catch (e) {
    organizeStatus.value = 'error'
    organizeStatusText.value = `整理失败：${e.message}`
    setTimeout(() => { organizeStatus.value = ''; organizeStream.value = ''; orgThinkingStream.value = '' }, 5000)
  } finally {
    organizing.value = false
  }
}

function onTabChange(index) {
  if (index === 1) {
    historyPage.value = 1
    loadHistory()
  }
  if (index === 2 && diaryStore.verified) {
    loadDiaryData()
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    await store.fetchHistory(historyPage.value)
  } finally {
    loadingHistory.value = false
  }
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatDateTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ========== 流光剪影 (Diary) ==========

const diaryPwd = ref('')
const diaryVerifying = ref(false)
const diaryPwdError = ref('')
const diaryExpandedIds = ref(new Set())
const diaryPage = ref(1)

// Editor state
const showDiaryEditor = ref(false)
const editingDiaryId = ref(null)
const savingDiary = ref(false)
const diaryForm = ref({ title: '', content: '', diary_date: '', tag_ids: [] })

// Tag inline-edit state (aligned with TalentCardsView pattern)
const diarySelectedTagIds = ref(new Set())
const diaryEditingTagId = ref(null)
const diaryEditingTagName = ref('')
const diaryTagEditInput = ref(null)
const showDeleteDiaryTagConfirm = ref(false)
const deletingDiaryTag = ref(null)

// Prompt editor state
const showDiaryPromptPreview = ref(false)
const showDiaryPromptEditor = ref(false)
const diaryPromptText = ref('')
const diaryPromptEditText = ref('')
const diaryPromptDefault = ref('')
const diaryLikedExamples = ref([])
const diaryDislikedCount = ref(0)

const diaryGroupedEntries = computed(() => {
  const groups = {}
  for (const e of diaryStore.entries) {
    const d = e.diary_date || '未知日期'
    if (!groups[d]) groups[d] = []
    groups[d].push(e)
  }
  return groups
})

async function verifyDiaryPwd() {
  if (!diaryPwd.value.trim()) return
  diaryVerifying.value = true
  diaryPwdError.value = ''
  try {
    const ok = await diaryStore.verifyPassword(diaryPwd.value)
    if (ok) {
      diaryPwd.value = ''
      await loadDiaryData()
    } else {
      diaryPwdError.value = '密码错误'
    }
  } catch {
    diaryPwdError.value = '验证失败'
  } finally {
    diaryVerifying.value = false
  }
}

async function loadDiaryData() {
  try {
    await Promise.all([
      diaryStore.fetchEntries(1, null),
      diaryStore.fetchTags(),
    ])
  } catch (e) {
    console.error('loadDiaryData error:', e)
  }
}

async function loadDiaryEntries() {
  await diaryStore.fetchEntries(diaryPage.value, diaryStore.selectedTagId)
}

// Tag multi-select filtering (aligned with TalentCardsView)
const diaryAllTagsSelected = computed(() => {
  if (diaryStore.tags.length === 0) return true
  return diaryStore.tags.every(t => diarySelectedTagIds.value.has(t.id))
})

function selectAllDiaryTags() {
  if (diaryAllTagsSelected.value) {
    diarySelectedTagIds.value = new Set()
  } else {
    diarySelectedTagIds.value = new Set(diaryStore.tags.map(t => t.id))
  }
  diaryStore.selectedTagId = null
  diaryPage.value = 1
  diaryStore.fetchEntries(1, null)
}

function toggleDiaryTagFilter(tagId) {
  const s = new Set(diarySelectedTagIds.value)
  if (s.has(tagId)) s.delete(tagId)
  else s.add(tagId)
  diarySelectedTagIds.value = s
  // If only one tag selected, use it as filter; otherwise clear filter
  if (s.size === 1) {
    const [id] = s
    diaryStore.selectedTagId = id
    diaryStore.fetchEntries(1, id)
  } else {
    diaryStore.selectedTagId = null
    diaryStore.fetchEntries(1, null)
  }
  diaryPage.value = 1
}

// Initialize selected tags when tags load
watch(() => diaryStore.tags, (tags) => {
  if (tags.length > 0 && diarySelectedTagIds.value.size === 0) {
    diarySelectedTagIds.value = new Set(tags.map(t => t.id))
  }
})

// Inline tag editing (same as TalentCardsView)
async function startEditDiaryTag(tag) {
  diaryEditingTagId.value = tag.id
  diaryEditingTagName.value = tag.name
  await nextTick()
  const inputs = diaryTagEditInput.value
  if (inputs) {
    const el = Array.isArray(inputs) ? inputs[0] : inputs
    el?.focus()
    el?.select()
  }
}

function cancelEditDiaryTag() {
  diaryEditingTagId.value = null
  diaryEditingTagName.value = ''
}

async function finishEditDiaryTag(tag) {
  const newName = diaryEditingTagName.value.trim()
  diaryEditingTagId.value = null
  if (!newName || newName === tag.name) return
  try {
    await diaryStore.updateTag(tag.id, { name: newName, color: tag.color })
    showToast('标签已更新')
  } catch (e) {
    showToast(e.response?.data?.detail || '更新失败')
  }
}

function confirmDeleteDiaryTag(tag) {
  deletingDiaryTag.value = tag
  showDeleteDiaryTagConfirm.value = true
}

async function handleDeleteDiaryTag() {
  try {
    await diaryStore.deleteTag(deletingDiaryTag.value.id)
    showToast('标签已删除')
    const s = new Set(diarySelectedTagIds.value)
    s.delete(deletingDiaryTag.value.id)
    diarySelectedTagIds.value = s
  } catch (e) {
    showToast('删除失败')
  }
}

// Prompt editor functions
const diaryPromptLoaded = ref(false)

const DIARY_PROMPT_FALLBACK = `你是一位阅历丰富、思维敏锐的朋友。请阅读以下手记，给出你的真实想法。

要求：
- 说人话，不要鸡汤、不要空洞的鼓励，不要"加油"之类的废话
- 如果手记提到了具体问题或困惑，直接给出你的分析和可操作的建议
- 如果手记记录了一个想法，指出你觉得有意思的点，也可以指出潜在的盲区
- 如果手记是情绪表达，简短回应即可，不要过度共情或说教
- 有自己的观点，可以提出不同看法，但要言之有理
- 控制在100-200字以内，言简意赅`

async function loadDiaryPrompt() {
  if (diaryPromptLoaded.value) return
  try {
    const res = await api.get('/api/diary/comment-prompt', { headers: { 'X-Diary-Password': diaryStore.password } })
    diaryPromptText.value = res.data.instructions
    diaryPromptDefault.value = res.data.default
    diaryLikedExamples.value = res.data.liked_examples || []
    diaryDislikedCount.value = res.data.disliked_count || 0
    diaryPromptLoaded.value = true
  } catch {
    // Fallback to hardcoded default if API unavailable
    diaryPromptText.value = DIARY_PROMPT_FALLBACK
    diaryPromptDefault.value = DIARY_PROMPT_FALLBACK
  }
}

async function toggleDiaryPromptPreview() {
  showDiaryPromptPreview.value = !showDiaryPromptPreview.value
  if (showDiaryPromptPreview.value && !diaryPromptLoaded.value) {
    await loadDiaryPrompt()
  }
}

async function openDiaryPromptEditor() {
  if (!diaryPromptLoaded.value) await loadDiaryPrompt()
  diaryPromptEditText.value = diaryPromptText.value
  showDiaryPromptEditor.value = true
}

async function saveDiaryPrompt() {
  try {
    await api.put('/api/diary/comment-prompt', { instructions: diaryPromptEditText.value }, { headers: { 'X-Diary-Password': diaryStore.password } })
    diaryPromptText.value = diaryPromptEditText.value
    showDiaryPromptEditor.value = false
    showToast('已保存')
  } catch {
    showToast('保存失败')
  }
}

function toggleDiaryExpand(id) {
  const s = new Set(diaryExpandedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  diaryExpandedIds.value = s
}

function openNewDiary() {
  editingDiaryId.value = null
  const today = new Date()
  diaryForm.value = {
    title: '',
    content: '',
    diary_date: `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
    tag_ids: [],
  }
  showDiaryEditor.value = true
}

function openEditDiary(entry) {
  editingDiaryId.value = entry.id
  diaryForm.value = {
    title: entry.title || '',
    content: entry.content,
    diary_date: entry.diary_date,
    tag_ids: (entry.tags || []).map(t => t.id),
  }
  showDiaryEditor.value = true
}

function toggleDiaryFormTag(tagId) {
  const idx = diaryForm.value.tag_ids.indexOf(tagId)
  if (idx >= 0) diaryForm.value.tag_ids.splice(idx, 1)
  else diaryForm.value.tag_ids.push(tagId)
}

async function saveDiary() {
  if (!diaryForm.value.content.trim()) {
    showToast('请填写内容')
    return
  }
  savingDiary.value = true
  try {
    if (editingDiaryId.value) {
      await diaryStore.updateEntry(editingDiaryId.value, diaryForm.value)
    } else {
      await diaryStore.createEntry(diaryForm.value)
    }
    showDiaryEditor.value = false
    showToast(editingDiaryId.value ? '已更新' : '已保存')
    // Refresh after auto-tag completes
    diaryStore.refreshAfterAutoTag()
  } catch (e) {
    showToast('保存失败')
  } finally {
    savingDiary.value = false
  }
}

async function handleDeleteDiary(id) {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后不可恢复' })
    await diaryStore.deleteEntry(id)
    showToast('已删除')
  } catch { /* cancelled */ }
}

async function setDiaryCommentFeedback(entry, feedback) {
  // Toggle: clicking the same feedback again clears it
  const newFeedback = entry.comment_feedback === feedback ? null : feedback
  try {
    await diaryStore.setCommentFeedback(entry.id, newFeedback)
    if (newFeedback === 'liked') showToast('已标记为优秀范例')
    else if (newFeedback === 'disliked') showToast('今晚会重新生成')
    else showToast('已取消')
  } catch {
    showToast('操作失败')
  }
}

</script>

<style scoped>
.idea-input {
  border: 1px solid #d1d5db !important;
  border-radius: 12px !important;
  padding: 12px !important;
  overflow: hidden;
}
.idea-input::after {
  display: none !important;
}
.idea-input:focus-within {
  border-color: #3b82f6 !important;
}
.idea-input :deep(.van-field__control) {
  font-size: 15px !important;
  line-height: 1.7 !important;
}
.ideas-tabs :deep(.van-tabs__nav) {
  background: #fff;
}
.diary-pwd-input {
  border: 1px solid #d1d5db !important;
  border-radius: 12px !important;
  overflow: hidden;
}
.diary-pwd-input::after {
  display: none !important;
}
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.diary-tag-closeable :deep(.van-tag__close) {
  opacity: 0;
  width: 0;
  margin-left: 0;
  transition: all 0.2s;
}
.diary-tag-closeable:hover :deep(.van-tag__close) {
  opacity: 1;
  width: 12px;
  margin-left: 2px;
}
.diary-edit-tag-input {
  border: 1.5px solid #3b82f6;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 13px;
  width: 80px;
  outline: none;
  background: #fff;
}
</style>

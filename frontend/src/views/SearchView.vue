<template>
  <div class="min-h-screen bg-gray-100">
    <!-- Header -->
    <div class="bg-white shadow-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
        <van-icon name="arrow-left" size="20" class="cursor-pointer" @click="$router.back()" />
        <van-search
          v-model="searchQuery"
          placeholder="搜索人才..."
          shape="round"
          class="flex-1"
          show-action
          @search="handleSearch"
        >
          <template #action>
            <div class="flex items-center gap-2">
              <VoiceInputButton v-model="searchQuery" mode="replace" />
              <div @click="handleSearch" class="text-blue-500">搜索</div>
            </div>
          </template>
        </van-search>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 py-4">
      <!-- Search Mode Toggle -->
      <div class="flex gap-2 mb-4">
        <van-tag
          :type="searchMode === 'pinyin' ? 'primary' : 'default'"
          size="medium"
          class="cursor-pointer"
          @click="searchMode = 'pinyin'"
        >
          拼音搜索
        </van-tag>
        <van-tag
          :type="searchMode === 'semantic' ? 'primary' : 'default'"
          size="medium"
          class="cursor-pointer"
          @click="searchMode = 'semantic'"
        >
          智能搜索 (AI)
        </van-tag>
      </div>

      <p v-if="searchMode === 'semantic'" class="text-xs text-gray-400 mb-4">
        智能搜索支持自然语言描述，如："有前端经验的管理型人才"、"沟通能力强的技术骨干"
      </p>

      <!-- Loading -->
      <div v-if="searching" class="flex justify-center py-12">
        <van-loading size="36px">搜索中...</van-loading>
      </div>

      <!-- Results -->
      <div v-else-if="results.length > 0" class="space-y-3">
        <p class="text-sm text-gray-500">找到 {{ results.length }} 个结果</p>
        <div
          v-for="talent in results"
          :key="talent.id"
          class="bg-white rounded-xl shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow active:bg-gray-50"
          @click="$router.push(`/talent/${talent.id}`)"
        >
          <div class="flex items-start justify-between mb-1">
            <h3 class="text-base font-semibold text-gray-800">{{ talent.name }}</h3>
            <div class="flex gap-1">
              <van-tag
                v-for="tag in (talent.tags || []).slice(0, 2)"
                :key="tag.id || tag"
                :color="tag.color"
                size="small"
                plain
              >
                {{ tag.name || tag }}
              </van-tag>
            </div>
          </div>
          <p class="text-xs text-gray-500">{{ talent.current_role || '' }} {{ talent.department || '' }}</p>
          <p class="text-sm text-gray-600 mt-1 line-clamp-2">{{ talent.summary || '' }}</p>
        </div>
      </div>

      <!-- No Results -->
      <div v-else-if="searched" class="text-center py-16 text-gray-400">
        <div class="text-4xl mb-3">🔍</div>
        <p>未找到匹配的人才</p>
      </div>

      <!-- Default State -->
      <div v-else class="text-center py-16 text-gray-400">
        <div class="text-4xl mb-3">🔍</div>
        <p>输入关键词开始搜索</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useTalentStore } from '../stores/talent'
import { showToast } from 'vant'
import VoiceInputButton from '../components/VoiceInputButton.vue'

const store = useTalentStore()

const searchQuery = ref('')
const searchMode = ref('pinyin')
const results = ref([])
const searching = ref(false)
const searched = ref(false)

async function handleSearch() {
  const q = searchQuery.value.trim()
  if (!q) return

  searching.value = true
  searched.value = false

  try {
    if (searchMode.value === 'pinyin') {
      results.value = await store.searchTalents(q)
    } else {
      results.value = await store.semanticSearch(q)
    }
    searched.value = true
  } catch (e) {
    showToast('搜索失败')
  } finally {
    searching.value = false
  }
}
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>

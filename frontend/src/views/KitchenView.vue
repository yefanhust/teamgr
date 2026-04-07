<template>
  <div class="min-h-screen bg-gray-100">
    <TopNavBar />
    <van-tabs v-model:active="activeTab" sticky offset-top="52" class="kitchen-tabs">
      <van-tab title="每日食谱" name="menu">
        <DailyMenuTab />
      </van-tab>
    </van-tabs>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopNavBar from '../components/TopNavBar.vue'
import DailyMenuTab from '../components/DailyMenuTab.vue'

const route = useRoute()
const router = useRouter()

const validTabs = ['menu']
const initial = validTabs.includes(route.query.tab) ? route.query.tab : 'menu'
const activeTab = ref(initial)

watch(activeTab, (tab) => {
  const q = tab === 'menu' ? undefined : tab
  router.replace({ query: { ...route.query, tab: q } })
})
</script>

<style scoped>
.kitchen-tabs :deep(.van-tabs__nav) {
  background: #fff;
}
</style>

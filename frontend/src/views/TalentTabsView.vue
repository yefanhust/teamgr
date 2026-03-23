<template>
  <div class="min-h-screen bg-gray-100">
    <TopNavBar />
    <van-tabs v-model:active="activeTab" sticky offset-top="52" class="todo-tabs">
      <van-tab title="人才卡" name="cards">
        <TalentCardsView />
      </van-tab>
      <van-tab title="组织" name="org">
        <OrganizationView />
      </van-tab>
      <van-tab title="项目" name="projects">
        <ProjectTeamView />
      </van-tab>
    </van-tabs>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopNavBar from '../components/TopNavBar.vue'
import TalentCardsView from './TalentCardsView.vue'
import OrganizationView from './OrganizationView.vue'
import ProjectTeamView from './ProjectTeamView.vue'

const route = useRoute()
const router = useRouter()

const validTabs = ['cards', 'org', 'projects']
const initial = validTabs.includes(route.query.tab) ? route.query.tab : 'cards'
const activeTab = ref(initial)

watch(activeTab, (tab) => {
  const q = tab === 'cards' ? undefined : tab
  router.replace({ query: { ...route.query, tab: q } })
})
</script>

<style scoped>
.todo-tabs :deep(.van-tabs__nav) {
  background: #fff;
}
</style>

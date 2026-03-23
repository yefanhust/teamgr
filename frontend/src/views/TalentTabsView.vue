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
import { ref } from 'vue'
import TopNavBar from '../components/TopNavBar.vue'
import TalentCardsView from './TalentCardsView.vue'
import OrganizationView from './OrganizationView.vue'
import ProjectTeamView from './ProjectTeamView.vue'

const activeTab = ref('cards')
</script>

<style scoped>
.todo-tabs :deep(.van-tabs__nav) {
  background: #fff;
}
</style>

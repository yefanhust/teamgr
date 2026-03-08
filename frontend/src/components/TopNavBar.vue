<template>
  <div class="top-nav bg-white shadow-sm sticky top-0 z-10">
    <div class="max-w-3xl mx-auto px-4 py-2">
      <div class="flex gap-2">
        <div
          v-for="item in navItems"
          :key="item.route"
          class="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg cursor-pointer transition-all"
          :class="isActive(item.route) ? item.activeClass : item.inactiveClass"
          @click="navigateTo(item.route)"
        >
          <van-icon :name="item.icon" :size="isActive(item.route) ? '20' : '16'" :color="isActive(item.route) ? 'white' : item.color" />
          <span class="text-sm font-medium" :class="{ 'font-bold': isActive(item.route) }">{{ item.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const navItems = [
  {
    label: 'Studio',
    route: '/',
    icon: 'apps-o',
    color: '#8B5CF6',
    activeClass: 'bg-violet-500 text-white shadow-md scale-105',
    inactiveClass: 'bg-violet-50 text-violet-700',
  },
  {
    label: '灵感',
    route: '/ideas',
    icon: 'fire-o',
    color: '#F97316',
    activeClass: 'bg-orange-500 text-white shadow-md scale-105',
    inactiveClass: 'bg-orange-50 text-orange-700',
  },
  {
    label: '人才卡',
    route: '/talent-cards',
    icon: 'friends-o',
    color: '#3B82F6',
    activeClass: 'bg-blue-500 text-white shadow-md scale-105',
    inactiveClass: 'bg-blue-50 text-blue-700',
  },
  {
    label: '统计',
    route: '/stats',
    icon: 'chart-trending-o',
    color: '#10B981',
    activeClass: 'bg-emerald-500 text-white shadow-md scale-105',
    inactiveClass: 'bg-emerald-50 text-emerald-700',
  },
]

function isActive(itemRoute) {
  return route.path === itemRoute
}

function navigateTo(target) {
  if (route.path !== target) {
    router.push(target)
  }
}
</script>

<style scoped>
.top-nav .scale-105 {
  transform: scale(1.05);
}
</style>

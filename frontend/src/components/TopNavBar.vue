<template>
  <div class="top-nav bg-white shadow-sm sticky top-0 z-10">
    <div class="max-w-3xl mx-auto px-4 py-2">
      <div class="flex gap-2 items-center">
        <div
          v-for="item in navItems"
          :key="item.route"
          class="flex-1 flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 rounded-lg cursor-pointer transition-all"
          :class="isActive(item.route) ? item.activeClass : item.inactiveClass"
          @click="navigateTo(item.route)"
        >
          <van-icon :name="item.icon" size="18" :color="isActive(item.route) ? 'white' : item.color" />
          <span class="text-xs font-medium whitespace-nowrap" :class="{ 'font-bold': isActive(item.route) }">{{ item.label }}</span>
        </div>
        <van-icon name="chart-trending-o" size="20" class="text-gray-400 cursor-pointer flex-shrink-0 ml-1" @click="router.push('/stats')" />
        <van-icon name="setting-o" size="20" class="text-gray-400 cursor-pointer flex-shrink-0 ml-1" @click="router.push('/settings')" />
        <div class="relative flex-shrink-0 cursor-pointer ml-0.5" @click="router.push('/backup-logs')">
          <van-icon name="shield-o" size="20" :class="backupHealthy ? 'text-gray-400' : 'text-red-500'" />
          <span v-if="!backupHealthy" class="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full border border-white"></span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'

const router = useRouter()
const route = useRoute()

const backupHealthy = ref(true)

const navItems = [
  {
    label: 'Studio',
    route: '/',
    icon: 'apps-o',
    color: '#8B5CF6',
    activeClass: 'bg-violet-500 text-white shadow-md',
    inactiveClass: 'bg-violet-50 text-violet-700',
  },
  {
    label: '灵感',
    route: '/ideas',
    icon: 'fire-o',
    color: '#F97316',
    activeClass: 'bg-orange-500 text-white shadow-md',
    inactiveClass: 'bg-orange-50 text-orange-700',
  },
  {
    label: '人才',
    route: '/talent-cards',
    icon: 'friends-o',
    color: '#3B82F6',
    activeClass: 'bg-blue-500 text-white shadow-md',
    inactiveClass: 'bg-blue-50 text-blue-700',
  },
  {
    label: '龙图阁',
    route: '/scholar',
    icon: 'records-o',
    color: '#8B5CF6',
    activeClass: 'bg-purple-500 text-white shadow-md',
    inactiveClass: 'bg-purple-50 text-purple-700',
  },
  {
    label: '御膳房',
    route: '/kitchen',
    icon: 'shop-o',
    color: '#EF4444',
    activeClass: 'bg-red-500 text-white shadow-md',
    inactiveClass: 'bg-red-50 text-red-700',
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

async function checkBackupStatus() {
  try {
    const { data } = await api.get('/api/backup/status')
    backupHealthy.value = data.healthy
  } catch {
    // Silently ignore - don't block UI
  }
}

onMounted(() => {
  checkBackupStatus()
})
</script>

<style scoped>
</style>

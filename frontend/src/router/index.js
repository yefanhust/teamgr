import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/setup',
    name: 'Setup',
    component: () => import('../views/SetupView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Studio',
    component: () => import('../views/TodoView.vue'),
  },
  {
    path: '/talent-cards',
    name: 'TalentCards',
    component: () => import('../views/TalentCardsView.vue'),
  },
  {
    path: '/talent/:id',
    name: 'TalentDetail',
    component: () => import('../views/TalentDetailView.vue'),
  },
  {
    path: '/entry',
    name: 'InfoEntry',
    component: () => import('../views/InfoEntryView.vue'),
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import('../views/SearchView.vue'),
  },
  {
    path: '/ideas',
    name: 'Ideas',
    component: () => import('../views/IdeasView.vue'),
  },
  {
    path: '/scholar',
    name: 'Scholar',
    component: () => import('../views/ScholarView.vue'),
  },
  {
    path: '/todos',
    redirect: '/',
  },
  {
    path: '/stats',
    name: 'Stats',
    component: () => import('../views/StatsView.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
  },
  {
    path: '/backup-logs',
    name: 'BackupLogs',
    component: () => import('../views/BackupLogsView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()

  // Check auth status on first load
  if (!auth.statusChecked) {
    await auth.checkStatus()
  }

  // If no password configured, block all access — must configure password first
  if (!auth.passwordConfigured && to.name !== 'Setup') {
    return next({ name: 'Setup' })
  }

  // If password is configured but not authenticated, redirect to login
  if (auth.passwordConfigured && !auth.authenticated && !to.meta.guest) {
    return next({ name: 'Login' })
  }

  next()
})

export default router

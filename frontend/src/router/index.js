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

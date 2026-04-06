<template>
  <div class="min-h-screen bg-gray-100">
    <TopNavBar />
    <div class="max-w-3xl mx-auto px-4 py-1">
      <h1 class="text-sm font-bold text-gray-500">御膳房</h1>
    </div>

    <div class="max-w-3xl mx-auto px-4 py-4">
      <van-empty description="御膳房正在筹备中..." />
    </div>
  </div>
</template>

<script setup>
import TopNavBar from '../components/TopNavBar.vue'
</script>

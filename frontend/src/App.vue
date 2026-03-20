<template>
  <router-view v-slot="{ Component }">
    <keep-alive include="ScholarView">
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>

<script setup>
</script>

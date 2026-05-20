<template>
  <div id="app-container">
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <h2 @click="$router.push('/')" class="logo">VideoSplitter</h2>
        </div>
        <div class="header-right">
          <el-button :icon="isDark ? Sunny : Moon" circle @click="toggleDark" />
          <el-button type="primary" @click="$router.push('/add')">添加视频</el-button>
          <el-button @click="$router.push('/settings')">设置</el-button>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ref, provide, onMounted } from 'vue'
import { Sunny, Moon } from '@element-plus/icons-vue'

const selectedCategoryId = ref(null)
provide('selectedCategoryId', selectedCategoryId)

const isDark = ref(false)

function toggleDark() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    isDark.value = true
    document.documentElement.classList.add('dark')
  }
})
</script>

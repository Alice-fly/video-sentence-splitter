<template>
  <div class="page-container">
    <div class="dashboard-layout">
      <aside class="sidebar">
        <CategoryTree />
      </aside>
      <main class="content">
        <div class="content-header">
          <el-input
            v-model="search"
            placeholder="搜索视频..."
            clearable
            style="width: 300px"
          />
          <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 160px; margin-left: 12px">
            <el-option label="处理中" value="processing" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
        </div>
        <div v-if="filteredVideos.length === 0" class="empty-state">
          <el-empty description="暂无视频，点击右上角添加" />
        </div>
        <div v-else class="video-grid">
          <VideoCard
            v-for="video in filteredVideos"
            :key="video.id"
            :video="video"
            @click="$router.push(`/video/${video.id}`)"
            @delete="handleDelete(video.id)"
          />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { getVideos, deleteVideo } from '../api/videos'
import CategoryTree from '../components/CategoryTree.vue'
import VideoCard from '../components/VideoCard.vue'

const search = ref('')
const statusFilter = ref('')
const videos = ref([])
const selectedCategoryId = inject('selectedCategoryId', ref(null))

onMounted(() => {
  loadVideos()
})

async function loadVideos() {
  try {
    const { data } = await getVideos()
    videos.value = data
  } catch (e) {
    console.error('Failed to load videos', e)
  }
}

const filteredVideos = computed(() => {
  let list = videos.value
  if (selectedCategoryId.value) {
    list = list.filter(v => v.category_id === selectedCategoryId.value)
  }
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(v => v.title.toLowerCase().includes(q))
  }
  if (statusFilter.value) {
    if (statusFilter.value === 'processing') {
      list = list.filter(v => !['completed', 'failed'].includes(v.status))
    } else {
      list = list.filter(v => v.status === statusFilter.value)
    }
  }
  return list
})

async function handleDelete(id) {
  try {
    await deleteVideo(id)
    videos.value = videos.value.filter(v => v.id !== id)
  } catch (e) {
    console.error('Failed to delete video', e)
  }
}
</script>

<style scoped>
.dashboard-layout {
  display: flex;
  gap: 24px;
}
.sidebar {
  width: 220px;
  flex-shrink: 0;
}
.content {
  flex: 1;
  min-width: 0;
}
.content-header {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}
.empty-state {
  padding: 60px 0;
}
</style>

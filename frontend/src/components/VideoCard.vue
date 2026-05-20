<template>
  <el-card class="video-card" shadow="hover" @click="$emit('click')">
    <div class="card-thumb">
      <img v-if="video.thumbnail" :src="`/api/videos/${video.id}/thumbnail`" alt="" />
      <div v-else class="no-thumb">暂无封面</div>
      <div class="card-status-tag">
        <el-tag v-if="isDone" type="success" size="small">完成</el-tag>
        <el-tag v-else-if="isFailed" type="danger" size="small">失败</el-tag>
        <el-tag v-else type="warning" size="small">处理中</el-tag>
      </div>
    </div>
    <div class="card-body">
      <div class="card-title">{{ video.title || '未命名视频' }}</div>
      <ProgressBar
        v-if="!isDone && !isFailed"
        :progress="video.progress"
        :message="video.progress_message"
        compact
      />
      <div v-if="isFailed" class="error-msg">{{ video.error_message }}</div>
      <div class="step-dots">
        <span class="dot" :class="dotClass(video.import_status)" title="导入">导</span>
        <span class="dot-arrow">→</span>
        <span class="dot" :class="dotClass(video.subtitle_status)" title="字幕">字</span>
        <span class="dot-arrow">→</span>
        <span class="dot" :class="dotClass(video.segment_status)" title="断句">断</span>
        <span class="dot-arrow">→</span>
        <span class="dot" :class="dotClass(video.translate_status)" title="翻译">译</span>
      </div>
      <div class="card-meta">
        <span>{{ video.sentence_count }} 个句子</span>
        <span>{{ formatDate(video.created_at) }}</span>
      </div>
    </div>
    <div class="card-actions" @click.stop>
      <el-button size="small" text type="danger" @click="$emit('delete')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import ProgressBar from './ProgressBar.vue'

const props = defineProps({
  video: { type: Object, required: true },
})
defineEmits(['click', 'delete'])

const isDone = computed(() => props.video?.translate_status === 'completed')
const isFailed = computed(() => {
  const v = props.video
  return v && (
    v.import_status === 'failed' || v.subtitle_status === 'failed' ||
    v.segment_status === 'failed' || v.translate_status === 'failed'
  )
})

function dotClass(status) {
  if (!status) return 'dot--pending'
  if (status === 'completed') return 'dot--done'
  if (status === 'processing') return 'dot--active'
  if (status === 'failed') return 'dot--fail'
  return 'dot--pending'
}

function formatDate(d) {
  if (!d) return ''
  const date = new Date(d)
  const now = new Date()
  const diff = now - date
  if (diff < 3600000) return '刚刚'
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`
  return date.toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.video-card {
  cursor: pointer;
  transition: transform 0.2s;
}
.video-card:hover {
  transform: translateY(-2px);
}
.card-thumb {
  position: relative;
  height: 160px;
  background: var(--border-color);
  overflow: hidden;
}
.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.no-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
}
.card-status-tag {
  position: absolute;
  top: 8px;
  right: 8px;
}
.card-body {
  padding: 12px 0;
}
.card-title {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 8px;
}
.error-msg {
  color: #f56c6c;
  font-size: 12px;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 8px;
}
.card-actions {
  text-align: right;
  padding-top: 4px;
  border-top: 1px solid var(--border-light);
}
.step-dots {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-bottom: 8px;
}
.dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 500;
  background: var(--dot-bg);
  color: var(--dot-text);
}
.dot--done { background: #e1f3d8; color: #67c23a; }
.dot--active { background: #d9ecff; color: #409eff; }
.dot--fail { background: #fde2e2; color: #f56c6c; }
.dot-arrow { font-size: 10px; color: var(--text-muted); }
</style>

<template>
  <div class="raw-timeline">
    <div class="timeline-header">
      <span>原始字幕（共 {{ entries.length }} 条，AI 断句前）</span>
      <el-button size="small" type="primary" @click="$emit('trigger-segment')">执行 AI 断句</el-button>
    </div>
    <div class="timeline-list">
      <div
        v-for="e in entries"
        :key="e.id"
        class="timeline-row"
        @click="$emit('seek', null, e.start_time)"
      >
        <span class="timeline-time">{{ formatTime(e.start_time) }}</span>
        <span class="timeline-arrow">→</span>
        <span class="timeline-time">{{ formatTime(e.end_time) }}</span>
        <span class="timeline-text">{{ e.text }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  entries: { type: Array, required: true },
})
defineEmits(['seek', 'trigger-segment'])

function formatTime(s) {
  if (s == null) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.raw-timeline {
  margin-top: 8px;
}
.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: #909399;
  font-size: 14px;
}
.timeline-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.timeline-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
}
.timeline-row:hover { background: #f0f5ff; }
.timeline-row:last-child { border-bottom: none; }
.timeline-time {
  color: #409eff;
  font-family: monospace;
  font-size: 12px;
  white-space: nowrap;
  min-width: 42px;
}
.timeline-arrow { color: #c0c4cc; font-size: 11px; }
.timeline-text {
  flex: 1;
  color: #303133;
  line-height: 1.4;
}
</style>

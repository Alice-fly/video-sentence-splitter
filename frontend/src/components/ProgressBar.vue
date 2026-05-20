<template>
  <div class="progress-bar" :class="{ compact }">
    <div class="progress-track">
      <div class="progress-fill" :style="{ width: progress + '%' }"></div>
    </div>
    <span v-if="!compact" class="progress-text">{{ progress }}%</span>
    <span v-if="message && !compact" class="progress-message">{{ message }}</span>
  </div>
</template>

<script setup>
defineProps({
  progress: { type: Number, default: 0 },
  message: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.progress-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-bar.compact {
  gap: 4px;
}
.progress-track {
  flex: 1;
  height: 6px;
  background: var(--progress-track);
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: #409eff;
  border-radius: 3px;
  transition: width 0.3s;
}
.progress-text {
  font-size: 13px;
  color: var(--text-secondary);
  min-width: 36px;
}
.progress-message {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

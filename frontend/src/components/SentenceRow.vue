<template>
  <div
    class="sentence-row"
    :class="{ active, editing }"
    @click="$emit('seek', sentence.id, sentence.start_time)"
  >
    <div class="sentence-index">
      {{ sentence.index }}
    </div>

    <div class="sentence-content">
      <!-- Original text: double-click to edit -->
      <div v-if="!editingOriginal" class="original" @dblclick="startEdit('original')">
        {{ sentence.original_text }}
        <span v-if="sentence.edited_at" class="edited-dot" title="已编辑">*</span>
      </div>
      <el-input
        v-else
        ref="origInputRef"
        v-model="editOriginal"
        class="inline-input"
        @blur="saveEdit"
        @keydown.enter="saveEdit"
        @keydown.escape="cancelEdit"
      />

      <!-- Translation: double-click to edit -->
      <div v-if="!editingTranslated" class="translated" @dblclick="startEdit('translated')">
        {{ sentence.translated_text }}
      </div>
      <el-input
        v-else
        v-model="editTranslated"
        class="inline-input inline-input--translated"
        @blur="saveEdit"
        @keydown.enter="saveEdit"
        @keydown.escape="cancelEdit"
      />
    </div>

    <!-- Action buttons (edit mode only) -->
    <div v-if="editable" class="sentence-actions">
      <el-tooltip content="前插" placement="top"><el-icon class="action-icon" @click.stop="$emit('insertBefore', sentence.id, sentence.index)"><Plus /></el-icon></el-tooltip>
      <el-tooltip content="后插" placement="top"><el-icon class="action-icon" @click.stop="$emit('insertAfter', sentence.id, sentence.index)"><Plus /></el-icon></el-tooltip>
      <el-tooltip content="拆分" placement="top"><span class="action-icon action-split" @click.stop="$emit('split', sentence.id)">✂</span></el-tooltip>
      <el-tooltip content="合并到下一句" placement="top"><span class="action-icon" @click.stop="$emit('mergeDown', sentence.id)">⤓</span></el-tooltip>
      <el-tooltip content="删除" placement="top"><el-icon class="action-icon action-delete" @click.stop="$emit('delete', sentence.id)"><Delete /></el-icon></el-tooltip>
    </div>

    <div class="sentence-meta">
      <!-- Timestamps: editable when in edit mode -->
      <template v-if="editable && editingTimestamps">
        <el-input-number
          v-model="editStart"
          :precision="3"
          :step="0.1"
          :min="0"
          size="small"
          controls-position="right"
          style="width: 90px"
        />
        <span>-</span>
        <el-input-number
          v-model="editEnd"
          :precision="3"
          :step="0.1"
          :min="0"
          size="small"
          controls-position="right"
          style="width: 90px"
          @change="saveTimestamps"
        />
        <el-icon class="check-icon" @click="saveTimestamps"><Check /></el-icon>
      </template>
      <template v-else>
        <span class="duration" @click.stop="editable && startEditTimestamps()">
          {{ formatDuration(sentence.duration || (sentence.end_time - sentence.start_time)) }}
        </span>
        <span class="timestamp-hint" v-if="editable" style="font-size:10px;color:var(--text-muted)">
          {{ sentence.start_time?.toFixed(1) }}-{{ sentence.end_time?.toFixed(1) }}s
        </span>
        <el-icon class="play-icon" @click.stop="$emit('seek', sentence.id, sentence.start_time)"><VideoPlay /></el-icon>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { VideoPlay, Check, Plus, Delete } from '@element-plus/icons-vue'
// Scissor icon not in Element Plus — use a text fallback


const props = defineProps({
  sentence: { type: Object, required: true },
  active: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
})

const emit = defineEmits(['seek', 'update', 'delete', 'split', 'insertBefore', 'insertAfter', 'mergeDown'])

const editingOriginal = ref(false)
const editingTranslated = ref(false)
const editingTimestamps = ref(false)
const editOriginal = ref('')
const editTranslated = ref('')
const editStart = ref(0)
const editEnd = ref(0)
const origInputRef = ref(null)

function startEdit(field) {
  if (!props.editable) return
  if (field === 'original') {
    editOriginal.value = props.sentence.original_text
    editingOriginal.value = true
    nextTick(() => origInputRef.value?.focus())
  } else if (field === 'translated') {
    editTranslated.value = props.sentence.translated_text
    editingTranslated.value = true
    nextTick(() => origInputRef.value?.focus())
  }
}

function cancelEdit() {
  editingOriginal.value = false
  editingTranslated.value = false
}

async function saveEdit() {
  if (!editingOriginal.value && !editingTranslated.value) return

  const patch = {}
  if (editingOriginal.value && editOriginal.value !== props.sentence.original_text) {
    patch.original_text = editOriginal.value
  }
  if (editingTranslated.value && editTranslated.value !== props.sentence.translated_text) {
    patch.translated_text = editTranslated.value
  }

  editingOriginal.value = false
  editingTranslated.value = false

  if (Object.keys(patch).length > 0) {
    emit('update', props.sentence.id, patch)
  }
}

function startEditTimestamps() {
  editStart.value = props.sentence.start_time
  editEnd.value = props.sentence.end_time
  editingTimestamps.value = true
}

function saveTimestamps() {
  editingTimestamps.value = false
  if (editStart.value !== props.sentence.start_time || editEnd.value !== props.sentence.end_time) {
    emit('update', props.sentence.id, {
      start_time: editStart.value,
      end_time: editEnd.value,
    })
  }
}

function formatDuration(s) {
  if (!s) return '0s'
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<style scoped>
.sentence-index {
  width: 36px;
  color: var(--text-secondary);
  font-size: 13px;
  flex-shrink: 0;
}
.sentence-content {
  flex: 1;
  min-width: 0;
}
.original {
  font-size: 15px;
  line-height: 1.5;
  margin-bottom: 2px;
  cursor: default;
}
.translated {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  cursor: default;
}
.inline-input {
  margin-bottom: 2px;
}
.inline-input--translated {
  font-size: 13px;
}
.sentence-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 13px;
  flex-shrink: 0;
  margin-left: 12px;
}
.duration { cursor: default; }
.play-icon { cursor: pointer; color: #409eff; }
.check-icon { cursor: pointer; color: #67c23a; }
.edited-dot {
  color: #e6a23c;
  font-weight: bold;
  margin-left: 2px;
}
.editing .sentence-content {
  background: var(--bg-panel);
  border-radius: 4px;
  padding: 2px 4px;
}
.sentence-actions {
  display: flex;
  gap: 2px;
  margin-right: 8px;
  flex-shrink: 0;
}
.action-icon {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 14px;
  transition: color 0.2s, background 0.2s;
}
.action-icon:hover { color: #409eff; background: #ecf5ff; }
.action-split { font-size: 12px; }
.action-delete:hover { color: #f56c6c; background: #fef0f0; }
</style>

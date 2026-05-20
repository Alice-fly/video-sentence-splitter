<template>
  <div class="workflow-panel">
    <div class="steps">
      <!-- Step 1: Import -->
      <div class="step" :class="stepClass(video.import_status)">
        <div class="step-header">
          <span class="step-icon">
            <el-icon v-if="video.import_status === 'completed'"><CircleCheck /></el-icon>
            <el-icon v-else-if="video.import_status === 'processing'"><Loading /></el-icon>
            <el-icon v-else-if="video.import_status === 'failed'"><CircleClose /></el-icon>
            <span v-else>1</span>
          </span>
          <span class="step-label">导入</span>
          <span v-if="video.source_type" class="step-source">({{ sourceLabel }})</span>
        </div>
        <div v-if="video.import_status === 'processing'" class="step-progress">
          <ProgressBar :progress="video.import_progress" :message="video.import_progress_message" compact />
        </div>
        <div v-if="video.import_status === 'failed'" class="step-error">
          {{ video.import_error_message }}
        </div>
        <div v-if="video.import_status === 'not_started'" class="step-actions">
          <el-dropdown @command="(cmd) => { if (cmd === 'youtube') $emit('import-youtube'); else $emit('import-bilibili') }">
            <el-button size="small" type="primary">导入视频</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="youtube">YouTube</el-dropdown-item>
                <el-dropdown-item command="bilibili">B站</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="step-arrow">→</div>

      <!-- Step 2: Subtitle -->
      <div class="step" :class="stepClass(video.subtitle_status)">
        <div class="step-header">
          <span class="step-icon">
            <el-icon v-if="video.subtitle_status === 'completed'"><CircleCheck /></el-icon>
            <el-icon v-else-if="video.subtitle_status === 'processing'"><Loading /></el-icon>
            <el-icon v-else-if="video.subtitle_status === 'failed'"><CircleClose /></el-icon>
            <span v-else>2</span>
          </span>
          <span class="step-label">字幕</span>
          <span v-if="video.subtitle_method" class="step-source">({{ methodLabel }})</span>
        </div>
        <div v-if="video.subtitle_status === 'processing'" class="step-progress">
          <ProgressBar :progress="video.subtitle_progress" :message="video.subtitle_progress_message" compact />
        </div>
        <div v-if="video.subtitle_status === 'failed'" class="step-error">
          {{ video.subtitle_error_message }}
        </div>
        <!-- Not started: full action buttons -->
        <div v-if="video.subtitle_status === 'not_started' && video.import_status === 'completed'" class="step-actions">
          <el-button size="small" type="primary" @click="$emit('trigger-whisper')">Whisper 识别</el-button>
          <el-upload
            :show-file-list="false"
            :before-upload="(f) => { $emit('import-subtitle-file', f); return false }"
            accept=".srt,.vtt"
            style="display:inline-block;margin-left:4px"
          >
            <el-button size="small">上传字幕</el-button>
          </el-upload>
        </div>
        <!-- Completed: re-do -->
        <div v-if="video.subtitle_status === 'completed'" class="step-actions">
          <el-button size="small" text @click="$emit('trigger-whisper')">重新 Whisper</el-button>
          <el-button size="small" text @click="$emit('trigger-ocr')">重新 OCR</el-button>
          <el-upload
            :show-file-list="false"
            :before-upload="(f) => { $emit('import-subtitle-file', f); return false }"
            accept=".srt,.vtt"
            style="display:inline-block;margin-left:4px"
          >
            <el-button size="small" text>重新导入</el-button>
          </el-upload>
        </div>
        <!-- Failed: retry -->
        <div v-if="video.subtitle_status === 'failed' && video.import_status === 'completed'" class="step-actions">
          <el-button size="small" type="primary" @click="$emit('trigger-whisper')">Whisper 识别</el-button>
          <el-upload
            :show-file-list="false"
            :before-upload="(f) => { $emit('import-subtitle-file', f); return false }"
            accept=".srt,.vtt"
            style="display:inline-block;margin-left:4px"
          >
            <el-button size="small">上传字幕</el-button>
          </el-upload>
        </div>
      </div>

      <div class="step-arrow">→</div>

      <!-- Step 3: Segment -->
      <div class="step step--sub" :class="stepClass(video.segment_status)">
        <div class="step-header">
          <span class="step-icon">
            <el-icon v-if="video.segment_status === 'completed'"><CircleCheck /></el-icon>
            <el-icon v-else-if="video.segment_status === 'processing'"><Loading /></el-icon>
            <el-icon v-else-if="video.segment_status === 'failed'"><CircleClose /></el-icon>
            <span v-else>3</span>
          </span>
          <span class="step-label">断句</span>
        </div>
        <div v-if="video.segment_status === 'processing'" class="step-progress">
          <ProgressBar :progress="video.segment_progress" :message="video.segment_progress_message" compact />
        </div>
        <div v-if="video.segment_status === 'failed'" class="step-error">
          {{ video.segment_error_message }}
        </div>
        <div v-if="video.segment_status === 'not_started' && video.subtitle_status === 'completed'" class="step-actions">
          <el-button size="small" type="primary" @click="$emit('trigger-segment')">AI 断句</el-button>
        </div>
        <div v-if="video.segment_status === 'completed'" class="step-actions">
          <el-button size="small" text @click="$emit('trigger-segment')">重新断句</el-button>
        </div>
      </div>

      <div class="step-arrow">→</div>

      <!-- Step 4: Translate -->
      <div class="step step--sub" :class="stepClass(video.translate_status)">
        <div class="step-header">
          <span class="step-icon">
            <el-icon v-if="video.translate_status === 'completed'"><CircleCheck /></el-icon>
            <el-icon v-else-if="video.translate_status === 'processing'"><Loading /></el-icon>
            <el-icon v-else-if="video.translate_status === 'failed'"><CircleClose /></el-icon>
            <span v-else>4</span>
          </span>
          <span class="step-label">翻译</span>
        </div>
        <div v-if="video.translate_status === 'processing'" class="step-progress">
          <ProgressBar :progress="video.translate_progress" :message="video.translate_progress_message" compact />
        </div>
        <div v-if="video.translate_status === 'failed'" class="step-error">
          {{ video.translate_error_message }}
        </div>
        <div v-if="video.translate_status === 'not_started' && video.segment_status === 'completed'" class="step-actions">
          <el-button size="small" type="primary" @click="$emit('trigger-translate')">{{ translateLabel }}</el-button>
        </div>
        <div v-if="video.translate_status === 'completed'" class="step-actions">
          <el-button size="small" text @click="$emit('trigger-translate')">重新{{ translateLabel }}</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'
import ProgressBar from './ProgressBar.vue'

const props = defineProps({
  video: { type: Object, required: true },
  translateMethod: { type: String, default: 'deepseek' },
})

const translateLabel = computed(() => ({
  deepseek: 'AI 翻译',
  google: 'Google 翻译',
  microsoft: 'MS 翻译',
}[props.translateMethod] || 'AI 翻译'))

defineEmits([
  'import-youtube', 'import-bilibili',
  'trigger-whisper', 'import-subtitle-file',
  'trigger-segment', 'trigger-translate',
])

const sourceLabel = computed(() => ({
  youtube: 'YouTube', bilibili: 'B站', local_file: '本地',
}[props.video.source_type] || props.video.source_type))

const methodLabel = computed(() => ({
  whisper: 'Whisper', local_import: '导入', embedded: '内嵌',
}[props.video.subtitle_method] || props.video.subtitle_method))

function stepClass(status) {
  return `step--${status || 'not_started'}`
}
</script>

<style scoped>
.workflow-panel {
  background: var(--bg-panel);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.steps {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}
.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 60px;
}
.step--sub {
  opacity: 0.85;
  padding-left: 8px;
  border-left: 2px solid var(--border-color);
}
.step-header {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}
.step-icon { font-size: 18px; }
.step--completed .step-icon { color: #67c23a; }
.step--processing .step-icon { color: #409eff; }
.step--failed .step-icon { color: #f56c6c; }
.step--not_started .step-icon { color: var(--text-muted); }
.step-label { font-weight: 500; }
.step-source { font-size: 11px; color: var(--text-secondary); }
.step-progress { max-width: 120px; }
.step-error {
  font-size: 11px;
  color: #f56c6c;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step-actions { margin-top: 2px; display: flex; gap: 4px; align-items: center; }
.step-arrow {
  font-size: 16px;
  color: var(--text-muted);
  align-self: center;
}
</style>

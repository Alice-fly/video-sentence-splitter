<template>
  <div class="page-container">
    <div class="back-row">
      <el-button @click="$router.push('/')" text>
        &larr; 返回列表
      </el-button>
      <h3 v-if="video">{{ video.title }}</h3>
    </div>

    <div v-if="loading" class="loading">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else-if="video">
      <!-- Workflow panel -->
      <WorkflowPanel
        :video="video"
        :translate-method="translateMethod"
        @import-youtube="triggerImport('youtube')"
        @import-bilibili="triggerImport('bilibili')"
        @trigger-whisper="triggerSubtitle('whisper')"
        @import-subtitle-file="handleSubtitleFile"
        @trigger-segment="triggerSegment()"
        @trigger-translate="triggerTranslation()"
      />

      <!-- Status banner when processing -->
      <div v-if="isProcessing" class="status-banner">
        <el-alert
          :title="video.progress_message || '处理中...'"
          type="info"
          show-icon
        />
      </div>

      <!-- Video player -->
      <div v-if="video.local_video_path" class="player-wrapper" :class="{ mini: showMiniPlayer }">
        <video
          ref="playerRef"
          :src="`/api/videos/${video.id}/stream`"
          controls
          preload="auto"
          @timeupdate="onTimeUpdate"
          @loadedmetadata="onLoaded"
        ></video>
      </div>
      <div v-else-if="video.import_status === 'not_started'" class="player-placeholder">
        <el-empty description="请先导入视频" />
      </div>

      <!-- Sentence toolbar -->
      <div class="sentence-header">
        <span>共 {{ sentences.length }} 个句子</span>
        <el-switch
          v-if="sentences.length > 0"
          v-model="editMode"
          active-text="编辑"
          size="small"
          style="margin-left:12px"
        />
      </div>

      <!-- Sentence list -->
      <div class="sentence-list">
        <SentenceRow
          v-for="s in sentences"
          :key="s.id"
          :sentence="s"
          :active="activeSentenceId === s.id"
          :editable="editMode"
          @seek="seekTo"
          @update="handleSentenceUpdate"
          @delete="handleSentenceDelete"
          @split="handleSentenceSplit"
          @insertBefore="handleSentenceInsertBefore"
          @insertAfter="handleSentenceInsertAfter"
          @mergeDown="handleMergeDown"
        />
      </div>

      <!-- Raw subtitle timeline (before segmentation) -->
      <RawSubtitleTimeline
        v-if="!loading && sentences.length === 0 && video.subtitle_status === 'completed'"
        :entries="rawSubtitles"
        @seek="seekTo"
        @trigger-segment="triggerSegment"
      />

      <!-- Empty state -->
      <div v-if="!loading && sentences.length === 0 && !isProcessing && video.subtitle_status !== 'completed'" class="empty-state">
        <el-empty v-if="video.segment_status === 'not_started'"
          description="尚未开始断句，请先提取字幕再进行 AI 断句" />
        <el-empty v-else description="暂无句子数据" />
      </div>
    </template>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getVideo, getSentences, updateSentence, createSentence, deleteSentence,
  triggerImportYoutube, triggerImportBilibili,
  triggerSubtitleWhisper, importSubtitleFile,
  triggerSegment as apiTriggerSegment,
  triggerTranslate as apiTriggerTranslate,
  getRawSubtitles,
} from '../api/videos'
import SentenceRow from '../components/SentenceRow.vue'
import WorkflowPanel from '../components/WorkflowPanel.vue'
import RawSubtitleTimeline from '../components/RawSubtitleTimeline.vue'
import { useSettingsStore } from '../stores/settings'

const route = useRoute()
const store = useSettingsStore()
const video = ref(null)
const translateMethod = computed(() => store.translate_method || 'deepseek')
const sentences = ref([])
const loading = ref(true)
const activeSentenceId = ref(null)
const playerRef = ref(null)
const editMode = ref(false)
const rawSubtitles = ref([])
const showMiniPlayer = ref(false)
let playerObserver = null

const isProcessing = computed(() => {
  if (!video.value) return false
  const v = video.value
  return ['processing'].includes(v.import_status) ||
         ['processing'].includes(v.subtitle_status) ||
         ['processing'].includes(v.segment_status) ||
         ['processing'].includes(v.translate_status)
})

onMounted(async () => {
  if (!store.loaded) await store.load()
  await loadData()
  connectWebSocket()

  // IntersectionObserver for mini-player
  const playerEl = document.querySelector('.player-wrapper')
  if (playerEl) {
    playerObserver = new IntersectionObserver(([entry]) => {
      showMiniPlayer.value = !entry.isIntersecting && !!video.value?.local_video_path
    }, { threshold: 0.1 })
    playerObserver.observe(playerEl)
  }
})

onUnmounted(() => {
  if (playerObserver) playerObserver.disconnect()
})

async function loadData() {
  try {
    const [vRes, sRes] = await Promise.all([
      getVideo(route.params.id),
      getSentences(route.params.id),
    ])
    video.value = vRes.data
    sentences.value = sRes.data
    // Load raw subtitles if no sentences yet
    if (sRes.data.length === 0) {
      try {
        const rawRes = await getRawSubtitles(route.params.id)
        rawSubtitles.value = rawRes.data
      } catch (_) { rawSubtitles.value = [] }
    } else {
      rawSubtitles.value = []
    }
  } catch (e) {
    console.error('Failed to load video', e)
  } finally {
    loading.value = false
  }
}

function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${location.host}/api/videos/ws/${route.params.id}`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'progress' && video.value) {
      // Update per-step progress
      Object.assign(video.value, {
        status: msg.status,
        progress: msg.progress,
        progress_message: msg.progress_message,
        import_status: msg.import_status,
        import_progress: msg.import_progress,
        import_progress_message: msg.import_progress_message,
        subtitle_status: msg.subtitle_status,
        subtitle_progress: msg.subtitle_progress,
        subtitle_progress_message: msg.subtitle_progress_message,
        segment_status: msg.segment_status,
        segment_progress: msg.segment_progress,
        segment_progress_message: msg.segment_progress_message,
        translate_status: msg.translate_status,
        translate_progress: msg.translate_progress,
        translate_progress_message: msg.translate_progress_message,
      })
      // Reload data when any step completes
      if (msg.subtitle_status === 'completed' || msg.segment_status === 'completed' ||
          msg.translate_status === 'completed' || msg.status === 'completed') {
        loadData()
      }
    }
  }
}

// ── Import ──
async function triggerImport(source) {
  try {
    const v = video.value
    const body = {
      url: v.url || '',
      original_language: v.original_language || 'auto',
      trim_start: v.trim_start,
      trim_end: v.trim_end,
    }
    if (source === 'youtube') {
      await triggerImportYoutube(route.params.id, body)
      ElMessage.success('YouTube 导入已开始')
    } else {
      await triggerImportBilibili(route.params.id, body)
      ElMessage.success('B站导入已开始')
    }
    video.value.import_status = 'processing'
    video.value.progress_message = '正在导入...'
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  }
}

// ── Subtitle ──
async function triggerSubtitle(method) {
  try {
    if (method === 'whisper') {
      await triggerSubtitleWhisper(route.params.id)
    }
    ElMessage.success('字幕提取已开始')
    video.value.subtitle_status = 'processing'
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '字幕提取失败')
  }
}

async function handleSubtitleFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const { data } = await importSubtitleFile(route.params.id, formData)
    ElMessage.success(data.message)
    video.value.subtitle_status = 'completed'
    video.value.subtitle_method = 'local_import'
    loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '字幕导入失败')
  }
}

// ── Segment ──
async function triggerSegment() {
  try {
    await apiTriggerSegment(route.params.id)
    ElMessage.success('AI 断句已开始')
    video.value.segment_status = 'processing'
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '断句失败')
  }
}

// ── Translate ──
async function triggerTranslation() {
  try {
    await apiTriggerTranslate(route.params.id)
    ElMessage.success('翻译已开始')
    video.value.translate_status = 'processing'
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '翻译失败')
  }
}

// ── Playback ──
function seekTo(sentenceId, time) {
  activeSentenceId.value = sentenceId
  const video = playerRef.value
  if (!video) return
  if (video.readyState === 0) {
    // Video metadata not loaded yet, wait and retry
    video.addEventListener('loadedmetadata', () => {
      video.currentTime = time
      video.play()
    }, { once: true })
    return
  }
  video.currentTime = time
  video.play()
}

function onTimeUpdate() {
  if (!activeSentenceId.value || !playerRef.value) return
  const current = sentences.value.find(s => s.id === activeSentenceId.value)
  if (current && playerRef.value.currentTime >= current.end_time) {
    playerRef.value.pause()
    const idx = sentences.value.findIndex(s => s.id === activeSentenceId.value)
    if (idx >= 0 && idx < sentences.value.length - 1) {
      const next = sentences.value[idx + 1]
      activeSentenceId.value = next.id
      playerRef.value.currentTime = next.start_time
      playerRef.value.play()
    } else {
      activeSentenceId.value = null
    }
  }
}

function onLoaded() {}

// ── Sentence editing ──
async function handleSentenceUpdate(sentenceId, patch) {
  try {
    const { data } = await updateSentence(route.params.id, sentenceId, patch)
    const idx = sentences.value.findIndex(s => s.id === sentenceId)
    if (idx >= 0) {
      sentences.value[idx] = { ...sentences.value[idx], ...data }
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleSentenceDelete(sentenceId) {
  try {
    await ElMessageBox.confirm('确定删除此句子？', '确认', { type: 'warning' })
    await deleteSentence(route.params.id, sentenceId)
    await loadData()
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleSentenceSplit(sentenceId) {
  const s = sentences.value.find(x => x.id === sentenceId)
  if (!s) return
  try {
    const { value: splitAt } = await ElMessageBox.prompt('在哪个时间点拆分？（秒）', '拆分句子', {
      inputValue: String(((s.start_time + s.end_time) / 2).toFixed(1)),
      inputPattern: /[\d.]+/,
      inputErrorMessage: '请输入有效时间点',
    })
    const mid = parseFloat(splitAt)
    if (mid <= s.start_time || mid >= s.end_time) {
      ElMessage.warning('拆分时间需在句子时间范围内')
      return
    }
    // Split text roughly proportionally
    const ratio = (mid - s.start_time) / (s.end_time - s.start_time)
    const charSplit = Math.round(s.original_text.length * ratio)
    const text1 = s.original_text.slice(0, charSplit).trim()
    const text2 = s.original_text.slice(charSplit).trim()
    const trans1 = s.translated_text ? s.translated_text.slice(0, Math.round(s.translated_text.length * ratio)).trim() : ''
    const trans2 = s.translated_text ? s.translated_text.slice(Math.round(s.translated_text.length * ratio)).trim() : ''

    // Update first half
    await updateSentence(route.params.id, sentenceId, { end_time: mid, original_text: text1, translated_text: trans1, start_time: s.start_time })
    // Create second half
    await createSentence(route.params.id, { index: s.index + 1, start_time: mid, end_time: s.end_time, original_text: text2, translated_text: trans2 })
    await loadData()
    ElMessage.success('已拆分')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('拆分失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleSentenceInsertBefore(sentenceId, index) {
  try {
    const prev = index > 1 ? sentences.value.find(s => s.index === index - 1) : null
    const curr = sentences.value.find(s => s.id === sentenceId)
    const st = prev ? prev.end_time : (curr ? curr.start_time - 2 : 0)
    const et = curr ? curr.start_time : (st + 2)
    await createSentence(route.params.id, {
      index, start_time: Math.max(0, st), end_time: Math.max(st + 0.5, et),
      original_text: '', translated_text: '',
    })
    await loadData()
    ElMessage.success('已插入')
  } catch (e) {
    ElMessage.error('插入失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleSentenceInsertAfter(sentenceId, index) {
  try {
    const curr = sentences.value.find(s => s.id === sentenceId)
    const next = sentences.value.find(s => s.index === index + 1)
    const st = curr ? curr.end_time : 0
    const et = next ? next.start_time : (st + 2)
    await createSentence(route.params.id, {
      index: index + 1, start_time: st, end_time: et,
      original_text: '', translated_text: '',
    })
    await loadData()
    ElMessage.success('已插入')
  } catch (e) {
    ElMessage.error('插入失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleMergeDown(sentenceId) {
  const s1 = sentences.value.find(s => s.id === sentenceId)
  const s2 = sentences.value.find(s => s.index === s1?.index + 1)
  if (!s1 || !s2) {
    ElMessage.warning('没有下一句可合并')
    return
  }
  try {
    const mergedText = (s1.original_text + ' ' + s2.original_text).trim()
    const mergedTrans = [s1.translated_text, s2.translated_text].filter(Boolean).join(' ')
    const mergedStart = Math.min(s1.start_time, s2.start_time)
    const mergedEnd = Math.max(s1.end_time, s2.end_time)

    await updateSentence(route.params.id, s1.id, {
      start_time: mergedStart, end_time: mergedEnd,
      original_text: mergedText, translated_text: mergedTrans,
    })
    await deleteSentence(route.params.id, s2.id)
    await loadData()
    ElMessage.success('已合并')
  } catch (e) {
    ElMessage.error('合并失败: ' + (e.response?.data?.detail || e.message))
  }
}
</script>

<style scoped>
.back-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.back-row h3 {
  margin: 0;
}
.loading {
  padding: 40px 0;
}
.status-banner {
  margin-bottom: 16px;
}
.player-wrapper {
  margin-bottom: 16px;
}
.player-wrapper video {
  width: 100%;
  max-height: 480px;
  border-radius: 8px;
  background: #000;
}
.player-placeholder {
  padding: 40px;
  text-align: center;
}
.sentence-header {
  padding: 12px 0;
  color: #909399;
  font-size: 14px;
  display: flex;
  align-items: center;
}
.empty-state {
  padding: 40px 0;
}
.player-wrapper.mini {
  background: transparent;
}
.player-wrapper.mini video {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 320px;
  max-height: 180px;
  z-index: 1000;
  border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}
</style>

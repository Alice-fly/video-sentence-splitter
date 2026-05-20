import api from './index'

// ── Video CRUD ──
export function getVideos(params) {
  return api.get('/videos', { params })
}

export function getVideo(id) {
  return api.get(`/videos/${id}`)
}

export function addVideo(data) {
  return api.post('/videos', data)
}

export function updateVideo(id, data) {
  return api.put(`/videos/${id}`, data)
}

export function deleteVideo(id) {
  return api.delete(`/videos/${id}`)
}

// ── Sentences ──
export function getSentences(videoId) {
  return api.get(`/videos/${videoId}/sentences`)
}

export function updateSentence(videoId, sentenceId, data) {
  return api.put(`/videos/${videoId}/sentences/${sentenceId}`, data)
}

export function createSentence(videoId, data) {
  return api.post(`/videos/${videoId}/sentences`, data)
}

export function deleteSentence(videoId, sentenceId) {
  return api.delete(`/videos/${videoId}/sentences/${sentenceId}`)
}

// ── Import triggers ──
export function triggerImportYoutube(videoId, data) {
  return api.post(`/videos/${videoId}/import/youtube`, data)
}

export function triggerImportBilibili(videoId, data) {
  return api.post(`/videos/${videoId}/import/bilibili`, data)
}

export function addLocalVideo(formData) {
  return api.post('/videos/local', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
  })
}

// ── Subtitle triggers ──
export function triggerSubtitleWhisper(videoId) {
  return api.post(`/videos/${videoId}/subtitle/whisper`)
}

export function importSubtitleFile(videoId, formData) {
  return api.post(`/videos/${videoId}/subtitle/import`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function getRawSubtitles(videoId) {
  return api.get(`/videos/${videoId}/subtitles`)
}

// ── Segment & Translate ──
export function triggerSegment(videoId) {
  return api.post(`/videos/${videoId}/segment`)
}

export function triggerTranslate(videoId) {
  return api.post(`/videos/${videoId}/translate`)
}

// ── One-click full pipeline ──
export function processAll(videoId) {
  return api.post(`/videos/${videoId}/process-all`, {}, { timeout: 600000 })
}

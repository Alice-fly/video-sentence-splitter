import api from './index'

export function getSettings() {
  return api.get('/settings')
}

export function updateSettings(data) {
  return api.put('/settings', data)
}

export function fetchModels() {
  return api.get('/settings/models')
}

export function validateCookies(platform, browser, cookiesText) {
  return api.post('/settings/validate-cookies', { platform, browser, cookies_text: cookiesText })
}

export function fetchCookiesFromBrowser(browser, platform) {
  return api.post('/settings/fetch-cookies', { browser, platform })
}

export function installCudaRuntime() {
  return api.post('/settings/install-cuda-runtime', {}, { timeout: 600000 })
}

export function preloadWhisperModel(modelSize, device, computeType) {
  return api.post('/settings/preload-whisper-model', {
    model_size: modelSize,
    device: device,
    compute_type: computeType,
  }, {
    timeout: 600000,  // 10 min — model download can be several GB
  })
}

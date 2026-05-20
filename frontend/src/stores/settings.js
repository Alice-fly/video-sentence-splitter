import { defineStore } from 'pinia'
import { getSettings as fetchSettings, updateSettings as saveSettings } from '../api/settings'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    deepseek_api_key: '',
    deepseek_base_url: 'https://api.deepseek.com',
    deepseek_model: '',
    deepseek_max_mode: false,
    target_language: '中文',
    video_quality: '720p',
    cookies_from_browser_youtube: '',
    cookies_text_youtube: '',
    cookies_from_browser_bilibili: '',
    cookies_text_bilibili: '',
    subtitle_method: 'whisper',
    whisper_model_size: 'small',
    whisper_device: 'auto',
    whisper_compute_type: 'auto',
    whisper_beam_size: 5,
    whisper_vad_filter: true,
    translate_method: 'deepseek',
    microsoft_translator_key: '',
    microsoft_translator_region: 'eastasia',
    loaded: false,
  }),
  actions: {
    async load() {
      try {
        const { data } = await fetchSettings()
        Object.assign(this, data)
        this.loaded = true
      } catch (e) {
        console.error('Failed to load settings', e)
      }
    },
    async save() {
      const { data } = await saveSettings({
        deepseek_api_key: this.deepseek_api_key,
        deepseek_base_url: this.deepseek_base_url,
        deepseek_model: this.deepseek_model,
        deepseek_max_mode: this.deepseek_max_mode,
        target_language: this.target_language,
        video_quality: this.video_quality,
        cookies_from_browser_youtube: this.cookies_from_browser_youtube,
        cookies_text_youtube: this.cookies_text_youtube,
        cookies_from_browser_bilibili: this.cookies_from_browser_bilibili,
        cookies_text_bilibili: this.cookies_text_bilibili,
        subtitle_method: this.subtitle_method,
        whisper_model_size: this.whisper_model_size,
        whisper_device: this.whisper_device,
        whisper_compute_type: this.whisper_compute_type,
        whisper_beam_size: this.whisper_beam_size,
        whisper_vad_filter: this.whisper_vad_filter,
        translate_method: this.translate_method,
        microsoft_translator_key: this.microsoft_translator_key,
        microsoft_translator_region: this.microsoft_translator_region,
      })
      Object.assign(this, data)
    },
  },
})

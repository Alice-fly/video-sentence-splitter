<template>
  <div class="page-container">
    <div class="form-wrapper">
      <h3>API 配置</h3>
      <el-form :model="form" label-width="180px">
        <el-form-item label="API Key">
          <el-input
            v-model="form.deepseek_api_key"
            type="password"
            show-password
            placeholder="输入 API Key..."
          />
        </el-form-item>
        <el-form-item>
          <template #label>
            API Base URL
            <el-tooltip content="支持 OpenAI 兼容 API：DeepSeek、OpenAI、Groq、本地模型（Ollama/LM Studio）等。" placement="top">
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input v-model="form.deepseek_base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型">
          <div class="model-row">
            <el-select
              v-model="form.deepseek_model"
              filterable
              allow-create
              clearable
              placeholder="点击右侧按钮检测可用模型"
              :loading="detecting"
              class="model-select"
            >
              <el-option
                v-for="m in availableModels"
                :key="m"
                :label="m"
                :value="m"
              />
            </el-select>
            <el-button @click="detectModels" :loading="detecting" type="primary" plain>
              检测模型
            </el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="isDeepSeek">
          <template #label>
            DeepSeek Max 模式
            <el-tooltip content="开启后使用 1M token 上下文窗口（900K 输入 + 128K 输出），需选择 Max 系列模型（如 deepseek-v4-max）。标准模式为 120K 上下文（96K 输入 + 64K 输出），适用于普通模型。" placement="top">
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-switch v-model="form.deepseek_max_mode" active-text="1M 上下文" inactive-text="标准 128K" />
        </el-form-item>
        <el-form-item label="翻译目标语言">
          <el-input v-model="form.target_language" placeholder="中文" />
        </el-form-item>
        <el-form-item label="视频画质上限">
          <el-select v-model="form.video_quality">
            <el-option label="360p" value="360p" />
            <el-option label="480p" value="480p" />
            <el-option label="720p（推荐）" value="720p" />
            <el-option label="1080p" value="1080p" />
            <el-option label="2160p (4K)" value="2160p" />
          </el-select>
        </el-form-item>

        <!-- ── 字幕识别 ── -->
        <el-divider />
        <h4>字幕识别</h4>
        <el-form-item>
          <template #label>
            无软字幕时使用
            <el-tooltip content="Whisper 通过语音识别提取文字，适合有语音的视频。" placement="top">
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select v-model="form.subtitle_method">
            <el-option label="Whisper 语音识别" value="whisper" />
          </el-select>
        </el-form-item>

        <template v-if="form.subtitle_method === 'whisper'">
          <el-form-item label="Whisper 模型">
            <div class="whisper-model-row">
              <el-select v-model="form.whisper_model_size" class="whisper-model-select">
                <el-option label="tiny（~75MB，最快）" value="tiny" />
                <el-option label="base（~145MB，很快）" value="base" />
                <el-option label="small（~488MB，推荐）" value="small" />
                <el-option label="medium（~1.5GB，更准）" value="medium" />
                <el-option label="large-v3（~3GB，最准）" value="large-v3" />
              </el-select>
              <el-button
                @click="preloadModel"
                :loading="preloadingModel"
                :type="cachedModels[form.whisper_model_size]?.has_files ? 'default' : 'primary'"
                plain
                size="small"
              >
                {{ cachedModels[form.whisper_model_size]?.has_files ? '重新下载' : '下载模型' }}
              </el-button>
            </div>
            <div v-if="preloadResult" class="preload-result" :class="{ success: preloadResult.success }">
              {{ preloadResult.message }}
            </div>
            <div class="form-hint model-table-hint">
              <table class="model-table">
                <thead><tr><th>模型</th><th>大小</th><th>速度</th><th>适用场景</th><th>状态</th></tr></thead>
                <tbody>
                  <tr v-for="m in modelList" :key="m.size" :class="{ active: form.whisper_model_size === m.size }">
                    <td>{{ m.label }}</td><td>{{ m.vram }}</td><td>{{ m.speed }}</td><td>{{ m.desc }}</td>
                    <td>
                      <el-tag v-if="cachedModels[m.size]?.has_files" type="success" size="small">已下载</el-tag>
                      <el-tag v-else type="info" size="small">未下载</el-tag>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div class="form-hint model-table-footer">
                模型越大识别越准，但占用更多显存 (VRAM)。首次使用会自动从 Hugging Face 下载模型到项目目录（data/whisper_models/）。
              </div>
            </div>
          </el-form-item>

          <el-form-item>
            <template #label>
              运行设备
              <el-tooltip placement="top">
                <template #content>
                  <div style="max-width:320px;line-height:1.6">
                    <strong>自动检测</strong>：有 NVIDIA 显卡则用 GPU，否则自动切换 CPU。<br />
                    <strong>CUDA (GPU)</strong>：利用显卡硬件加速，比 CPU 快 5–20 倍。需安装 CUDA 驱动。<br />
                    <strong>CPU</strong>：纯 CPU 推理，速度较慢但兼容性最好，无需独立显卡。<br />
                    如遇 "CUDA out of memory" 错误，请减小模型或切换至 CPU。
                  </div>
                </template>
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-select v-model="form.whisper_device" style="width:200px">
              <el-option label="自动检测（推荐）" value="auto" />
              <el-option label="CUDA (GPU 加速)" value="cuda" />
              <el-option label="CPU" value="cpu" />
            </el-select>
            <el-button size="small" @click="checkGPU" :loading="gpuChecking" style="margin-left:8px">
              <template v-if="!gpuChecked">检测 GPU</template>
              <template v-else>重新检测</template>
            </el-button>
            <div v-if="gpuResult" class="gpu-result" :class="gpuResult.can_use_cuda ? 'gpu-ok' : 'gpu-warn'">
              <template v-if="gpuResult.can_use_cuda">
                <span class="gpu-icon">✓</span> CUDA GPU 可用 — {{ gpuResult.cuda_detail }}
              </template>
              <template v-else-if="gpuResult.cuda_available">
                <span class="gpu-icon">!</span> CUDA 驱动已安装但无法用于推理 — {{ gpuResult.cuda_detail }}
              </template>
              <template v-else>
                <span class="gpu-icon">✗</span> 未检测到 CUDA 驱动，Whisper 将使用 CPU 模式。
                <template v-if="form.whisper_device === 'cuda'">
                  <strong>建议将设备切换为「CPU」或「自动检测」。</strong>
                </template>
              </template>
            </div>
          </el-form-item>

          <el-form-item>
            <template #label>
              CUDA 运行库
              <el-tooltip content="有 NVIDIA 独显的用户可安装 CUDA 运行库加速 Whisper。装完后点击「检测 GPU」确认。" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-button size="small" @click="installCuda" :loading="cudaInstalling">
              {{ cudaResult?.success ? '重新安装 CUDA' : '安装 CUDA 运行库' }}
            </el-button>
            <div v-if="cudaResult" class="gpu-result" :class="cudaResult.success ? 'gpu-ok' : 'gpu-warn'">
              {{ cudaResult.message }}
            </div>
          </el-form-item>

          <el-form-item>
            <template #label>
              计算精度
              <el-tooltip placement="top">
                <template #content>
                  <div style="max-width:320px;line-height:1.6">
                    <strong>自动选择</strong>：根据设备自动选择最佳精度。<br />
                    <strong>float16</strong>：半精度浮点，显存占用最小、速度最快，仅限 CUDA。<br />
                    <strong>int8_float16</strong>：混合精度，显存比 float16 更小，仅限 CUDA。<br />
                    <strong>int8</strong>：8 位整数量化，适合 CPU 或低显存 GPU，速度较快但可能轻微影响准确度。<br />
                    不确定时保持「自动选择」即可。
                  </div>
                </template>
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-select v-model="form.whisper_compute_type">
              <el-option label="自动选择（推荐）" value="auto" />
              <el-option label="float16（半精度，仅 CUDA）" value="float16" />
              <el-option label="int8_float16（混合精度，仅 CUDA）" value="int8_float16" />
              <el-option label="int8（整数量化，CPU/GPU 通用）" value="int8" />
            </el-select>
          </el-form-item>

          <el-form-item>
            <template #label>
              搜索宽度
              <el-tooltip content="束搜索 (beam search) 宽度。值越大识别越准确，但速度越慢、显存占用越高。推荐默认值 5。追求速度可设为 3，追求最高准确度可设为 10。" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-select v-model="form.whisper_beam_size">
              <el-option v-for="n in 10" :key="n" :label="String(n)" :value="n" />
            </el-select>
          </el-form-item>

          <el-form-item>
            <template #label>
              VAD 静音过滤
              <el-tooltip content="VAD (Voice Activity Detection) 自动检测并跳过静音段，减少无效识别、加快处理速度。建议保持开启。" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-switch v-model="form.whisper_vad_filter" active-text="开启" inactive-text="关闭" />
          </el-form-item>
        </template>

        <!-- ── Translation ── -->
        <el-divider />
        <h4>翻译方式</h4>
        <el-form-item>
          <template #label>
            翻译引擎
            <el-tooltip placement="top">
              <template #content>
                <div style="max-width:320px;line-height:1.6">
                  <strong>LLM AI 翻译</strong>：调用大模型翻译，效果最佳，需消耗 API Key 余额。请在顶部 API 配置中填入 Key 和模型。<br />
                  <strong>Google 翻译</strong>：免费网页翻译，速度较快。每批最多 {{ maxChars.google }} 字符，长文本自动分批。<br />
                  <strong>Microsoft 翻译</strong>：Azure 免费层（每月 200 万字符），需配置 API Key，质量好。每批最多 {{ maxChars.microsoft }} 字符。
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select v-model="form.translate_method">
            <el-option
              v-if="form.deepseek_api_key"
              :label="llmTranslateLabel"
              value="deepseek"
            />
            <el-option label="Google 翻译（免费）" value="google" />
            <el-option label="Microsoft 翻译（免费）" value="microsoft" />
          </el-select>
        </el-form-item>

        <template v-if="form.translate_method === 'microsoft'">
          <el-form-item>
            <template #label>
              MS API Key
              <el-tooltip content="在 Azure Portal 创建 Translator 资源（F0 免费层），获取 Key。" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input v-model="form.microsoft_translator_key" placeholder="Azure Translator API Key" show-password />
          </el-form-item>
          <el-form-item>
            <template #label>
              MS Region
              <el-tooltip content="Azure 资源所在区域，如 eastasia（东亚）、japaneast（日本东部）等。" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input v-model="form.microsoft_translator_region" placeholder="eastasia" />
          </el-form-item>
        </template>

        <!-- ── YouTube Cookies ── -->
        <el-divider />
        <h4>YouTube Cookies</h4>
        <el-form-item label="浏览器">
          <el-select v-model="form.cookies_from_browser_youtube" clearable placeholder="选择登录过的浏览器">
            <el-option label="不使用" value="" />
            <el-option label="Chrome" value="chrome" />
            <el-option label="Firefox" value="firefox" />
            <el-option label="Edge" value="edge" />
            <el-option label="Brave" value="brave" />
            <el-option label="Opera" value="opera" />
          </el-select>
          <div class="form-hint">
            <template v-if="isNonChromeBrowser(form.cookies_from_browser_youtube)">
              已选择 {{ browserDisplayName(form.cookies_from_browser_youtube) }}，程序将自动从浏览器读取 YouTube cookies。
            </template>
            <template v-else-if="chromiumBrowsers.includes(form.cookies_from_browser_youtube)">
              {{ browserDisplayName(form.cookies_from_browser_youtube) }} 基于 Chromium 内核，cookies 经过系统级加密，yt-dlp 无法自动提取。请在下方手动粘贴 cookies 文本。
            </template>
          </div>
        </el-form-item>
        <el-form-item v-if="isManualCookieMode(form.cookies_from_browser_youtube)" label="Cookies 文本">
          <el-input
            v-model="form.cookies_text_youtube"
            type="textarea"
            :rows="4"
            placeholder="支持多种格式：Netscape 格式 / 请求头 Cookie 字符串 / 每行一个 key=value"
          />
        </el-form-item>
        <el-form-item>
          <div class="cookie-actions">
            <el-button @click="validateCookies('youtube')" :loading="validatingYoutube" size="small">
              验证 Cookies
            </el-button>
            <el-button
              v-if="isNonChromeBrowser(form.cookies_from_browser_youtube)"
              @click="fetchCookies('youtube')"
              :loading="fetchingYoutube"
              size="small"
              type="primary"
              plain
            >
              获取 Cookies
            </el-button>
          </div>
          <div v-if="cookieResult.youtube" class="cookie-result" :class="{ success: cookieResult.youtube.success }">
            {{ cookieResult.youtube.message }}
          </div>
        </el-form-item>

        <!-- ── Bilibili Cookies ── -->
        <el-divider />
        <h4>B站 Cookies</h4>
        <el-form-item label="浏览器">
          <el-select v-model="form.cookies_from_browser_bilibili" clearable placeholder="选择登录过的浏览器">
            <el-option label="不使用" value="" />
            <el-option label="Chrome" value="chrome" />
            <el-option label="Firefox" value="firefox" />
            <el-option label="Edge" value="edge" />
            <el-option label="Brave" value="brave" />
            <el-option label="Opera" value="opera" />
          </el-select>
          <div class="form-hint">
            <template v-if="isNonChromeBrowser(form.cookies_from_browser_bilibili)">
              已选择 {{ browserDisplayName(form.cookies_from_browser_bilibili) }}，程序将自动从浏览器读取 B站 cookies。
            </template>
            <template v-else-if="chromiumBrowsers.includes(form.cookies_from_browser_bilibili)">
              {{ browserDisplayName(form.cookies_from_browser_bilibili) }} 基于 Chromium 内核，cookies 经过系统级加密，yt-dlp 无法自动提取。请在下方手动粘贴 cookies 文本。
            </template>
          </div>
        </el-form-item>
        <el-form-item v-if="isManualCookieMode(form.cookies_from_browser_bilibili)" label="Cookies 文本">
          <el-input
            v-model="form.cookies_text_bilibili"
            type="textarea"
            :rows="4"
            placeholder="支持多种格式：Netscape 格式 / 请求头 Cookie 字符串 / 每行一个 key=value"
          />
        </el-form-item>
        <el-form-item>
          <div class="cookie-actions">
            <el-button @click="validateCookies('bilibili')" :loading="validatingBilibili" size="small">
              验证 Cookies
            </el-button>
            <el-button
              v-if="isNonChromeBrowser(form.cookies_from_browser_bilibili)"
              @click="fetchCookies('bilibili')"
              :loading="fetchingBilibili"
              size="small"
              type="primary"
              plain
            >
              获取 Cookies
            </el-button>
          </div>
          <div v-if="cookieResult.bilibili" class="cookie-result" :class="{ success: cookieResult.bilibili.success }">
            {{ cookieResult.bilibili.message }}
          </div>
        </el-form-item>

        <el-divider />
        <el-form-item>
          <el-button type="primary" @click="save" :loading="saving">保存配置</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import { fetchModels, validateCookies as apiValidateCookies, fetchCookiesFromBrowser, preloadWhisperModel, installCudaRuntime } from '../api/settings'

const store = useSettingsStore()
const saving = ref(false)
const detecting = ref(false)
const availableModels = ref([])
const validatingYoutube = ref(false)
const validatingBilibili = ref(false)
const fetchingYoutube = ref(false)
const fetchingBilibili = ref(false)
const cookieResult = reactive({ youtube: null, bilibili: null })
const preloadingModel = ref(false)
const preloadResult = ref(null)
const isDeepSeek = computed(() => {
  const url = form.value.deepseek_base_url || ''
  return url.includes('deepseek')
})

const llmTranslateLabel = computed(() => {
  const model = form.value.deepseek_model
  if (model) return `AI 翻译 — ${model}`
  return 'AI 翻译（LLM，推荐）'
})

const gpuChecking = ref(false)
const gpuChecked = ref(false)
const gpuResult = ref(null)
const cudaInstalling = ref(false)
const cudaResult = ref(null)
const cachedModels = ref({})

const maxChars = { google: 4500, microsoft: 4500 }

const modelList = [
  { size: 'tiny', label: 'tiny', vram: '~75 MB', speed: '最快', desc: '英语快速测试，中日文准确度较低' },
  { size: 'base', label: 'base', vram: '~145 MB', speed: '很快', desc: '简单多语言，短句可用' },
  { size: 'small', label: 'small ★', vram: '~488 MB', speed: '较快', desc: '推荐 — 中日英均衡，适合 4GB 显存' },
  { size: 'medium', label: 'medium', vram: '~1.5 GB', speed: '中等', desc: '更高准确度，需 6GB+ 显存' },
  { size: 'large-v3', label: 'large-v3', vram: '~3 GB', speed: '基准', desc: '最高准确度，需 8GB+ 显存' },
]

const form = ref({
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
})

const chromiumBrowsers = ['chrome', 'edge']

function isNonChromeBrowser(val) {
  return !!val && !chromiumBrowsers.includes(val)
}

function isManualCookieMode(val) {
  return !val || chromiumBrowsers.includes(val)
}

function browserDisplayName(val) {
  const map = { firefox: 'Firefox', edge: 'Edge', brave: 'Brave', opera: 'Opera' }
  return map[val] || val
}

onMounted(async () => {
  await store.load()
  form.value = {
    deepseek_api_key: store.deepseek_api_key,
    deepseek_base_url: store.deepseek_base_url,
    deepseek_model: store.deepseek_model,
    deepseek_max_mode: store.deepseek_max_mode || false,
    target_language: store.target_language,
    video_quality: store.video_quality || '720p',
    cookies_from_browser_youtube: store.cookies_from_browser_youtube || '',
    cookies_text_youtube: store.cookies_text_youtube || '',
    cookies_from_browser_bilibili: store.cookies_from_browser_bilibili || '',
    cookies_text_bilibili: store.cookies_text_bilibili || '',
    subtitle_method: store.subtitle_method || 'whisper',
    whisper_model_size: store.whisper_model_size || 'small',
    whisper_device: store.whisper_device || 'auto',
    whisper_compute_type: store.whisper_compute_type || 'auto',
    whisper_beam_size: store.whisper_beam_size ?? 5,
    whisper_vad_filter: store.whisper_vad_filter ?? true,
    translate_method: store.translate_method || 'deepseek',
    microsoft_translator_key: store.microsoft_translator_key || '',
    microsoft_translator_region: store.microsoft_translator_region || 'eastasia',
  }
  if (store.deepseek_api_key) {
    detectModels()
  }
  fetchCachedModels()
})

async function fetchCachedModels() {
  try {
    const { data } = await api.get('/settings/whisper-cached-models')
    cachedModels.value = data.cached || {}
  } catch (e) {
    // Silently fail — not critical
  }
}

async function detectModels() {
  if (!form.value.deepseek_api_key) {
    ElMessage.warning('请先填写 API Key')
    return
  }
  const storeBackup = {
    deepseek_api_key: store.deepseek_api_key,
    deepseek_base_url: store.deepseek_base_url,
  }
  store.deepseek_api_key = form.value.deepseek_api_key
  store.deepseek_base_url = form.value.deepseek_base_url
  try {
    await store.save()
  } catch (_) { /* ignore save errors during detection */ }

  detecting.value = true
  try {
    const { data } = await fetchModels()
    availableModels.value = data.models || []
    if (availableModels.value.length > 0) {
      ElMessage.success(`检测到 ${availableModels.value.length} 个可用模型`)
      if (!form.value.deepseek_model && availableModels.value.length > 0) {
        const chatModel = availableModels.value.find(m => m.includes('chat'))
        form.value.deepseek_model = chatModel || availableModels.value[0]
      }
    } else {
      ElMessage.warning('未检测到可用模型')
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    ElMessage.error(`模型检测失败: ${msg}`)
  } finally {
    detecting.value = false
    store.deepseek_api_key = storeBackup.deepseek_api_key
    store.deepseek_base_url = storeBackup.deepseek_base_url
  }
}

async function validateCookies(platform) {
  const loading = platform === 'youtube' ? validatingYoutube : validatingBilibili
  loading.value = true
  cookieResult[platform] = null
  try {
    const browser = platform === 'youtube'
      ? form.value.cookies_from_browser_youtube
      : form.value.cookies_from_browser_bilibili
    const text = platform === 'youtube'
      ? form.value.cookies_text_youtube
      : form.value.cookies_text_bilibili

    const { data } = await apiValidateCookies(platform, browser || null, text || null)
    cookieResult[platform] = data
    if (data.success) {
      ElMessage.success(`${platform === 'youtube' ? 'YouTube' : 'B站'} Cookies 验证通过`)
    } else {
      ElMessage.warning(data.message)
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    cookieResult[platform] = { success: false, message: msg }
    ElMessage.error(`验证失败: ${msg}`)
  } finally {
    loading.value = false
  }
}

async function fetchCookies(platform) {
  const loading = platform === 'youtube' ? fetchingYoutube : fetchingBilibili
  loading.value = true
  cookieResult[platform] = null
  try {
    const browser = platform === 'youtube'
      ? form.value.cookies_from_browser_youtube
      : form.value.cookies_from_browser_bilibili

    const { data } = await fetchCookiesFromBrowser(browser, platform)
    cookieResult[platform] = data
    if (data.success && data.cookies_text) {
      if (platform === 'youtube') {
        form.value.cookies_text_youtube = data.cookies_text
      } else {
        form.value.cookies_text_bilibili = data.cookies_text
      }
      // Switch to manual mode so user can see the extracted text
      if (platform === 'youtube') {
        form.value.cookies_from_browser_youtube = ''
      } else {
        form.value.cookies_from_browser_bilibili = ''
      }
      ElMessage.success(data.message)
    } else if (data.success) {
      ElMessage.success(data.message)
    } else {
      ElMessage.warning(data.message)
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    cookieResult[platform] = { success: false, message: msg }
    ElMessage.error(`获取失败: ${msg}`)
  } finally {
    loading.value = false
  }
}

async function preloadModel() {
  preloadingModel.value = true
  preloadResult.value = null
  try {
    const { data } = await preloadWhisperModel(
      form.value.whisper_model_size,
      form.value.whisper_device,
      form.value.whisper_compute_type,
    )
    preloadResult.value = data
    if (data.success) {
      ElMessage.success(`Whisper 模型 ${form.value.whisper_model_size} 下载完成`)
      fetchCachedModels()
    } else {
      ElMessage.warning(data.message)
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.response?.data?.message || e.message
    preloadResult.value = { success: false, message: msg }
    ElMessage.error(`模型下载失败: ${msg}`)
  } finally {
    preloadingModel.value = false
  }
}

async function checkGPU() {
  gpuChecking.value = true
  gpuResult.value = null
  try {
    const { data } = await api.get('/settings/check-gpu')
    gpuResult.value = data
    gpuChecked.value = true
    if (!data.can_use_cuda && form.value.whisper_device === 'cuda') {
      ElMessage.warning('未检测到可用 GPU，建议切换设备为 CPU 或自动检测')
    }
  } catch (e) {
    ElMessage.error('GPU 检测失败: ' + (e.message || '网络错误'))
  } finally {
    gpuChecking.value = false
  }
}

async function installCuda() {
  cudaInstalling.value = true
  cudaResult.value = null
  try {
    const { data } = await installCudaRuntime()
    cudaResult.value = data
    if (data.success) {
      ElMessage.success('CUDA 运行库安装完成')
      checkGPU()
    } else {
      ElMessage.warning(data.message)
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    cudaResult.value = { success: false, message: msg }
    ElMessage.error('安装失败: ' + msg)
  } finally {
    cudaInstalling.value = false
  }
}

async function save() {
  saving.value = true
  try {
    // If API key is cleared, switch translation away from LLM
    if (!form.value.deepseek_api_key && form.value.translate_method === 'deepseek') {
      form.value.translate_method = 'google'
    }
    // Non-Chrome browsers auto-extract cookies — clear stale text (Chromium browsers keep manual text)
    if (form.value.cookies_from_browser_youtube && !chromiumBrowsers.includes(form.value.cookies_from_browser_youtube)) {
      form.value.cookies_text_youtube = ''
    }
    if (form.value.cookies_from_browser_bilibili && !chromiumBrowsers.includes(form.value.cookies_from_browser_bilibili)) {
      form.value.cookies_text_bilibili = ''
    }
    Object.assign(store, form.value)
    await store.save()
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form-wrapper {
  max-width: 840px;
  margin: 0 auto;
  background: var(--bg-surface);
  padding: 32px;
  border-radius: 8px;
}
.form-wrapper h3 {
  margin-bottom: 24px;
}
.form-wrapper h4 {
  margin: 0 0 12px 0;
  color: var(--text-primary);
}
.model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.model-select {
  flex: 1;
}
.form-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.help-icon {
  margin-left: 2px;
  color: var(--text-secondary);
  cursor: help;
  font-size: 13px;
  vertical-align: top;
}
.model-table-footer {
  margin-top: 4px;
}
.gpu-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.5;
}
.gpu-ok {
  background: #f0f9eb;
  color: #67c23a;
}
.gpu-warn {
  background: #fdf6ec;
  color: #e6a23c;
}
.gpu-icon {
  font-weight: bold;
  margin-right: 4px;
}
.cookie-actions {
  display: flex;
  gap: 8px;
}
.cookie-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  background: #fdf6ec;
  color: #e6a23c;
}
.cookie-result.success {
  background: #f0f9eb;
  color: #67c23a;
}
.model-table-hint {
  margin-top: 8px;
}
.model-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-bottom: 6px;
}
.model-table th, .model-table td {
  padding: 4px 8px;
  border: 1px solid var(--border-light);
  text-align: left;
}
.model-table th {
  background: var(--bg-panel);
  font-weight: 600;
  color: var(--text-primary);
}
.model-table tr.active {
  background: var(--bg-panel);
  font-weight: 600;
  color: #409eff;
}
.whisper-model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.whisper-model-select {
  flex: 1;
}
.preload-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  background: #fdf6ec;
  color: #e6a23c;
}
.preload-result.success {
  background: #f0f9eb;
  color: #67c23a;
}
</style>

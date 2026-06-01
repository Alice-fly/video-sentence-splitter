<template>
  <div class="page-container">
    <div class="form-wrapper">
      <h3>添加新视频</h3>

      <!-- Source type selection -->
      <el-radio-group v-model="sourceType" class="source-tabs" size="large">
        <el-radio-button value="youtube">YouTube</el-radio-button>
        <el-radio-button value="bilibili">B站</el-radio-button>
        <el-radio-button value="local_file">本地文件</el-radio-button>
      </el-radio-group>

      <el-form :model="form" label-width="100px" @submit.prevent="submit" class="add-form">
        <!-- URL input for YouTube / Bilibili -->
        <el-form-item v-if="sourceType !== 'local_file'" label="视频链接">
          <el-input
            v-model="form.url"
            :placeholder="sourceType === 'youtube' ? '粘贴 YouTube 视频链接...' : '粘贴 B站 视频链接...'"
          />
        </el-form-item>

        <!-- File upload for local -->
        <el-form-item v-if="sourceType === 'local_file'" label="选择文件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            accept="video/*"
            drag
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              拖拽视频文件到这里 或 <em>点击上传</em>
            </div>
          </el-upload>
        </el-form-item>

        <!-- Trim range (YouTube / Bilibili only) -->
        <el-form-item v-if="sourceType !== 'local_file'">
          <template #label>
            裁剪范围
            <el-tooltip content="可选，设置后只下载视频的指定时间段。单位：秒。留空则下载完整视频。">
              <el-icon style="margin-left:4px;cursor:help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-row :gutter="8" style="width:100%">
            <el-col :span="11">
              <el-input-number
                v-model="form.trim_start"
                :min="0"
                :step="1"
                :precision="1"
                placeholder="起始 (秒)"
                controls-position="right"
                style="width:100%"
              />
            </el-col>
            <el-col :span="2" style="text-align:center;line-height:32px">-</el-col>
            <el-col :span="11">
              <el-input-number
                v-model="form.trim_end"
                :min="0"
                :step="1"
                :precision="1"
                placeholder="结束 (秒)"
                controls-position="right"
                style="width:100%"
              />
            </el-col>
          </el-row>
        </el-form-item>

        <el-form-item label="分类">
          <el-select v-model="form.category_id" placeholder="可选" clearable>
            <el-option
              v-for="cat in flatCategories"
              :key="cat.id"
              :label="cat.name"
              :value="cat.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="源语言">
          <el-radio-group v-model="form.original_language">
            <el-radio value="auto">自动检测</el-radio>
            <el-radio value="ja">日语</el-radio>
            <el-radio value="en">英语</el-radio>
            <el-radio value="zh">中文</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="submit" :loading="submitting">
            {{ sourceType === 'local_file' ? '上传并添加' : '添加并导入' }}
          </el-button>
          <el-button @click="$router.push('/')">取消</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { UploadFilled, QuestionFilled } from '@element-plus/icons-vue'
import { addVideo, addLocalVideo, triggerImportYoutube, triggerImportBilibili } from '../api/videos'
import { getCategories } from '../api/categories'

const router = useRouter()
const submitting = ref(false)
const sourceType = ref('youtube')
const flatCategories = ref([])
const selectedFile = ref(null)

const form = ref({
  url: '',
  category_id: null,
  original_language: 'auto',
  source_type: 'youtube',
  trim_start: null,
  trim_end: null,
})

onMounted(async () => {
  try {
    const { data } = await getCategories()
    flatCategories.value = flatten(data)
  } catch (e) {
    console.error('Failed to load categories', e)
  }
})

function flatten(cats, prefix = '') {
  let result = []
  for (const c of cats) {
    result.push({ id: c.id, name: prefix + c.name })
    if (c.children?.length) {
      result = result.concat(flatten(c.children, prefix + '  '))
    }
  }
  return result
}

function onFileChange(file) {
  selectedFile.value = file.raw
}

async function submit() {
  if (sourceType.value === 'local_file') {
    if (!selectedFile.value) return
  } else {
    if (!form.value.url.trim()) return
  }
  submitting.value = true
  try {
    let data
    if (sourceType.value === 'local_file') {
      const fd = new FormData()
      fd.append('file', selectedFile.value)
      fd.append('original_language', form.value.original_language)
      if (form.value.category_id) fd.append('category_id', form.value.category_id)
      const res = await addLocalVideo(fd)
      data = res.data
    } else {
      form.value.source_type = sourceType.value
      const res = await addVideo(form.value)
      data = res.data
      // Auto-trigger import immediately
      const importBody = {
        url: form.value.url,
        original_language: form.value.original_language,
        trim_start: form.value.trim_start,
        trim_end: form.value.trim_end,
      }
      try {
        if (sourceType.value === 'youtube') {
          await triggerImportYoutube(data.id, importBody)
        } else if (sourceType.value === 'bilibili') {
          await triggerImportBilibili(data.id, importBody)
        }
      } catch (e) {
        console.error('Auto-import failed, user can retry manually', e)
      }
    }
    router.push(`/video/${data.id}`)
  } catch (e) {
    console.error('Failed to add video', e)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.form-wrapper {
  max-width: 600px;
  margin: 0 auto;
  background: #fff;
  padding: 32px;
  border-radius: 8px;
}
.form-wrapper h3 {
  margin-bottom: 20px;
}
.source-tabs {
  margin-bottom: 24px;
  width: 100%;
  display: flex;
  justify-content: center;
}
.add-form {
  margin-top: 8px;
}
</style>

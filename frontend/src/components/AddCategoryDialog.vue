<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="新增分类"
    width="400px"
  >
    <el-form label-width="80px">
      <el-form-item label="名称">
        <el-input v-model="name" placeholder="分类名称..." />
      </el-form-item>
      <el-form-item label="父分类">
        <el-select v-model="parentId" placeholder="可选" clearable>
          <el-option
            v-for="cat in flatCats"
            :key="cat.id"
            :label="cat.name"
            :value="cat.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { createCategory } from '../api/categories'

const props = defineProps({
  visible: { type: Boolean, default: false },
  categories: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'saved'])

const name = ref('')
const parentId = ref(null)

const flatCats = computed(() => {
  function flatten(list, prefix = '') {
    let result = []
    for (const c of list) {
      result.push({ id: c.id, name: prefix + c.name })
      if (c.children?.length) result = result.concat(flatten(c.children, prefix + '  '))
    }
    return result
  }
  return flatten(props.categories)
})

async function confirm() {
  if (!name.value.trim()) return
  try {
    await createCategory({ name: name.value.trim(), parent_id: parentId.value || null })
    name.value = ''
    parentId.value = null
    emit('update:visible', false)
    emit('saved')
  } catch (e) {
    console.error('Failed to create category', e)
  }
}
</script>

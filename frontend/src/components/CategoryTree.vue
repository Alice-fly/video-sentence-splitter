<template>
  <div class="category-tree">
    <div class="tree-header">
      <span>分类</span>
      <el-button size="small" text @click="showAdd = true">+ 新增</el-button>
    </div>
    <el-menu class="tree-menu" :default-active="selectedId || 'all'" @select="handleSelect">
      <el-menu-item index="all">
        <span>全部</span>
      </el-menu-item>
      <template v-for="cat in categories" :key="cat.id">
        <el-menu-item :index="cat.id">
          {{ cat.name }}
        </el-menu-item>
        <el-menu-item
          v-for="child in cat.children"
          :key="child.id"
          :index="child.id"
          style="padding-left: 40px"
        >
          {{ child.name }}
        </el-menu-item>
      </template>
    </el-menu>

    <AddCategoryDialog
      v-model:visible="showAdd"
      :parent-id="null"
      :categories="categories"
      @saved="reload"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { getCategories } from '../api/categories'
import AddCategoryDialog from './AddCategoryDialog.vue'

const categories = ref([])
const showAdd = ref(false)
const selectedId = inject('selectedCategoryId', ref(null))

onMounted(() => reload())

async function reload() {
  try {
    const { data } = await getCategories()
    categories.value = data
  } catch (e) {
    console.error('Failed to load categories', e)
  }
}

function handleSelect(id) {
  selectedId.value = id === 'all' ? null : id
}
</script>

<style scoped>
.tree-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px;
  margin-bottom: 8px;
  font-weight: 500;
}
.tree-menu {
  border-right: none;
}
</style>

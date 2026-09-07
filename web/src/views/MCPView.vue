<template>
  <div class="mcp">
    <el-page-header title="返回" @back="$router.push('/')" />
    <h2>MCP 工具箱</h2>
    <el-table :data="tools" v-loading="loading" style="margin-top: 16px">
      <el-table-column prop="name" label="工具名" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="操作" width="120">
        <template #default>
          <el-button link type="primary" disabled>调用</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import apiClient from '@/api/client'

interface MCPTool {
  name: string
  description: string
}

const tools = ref<MCPTool[]>([])
const loading = ref(false)

const fetchTools = async () => {
  loading.value = true
  try {
    const { data } = await apiClient.get('/mcp/tools')
    tools.value = data
  } finally {
    loading.value = false
  }
}

onMounted(fetchTools)
</script>

<style scoped>
.mcp {
  padding: 24px;
}
</style>

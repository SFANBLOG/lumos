<template>
  <div class="mcp">
    <el-card shadow="never">
      <template #header>
        <div class="mcp-head">
          <span class="card-title">可用 MCP 工具</span>
          <el-button :icon="Refresh" circle plain @click="fetchTools" />
        </div>
      </template>
      <el-table :data="tools" v-loading="loading" empty-text="暂无工具">
        <el-table-column prop="name" label="工具名" width="180">
          <template #default="{ row }">
            <span class="tool-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" />
        <el-table-column label="操作" width="110" align="center">
          <template #default>
            <el-button link type="primary" disabled>调用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
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
.mcp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title {
  font-weight: 600;
  color: #303133;
}
.tool-name {
  font-weight: 500;
  color: #303133;
}
</style>

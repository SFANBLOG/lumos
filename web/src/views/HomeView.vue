<template>
  <div class="home">
    <el-header class="header">
      <div class="brand">Lumos · 契光鉴微</div>
      <div class="user">
        <span v-if="auth.user">{{ auth.user.username }}</span>
        <el-button type="danger" text @click="handleLogout">退出</el-button>
      </div>
    </el-header>
    <el-main>
      <el-row :gutter="20" class="actions">
        <el-col :span="8">
          <el-card shadow="hover" @click="$router.push('/analysis')">
            <el-icon><Document /></el-icon>
            <div>文本分析</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" @click="$router.push('/analysis')">
            <el-icon><Upload /></el-icon>
            <div>文件分析</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" @click="$router.push('/mcp')">
            <el-icon><Tools /></el-icon>
            <div>MCP 工具</div>
          </el-card>
        </el-col>
      </el-row>
    </el-main>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Document, Upload, Tools } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const handleLogout = () => {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 60px;
  border-bottom: 1px solid #ebeef5;
}
.brand {
  font-size: 20px;
  font-weight: bold;
}
.user {
  display: flex;
  align-items: center;
  gap: 12px;
}
.actions {
  margin-top: 20px;
}
.actions .el-card {
  text-align: center;
  padding: 24px 0;
  cursor: pointer;
}
.actions .el-icon {
  font-size: 36px;
  margin-bottom: 12px;
}
</style>

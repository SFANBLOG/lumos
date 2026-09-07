<template>
  <el-container class="app-layout">
    <el-aside width="200px" class="aside">
      <div class="logo">
        <div class="logo-name">Lumos</div>
        <div class="logo-sub">契光鉴微</div>
      </div>
      <el-menu :default-active="activeMenu" router class="side-menu">
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>主看板</span>
        </el-menu-item>
        <el-menu-item index="/analysis">
          <el-icon><Document /></el-icon>
          <span>智能分析</span>
        </el-menu-item>
        <el-menu-item index="/consult">
          <el-icon><ChatLineRound /></el-icon>
          <span>智能咨询</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Clock /></el-icon>
          <span>历史报告</span>
        </el-menu-item>
        <el-menu-item index="/mcp">
          <el-icon><MagicStick /></el-icon>
          <span>MCP 工具</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="body">
      <el-header class="header">
        <div class="page-title">{{ route.meta?.title ?? '' }}</div>
        <div class="user">
          <el-icon class="user-icon"><User /></el-icon>
          <span class="username">{{ auth.user?.username ?? '...' }}</span>
          <el-button type="danger" text size="small" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatLineRound, Clock, Document, MagicStick, Odometer, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)

const handleLogout = () => {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  // 刷新页面后 token 仍在而用户信息为空时补拉一次
  if (auth.isLoggedIn() && !auth.user) {
    auth.fetchUser()
  }
})
</script>

<style scoped>
.app-layout {
  height: 100vh;
}
.aside {
  background: #ffffff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.logo {
  height: 72px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2px;
  border-bottom: 1px solid #f0f2f5;
  flex-shrink: 0;
}
.logo-name {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  letter-spacing: 0.5px;
}
.logo-sub {
  font-size: 12px;
  color: #909399;
  letter-spacing: 6px;
  transform: translateX(3px);
}
.side-menu {
  border-right: none;
  flex: 1;
  padding-top: 8px;
}
.side-menu .el-menu-item {
  margin: 2px 8px;
  border-radius: 6px;
  height: 44px;
}
.side-menu .el-menu-item.is-active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 500;
}
.body {
  min-width: 0;
}
.header {
  height: 60px;
  background: #ffffff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-icon {
  color: #909399;
}
.username {
  color: #606266;
  font-size: 14px;
}
.main {
  background: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}
</style>

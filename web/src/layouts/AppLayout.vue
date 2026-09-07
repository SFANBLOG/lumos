<template>
  <el-container class="app-layout">
    <el-aside width="200px" class="aside">
      <div class="logo">
        <div class="logo-name">Lumos</div>
        <div class="logo-sub">契光鉴微</div>
      </div>
      <el-menu
        :default-active="activeMenu"
        :default-openeds="defaultOpeneds"
        class="side-menu"
      >
        <el-menu-item index="/dashboard" @click="nav('/dashboard')">
          <el-icon><Odometer /></el-icon>
          <span>主看板</span>
        </el-menu-item>
        <el-menu-item index="/analysis" @click="nav('/analysis')">
          <el-icon><Document /></el-icon>
          <span>智能分析</span>
        </el-menu-item>

        <!-- 智能咨询: 可展开, 下含「新对话」与历史会话子项 -->
        <el-sub-menu index="consult">
          <template #title>
            <el-icon><ChatLineRound /></el-icon>
            <span>智能咨询</span>
          </template>
          <el-menu-item index="/consult" @click="nav('/consult')">
            <el-icon><Plus /></el-icon>
            <span>新对话</span>
          </el-menu-item>
          <el-menu-item
            v-for="s in consult.sessions"
            :key="s.id"
            :index="`/consult?s=${s.id}`"
            @click="navSession(s.id)"
          >
            <el-icon><ChatLineSquare /></el-icon>
            <span class="session-title" :title="s.title">{{ s.title || '未命名会话' }}</span>
          </el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/reports" @click="nav('/reports')">
          <el-icon><Clock /></el-icon>
          <span>历史报告</span>
        </el-menu-item>
        <el-menu-item index="/mcp" @click="nav('/mcp')">
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
import {
  ChatLineRound,
  ChatLineSquare,
  Clock,
  Document,
  MagicStick,
  Odometer,
  Plus,
  User,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useConsultStore } from '@/stores/consult'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const consult = useConsultStore()

// 顶级菜单与子项的激活态完全由本计算属性驱动, 不依赖 el-menu 的 router 模式,
// 避免 query 参数(/consult?s=xxx)无法被自动匹配为活动项的问题.
const activeMenu = computed(() => {
  if (route.path === '/consult' && route.query.s) {
    return `/consult?s=${route.query.s}`
  }
  return route.path
})

// 进入 /consult 时自动展开「智能咨询」子菜单
const defaultOpeneds = computed(() =>
  route.path.startsWith('/consult') ? ['consult'] : []
)

const nav = (path: string) => {
  if (route.path !== path) router.push(path)
}

const navSession = (id: string) => {
  router.push({ path: '/consult', query: { s: id } })
}

const handleLogout = () => {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  // 刷新页面后 token 仍在而用户信息为空时补拉一次
  if (auth.isLoggedIn() && !auth.user) {
    auth.fetchUser()
  }
  // 登录态下预取会话列表, 让侧栏「历史会话」子项即时可见
  if (auth.isLoggedIn()) {
    consult.fetchSessions()
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
  overflow-y: auto;
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
/* 子菜单内的项: 去掉外侧 8px 边距, 依靠 EP 自带的缩进对齐 */
.side-menu .el-sub-menu .el-menu-item {
  margin-left: 4px;
  margin-right: 8px;
}
/* 智能咨询标题在子项激活时高亮 (EP 会自动加 is-active) */
.side-menu .el-sub-menu.is-active > .el-sub-menu__title {
  color: #409eff;
}
/* 历史会话子项: 标题过长省略, 鼠标悬停显示完整标题 */
.session-title {
  display: inline-block;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
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

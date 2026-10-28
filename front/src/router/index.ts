import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { public: true },
    },
    {
      path: '/forgot-password',
      name: 'ForgotPassword',
      component: () => import('@/views/ForgotPasswordView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'App',
      component: () => import('@/layouts/AppLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '工作台' },
        },
        {
          path: 'contracts',
          name: 'Contracts',
          component: () => import('@/views/ContractsView.vue'),
          meta: { title: '合同管理' },
        },
        {
          path: 'knowledge',
          name: 'Knowledge',
          component: () => import('@/views/KnowledgeView.vue'),
          meta: { title: '知识库' },
        },
        {
          path: 'rules',
          name: 'Rules',
          component: () => import('@/views/RulesView.vue'),
          meta: { title: '规则中心' },
        },
        {
          path: 'reports',
          name: 'Reports',
          component: () => import('@/views/ReportsView.vue'),
          meta: { title: '审查报告' },
        },
        {
          path: 'review',
          name: 'Review',
          component: () => import('@/views/ReviewView.vue'),
          meta: { title: 'AI 初审' },
        },
        {
          path: 'analysis',
          name: 'Analysis',
          component: () => import('@/views/AnalysisView.vue'),
          meta: { title: 'AI 合同审查' },
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/SystemView.vue'),
          meta: { title: '系统设置' },
        },
        {
          path: 'consult',
          name: 'Consult',
          component: () => import('@/views/ConsultView.vue'),
          meta: { title: '智能咨询' },
        },
        {
          path: 'mcp',
          name: 'MCP',
          component: () => import('@/views/MCPView.vue'),
          meta: { title: 'MCP 工具' },
        },
        {
          path: 'approvals',
          name: 'Approvals',
          component: () => import('@/views/ApprovalsView.vue'),
          meta: { title: '审批队列' },
        },
        {
          path: 'playbooks',
          name: 'Playbooks',
          component: () => import('@/views/PlaybooksView.vue'),
          meta: { title: '审查标准' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn()) {
    next('/login')
  } else {
    next()
  }
})

export default router

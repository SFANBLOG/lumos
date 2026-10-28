import { defineStore } from 'pinia'
import { ref } from 'vue'
import { consultApi, type ConsultSession } from '@/api/consult'

/**
 * 智能咨询会话列表的全局缓存，供左侧导航与咨询页共享。
 *
 * - 侧栏 el-sub-menu 据此渲染「历史会话」子项
 * - 咨询页发送完一轮问答后调用 fetchSessions() 刷新，让侧栏立刻出现新会话
 */
export const useConsultStore = defineStore('consult', () => {
  const sessions = ref<ConsultSession[]>([])

  const fetchSessions = async () => {
    try {
      const { data } = await consultApi.sessions(1, 20)
      sessions.value = data.items
    } catch {
      // 静默失败: 侧栏/咨询页可各自按需提示
    }
  }

  return { sessions, fetchSessions }
})

import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截：自动附加 JWT
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 跳转登录
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// 提取用户可读的接口错误信息：
// - 业务错误（FastAPI 400/401/422）：优先取 detail（422 校验错误取每条 msg）
// - 有响应但非标准错误体（如代理打到非后端服务返回 HTML）：带状态码提示
// - 无响应（后端未启动 / 网络不可达 / 代理不通）：明确提示检查后端服务
export function apiErrorMessage(e: any, fallback: string): string {
  const data = e?.response?.data
  if (data?.detail) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d: any) => d.msg ?? '').filter(Boolean).join('；')
      : typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    return detail || fallback
  }
  if (e?.response) {
    return `请求失败（HTTP ${e.response.status}）`
  }
  if (e?.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试'
  }
  return '无法连接服务器，请确认后端服务已启动（默认 http://localhost:8001）'
}

export default apiClient
